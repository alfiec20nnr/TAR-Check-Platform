"""Google Programmable Search connector — general public web results.

⚠ Google closed the Custom Search JSON API to NEW customers on 20 Jan 2026
(existing customers are grandfathered until Jan 2027). New projects receive
403 "This project does not have the access to Custom Search JSON API". Use
the Brave Search connector instead unless you have a grandfathered key.

Two queries per search: the subject's name alone, and the name combined with
adverse-media terms (the standard screening "dork"). Results whose text
contains adverse terms are categorised as adverse media so the risk scorer's
keyword escalation applies; everything else stays in the low-weight web
category.
"""

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Finding, SearchSubject


class GoogleSearchConnector(BaseConnector):
    name = "google_search"
    display_name = "Google Search"
    description = (
        "General public web results via the Google Programmable Search API "
        "(grandfathered keys only — closed to new customers since Jan 2026)."
    )

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def is_configured(self) -> bool:
        return bool(self.settings.google_api_key and self.settings.google_cse_id)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.web_mock(subject, source=self.name)

    async def _query(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        params = {
            "key": self.settings.google_api_key,
            "cx": self.settings.google_cse_id,
            "q": query,
            "num": 10,
        }
        resp = await client.get(self.API_URL, params=params)
        resp.raise_for_status()
        return resp.json().get("items", [])

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        name = subject.full_name
        items = await self._query(client, f'"{name}"')
        items += await self._query(client, f'"{name}" ({web_common.ADVERSE_QUERY_TERMS})')

        findings = []
        seen_links: set[str] = set()
        for item in items:
            link = item.get("link") or ""
            if link and link in seen_links:
                continue
            seen_links.add(link)
            title = item.get("title", "Untitled result")
            snippet = item.get("snippet") or ""
            text = f"{title} {snippet}"
            # Web pages only *mention* a name — subject_name is deliberately
            # left unset so identity matching treats this as an unstructured
            # mention (low confidence ceiling), never a verified name match.
            if not web_common.mentions_subject(name, text):
                continue
            findings.append(
                Finding(
                    source=self.name,
                    category=web_common.categorise(text),
                    title=title,
                    description=item.get("snippet"),
                    url=item.get("link"),
                    raw=item,
                )
            )
        return findings
