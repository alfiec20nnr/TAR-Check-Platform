"""UK newspapers connector — coverage in major UK national and regional press.

Searches the publicly indexed articles of every outlet in UK_NEWSPAPER_SITES
(BBC, Guardian, Times, Telegraph, FT, Independent, i, Mail, Mirror, Express,
Sun, Standard, Metro, Sky News, ITV, plus the main Scottish, Welsh, Northern
Irish and English regional titles) through the Brave Search API, localised to
the UK market. Like the social-media connector this uses ``site:`` restricted
queries — the same results a manual search of each paper would surface —
rather than scraping the publishers, many of which are paywalled.

Sites are grouped into ``site:a OR site:b …`` batches so a full sweep of the
UK press costs a handful of requests per name form, not one per paper (all
Brave requests share one 1 req/s throttle — see
:mod:`app.connectors.brave_search`). Reuses BRAVE_API_KEY.

Only articles that actually name the subject (forename and surname together,
see :func:`web_common.mentions_subject`) and are hosted on a listed outlet are
kept; everything else is discarded. Articles containing adverse terms are
categorised as adverse media; neutral coverage stays in the web category.
"""

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Finding, SearchSubject
from app.connectors.brave_search import brave_query

# Sites per OR-batch: keeps each query well inside Brave's query-length limit.
_SITES_PER_QUERY = 8


class UkNewspapersConnector(BaseConnector):
    name = "uk_newspapers"
    display_name = "UK Newspapers"
    description = (
        "Articles in major UK national and regional newspapers and broadcasters "
        "(BBC, Guardian, Times, Telegraph, FT, Mail, Mirror, Sky News, regional "
        "titles…), searched via the Brave Search API's public index."
    )

    def is_configured(self) -> bool:
        return bool(self.settings.brave_api_key and self._sites())

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.uk_newspapers_mock(subject)

    def _sites(self) -> list[str]:
        return web_common.parse_sites(self.settings.uk_newspaper_sites)

    def _site_batches(self) -> list[list[str]]:
        sites = self._sites()
        return [sites[i : i + _SITES_PER_QUERY] for i in range(0, len(sites), _SITES_PER_QUERY)]

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        sites = self._sites()
        country = self.settings.brave_country or None
        results: list[dict] = []
        for name in names:
            for batch in self._site_batches():
                site_filter = " OR ".join(f"site:{s}" for s in batch)
                results += await brave_query(
                    client, self.settings.brave_api_key, f"{name} ({site_filter})", country=country
                )

        findings = []
        seen_links: set[str] = set()
        for item in results:
            link = item.get("url") or ""
            if not link or link in seen_links:
                continue
            outlet = next((s for s in sites if web_common.on_site(link, s)), None)
            if outlet is None:
                continue  # provider noise from outside the UK press list
            seen_links.add(link)
            title = item.get("title", "Untitled article")
            description = item.get("description") or ""
            text = f"{title} {description}"
            # Articles only *mention* a name — subject_name stays unset so
            # identity matching applies its unstructured-mention ceiling.
            # Articles that don't name the subject are discarded.
            if not any(web_common.mentions_subject(n, text) for n in names):
                continue
            page_age = (item.get("page_age") or "")[:10] or None
            findings.append(
                Finding(
                    source=self.name,
                    category=web_common.categorise(text),
                    title=title,
                    description=description or None,
                    url=link,
                    date=page_age,
                    raw={"publication": outlet},
                )
            )
        return findings
