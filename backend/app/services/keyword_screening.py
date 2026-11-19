"""Adverse-keyword screening.

Every finding from every source is screened against one shared, deliberately
broad keyword list (config/adverse_keywords.yaml). Screening never discards a
finding — it is better to surface an irrelevant result than to lose a
valuable one. A hit:

- records the matched terms on the finding (``raw["flagged_terms"]``) so the
  UI and report can show *why* a result was flagged,
- re-categorises neutral web / social-media results as adverse media, and
- supplies the tier weight the risk scorer uses to escalate media findings.
"""

import functools
import html
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.connectors.base import Category, Finding

# Neutral categories that become adverse media when a keyword is found.
RECATEGORISE = {Category.WEB, Category.SOCIAL_MEDIA}


@dataclass(frozen=True)
class _Term:
    term: str
    tier: str
    group: str
    weight: float
    pattern: re.Pattern[str]


@dataclass
class KeywordHits:
    terms: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    tier: str | None = None  # highest-weighted tier matched
    weight: float = 0.0

    def __bool__(self) -> bool:
        return bool(self.terms)


def normalise_text(text: str) -> str:
    """Lowercase, strip HTML tags (search APIs wrap hits in <strong>) and
    accents, collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace("’", "'").split())


def _compile(term: str) -> re.Pattern[str]:
    raw = term.strip().lower()
    wildcard = raw.endswith("*")
    words = raw.rstrip("*").split()
    body = r"[\s-]+".join(re.escape(w) for w in words)
    # "*" = any word ending; otherwise allow a simple plural only.
    ending = r"[\w'-]*" if wildcard else r"(?:s|es)?"
    return re.compile(rf"(?<![\w-]){body}{ending}(?![\w])")


class KeywordScreener:
    def __init__(self, terms: list[_Term]):
        self._terms = terms

    @classmethod
    def from_path(cls, path: Path) -> "KeywordScreener":
        return _load(str(path))

    @property
    def term_count(self) -> int:
        return len(self._terms)

    def screen(self, text: str) -> KeywordHits:
        normalised = normalise_text(text)
        hits = KeywordHits()
        if not normalised:
            return hits
        for t in self._terms:
            match = t.pattern.search(normalised)
            if not match:
                continue
            # Report the word as it appears ("fraudulent"), not the pattern.
            word = match.group(0)
            if word not in hits.terms:
                hits.terms.append(word)
            if t.group not in hits.groups:
                hits.groups.append(t.group)
            if t.weight > hits.weight:
                hits.weight, hits.tier = t.weight, t.tier
        return hits

    def screen_finding(self, finding: Finding) -> KeywordHits:
        return self.screen(f"{finding.title} {finding.description or ''}")

    def flag(self, finding: Finding) -> KeywordHits:
        """Annotate `finding` in place with its keyword hits (never removes it)."""
        hits = self.screen_finding(finding)
        if hits:
            finding.raw = {
                **(finding.raw or {}),
                "flagged_terms": hits.terms,
                "flagged_groups": hits.groups,
                "flag_tier": hits.tier,
            }
            if finding.category in RECATEGORISE:
                finding.category = Category.ADVERSE_MEDIA
        return hits


@functools.lru_cache(maxsize=4)
def _load(path_str: str) -> KeywordScreener:
    data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8")) or {}
    terms: list[_Term] = []
    seen: dict[str, int] = {}
    for tier_name, tier in (data.get("tiers") or {}).items():
        weight = float(tier.get("weight", 20))
        for group, words in (tier.get("groups") or {}).items():
            for word in words or []:
                key = str(word).strip().lower()
                if not key:
                    continue
                entry = _Term(key, tier_name, group, weight, _compile(key))
                # A term listed in several tiers keeps its highest weight.
                if key in seen:
                    if terms[seen[key]].weight >= weight:
                        continue
                    terms[seen[key]] = entry
                    continue
                seen[key] = len(terms)
                terms.append(entry)
    # Check the most severe terms first so `tier` reflects the worst hit.
    terms.sort(key=lambda t: -t.weight)
    return KeywordScreener(terms)


def default_screener() -> KeywordScreener:
    from app.config import get_settings

    return KeywordScreener.from_path(get_settings().adverse_keywords_path)
