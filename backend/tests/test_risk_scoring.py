"""Unit tests for the Risk Scoring Engine."""

from app.config import get_settings
from app.connectors.base import Category, Finding
from app.services.risk_scoring import RiskScorer


def scorer() -> RiskScorer:
    return RiskScorer.from_path(get_settings().risk_config_path)


def make(category: str, title: str = "finding", description: str = "") -> Finding:
    return Finding(source="test", category=category, title=title, description=description)


def test_no_findings_is_low_risk():
    assessment = scorer().assess([])
    assert assessment.score == 0.0
    assert assessment.level == "low"
    assert assessment.factors == []


def test_sanctions_match_is_critical():
    assessment = scorer().assess([(make(Category.SANCTIONS), 95.0)])
    assert assessment.score >= 80
    assert assessment.level == "critical"


def test_confidence_scales_score():
    high = scorer().assess([(make(Category.INSOLVENCY), 100.0)])
    low = scorer().assess([(make(Category.INSOLVENCY), 50.0)])
    assert high.score == 2 * low.score


def test_below_threshold_findings_excluded():
    threshold = scorer().config.confidence_threshold
    assessment = scorer().assess([(make(Category.SANCTIONS), threshold - 1)])
    assert assessment.score == 0.0
    assert assessment.factors == []


def test_media_keyword_escalation():
    plain = make(Category.ADVERSE_MEDIA, title="Person criticised over parking dispute")
    serious = make(
        Category.ADVERSE_MEDIA,
        title="Person investigated over money laundering allegations",
    )
    plain_score = scorer().assess([(plain, 90.0)]).score
    serious_score = scorer().assess([(serious, 90.0)]).score
    assert serious_score > plain_score
    factors = scorer().assess([(serious, 90.0)]).factors
    assert factors[0]["escalated"] is True


def test_secondary_findings_add_less_than_primary():
    one = scorer().assess([(make(Category.INSOLVENCY), 100.0)])
    two = scorer().assess(
        [(make(Category.INSOLVENCY, "a"), 100.0), (make(Category.INSOLVENCY, "b"), 100.0)]
    )
    assert two.score > one.score
    assert two.score < 2 * one.score  # secondary factor < 1


def test_score_is_capped():
    findings = [(make(Category.SANCTIONS, f"f{i}"), 100.0) for i in range(10)]
    assessment = scorer().assess(findings)
    assert assessment.score <= scorer().config.cap


def test_level_thresholds():
    s = scorer()
    assert s.level_for(0) == "low"
    assert s.level_for(24.9) == "low"
    assert s.level_for(25) == "medium"
    assert s.level_for(50) == "high"
    assert s.level_for(80) == "critical"


def test_directorship_alone_is_low():
    assessment = scorer().assess([(make(Category.DIRECTORSHIP), 100.0)])
    assert assessment.level == "low"
