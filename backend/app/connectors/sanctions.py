"""UK Sanctions List connector.

Downloads the published UK Sanctions List from GOV.UK/FCDO, caches the parsed
designations in memory for an hour, and fuzzy-matches designated individuals
against the search subject.

The authoritative source is the FCDO UK Sanctions List XML feed
(https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml) — the OFSI
consolidated-list JSON was retired in January 2026. JSON payloads are still
accepted (`UK_SANCTIONS_LIST_URL` is configurable) so a licensed screening
provider can be substituted without code changes.
"""

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.connectors import mock_data
from app.connectors.base import (
    BaseConnector,
    Category,
    Finding,
    SearchSubject,
    screening_score,
)

_CACHE_TTL_SECONDS = 3600
# Screening threshold. token_set_ratio tolerates extra name parts (patronymics,
# middle names — e.g. "Roman Abramovich" vs "Roman Arkadyevich Abramovich")
# while ≥ 90 still rejects merely similar names. Missing a true sanctions hit
# is worse than surfacing a possible one: downstream identity matching caps the
# confidence of uncorroborated matches, so candidates are labelled honestly.
_MATCH_THRESHOLD = 90
# The full list is ~20 MB; allow a generous one-off download window.
_DOWNLOAD_TIMEOUT_SECONDS = 120


@dataclass
class _Designation:
    """A parsed individual designation, normalised across XML/JSON sources."""

    primary_name: str
    names: list[str] = field(default_factory=list)  # primary + aliases
    regime: str = "UK Sanctions"
    date_designated: str | None = None
    date_of_birth: str | None = None  # ISO where derivable
    country: str | None = None
    unique_id: str | None = None


def _iso_date(value: str | None) -> str | None:
    """FCDO dates are DD/MM/YYYY; pass through anything already ISO-ish."""
    if not value:
        return None
    value = value.strip()
    parts = value.split("/")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        day, month, year = parts
        if len(year) == 4:
            return f"{year}-{int(month):02d}-{int(day):02d}"
    return value or None


def _full_name(name_node: ET.Element) -> str:
    """FCDO name parts: Name1-Name5 are forenames/middle names, Name6 is the
    primary/family name. Join whichever parts are present."""
    parts = [
        (name_node.findtext(f"Name{i}") or "").strip() for i in range(1, 7)
    ]
    return " ".join(p for p in parts if p)


def _parse_xml(content: bytes) -> list[_Designation]:
    root = ET.fromstring(content)
    designations: list[_Designation] = []
    for node in root.iter("Designation"):
        entity_type = (node.findtext("IndividualEntityShip") or "").strip().lower()
        if entity_type != "individual":
            continue
        names: list[str] = []
        primary = ""
        for name_node in node.iter("Name"):
            combined = _full_name(name_node)
            if not combined:
                continue
            names.append(combined)
            if (name_node.findtext("NameType") or "").strip() == "Primary Name":
                primary = combined
        if not names:
            continue
        primary = primary or names[0]
        dob = None
        for dob_node in node.iter("DOB"):
            if dob_node.text and dob_node.text.strip():
                dob = _iso_date(dob_node.text)
                break
        country = None
        for country_node in node.iter("AddressCountry"):
            if country_node.text and country_node.text.strip():
                country = country_node.text.strip()
                break
        designations.append(
            _Designation(
                primary_name=primary,
                names=names,
                regime=(node.findtext("RegimeName") or "UK Sanctions").strip(),
                date_designated=_iso_date(node.findtext("DateDesignated")),
                date_of_birth=dob,
                country=country,
                unique_id=(node.findtext("UniqueID") or "").strip() or None,
            )
        )
    return designations


def _json_names_of(entry: dict[str, Any]) -> list[str]:
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


def _parse_json(data: Any) -> list[_Designation]:
    if isinstance(data, list):
        entries = data
    else:
        entries = (
            data.get("designations")
            or data.get("Designations")
            or data.get("results")
            or []
        )
    designations = []
    for entry in entries:
        entity_type = str(
            entry.get("IndividualEntityShip") or entry.get("type") or "individual"
        ).lower()
        if "individual" not in entity_type:
            continue
        names = _json_names_of(entry)
        if not names:
            continue
        designations.append(
            _Designation(
                primary_name=names[0],
                names=names,
                regime=str(entry.get("RegimeName") or entry.get("regime") or "UK Sanctions"),
                date_designated=_iso_date(
                    str(entry.get("DateDesignated") or entry.get("date") or "") or None
                ),
                date_of_birth=_iso_date(
                    str(entry.get("DOB") or entry.get("dateOfBirth") or "") or None
                ),
                unique_id=str(entry.get("UniqueID") or "") or None,
            )
        )
    return designations


class UkSanctionsConnector(BaseConnector):
    name = "uk_sanctions"
    display_name = "UK Sanctions List"
    description = "Designated individuals on the UK Sanctions List (FCDO)."

    _cache: list[_Designation] | None = None
    _cache_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.settings.uk_sanctions_list_url)

    def mock_findings(self, subject: SearchSubject) -> list[Finding]:
        return mock_data.sanctions_mock(subject)

    async def _load_list(self, client: httpx.AsyncClient) -> list[_Designation]:
        cls = type(self)
        if cls._cache is not None and time.monotonic() - cls._cache_at < _CACHE_TTL_SECONDS:
            return cls._cache
        resp = await client.get(
            self.settings.uk_sanctions_list_url, timeout=_DOWNLOAD_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        content = resp.content.lstrip()
        if content.startswith(b"<"):
            designations = _parse_xml(resp.content)
        else:
            designations = _parse_json(resp.json())
        cls._cache = designations
        cls._cache_at = time.monotonic()
        return designations

    async def fetch(self, subject: SearchSubject, client: httpx.AsyncClient) -> list[Finding]:
        designations = await self._load_list(client)
        findings = []
        for entry in designations:
            best_score = 0.0
            best_name = None
            for candidate in entry.names:
                score = screening_score(subject.full_name, candidate)
                if score > best_score:
                    best_score, best_name = score, candidate
            if best_score < _MATCH_THRESHOLD or best_name is None:
                continue
            findings.append(
                Finding(
                    source=self.name,
                    category=Category.SANCTIONS,
                    title=f"UK Sanctions List match — {entry.primary_name}",
                    description=(
                        f"Designated under: {entry.regime}. "
                        f"Matched name: {best_name} ({best_score:.0f}%)."
                    ),
                    url="https://search-uk-sanctions-list.service.gov.uk/",
                    date=entry.date_designated,
                    subject_name=best_name,
                    location=entry.country,
                    date_of_birth=entry.date_of_birth,
                    raw={
                        "regime": entry.regime,
                        "match_score": best_score,
                        "unique_id": entry.unique_id,
                        "primary_name": entry.primary_name,
                    },
                )
            )
        return findings
