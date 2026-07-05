"""Brave Search connector — general public web results.

The recommended web-search source: Brave operates an independent full-web
index with an official API open to new customers (unlike Google's Custom
Search JSON API, closed to new sign-ups since Jan 2026). Free tier available
at https://api-dashboard.search.brave.com/register — set BRAVE_API_KEY.

Two queries per search (plain name + adverse-media screening query), with the
shared web mention filter and adverse categorisation. The free tier allows
one request per second, so the two queries are spaced apart.
"""

import asyncio

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Finding, SearchSubject

# Free-tier rate limit is 1 request/second.
_QUERY_SPACING_SECONDS = 1.1


class BraveSearchConnector(BaseConnector):
    name = "brave_search"
    display_name = "Brave Web Search"
    description = "General public web results and adverse-media screening via the Brave Search API."

    API_URL = "https://api.search.brave.com/res/v1/web/search"

    def is_configured(self) -> bool:
        return bool(self.settings.brave_api_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.web_mock(subject, source=self.name)

    async def _query(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        resp = await client.get(
            self.API_URL,
            params={"q": query, "count": 20},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.settings.brave_api_key,
            },
        )
        resp.raise_for_status()
        return ((resp.json().get("web") or {}).get("results")) or []

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        name = subject.full_name
        results = await self._query(client, f'"{name}"')
        await asyncio.sleep(_QUERY_SPACING_SECONDS)
        results += await self._query(client, f'"{name}" ({web_common.ADVERSE_QUERY_TERMS})')

        findings = []
        seen_links: set[str] = set()
        for item in results:
            link = item.get("url") or ""
            if link and link in seen_links:
                continue
            seen_links.add(link)
            title = item.get("title", "Untitled result")
            description = item.get("description") or ""
            text = f"{title} {description}"
            # Web pages only *mention* a name — subject_name is deliberately
            # left unset so identity matching treats this as an unstructured
            # mention (low confidence ceiling), never a verified name match.
            if not web_common.mentions_subject(name, text):
                continue
            page_age = (item.get("page_age") or "")[:10] or None
            findings.append(
                Finding(
                    source=self.name,
                    category=web_common.categorise(text),
                    title=title,
                    description=description or None,
                    url=link or None,
                    date=page_age,
                    raw={"profile": (item.get("profile") or {}).get("name")},
                )
            )
        return findings
