"""Risk Scoring Engine.

Applies configurable weightings (config/risk_weights.yaml) to matched findings
and produces an overall 0-100 score plus a Low/Medium/High/Critical level.
"""

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.connectors.base import Finding
from app.services.keyword_screening import KeywordScreener, default_screener


@dataclass
class ScoredFinding:
    finding: Finding
    confidence: float
    base_weight: float
    weighted_score: float
    escalated: bool = False


@dataclass
class RiskAssessment:
    score: float
    level: str
    factors: list[dict]


@dataclass
class RiskConfig:
    categories: dict[str, float]
    escalate_categories: set[str]
    confidence_threshold: float
    secondary_factor: float
    cap: float
    thresholds: dict[str, float]

    @classmethod
    def load(cls, path: Path) -> "RiskConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        agg = data.get("aggregation", {})
        return cls(
            categories=data.get("categories", {}),
            escalate_categories=set(
                data.get("keyword_escalation_categories", ["adverse_media", "web",
                                                           "social_media"])
            ),
            confidence_threshold=float(data.get("confidence_threshold", 40)),
            secondary_factor=float(agg.get("secondary_factor", 0.25)),
            cap=float(agg.get("cap", 100)),
            thresholds=data.get("thresholds", {"low": 0, "medium": 25, "high": 50,
                                               "critical": 80}),
        )


@functools.lru_cache(maxsize=4)
def _load_config(path_str: str) -> RiskConfig:
    return RiskConfig.load(Path(path_str))


class RiskScorer:
    def __init__(self, config: RiskConfig, screener: KeywordScreener | None = None):
        self.config = config
        self.screener = screener or default_screener()

    @classmethod
    def from_path(cls, path: Path, keywords_path: Path | None = None) -> "RiskScorer":
        screener = KeywordScreener.from_path(keywords_path) if keywords_path else None
        return cls(_load_config(str(path)), screener)

    def _weight_for(self, finding: Finding) -> tuple[float, bool]:
        """Base severity weight for a finding, escalated for media-type findings
        by the tier of the worst adverse keyword they contain
        (config/adverse_keywords.yaml). Structured records (sanctions,
        insolvency, …) keep their calibrated category weight."""
        weight = float(self.config.categories.get(finding.category, 5))
        escalated = False
        if finding.category in self.config.escalate_categories:
            hits = self.screener.screen_finding(finding)
            if hits and hits.weight > weight:
                weight, escalated = hits.weight, True
        return weight, escalated

    def assess(self, findings_with_confidence: list[tuple[Finding, float]]) -> RiskAssessment:
        scored: list[ScoredFinding] = []
        for finding, confidence in findings_with_confidence:
            if confidence < self.config.confidence_threshold:
                continue
            weight, escalated = self._weight_for(finding)
            scored.append(
                ScoredFinding(
                    finding=finding,
                    confidence=confidence,
                    base_weight=weight,
                    weighted_score=weight * confidence / 100.0,
                    escalated=escalated,
                )
            )

        if not scored:
            return RiskAssessment(score=0.0, level="low", factors=[])

        scored.sort(key=lambda s: s.weighted_score, reverse=True)
        primary, rest = scored[0], scored[1:]
        score = primary.weighted_score + self.config.secondary_factor * sum(
            s.weighted_score for s in rest
        )
        score = round(min(score, self.config.cap), 1)

        factors = [
            {
                "title": s.finding.title,
                "category": s.finding.category,
                "source": s.finding.source,
                "confidence": s.confidence,
                "base_weight": s.base_weight,
                "weighted_score": round(s.weighted_score, 1),
                "escalated": s.escalated,
            }
            for s in scored
        ]
        return RiskAssessment(score=score, level=self.level_for(score), factors=factors)

    def level_for(self, score: float) -> str:
        thresholds = self.config.thresholds
        level = "low"
        for name in ("low", "medium", "high", "critical"):
            if score >= float(thresholds.get(name, 999)):
                level = name
        return level

    def per_finding_contribution(self, finding: Finding, confidence: float) -> float:
        """Standalone weighted score for a single finding (stored per result)."""
        if confidence < self.config.confidence_threshold:
            return 0.0
        weight, _ = self._weight_for(finding)
        return round(weight * confidence / 100.0, 1)
