"""UK Sanctions List connector.

Downloads the published UK Sanctions List (JSON) from GOV.UK, caches it in
memory for an hour, and fuzzy-matches designated individuals against the search
subject. The download URL is configurable (`UK_SANCTIONS_LIST_URL`) because the
published asset location changes between releases.
"""

import time
from typing import Any

import httpx
from rapidfuzz import fuzz

from app.connectors import mock_data
from app.connectors.base import BaseConnector, Category, Finding, SearchSubject

_CACHE_TTL_SECONDS = 3600
# token_sort_ratio ≥ 90 — 85 was loose enough to pull in near-miss surnames,
# which produced sanctions "hits" for unrelated people with similar names.
_MATCH_THRESHOLD = 90


class UkSanctionsConnector(BaseConnector):
    name = "uk_sanctions"
    display_name = "UK Sanctions List"
    description = "Designated individuals on the UK Sanctions List (FCDO)."

    _cache: list[dict[str, Any]] | None = None
    _cache_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.settings.uk_sanctions_list_url)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.sanctions_mock(subject)

    async def _load_list(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        cls = type(self)
        if cls._cache is not None and time.monotonic() - cls._cache_at < _CACHE_TTL_SECONDS:
            return cls._cache
        resp = await client.get(self.settings.uk_sanctions_list_url)
        resp.raise_for_status()
        data = resp.json()
        # The published shape nests designations; accept either a bare list or
        # common wrapper keys so minor format changes don't break the connector.
        if isinstance(data, list):
            designations = data
        else:
            designations = (
                data.get("designations")
                or data.get("Designations")
                or data.get("results")
                or []
            )
        cls._cache = designations
        cls._cache_at = time.monotonic()
        return designations

    @staticmethod
    def _names_of(entry: dict[str, Any]) -> list[str]:
        names = []
        for key in ("Names", "names", "aliases"):
            value = entry.get(key)
            if isinstance(value, list):
                for n in value:
                    if isinstance(n, str):
                        names.append(n)
                    elif isinstance(n, dict):
                        combined = n.get("Name6") or n.get("name") or ""
                        if combined:
                            names.append(combined)
        for key in ("Name", "name", "NameOfIndividual"):
            if isinstance(entry.get(key), str):
                names.append(entry[key])
        return names

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        designations = await self._load_list(client)
        findings = []
        target = subject.full_name.lower()
        for entry in designations:
            # Only individuals are relevant to this platform.
            entity_type = str(
                entry.get("IndividualEntityShip") or entry.get("type") or "individual"
            ).lower()
            if "individual" not in entity_type:
                continue
            for candidate in self._names_of(entry):
                score = fuzz.token_sort_ratio(target, candidate.lower())
                if score >= _MATCH_THRESHOLD:
                    regime = entry.get("RegimeName") or entry.get("regime") or "UK Sanctions"
                    findings.append(
                        Finding(
                            source=self.name,
                            category=Category.SANCTIONS,
                            title=f"UK Sanctions List match — {candidate}",
                            description=f"Designated under: {regime}. Name match {score:.0f}%.",
                            url="https://www.gov.uk/government/publications/the-uk-sanctions-list",
                            date=str(entry.get("DateDesignated") or entry.get("date") or "")
                            or None,
                            subject_name=candidate,
                            date_of_birth=str(entry.get("DOB") or entry.get("dateOfBirth") or "")
                            or None,
                            raw={"regime": regime, "match_score": score},
                        )
                    )
                    break
        return findings
