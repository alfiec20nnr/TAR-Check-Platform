"""Connector framework tests: mock mode, retries, skip behaviour, normalisation."""

import httpx
import pytest
import respx

from app.config import Settings
from app.connectors.base import Category, ConnectorStatus, SearchSubject, screening_score
from app.connectors.companies_house import CompaniesHouseConnector
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
async def test_brave_connector_normalises_and_categorises():
    from app.connectors.brave_search import BraveSearchConnector

    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Test Person faces fraud investigation",
                            "description": "Regulators are investigating Test Person.",
                            "url": "https://news.example.com/fraud",
                            "page_age": "2024-05-01T00:00:00",
                        },
                        {
                            "title": "Test Person — company profile",
                            "description": "About Test Person.",
                            "url": "https://example.com/profile",
                        },
                        {
                            "title": "Unrelated page",
                            "description": "No mention of the subject.",
                            "url": "https://example.com/noise",
                        },
                    ]
                }
            },
        )
    )
    connector = BraveSearchConnector(real_settings(brave_api_key="k"))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    by_url = {f.url: f for f in result.findings}
    assert set(by_url) == {"https://news.example.com/fraud", "https://example.com/profile"}
    assert by_url["https://news.example.com/fraud"].category == Category.ADVERSE_MEDIA
    assert by_url["https://news.example.com/fraud"].date == "2024-05-01"
    assert by_url["https://example.com/profile"].category == Category.WEB
    assert all(f.subject_name is None for f in result.findings)


@respx.mock
async def test_google_adverse_results_categorised_as_adverse_media():
    """Results containing adverse terms become adverse_media (so the risk
    scorer's keyword escalation applies); neutral pages stay low-weight web."""
    respx.get("https://www.googleapis.com/customsearch/v1").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "Test Person faces fraud investigation",
                        "snippet": "Regulators are investigating Test Person.",
                        "link": "https://news.example.com/fraud",
                    },
                    {
                        "title": "Test Person speaks at conference",
                        "snippet": "Test Person appeared as a panellist.",
                        "link": "https://example.com/conf",
                    },
                ]
            },
        )
    )
    connector = GoogleSearchConnector(real_settings(google_api_key="k", google_cse_id="c"))
    result = await connector.run(SUBJECT)
    by_url = {f.url: f.category for f in result.findings}
    assert by_url["https://news.example.com/fraud"] == Category.ADVERSE_MEDIA
    assert by_url["https://example.com/conf"] == Category.WEB
    # The same items arrive from both queries but are deduplicated by link.
    assert len(result.findings) == 2


@respx.mock
async def test_google_connector_drops_results_that_never_mention_the_name():
    respx.get("https://www.googleapis.com/customsearch/v1").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "Test Person — profile",
                        "snippet": "About Test Person",
                        "link": "https://example.com/p",
                    },
                    {
                        "title": "Completely unrelated page",
                        "snippet": "Nothing to do with the subject at all.",
                        "link": "https://example.com/noise",
                    },
                ]
            },
        )
    )
    connector = GoogleSearchConnector(real_settings(google_api_key="k", google_cse_id="c"))
    result = await connector.run(SUBJECT)
    assert len(result.findings) == 1
    # Web results are mentions, never source-attributed identities.
    assert result.findings[0].subject_name is None


async def test_mock_profiles_are_mostly_clean():
    """~70% of names must land in the clean profile — adverse findings are the
    exception in fixture data, mirroring reality."""
    from app.connectors.mock_data import CLEAN, profile_for

    names = [f"Person Number {i}" for i in range(200)]
    clean = sum(
        profile_for(SearchSubject(full_name=n)) == CLEAN for n in names
    )
    assert clean / len(names) > 0.6


@respx.mock
async def test_retry_on_transient_error_then_success():
    route = respx.get("https://www.googleapis.com/customsearch/v1")
    route.side_effect = [
        httpx.Response(503),
        # After the retry, the connector issues both its queries.
        httpx.Response(200, json={"items": []}),
        httpx.Response(200, json={"items": []}),
    ]
    connector = GoogleSearchConnector(real_settings(google_api_key="k", google_cse_id="c"))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert route.call_count == 3


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


_SANCTIONS_XML = """<?xml version="1.0" encoding="utf-8"?>
<Designations>
  <Designation>
    <DateDesignated>29/06/2012</DateDesignated>
    <UniqueID>TST0001</UniqueID>
    <Names>
      <Name><Name1>Test</Name1><Name6>Person</Name6><NameType>Primary Name</NameType></Name>
      <Name><Name6>Tester Person</Name6><NameType>Alias</NameType></Name>
    </Names>
    <RegimeName>The Test (Sanctions) Regulations</RegimeName>
    <IndividualEntityShip>Individual</IndividualEntityShip>
    <DOBs><DOB>02/03/1975</DOB></DOBs>
    <Addresses><Address><AddressCountry>United Kingdom</AddressCountry></Address></Addresses>
  </Designation>
  <Designation>
    <Names><Name><Name6>Unrelated Company Ltd</Name6></Name></Names>
    <IndividualEntityShip>Entity</IndividualEntityShip>
  </Designation>
  <Designation>
    <Names><Name><Name6>Somebody Else Entirely</Name6></Name></Names>
    <IndividualEntityShip>Individual</IndividualEntityShip>
  </Designation>
</Designations>
"""


@respx.mock
async def test_sanctions_connector_parses_fcdo_xml():
    """The live FCDO feed is XML: individuals only, aliases matched, dates and
    DOBs converted from DD/MM/YYYY, addresses surfaced as location."""
    UkSanctionsConnector._cache = None
    url = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml"
    respx.get(url).mock(
        return_value=httpx.Response(200, content=_SANCTIONS_XML, headers={
            "Content-Type": "text/xml",
        })
    )
    connector = UkSanctionsConnector(real_settings(uk_sanctions_list_url=url))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.category == Category.SANCTIONS
    assert finding.subject_name == "Test Person"
    assert finding.date_of_birth == "1975-03-02"
    assert finding.location == "United Kingdom"
    assert finding.date == "2012-06-29"
    assert "The Test (Sanctions) Regulations" in (finding.description or "")
    UkSanctionsConnector._cache = None


@respx.mock
async def test_sanctions_connector_accepts_licensed_provider_json():
    UkSanctionsConnector._cache = None  # reset the class-level list cache
    json_url = "https://provider.example.com/sanctions.json"
    respx.get(json_url).mock(
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
    connector = UkSanctionsConnector(real_settings(uk_sanctions_list_url=json_url))
    result = await connector.run(SUBJECT)
    assert result.status == ConnectorStatus.SUCCESS
    assert len(result.findings) == 1
    assert result.findings[0].category == Category.SANCTIONS
    UkSanctionsConnector._cache = None


def test_screening_score_rules():
    # Extra name parts (patronymics/middle names) must not hide a true hit.
    assert screening_score("Roman Abramovich", "Roman Arkadyevich Abramovich") >= 90
    # Registry "SURNAME, Forename" formatting is handled.
    assert screening_score("Philip Green", "GREEN, Philip") >= 90
    # A single-token alias (sanctions codename "Green") must never subset-match.
    assert screening_score("Philip Green", "Green") < 90
    # A different person sharing a surname is not a match.
    assert screening_score("Philip Green", "Terry Green") < 85


@respx.mock
async def test_companies_house_screens_out_other_names():
    """CH search is fuzzy — records for differently-named people are dropped."""
    respx.get("https://api.company-information.service.gov.uk/search/officers").mock(
        return_value=httpx.Response(
            200,
            json={"items": [
                {"title": "Philip GREEN", "address_snippet": "London",
                 "links": {"self": "/officers/1"}},
                {"title": "Terry GREEN", "address_snippet": "Leeds",
                 "links": {"self": "/officers/2"}},
            ]},
        )
    )
    respx.get(
        "https://api.company-information.service.gov.uk/search/disqualified-officers"
    ).mock(return_value=httpx.Response(200, json={"items": []}))
    connector = CompaniesHouseConnector(real_settings(companies_house_api_key="k"))
    result = await connector.run(SearchSubject(full_name="Philip Green"))
    assert result.status == ConnectorStatus.SUCCESS
    assert [f.subject_name for f in result.findings] == ["Philip GREEN"]


@pytest.mark.parametrize("cls", CONNECTOR_CLASSES)
async def test_every_connector_declares_metadata(cls):
    assert cls.name != "base"
    assert cls.display_name
    assert cls.description
