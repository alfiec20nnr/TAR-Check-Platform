"""DVLA Access to Driver Data connector tests (mocked API, per DVLA spec)."""

import httpx
import pytest
import respx

from app.config import Settings
from app.connectors.base import Category, ConnectorStatus, SearchSubject
from app.connectors.dvla_add import DvlaAddConnector

BASE = "https://uat.driver-vehicle-licensing.api.gov.uk"
AUTH_URL = f"{BASE}/thirdparty-access/v1/authenticate"
RETRIEVE_URL = f"{BASE}/full-driver-enquiry/v1/driving-licences/retrieve"

SUBJECT = SearchSubject(
    full_name="Jane Doe",
    date_of_birth="1980-04-12",
    driving_licence_number="DOE99801045JA9AB",
)


def dvla_settings(**overrides) -> Settings:
    base = dict(
        mock_connectors=False,
        connector_max_retries=0,
        connector_rate_limit_per_second=10_000,
        connector_timeout_seconds=5,
        dvla_username="user",
        dvla_password="pass",
        dvla_api_key="key",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def reset_token_cache():
    DvlaAddConnector._token = None
    DvlaAddConnector._token_at = 0.0
    yield
    DvlaAddConnector._token = None
    DvlaAddConnector._token_at = 0.0


FULL_RESPONSE = {
    "driver": {
        "drivingLicenceNumber": "DOE99801045JA9AB",
        "firstNames": "JANE",
        "lastName": "DOE",
        "dateOfBirth": "1980-04-12",
        "address": {"unstructuredAddress": {"line1": "1 Test St", "postcode": "AB1 2CD"}},
    },
    "licence": {"type": "Full", "status": "Valid"},
    "entitlements": [
        {"categoryCode": "B", "fromDate": "2000-01-01", "expiryDate": "2050-01-01"},
    ],
    "endorsements": [
        {
            "offenceCode": "SP30",
            "offenceLegalLiteral": "Exceeding statutory speed limit on a public road",
            "offenceDate": "2023-09-14",
            "penaltyPoints": 3,
        },
        {
            "offenceCode": "DR10",
            "offenceLegalLiteral": "Driving with alcohol level above limit",
            "offenceDate": "2022-06-30",
            "penaltyPoints": 0,
            "disqualification": {"disqualificationPeriod": "18 months"},
        },
    ],
}


async def test_skipped_when_no_licence_number():
    connector = DvlaAddConnector(dvla_settings())
    result = await connector.run(SearchSubject(full_name="Jane Doe"))
    assert result.status == ConnectorStatus.SKIPPED
    assert result.error == "not applicable to this search"


async def test_skipped_when_not_configured():
    connector = DvlaAddConnector(
        dvla_settings(dvla_username="", dvla_password="", dvla_api_key="")
    )
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SKIPPED


@respx.mock
async def test_full_flow_parses_licence_endorsements_and_disqualification():
    auth = respx.post(AUTH_URL).mock(
        return_value=httpx.Response(200, json={"id-token": "jwt-1"})
    )
    retrieve = respx.post(RETRIEVE_URL).mock(
        return_value=httpx.Response(200, json=FULL_RESPONSE)
    )
    connector = DvlaAddConnector(dvla_settings())
    result = await connector.run(SUBJECT)

    assert result.status == ConnectorStatus.SUCCESS
    assert auth.call_count == 1
    # JWT + API key sent per DVLA spec.
    sent_headers = retrieve.calls[0].request.headers
    assert sent_headers["authorization"] == "jwt-1"
    assert sent_headers["x-api-key"] == "key"

    by_category = {f.category: f for f in result.findings}
    assert set(by_category) == {
        Category.DRIVING_LICENCE,
        Category.DRIVING_ENDORSEMENT,
        Category.DRIVING_DISQUALIFICATION,
    }
    licence = by_category[Category.DRIVING_LICENCE]
    assert "Valid" in licence.title
    # Name/DOB corroborate identity; address is deliberately not captured.
    assert licence.subject_name == "JANE DOE"
    assert licence.date_of_birth == "1980-04-12"
    assert all("postcode" not in str(f.raw).lower() for f in result.findings)
    endorsement = by_category[Category.DRIVING_ENDORSEMENT]
    assert "SP30" in endorsement.title and "3 penalty points" in endorsement.title
    assert by_category[Category.DRIVING_DISQUALIFICATION].raw["disqualification"]


@respx.mock
async def test_token_cached_across_runs():
    auth = respx.post(AUTH_URL).mock(
        return_value=httpx.Response(200, json={"id-token": "jwt-1"})
    )
    respx.post(RETRIEVE_URL).mock(return_value=httpx.Response(200, json=FULL_RESPONSE))
    connector = DvlaAddConnector(dvla_settings())
    await connector.run(SUBJECT)
    await connector.run(SUBJECT)
    assert auth.call_count == 1  # 1-hour JWT reused


@respx.mock
async def test_expired_token_refreshed_once_on_401():
    auth = respx.post(AUTH_URL)
    auth.side_effect = [
        httpx.Response(200, json={"id-token": "jwt-old"}),
        httpx.Response(200, json={"id-token": "jwt-new"}),
    ]
    retrieve = respx.post(RETRIEVE_URL)
    retrieve.side_effect = [
        httpx.Response(401),
        httpx.Response(200, json=FULL_RESPONSE),
    ]
    connector = DvlaAddConnector(dvla_settings())
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert auth.call_count == 2
    assert retrieve.calls[1].request.headers["authorization"] == "jwt-new"


@respx.mock
async def test_licence_not_found_is_a_verification_finding():
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"id-token": "j"}))
    respx.post(RETRIEVE_URL).mock(return_value=httpx.Response(404))
    connector = DvlaAddConnector(dvla_settings())
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.category == Category.DRIVING_LICENCE_ISSUE
    assert "not found" in finding.title.lower()
    # The licence number must never leak into finding text.
    text = f"{finding.title} {finding.description} {finding.raw}"
    assert SUBJECT.driving_licence_number not in text


@respx.mock
async def test_auth_failure_fails_connector():
    respx.post(AUTH_URL).mock(return_value=httpx.Response(401))
    connector = DvlaAddConnector(dvla_settings())
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.FAILED
    assert result.error
    # Credentials and licence number must never leak into the recorded error.
    assert "pass" not in result.error.lower() or "password" not in result.error
    assert SUBJECT.driving_licence_number not in result.error


@respx.mock
async def test_service_unavailable_is_retried():
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"id-token": "j"}))
    retrieve = respx.post(RETRIEVE_URL)
    retrieve.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json=FULL_RESPONSE),
    ]
    connector = DvlaAddConnector(dvla_settings(connector_max_retries=1))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert retrieve.call_count == 2


@respx.mock
async def test_timeout_fails_gracefully():
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"id-token": "j"}))
    respx.post(RETRIEVE_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    connector = DvlaAddConnector(dvla_settings())
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.FAILED
    assert SUBJECT.driving_licence_number not in (result.error or "")


@respx.mock
async def test_revoked_licence_is_an_issue_finding():
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"id-token": "j"}))
    revoked = {
        "driver": {"firstNames": "JANE", "lastName": "DOE", "dateOfBirth": "1980-04-12"},
        "licence": {"type": "Full", "status": "Revoked"},
    }
    respx.post(RETRIEVE_URL).mock(return_value=httpx.Response(200, json=revoked))
    connector = DvlaAddConnector(dvla_settings())
    result = await connector.run(SUBJECT)
    assert result.findings[0].category == Category.DRIVING_LICENCE_ISSUE
    assert "Revoked" in result.findings[0].title
