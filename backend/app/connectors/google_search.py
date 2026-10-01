"""Google Programmable Search connector — general public web results.

⚠ Google closed the Custom Search JSON API to NEW customers on 20 Jan 2026
(existing customers are grandfathered until Jan 2027). New projects receive
403 "This project does not have the access to Custom Search JSON API". Use
the Brave Search connector instead unless you have a grandfathered key.

For each name form searched (the subject's name as given, plus any
nickname/variant forms), two queries are run — the name alone, and the name
combined with adverse-media terms (the standard screening "dork") — each
paginated across several pages. Names are sent unquoted: a quoted phrase
forces an exact, contiguous match and misses sources that write the name with
a middle initial, reordered ("Smith, John"), or otherwise slightly
differently — the fuzzy `mentions_subject` check afterwards is what keeps
results relevant, not the query syntax. Results whose text contains adverse
terms are categorised as adverse media so the risk scorer's keyword
escalation applies; everything else stays in the low-weight web category.
"""

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Finding, SearchSubject

# Google CSE returns at most 10 results per request; paginate via `start`.
_RESULTS_PER_PAGE = 10
_MAX_PAGES = 3


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
        items: list[dict] = []
        for page in range(_MAX_PAGES):
            params = {
                "key": self.settings.google_api_key,
                "cx": self.settings.google_cse_id,
                "q": query,
                "num": _RESULTS_PER_PAGE,
                "start": page * _RESULTS_PER_PAGE + 1,
            }
            resp = await client.get(self.API_URL, params=params)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                # The CSE free tier caps how far `start` can page; treat a
                # later-page failure as "no more pages" and keep what was
                # already fetched rather than discarding it.
                if page == 0:
                    raise
                break
            page_items = resp.json().get("items", [])
            if not page_items:
                break
            items.extend(page_items)
            if len(page_items) < _RESULTS_PER_PAGE:
                break
        return items

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        items: list[dict] = []
        for name in names:
            items += await self._query(client, name)
            items += await self._query(client, f"{name} ({web_common.ADVERSE_QUERY_TERMS})")

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
            # Checked against every name form queried (nicknames included),
            # since a result found via a nickname query won't mention the
            # subject's given name verbatim.
            if not any(web_common.mentions_subject(n, text) for n in names):
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
