"""UK Companies House connector.

Used only to surface a person's directorships (officer appointments) and any
director disqualifications — never for company-centric search.
"""

import httpx

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

BASE_URL = "https://api.company-information.service.gov.uk"


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

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(await self._search_officers(subject, client))
        findings.extend(await self._search_disqualified(subject, client))
        return findings

    async def _search_officers(
        self, subject: SearchSubject, client: httpx.AsyncClient
    ) -> list[Finding]:
        resp = await client.get(
            f"{BASE_URL}/search/officers",
            params={"q": subject.full_name, "items_per_page": 20},
            auth=self._auth(),
        )
        resp.raise_for_status()
        findings = []
        for item in resp.json().get("items", []):
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
                    url=(
                        "https://find-and-update.company-information.service.gov.uk"
                        + (item.get("links", {}).get("self") or "")
                    ),
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
        resp = await client.get(
            f"{BASE_URL}/search/disqualified-officers",
            params={"q": subject.full_name, "items_per_page": 10},
            auth=self._auth(),
        )
        resp.raise_for_status()
        findings = []
        for item in resp.json().get("items", []):
            dob_str = item.get("date_of_birth")
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.DISQUALIFICATION,
                    title=f"Director disqualification — {item.get('title', subject.full_name)}",
                    description=item.get("description"),
                    url=(
                        "https://find-and-update.company-information.service.gov.uk"
                        + (item.get("links", {}).get("self") or "")
                    ),
                    subject_name=item.get("title"),
                    location=item.get("address_snippet"),
                    date_of_birth=dob_str,
                    raw={},
                )
            )
        return findings
