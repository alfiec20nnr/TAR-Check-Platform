"""Brave Search connector — general public web results.

The recommended web-search source: Brave operates an independent full-web
index with an official API open to new customers (unlike Google's Custom
Search JSON API, closed to new sign-ups since Jan 2026). Free tier available
at https://api-dashboard.search.brave.com/register — set BRAVE_API_KEY.

For each name form searched (the subject's name as given, plus any
nickname/variant forms), two queries are run — plain name + adverse-media
screening query — each paginated across several pages. Names are sent
unquoted: a quoted phrase forces an exact, contiguous match and misses sources
that write the name with a middle initial, reordered, or otherwise slightly
differently — the fuzzy `mentions_subject` check afterwards is what keeps
results relevant, not the query syntax.

The free tier allows one request per second, and that budget is shared with
every other Brave-backed connector (e.g. social media) and every page of
every query, so all Brave requests go through one process-wide throttle
(:func:`brave_query`). Searching deeper costs time, not correctness — that
trade-off is intentional.
"""

import asyncio

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Finding, SearchSubject, _RateLimiter

API_URL = "https://api.search.brave.com/res/v1/web/search"

# Free-tier rate limit is 1 request/second — shared across connectors.
_QUERY_SPACING_SECONDS = 1.1

# Brave returns at most 20 results per request; paginate via `offset`.
_RESULTS_PER_PAGE = 20
_MAX_PAGES = 3

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


async def _brave_request(
    client: httpx.AsyncClient, api_key: str, query: str, count: int, offset: int
) -> list[dict]:
    """One Brave web-search request, throttled across all Brave connectors."""
    await _throttle()
    resp = await client.get(
        API_URL,
        params={"q": query, "count": count, "offset": offset},
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    resp.raise_for_status()
    return ((resp.json().get("web") or {}).get("results")) or []


async def brave_query(
    client: httpx.AsyncClient, api_key: str, query: str, count: int = _RESULTS_PER_PAGE
) -> list[dict]:
    """All pages of one Brave web-search query (up to `_MAX_PAGES`)."""
    results: list[dict] = []
    for page in range(_MAX_PAGES):
        try:
            page_results = await _brave_request(client, api_key, query, count, page * count)
        except httpx.HTTPStatusError:
            # A later page failing (e.g. offset beyond what the plan allows)
            # just means "no more pages" — keep what was already fetched.
            if page == 0:
                raise
            break
        if not page_results:
            break
        results.extend(page_results)
        if len(page_results) < count:
            break
    return results


class BraveSearchConnector(BaseConnector):
    name = "brave_search"
    display_name = "Brave Web Search"
    description = "General public web results and adverse-media screening via the Brave Search API."

    def is_configured(self) -> bool:
        return bool(self.settings.brave_api_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.web_mock(subject, source=self.name)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        api_key = self.settings.brave_api_key
        results: list[dict] = []
        for name in names:
            results += await brave_query(client, api_key, name)
            results += await brave_query(
                client, api_key, f"{name} ({web_common.ADVERSE_QUERY_TERMS})"
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
            # Checked against every name form queried (nicknames included).
            if not any(web_common.mentions_subject(n, text) for n in names):
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
