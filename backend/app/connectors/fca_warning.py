"""FCA connector — regulatory warnings from the FS Register API.

Uses the FCA Financial Services Register API (register.fca.org.uk) to search
individuals and surface associated warnings/prohibitions. Requires the free
developer email + key pair.
"""

import httpx

from app.connectors import mock_data, web_common
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

BASE_URL = "https://register.fca.org.uk/services/V0.1"


class FcaWarningConnector(BaseConnector):
    name = "fca_warning_list"
    display_name = "FCA Warning List"
    description = "Regulatory warnings and prohibitions from the FCA register."

    def is_configured(self) -> bool:
        return bool(self.settings.fca_api_email and self.settings.fca_api_key)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.fca_mock(subject)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Auth-Email": self.settings.fca_api_email,
            "X-Auth-Key": self.settings.fca_api_key,
            "Content-Type": "application/json",
        }

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        names = web_common.query_names(subject.full_name, self.settings.matching_config_path)
        items: list[dict] = []
        for name in names:
            resp = await client.get(
                f"{BASE_URL}/Search",
                params={"q": name, "type": "individual"},
                headers=self._headers(),
            )
            resp.raise_for_status()
            items += resp.json().get("Data", []) or []

        findings = []
        seen_refs: set[str] = set()
        for item in items:
            status = (item.get("Status") or "").lower()
            name = item.get("Name") or subject.full_name
            ref = item.get("Reference Number") or item.get("URL") or ""
            if ref and ref in seen_refs:
                continue
            # Only surface adverse statuses; clean register entries are not findings.
            adverse = any(
                token in status for token in ("prohibit", "warning", "unauthorised", "banned")
            )
            if not adverse:
                continue
            if ref:
                seen_refs.add(ref)
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.REGULATORY,
                    title=f"FCA register — {name} ({item.get('Status')})",
                    description=f"FCA register entry with status: {item.get('Status')}.",
                    url=item.get("URL") or "https://register.fca.org.uk/",
                    subject_name=name,
                    raw={"reference": item.get("Reference Number")},
                )
            )
        return findings
