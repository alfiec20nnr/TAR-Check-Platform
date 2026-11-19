"""Brave Search connector — general public web results (top-priority source).

The recommended web-search source: Brave operates an independent full-web
index with an official API open to new customers (unlike Google's Custom
Search JSON API, closed to new sign-ups since Jan 2026). Free tier available
at https://api-dashboard.search.brave.com/register — set BRAVE_API_KEY.

Query plan (see :func:`build_queries`), run in this order:

1. full name
2. full name + country
3. full name + location
4. full name + country + location
5. each nickname/variant form of the name (e.g. "Bill" for "William")

Steps 2-4 only run when that input is available (no country entered means the
platform default, United Kingdom). Each query is paginated across several
pages. Names are sent unquoted: a quoted phrase forces an exact, contiguous
match and misses pages that write the name with a middle initial or
reordered.

All results are collected first, then filtered: pages that do not actually
name the subject are dropped (:func:`web_common.mentions_subject`). Adverse
keyword screening is applied afterwards to every source's findings by the
pipeline (config/adverse_keywords.yaml) — the query itself is not restricted
to adverse terms, so nothing is missed because it lacked a particular word.

The free tier allows one request per second, and that budget is shared with
every other Brave-backed connector (UK newspapers, social media) and every
page of every query. All Brave requests go through one process-wide
*priority* throttle (:func:`brave_query`): when several connectors are
waiting, the highest-priority one (lowest number — this connector) is served
first.
"""

import asyncio
import heapq
import itertools
import time

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Finding, SearchSubject

API_URL = "https://api.search.brave.com/res/v1/web/search"

# Free-tier rate limit is 1 request/second — shared across connectors.
_QUERY_SPACING_SECONDS = 1.1

# Brave returns at most 20 results per request; paginate via `offset`, which
# Brave counts in PAGES (0-9), not results — offset=1 is results 21-40.
_RESULTS_PER_PAGE = 20
_MAX_PAGES = 3



class PriorityThrottle:
    """Spaces requests at least `spacing` seconds apart, serving waiters in
    priority order (lowest number first, FIFO within a priority)."""

    def __init__(self, spacing: float):
        self._spacing = spacing
        self._heap: list[tuple[int, int, asyncio.Future]] = []
        self._seq = itertools.count()
        self._last = float("-inf")
        self._dispatcher: asyncio.Task | None = None

    async def acquire(self, priority: int) -> None:
        if self._spacing <= 0:
            return
        future = asyncio.get_running_loop().create_future()
        heapq.heappush(self._heap, (priority, next(self._seq), future))
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = asyncio.create_task(self._dispatch())
        await future

    async def _dispatch(self) -> None:
        # Yield once so connectors starting together all queue up before the
        # first slot is handed out — otherwise whoever arrives first wins.
        await asyncio.sleep(0)
        while self._heap:
            wait = self._last + self._spacing - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            _, _, future = heapq.heappop(self._heap)
            if future.done():  # waiter was cancelled
                continue
            self._last = time.monotonic()
            future.set_result(None)


# Asyncio primitives cannot be shared across event loops, so the throttle is
# held per running loop (in production there is exactly one).
_limiters: dict[asyncio.AbstractEventLoop, PriorityThrottle] = {}

# Priority used by callers that don't pass one (lowest precedence).
_DEFAULT_PRIORITY = 1000


async def _throttle(priority: int = _DEFAULT_PRIORITY) -> None:
    loop = asyncio.get_running_loop()
    limiter = _limiters.get(loop)
    if limiter is None:
        limiter = PriorityThrottle(_QUERY_SPACING_SECONDS)
        _limiters[loop] = limiter
    await limiter.acquire(priority)


async def _brave_request(
    client: httpx.AsyncClient,
    api_key: str,
    query: str,
    count: int,
    offset: int,
    country: str | None,
    priority: int = _DEFAULT_PRIORITY,
) -> list[dict]:
    """One Brave web-search request, throttled across all Brave connectors."""
    await _throttle(priority)
    params: dict = {"q": query, "count": count, "offset": offset}
    if country:
        params["country"] = country
    resp = await client.get(
        API_URL,
        params=params,
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    resp.raise_for_status()
    return ((resp.json().get("web") or {}).get("results")) or []


async def brave_query(
    client: httpx.AsyncClient,
    api_key: str,
    query: str,
    count: int = _RESULTS_PER_PAGE,
    country: str | None = None,
    priority: int = _DEFAULT_PRIORITY,
) -> list[dict]:
    """All pages of one Brave web-search query (up to `_MAX_PAGES`).

    `country` (e.g. "GB") localises results to that market. `priority` is the
    calling connector's priority for the shared rate limit."""
    results: list[dict] = []
    for page in range(_MAX_PAGES):
        try:
            page_results = await _brave_request(
                client, api_key, query, count, page, country, priority
            )
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


def build_queries(subject: SearchSubject, name_variants: list[str] | None = None) -> list[str]:
    """The Brave query plan, in the order the queries are sent:

    1. name   2. name + country   3. name + location
    4. name + country + location  5. nickname/variant forms of the name

    Queries whose inputs are missing are skipped; identical queries (e.g. a
    location equal to the country) are sent once.
    """
    name = " ".join(subject.full_name.split())
    country = " ".join((subject.country or "").split())
    location = " ".join((subject.location or "").split())
    plan = [name]
    if country:
        plan.append(f"{name} {country}")
    if location:
        plan.append(f"{name} {location}")
    if country and location and country.lower() != location.lower():
        plan.append(f"{name} {country} {location}")
    plan += [" ".join(v.split()) for v in name_variants or []]

    queries: list[str] = []
    seen: set[str] = set()
    for q in plan:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    return queries


class BraveSearchConnector(BaseConnector):
    name = "brave_search"
    display_name = "Brave Web Search"
    description = (
        "General public web results via the Brave Search API: name, name + country, "
        "name + location, name + country + location."
    )

    def is_configured(self) -> bool:
        return bool(self.settings.brave_api_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.web_mock(subject, source=self.name)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        api_key = self.settings.brave_api_key
        country = self.settings.brave_country or None
        # Gather every query's results first; filtering happens afterwards.
        results: list[dict] = []
        for query in build_queries(subject, names[1:]):
            results += await brave_query(
                client, api_key, query, country=country, priority=self.priority
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
