"""Social media connector — public posts and profiles on major platforms.

The platforms themselves offer no person-search API suitable for screening
(X's API is paywalled, Meta's Graph API prohibits screening use cases, TikTok
has no public search API), and scraping them would breach their terms of
service. Instead, each platform's *publicly indexed* content is searched
through the Brave Search API with ``site:`` restricted queries — the same
results a manual public web search would surface, obtained in a
ToS-compliant way.

Reuses BRAVE_API_KEY (all Brave requests share one throttle — see
:mod:`app.connectors.brave_search`). The platform list is configurable via
SOCIAL_MEDIA_SITES, so adding e.g. linkedin.com is an env change, not code.

Results with personal-conduct or adverse terms (threats, harassment, racism,
fraud, …) are categorised as adverse media so risk scoring escalates them;
neutral profile/post mentions stay in the low-weight social_media category.
"""

from urllib.parse import urlparse

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject
from app.connectors.brave_search import brave_query

PLATFORM_LABELS = {
    "x.com": "X (Twitter)",
    "twitter.com": "X (Twitter)",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "reddit.com": "Reddit",
    "youtube.com": "YouTube",
    "linkedin.com": "LinkedIn",
}


def _on_site(url: str, site: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return host == site or host.endswith("." + site)


class SocialMediaConnector(BaseConnector):
    name = "social_media"
    display_name = "Social Media"
    description = (
        "Public posts and profiles on major social platforms (X/Twitter, Facebook, "
        "Instagram, TikTok, Reddit, YouTube), searched via the Brave Search API's "
        "public index — no platform scraping."
    )

    def is_configured(self) -> bool:
        return bool(self.settings.brave_api_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.social_mock(subject)

    def _sites(self) -> list[str]:
        return [
            s.strip().lower()
            for s in self.settings.social_media_sites.split(",")
            if s.strip()
        ]

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        name = subject.full_name
        findings = []
        seen_links: set[str] = set()
        for site in self._sites():
            results = await brave_query(
                client, self.settings.brave_api_key, f'"{name}" site:{site}'
            )
            for item in results:
                link = item.get("url") or ""
                # Drop provider noise from other hosts and cross-query repeats.
                if not link or link in seen_links or not _on_site(link, site):
                    continue
                seen_links.add(link)
                title = item.get("title", "Untitled result")
                description = item.get("description") or ""
                text = f"{title} {description}"
                # Same rule as the web connectors: a post/profile only
                # *mentions* a name — subject_name stays unset so identity
                # matching applies its unstructured-mention ceiling.
                if not web_common.mentions_subject(name, text):
                    continue
                page_age = (item.get("page_age") or "")[:10] or None
                findings.append(
                    Finding(
                        source=self.name,
                        category=web_common.categorise(
                            text,
                            default=Category.SOCIAL_MEDIA,
                            extra_terms=web_common.CONDUCT_TERMS,
                        ),
                        title=title,
                        description=description or None,
                        url=link,
                        date=page_age,
                        raw={"platform": PLATFORM_LABELS.get(site, site), "site": site},
                    )
                )
        return findings
