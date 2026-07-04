"""NewsAPI connector — adverse media / news coverage."""

import httpx
from rapidfuzz import fuzz

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

# An article must actually mention the subject's name in its title/description;
# anything below this partial-match score is provider noise, not evidence.
_MENTION_THRESHOLD = 70


class NewsApiConnector(BaseConnector):
    name = "news_api"
    display_name = "News API"
    description = "Adverse media and news coverage via newsapi.org."

    API_URL = "https://newsapi.org/v2/everything"

    def is_configured(self) -> bool:
        return bool(self.settings.newsapi_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.news_mock(subject)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        params = {
            "q": f'"{subject.full_name}"',
            "language": "en",
            "sortBy": "relevancy",
            "pageSize": 20,
        }
        headers = {"X-Api-Key": self.settings.newsapi_key}
        resp = await client.get(self.API_URL, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        findings = []
        target = subject.full_name.lower()
        for article in data.get("articles", []):
            published = (article.get("publishedAt") or "")[:10] or None
            title = article.get("title", "Untitled article")
            description = article.get("description") or ""
            # News articles only *mention* a name — subject_name is left unset
            # so identity matching treats this as an unstructured mention with
            # a low confidence ceiling, never a verified identity match.
            if fuzz.token_set_ratio(target, f"{title} {description}".lower()) < _MENTION_THRESHOLD:
                continue
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
