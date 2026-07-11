"""Brave Search connector — general public web results.

The recommended web-search source: Brave operates an independent full-web
index with an official API open to new customers (unlike Google's Custom
Search JSON API, closed to new sign-ups since Jan 2026). Free tier available
at https://api-dashboard.search.brave.com/register — set BRAVE_API_KEY.

Two queries per search (plain name + adverse-media screening query). The free
tier allows one request per second, and that budget is shared with every other
Brave-backed connector (e.g. social media), so all Brave requests go through
one process-wide throttle (:func:`brave_query`).
"""

import asyncio

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Finding, SearchSubject, _RateLimiter

API_URL = "https://api.search.brave.com/res/v1/web/search"

# Free-tier rate limit is 1 request/second — shared across connectors.
_QUERY_SPACING_SECONDS = 1.1

# Asyncio primitives cannot be shared across event loops, so the throttle is
# held per running loop (in production there is exactly one).
_limiters: dict[asyncio.AbstractEventLoop, _RateLimiter] = {}


async def _throttle() -> None:
    loop = asyncio.get_running_loop()
    limiter = _limiters.get(loop)
    if limiter is None:
        spacing = _QUERY_SPACING_SECONDS
        limiter = _RateLimiter(1.0 / spacing if spacing > 0 else 0.0)
        _limiters[loop] = limiter
    await limiter.acquire()


async def brave_query(
    client: httpx.AsyncClient, api_key: str, query: str, count: int = 20
) -> list[dict]:
    """One Brave web-search request, throttled across all Brave connectors."""
    await _throttle()
    resp = await client.get(
        API_URL,
        params={"q": query, "count": count},
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    resp.raise_for_status()
    return ((resp.json().get("web") or {}).get("results")) or []


class BraveSearchConnector(BaseConnector):
    name = "brave_search"
    display_name = "Brave Web Search"
    description = "General public web results and adverse-media screening via the Brave Search API."

    def is_configured(self) -> bool:
        return bool(self.settings.brave_api_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.web_mock(subject, source=self.name)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        name = subject.full_name
        api_key = self.settings.brave_api_key
        results = await brave_query(client, api_key, f'"{name}"')
        results += await brave_query(
            client, api_key, f'"{name}" ({web_common.ADVERSE_QUERY_TERMS})'
        )

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
