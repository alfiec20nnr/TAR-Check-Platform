"""Google Programmable Search connector — general public web results."""

import httpx
from rapidfuzz import fuzz

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

# A result must actually mention the subject's name in its title/snippet;
# anything below this partial-match score is provider noise, not evidence.
_MENTION_THRESHOLD = 70


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
        target = subject.full_name.lower()
        for item in data.get("items", []):
            title = item.get("title", "Untitled result")
            snippet = item.get("snippet") or ""
            # Web pages only *mention* a name — they do not attribute a record
            # to a person. subject_name is deliberately left unset so identity
            # matching treats this as an unstructured mention (low confidence
            # ceiling) instead of a source-verified name match.
            if fuzz.token_set_ratio(target, f"{title} {snippet}".lower()) < _MENTION_THRESHOLD:
                continue
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.WEB,
                    title=title,
                    description=item.get("snippet"),
                    url=item.get("link"),
                    raw=item,
                )
            )
        return findings
