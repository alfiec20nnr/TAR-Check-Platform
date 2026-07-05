"""Google Programmable Search connector — general public web results.

Two queries per search: the subject's name alone, and the name combined with
adverse-media terms (the standard screening "dork"). Results whose text
contains adverse terms are categorised as adverse media so the risk scorer's
keyword escalation applies; everything else stays in the low-weight web
category.
"""

import httpx
from rapidfuzz import fuzz

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

# A result must actually mention the subject's name in its title/snippet;
# anything below this partial-match score is provider noise, not evidence.
_MENTION_THRESHOLD = 70

# Terms that mark a result as adverse media rather than a neutral web mention.
# Aligned with (a superset of) the serious keywords in config/risk_weights.yaml,
# which the risk scorer uses for escalation.
ADVERSE_TERMS = [
    "fraud", "money laundering", "bribery", "corruption", "embezzlement",
    "terrorism", "trafficking", "sanctions violation", "insider trading",
    "tax evasion", "convicted", "conviction", "charged", "arrested",
    "investigation", "lawsuit", "tribunal", "misconduct", "scandal",
    "allegations", "banned", "disqualified", "fined", "penalty",
]

# The OR-query sent to Google alongside the plain name query.
_ADVERSE_QUERY_TERMS = (
    'fraud OR corruption OR "money laundering" OR convicted OR lawsuit '
    "OR scandal OR investigation OR misconduct OR fined"
)


def _categorise(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ADVERSE_TERMS):
        return Category.ADVERSE_MEDIA
    return Category.WEB


class GoogleSearchConnector(BaseConnector):
    name = "google_search"
    display_name = "Google Search"
    description = "General public web results via the Google Programmable Search API."

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def is_configured(self) -> bool:
        return bool(self.settings.google_api_key and self.settings.google_cse_id)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.google_mock(subject)

    async def _query(
        self, client: httpx.AsyncClient, query: str
    ) -> list[dict]:
        params = {
            "key": self.settings.google_api_key,
            "cx": self.settings.google_cse_id,
            "q": query,
            "num": 10,
        }
        resp = await client.get(self.API_URL, params=params)
        resp.raise_for_status()
        return resp.json().get("items", [])

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        name = subject.full_name
        items = await self._query(client, f'"{name}"')
        items += await self._query(client, f'"{name}" ({_ADVERSE_QUERY_TERMS})')

        findings = []
        seen_links: set[str] = set()
        target = name.lower()
        for item in items:
            link = item.get("link") or ""
            if link and link in seen_links:
                continue
            seen_links.add(link)
            title = item.get("title", "Untitled result")
            snippet = item.get("snippet") or ""
            text = f"{title} {snippet}"
            # Web pages only *mention* a name — they do not attribute a record
            # to a person. subject_name is deliberately left unset so identity
            # matching treats this as an unstructured mention (low confidence
            # ceiling) instead of a source-verified name match.
            if fuzz.token_set_ratio(target, text.lower()) < _MENTION_THRESHOLD:
                continue
            findings.append(
                Finding(
                    source=self.name,
                    category=_categorise(text),
                    title=title,
                    description=item.get("snippet"),
                    url=item.get("link"),
                    raw=item,
                )
            )
        return findings
