"""NewsAPI connector — adverse media / news coverage."""

import httpx

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject


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
        for article in data.get("articles", []):
            published = (article.get("publishedAt") or "")[:10] or None
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.ADVERSE_MEDIA,
                    title=article.get("title", "Untitled article"),
                    description=article.get("description"),
                    url=article.get("url"),
                    date=published,
                    subject_name=subject.full_name,
                    raw={
                        "source": (article.get("source") or {}).get("name"),
                        "author": article.get("author"),
                    },
                )
            )
        return findings
