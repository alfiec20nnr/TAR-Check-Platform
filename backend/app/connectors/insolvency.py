"""UK personal insolvency connector.

Two data paths:

- **Licensed provider** (`INSOLVENCY_API_URL` / `INSOLVENCY_API_KEY` set):
  mirrors the full Individual Insolvency Register, including IVAs and Debt
  Relief Orders. The expected response shape is a JSON body with a `records`
  array; adjust `_parse_provider` for your provider.

- **The Gazette (default, no key needed)**: bankruptcy orders and related
  personal-insolvency proceedings are published by law in The Gazette, whose
  official public data API is free under the Open Government Licence
  (https://github.com/TheGazette/DevDocs). Unlike the live register, Gazette
  notices are permanent, so historical bankruptcies stay findable. Coverage
  caveat: IVAs and DROs never appear in The Gazette — they need the licensed
  path above.

Gazette quirks handled here: quoted-phrase searches return HTTP 500, so the
name is sent unquoted and results are screened locally; notices carry no
reliable structured subject name, so findings are treated as unstructured
mentions (identity matching applies its low confidence ceiling).
"""

import html
import re

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

GAZETTE_API_URL = "https://www.thegazette.co.uk/insolvency/notice/data.json"

# Gazette notice category 25 = Personal Insolvency (24 is corporate).
_PERSONAL_INSOLVENCY_CATEGORY = "25"
_PAGE_SIZE = 50
_MAX_PAGES = 5

_TAG_RE = re.compile(r"<[^>]+>")

# Newer Gazette personal-insolvency notices carry a standardised birth-details
# line, e.g. "Birth details: 18 August 1968" — extracting it lets identity
# matching corroborate (or rule out) the record against a supplied DOB.
_DOB_RE = re.compile(r"Birth details:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _strip_html(text: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", text)).split())


def _extract_dob(text: str) -> str | None:
    match = _DOB_RE.search(text)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = _MONTHS.get(month_name.lower())
    if month is None:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def _as_list(value) -> list:
    """Atom-derived JSON collapses single-item lists to plain objects."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class InsolvencyConnector(BaseConnector):
    name = "insolvency_register"
    display_name = "UK Insolvency Register"
    description = (
        "Bankruptcies and personal-insolvency proceedings via The Gazette's official "
        "public data API (no key needed); a licensed provider endpoint can be "
        "configured instead for full register coverage including IVAs and DROs."
    )

    def is_configured(self) -> bool:
        return True  # the Gazette path needs no credentials

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.insolvency_mock(subject)

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        if self.settings.insolvency_api_url:
            return await self._fetch_provider(subject, client)
        return await self._fetch_gazette(subject, client)

    # -- licensed provider -------------------------------------------------------

    async def _fetch_provider(
        self, subject: SearchSubject, client: httpx.AsyncClient
    ) -> list[Finding]:
        headers = {}
        if self.settings.insolvency_api_key:
            headers["Authorization"] = f"Bearer {self.settings.insolvency_api_key}"
        resp = await client.get(
            self.settings.insolvency_api_url,
            params={"name": subject.full_name},
            headers=headers,
        )
        resp.raise_for_status()
        return self._parse_provider(resp.json(), subject)

    def _parse_provider(self, data: dict, subject: SearchSubject) -> list[Finding]:
        findings = []
        for record in data.get("records", []):
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.INSOLVENCY,
                    title=record.get("title")
                    or f"Insolvency record — {record.get('name', subject.full_name)}",
                    description=record.get("description") or record.get("order_type"),
                    url=record.get("url"),
                    date=record.get("date"),
                    subject_name=record.get("name"),
                    location=record.get("address"),
                    date_of_birth=record.get("date_of_birth"),
                    raw=record,
                )
            )
        return findings

    # -- The Gazette (default) ---------------------------------------------------

    async def _query_gazette(self, client: httpx.AsyncClient, name: str) -> list[dict]:
        entries: list[dict] = []
        for page in range(1, _MAX_PAGES + 1):
            resp = await client.get(
                GAZETTE_API_URL,
                params={
                    # Quoted phrases 500 on this API — send plain tokens and
                    # screen by name locally instead.
                    "text": name,
                    "categorycode": _PERSONAL_INSOLVENCY_CATEGORY,
                    "results-page-size": _PAGE_SIZE,
                    "start-page": page,
                },
                # NB: no Accept header — the .json extension selects the
                # format, and an explicit "Accept: application/json" makes
                # the Gazette's content negotiation return HTTP 500.
                headers={
                    "User-Agent": f"{self.settings.app_name} (compliance screening)",
                },
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                if page == 1:
                    raise
                break
            page_entries = _as_list(resp.json().get("entry"))
            if not page_entries:
                break
            entries.extend(page_entries)
            if len(page_entries) < _PAGE_SIZE:
                break
        return entries

    async def _fetch_gazette(
        self, subject: SearchSubject, client: httpx.AsyncClient
    ) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        entries: list[dict] = []
        for name in names:
            entries += await self._query_gazette(client, name)

        findings = []
        seen_ids: set[str] = set()
        for entry in entries:
            notice_id = entry.get("id") or ""
            if notice_id and notice_id in seen_ids:
                continue
            notice_type = (
                (entry.get("category") or {}).get("@term")
                or entry.get("title")
                or "Personal insolvency notice"
            )
            snippet = _strip_html(entry.get("content") or "")
            # The notice must actually name the subject — full-name tokens in
            # the text, same screening rule as the web connectors. Checked
            # against every name form queried (nicknames included).
            if not any(web_common.mentions_subject(n, snippet) for n in names):
                continue
            if notice_id:
                seen_ids.add(notice_id)
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.INSOLVENCY,
                    title=f"{entry.get('title') or notice_type} — The Gazette",
                    description=snippet[:400] or None,
                    url=self._notice_url(entry),
                    date=(entry.get("published") or "")[:10] or None,
                    # No reliable structured name in Gazette search results —
                    # left unset so identity matching treats this as an
                    # unstructured mention (low confidence ceiling).
                    date_of_birth=_extract_dob(snippet),
                    raw={
                        "notice_type": notice_type,
                        "notice_code": entry.get("f:notice-code"),
                        "notice_id": entry.get("id"),
                    },
                )
            )
        return findings

    @staticmethod
    def _notice_url(entry: dict) -> str | None:
        # Prefer the human notice page: the link entry with no @rel qualifier.
        for link in _as_list(entry.get("link")):
            href = link.get("@href")
            if href and "@rel" not in link and "@type" not in link:
                return href
        return entry.get("id")
