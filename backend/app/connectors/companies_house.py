"""UK Companies House connector.

Used only to surface a person's directorships (officer appointments) and any
director disqualifications — never for company-centric search.

Searches every nickname/variant form of the subject's name in addition to the
name as given, and pages through results instead of stopping at the first
page — a common surname can bury the real match well past the first 20-100
results.
"""

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import (
    BaseConnector,
    Category,
    Finding,
    SearchSubject,
    screening_score,
)

BASE_URL = "https://api.company-information.service.gov.uk"

# Companies House search is deliberately fuzzy (a query for "Philip Green"
# returns every Green on the register). Only records whose name actually
# matches the subject are surfaced; the rest are different people, not
# evidence.
_NAME_SCREEN_THRESHOLD = 85

# The API caps items_per_page at 100; page through the full result set rather
# than stopping at the first page.
_ITEMS_PER_PAGE = 100
_MAX_PAGES = 5


class CompaniesHouseConnector(BaseConnector):
    name = "companies_house"
    display_name = "UK Companies House"
    description = "Officer appointments (directorships) and director disqualifications."

    def is_configured(self) -> bool:
        return bool(self.settings.companies_house_api_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.companies_house_mock(subject)

    def _auth(self) -> tuple[str, str]:
        # Companies House uses HTTP basic auth with the API key as username.
        return (self.settings.companies_house_api_key, "")

    async def _paged_items(
        self, client: httpx.AsyncClient, path: str, query: str
    ) -> list[dict]:
        items: list[dict] = []
        for page in range(_MAX_PAGES):
            resp = await client.get(
                f"{BASE_URL}{path}",
                params={
                    "q": query,
                    "items_per_page": _ITEMS_PER_PAGE,
                    "start_index": page * _ITEMS_PER_PAGE,
                },
                auth=self._auth(),
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                if page == 0:
                    raise
                break
            data = resp.json()
            page_items = data.get("items", [])
            if not page_items:
                break
            items.extend(page_items)
            total = data.get("total_results", 0)
            if page * _ITEMS_PER_PAGE + len(page_items) >= total:
                break
        return items

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(await self._search_officers(subject, client))
        findings.extend(await self._search_disqualified(subject, client))
        return findings

    async def _search_officers(
        self, subject: SearchSubject, client: httpx.AsyncClient
    ) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        items: list[dict] = []
        for name in names:
            items += await self._paged_items(client, "/search/officers", name)
        findings = []
        seen_urls: set[str] = set()
        for item in items:
            title = item.get("title") or ""
            if not any(
                screening_score(n, title) >= _NAME_SCREEN_THRESHOLD for n in names
            ):
                continue
            url = (
                "https://find-and-update.company-information.service.gov.uk"
                + (item.get("links", {}).get("self") or "")
            )
            if url in seen_urls:
                continue
            seen_urls.add(url)
            dob = item.get("date_of_birth") or {}
            dob_str = None
            if dob.get("year"):
                dob_str = f"{dob['year']}-{dob.get('month', 1):02d}"
            address = item.get("address_snippet")
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.DIRECTORSHIP,
                    title=f"Officer record — {item.get('title', subject.full_name)}",
                    description=item.get("description"),
                    url=url,
                    subject_name=item.get("title"),
                    location=address,
                    date_of_birth=dob_str,
                    raw={"appointment_count": item.get("appointment_count")},
                )
            )
        return findings

    async def _search_disqualified(
        self, subject: SearchSubject, client: httpx.AsyncClient
    ) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        items: list[dict] = []
        for name in names:
            items += await self._paged_items(client, "/search/disqualified-officers", name)
        findings = []
        seen_urls: set[str] = set()
        for item in items:
            title = item.get("title") or ""
            if not any(
                screening_score(n, title) >= _NAME_SCREEN_THRESHOLD for n in names
            ):
                continue
            url = (
                "https://find-and-update.company-information.service.gov.uk"
                + (item.get("links", {}).get("self") or "")
            )
            if url in seen_urls:
                continue
            seen_urls.add(url)
            dob_str = item.get("date_of_birth")
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.DISQUALIFICATION,
                    title=f"Director disqualification — {item.get('title', subject.full_name)}",
                    description=item.get("description"),
                    url=url,
                    subject_name=item.get("title"),
                    location=item.get("address_snippet"),
                    date_of_birth=dob_str,
                    raw={},
                )
            )
        return findings
