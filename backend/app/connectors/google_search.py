"""Google Programmable Search connector — general public web results."""

import httpx

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject


class GoogleSearchConnector(BaseConnector):
    name = "google_search"
    display_name = "Google Search"
    description = "General public web results via the Google Programmable Search API."

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def is_configured(self) -> bool:
        return bool(self.settings.google_api_key and self.settings.google_cse_id)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.google_mock(subject)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        params = {
            "key": self.settings.google_api_key,
            "cx": self.settings.google_cse_id,
            "q": f'"{subject.full_name}"',
            "num": 10,
        }
        resp = await client.get(self.API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        findings = []
        for item in data.get("items", []):
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.WEB,
                    title=item.get("title", "Untitled result"),
                    description=item.get("snippet"),
                    url=item.get("link"),
                    subject_name=subject.full_name,
                    raw=item,
                )
            )
        return findings
