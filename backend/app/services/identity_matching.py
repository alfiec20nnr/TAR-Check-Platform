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
    name_only_cap: float
    mention_cap: float
    name_conflict_cap: float
    name_variants: dict[str, list[str]]

    @classmethod
    def load(cls, path: Path) -> "MatchingConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        caps = data.get("caps", {})
        return cls(
            weights=data.get("weights", {}),
            scores=data.get("scores", {}),
            dob_mismatch_cap=float(data.get("dob_mismatch_cap", 30)),
            name_only_cap=float(caps.get("name_only", 72)),
            mention_cap=float(caps.get("unstructured_mention", 55)),
            name_conflict_cap=float(caps.get("name_conflict", 35)),
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

    @staticmethod
    def _token_covered(token: str, others: list[str]) -> bool:
        """Whether a name token has a plausible counterpart in the other name
        (equal, close spelling variant, or initial)."""
        for other in others:
            if token == other:
                return True
            if len(token) == 1 and other.startswith(token):
                return True
            if len(other) == 1 and token.startswith(other):
                return True
            if fuzz.ratio(token, other) >= 75:
                return True
        return False

    def name_score(self, subject_name: str, candidate_name: str) -> float:
        a = self._canonicalise(subject_name)
        b = self._canonicalise(candidate_name)
        if not a or not b:
            return 0.0
        a_tokens, b_tokens = a.split(), b.split()
        score = float(fuzz.token_sort_ratio(a, b))
        if len(a_tokens) >= 2 and len(b_tokens) >= 2:
            # token_set_ratio tolerates extra tokens (middle names, titles) but
            # is more permissive, so blend rather than take it outright — and
            # never use it against single-token names, which it would match
            # trivially.
            loose = fuzz.token_set_ratio(a, b)
            score = max(score, 0.5 * score + 0.5 * loose)
        # A true conflict is when BOTH names carry a part the other lacks
        # ("Philip Green" vs "Terry Green") — almost certainly two different
        # people, so cap below the risk-scoring threshold. One name merely
        # omitting a middle name ("Philip Nigel Green" vs "Philip Green") is
        # not a conflict.
        subject_uncovered = any(not self._token_covered(t, b_tokens) for t in a_tokens)
        candidate_uncovered = any(not self._token_covered(t, a_tokens) for t in b_tokens)
        if subject_uncovered and candidate_uncovered:
            score = min(score, self.config.name_conflict_cap)
        return score

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

    def mention_score(self, subject_name: str, finding: Finding) -> float:
        """Name evidence for a record with no structured subject name.

        Checks whether the subject's name actually appears in the record's
        title/description. This is weaker evidence than a source-attributed
        name, so callers cap it at `unstructured_mention`.
        """
        text = self._canonicalise(f"{finding.title} {finding.description or ''}")
        target = self._canonicalise(subject_name)
        if not target or not text:
            return 0.0
        # token_set_ratio scores 100 when every name token appears in the text
        # and stays low otherwise; partial_ratio is too noisy for short names.
        return float(fuzz.token_set_ratio(target, text))

    # -- overall ----------------------------------------------------------------

    def confidence(self, subject: SearchSubject, finding: Finding) -> float:
        """Weighted confidence percentage that `finding` refers to `subject`."""
        weights = self.config.weights
        signals: list[tuple[float, float]] = []  # (weight, score)
        dob_mismatch = False

        # Name evidence tier: a name attributed by the source is a real signal;
        # a bare mention in unstructured text is much weaker.
        if finding.subject_name:
            name_evidence = self.name_score(subject.full_name, finding.subject_name)
        else:
            name_evidence = self.mention_score(subject.full_name, finding)
        signals.append((weights.get("name", 0.55), name_evidence))

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

        # Uncorroborated matches are capped: a name alone (however similar)
        # never proves identity, and a mere text mention proves even less.
        corroborated = len(signals) > 1
        if not corroborated:
            confidence = min(confidence, self.config.name_only_cap)
        if not finding.subject_name:
            confidence = min(confidence, self.config.mention_cap)
        if dob_mismatch:
            confidence = min(confidence, self.config.dob_mismatch_cap)
        return round(confidence, 1)
