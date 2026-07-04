"""Connector framework tests: mock mode, retries, skip behaviour, normalisation."""

import httpx
import pytest
import respx

from app.config import Settings
from app.connectors.base import Category, ConnectorStatus, SearchSubject
from app.connectors.google_search import GoogleSearchConnector
from app.connectors.registry import CONNECTOR_CLASSES, get_registry
from app.connectors.sanctions import UkSanctionsConnector

SUBJECT = SearchSubject(full_name="Test Person", country="United Kingdom")


def real_settings(**overrides) -> Settings:
    base = dict(
        mock_connectors=False,
        connector_max_retries=1,
        connector_rate_limit_per_second=10_000,
        connector_timeout_seconds=5,
    )
    base.update(overrides)
    return Settings(**base)


async def test_mock_mode_all_connectors_succeed():
    registry = get_registry(Settings(mock_connectors=True))
    results = await registry.run_all(SUBJECT)
    assert len(results) == len(CONNECTOR_CLASSES)
    assert all(r.status == ConnectorStatus.SUCCESS for r in results)
    # Every connector reports its execution time.
    assert all(r.duration_ms >= 0 for r in results)


async def test_mock_findings_are_deterministic():
    registry = get_registry(Settings(mock_connectors=True))
    first = await registry.run_all(SUBJECT)
    second = await registry.run_all(SUBJECT)
    assert [len(r.findings) for r in first] == [len(r.findings) for r in second]


async def test_unconfigured_connector_is_skipped():
    connector = GoogleSearchConnector(real_settings(google_api_key="", google_cse_id=""))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SKIPPED
    assert result.findings == []


@respx.mock
async def test_google_connector_normalises_results():
    respx.get("https://www.googleapis.com/customsearch/v1").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "Test Person — profile",
                        "snippet": "About Test Person",
                        "link": "https://example.com/p",
                    }
                ]
            },
        )
    )
    connector = GoogleSearchConnector(real_settings(google_api_key="k", google_cse_id="c"))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.category == Category.WEB
    assert finding.url == "https://example.com/p"
    assert finding.source == "google_search"


@respx.mock
async def test_retry_on_transient_error_then_success():
    route = respx.get("https://www.googleapis.com/customsearch/v1")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json={"items": []}),
    ]
    connector = GoogleSearchConnector(real_settings(google_api_key="k", google_cse_id="c"))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert route.call_count == 2


@respx.mock
async def test_non_retryable_error_fails_immediately():
    route = respx.get("https://www.googleapis.com/customsearch/v1").mock(
        return_value=httpx.Response(403)
    )
    connector = GoogleSearchConnector(real_settings(google_api_key="k", google_cse_id="c"))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.FAILED
    assert route.call_count == 1
    assert result.error


@respx.mock
async def test_sanctions_connector_fuzzy_matches_individuals():
    UkSanctionsConnector._cache = None  # reset the class-level list cache
    respx.get("https://assets.publishing.service.gov.uk/media/uk-sanctions-list.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "designations": [
                    {
                        "Name": "Test Person",
                        "IndividualEntityShip": "Individual",
                        "RegimeName": "Global Anti-Corruption",
                    },
                    {
                        "Name": "Unrelated Company Ltd",
                        "IndividualEntityShip": "Entity",
                    },
                    {
                        "Name": "Somebody Else Entirely",
                        "IndividualEntityShip": "Individual",
                    },
                ]
            },
        )
    )
    connector = UkSanctionsConnector(real_settings())
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert len(result.findings) == 1
    assert result.findings[0].category == Category.SANCTIONS
    UkSanctionsConnector._cache = None


@pytest.mark.parametrize("cls", CONNECTOR_CLASSES)
async def test_every_connector_declares_metadata(cls):
    assert cls.name != "base"
    assert cls.display_name
    assert cls.description
