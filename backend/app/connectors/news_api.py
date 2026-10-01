"""NewsAPI connector — adverse media / news coverage.

For each name form searched (the subject's name as given, plus any
nickname/variant forms), the query requires every name token to appear
somewhere in the article (NewsAPI's `+token` syntax) rather than the name as
an exact contiguous phrase — a quoted phrase misses articles that write the
name with a middle initial or in a different order. The fuzzy mention check
below is what keeps results relevant, not the query syntax. Results are
paginated up to `_MAX_PAGES` pages per name form.
"""

import httpx
from rapidfuzz import fuzz

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

# An article must actually mention the subject's name in its title/description;
# anything below this partial-match score is provider noise, not evidence.
_MENTION_THRESHOLD = 70

_PAGE_SIZE = 100
_MAX_PAGES = 3


class NewsApiConnector(BaseConnector):
    name = "news_api"
    display_name = "News API"
    description = "Adverse media and news coverage via newsapi.org."

    API_URL = "https://newsapi.org/v2/everything"

    def is_configured(self) -> bool:
        return bool(self.settings.newsapi_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.news_mock(subject)

    async def _query(self, client: httpx.AsyncClient, name: str) -> list[dict]:
        # Require every name token to appear (not necessarily adjacent),
        # rather than an exact quoted phrase.
        query = " ".join(f"+{token}" for token in name.split())
        headers = {"X-Api-Key": self.settings.newsapi_key}
        articles: list[dict] = []
        for page in range(1, _MAX_PAGES + 1):
            params = {
                "q": query,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": _PAGE_SIZE,
                "page": page,
            }
            resp = await client.get(self.API_URL, params=params, headers=headers)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                # Some plans cap total paginated results and 4xx once that cap
                # is hit (e.g. NewsAPI's developer tier). The first page is a
                # genuine failure (let the base connector retry/fail it); a
                # later page failing just means "no more pages available" —
                # keep what was already fetched instead of discarding it.
                if page == 1:
                    raise
                break
            data = resp.json()
            page_articles = data.get("articles", [])
            if not page_articles:
                break
            articles.extend(page_articles)
            if page * _PAGE_SIZE >= data.get("totalResults", 0):
                break
        return articles

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        articles: list[dict] = []
        for name in names:
            articles += await self._query(client, name)

        findings = []
        seen_urls: set[str] = set()
        targets = [n.lower() for n in names]
        for article in articles:
            url = article.get("url") or ""
            if url and url in seen_urls:
                continue
            published = (article.get("publishedAt") or "")[:10] or None
            title = article.get("title", "Untitled article")
            description = article.get("description") or ""
            text = f"{title} {description}".lower()
            # News articles only *mention* a name — subject_name is left unset
            # so identity matching treats this as an unstructured mention with
            # a low confidence ceiling, never a verified identity match.
            # Checked against every name form queried (nicknames included).
            if not any(
                fuzz.token_set_ratio(target, text) >= _MENTION_THRESHOLD for target in targets
            ):
                continue
            if url:
                seen_urls.add(url)
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.ADVERSE_MEDIA,
                    title=title,
                    description=article.get("description"),
                    url=article.get("url"),
                    date=published,
                    raw={
                        "source": (article.get("source") or {}).get("name"),
                        "author": article.get("author"),
                    },
                )
            )
        return findings
