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
        return web_common.parse_sites(self.settings.social_media_sites)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        findings = []
        seen_links: set[str] = set()
        for site in self._sites():
            results: list[dict] = []
            for name in names:
                results += await brave_query(
                    client,
                    self.settings.brave_api_key,
                    f"{name} site:{site}",
                    country=self.settings.brave_country or None,
                    priority=self.priority,
                )
            for item in results:
                link = item.get("url") or ""
                # Drop provider noise from other hosts and cross-query repeats.
                if not link or link in seen_links or not web_common.on_site(link, site):
                    continue
                seen_links.add(link)
                title = web_common.clean_snippet(item.get("title", "")) or "Untitled result"
                description = web_common.clean_snippet(item.get("description") or "")
                text = f"{title} {description}"
                # Same rule as the web connectors: a post/profile only
                # *mentions* a name — subject_name stays unset so identity
                # matching applies its unstructured-mention ceiling. Checked
                # against every name form queried (nicknames included).
                if not any(web_common.mentions_subject(n, text) for n in names):
                    continue
                page_age = (item.get("page_age") or "")[:10] or None
                findings.append(
                    Finding(
                        source=self.name,
                        category=web_common.categorise(text, default=Category.SOCIAL_MEDIA),
                        title=title,
                        description=description or None,
                        url=link,
                        date=page_age,
                        raw={"platform": PLATFORM_LABELS.get(site, site), "site": site},
                    )
                )
        return findings
