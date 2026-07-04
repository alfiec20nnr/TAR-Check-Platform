"""Identity Matching Engine.

Compares candidate records against the search subject and assigns a confidence
percentage per record. The engine never assumes two records belong to the same
person — it only reports weighted evidence across the signals available in the
MVP: name (with common variants), date of birth, and country/location.

Weightings live in config/matching_weights.yaml.
"""

import functools
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from rapidfuzz import fuzz

from app.connectors.base import Finding, SearchSubject


@dataclass
class MatchingConfig:
    weights: dict[str, float]
    scores: dict[str, int]
    dob_mismatch_cap: float
    name_variants: dict[str, list[str]]

    @classmethod
    def load(cls, path: Path) -> "MatchingConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            weights=data.get("weights", {}),
            scores=data.get("scores", {}),
            dob_mismatch_cap=float(data.get("dob_mismatch_cap", 30)),
            name_variants=data.get("name_variants", {}),
        )


@functools.lru_cache(maxsize=4)
def _load_config(path_str: str) -> MatchingConfig:
    return MatchingConfig.load(Path(path_str))


def _normalise(text: str) -> str:
    text = re.sub(r"[^a-z\s'-]", " ", text.lower())
    return " ".join(text.split())


class IdentityMatcher:
    def __init__(self, config: MatchingConfig):
        self.config = config
        # Build a token → canonical-form lookup from the variants map.
        self._canonical: dict[str, str] = {}
        for canonical, variants in config.name_variants.items():
            self._canonical[canonical] = canonical
            for v in variants:
                self._canonical[v] = canonical

    @classmethod
    def from_path(cls, path: Path) -> "IdentityMatcher":
        return cls(_load_config(str(path)))

    # -- signals ---------------------------------------------------------------

    def _canonicalise(self, name: str) -> str:
        tokens = _normalise(name).split()
        return " ".join(self._canonical.get(t, t) for t in tokens)

    def name_score(self, subject_name: str, candidate_name: str) -> float:
        a = self._canonicalise(subject_name)
        b = self._canonicalise(candidate_name)
        if not a or not b:
            return 0.0
        exact = fuzz.token_sort_ratio(a, b)
        # token_set_ratio tolerates extra tokens (middle names, titles) but is
        # more permissive, so blend rather than take it outright.
        loose = fuzz.token_set_ratio(a, b)
        return max(exact, 0.5 * exact + 0.5 * loose)

    @staticmethod
    def dob_score(subject_dob: str, candidate_dob: str) -> tuple[float, bool]:
        """Returns (score, mismatch). Handles partial DOBs like '1975' or '1975-03'."""
        s = subject_dob.strip()
        c = candidate_dob.strip()
        if not s or not c:
            return 0.0, False
        s_year, c_year = s[:4], c[:4]
        if s_year != c_year:
            return 0.0, True
        if len(c) >= 7 and len(s) >= 7:
            if s[:7] != c[:7]:
                return 0.0, True
            if len(c) >= 10 and len(s) >= 10:
                return (100.0, False) if s[:10] == c[:10] else (0.0, True)
            return 100.0, False  # year+month match, day unknown
        return 60.0, False  # year-only match

    @staticmethod
    def country_score(subject_country: str, candidate_location: str) -> float:
        subject_l = subject_country.lower().strip()
        location_l = candidate_location.lower()
        aliases = {
            "united kingdom": ["uk", "great britain", "england", "scotland", "wales",
                               "northern ireland", "united kingdom"],
            "united states": ["usa", "us", "united states", "america"],
        }
        candidates = aliases.get(subject_l, [subject_l])
        return 100.0 if any(alias in location_l for alias in candidates) else 0.0

    # -- overall ----------------------------------------------------------------

    def confidence(self, subject: SearchSubject, finding: Finding) -> float:
        """Weighted confidence percentage that `finding` refers to `subject`."""
        weights = self.config.weights
        signals: list[tuple[float, float]] = []  # (weight, score)
        dob_mismatch = False

        candidate_name = finding.subject_name or finding.title
        signals.append((weights.get("name", 0.55), self.name_score(subject.full_name,
                                                                   candidate_name)))

        if subject.date_of_birth and finding.date_of_birth:
            score, dob_mismatch = self.dob_score(subject.date_of_birth, finding.date_of_birth)
            if score == 100.0:
                score = float(self.config.scores.get("dob_exact", 100))
            elif score == 60.0:
                score = float(self.config.scores.get("dob_year_only", 60))
            signals.append((weights.get("date_of_birth", 0.25), score))

        if subject.country and finding.location:
            score = self.country_score(subject.country, finding.location)
            if score == 100.0:
                score = float(self.config.scores.get("country_match", 100))
            signals.append((weights.get("country", 0.20), score))

        total_weight = sum(w for w, _ in signals)
        if total_weight == 0:
            return 0.0
        confidence = sum(w * s for w, s in signals) / total_weight

        if dob_mismatch:
            confidence = min(confidence, self.config.dob_mismatch_cap)
        return round(confidence, 1)
