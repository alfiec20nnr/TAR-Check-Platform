"""Unit tests for the Identity Matching Engine."""

from app.config import get_settings
from app.connectors.base import Category, Finding, SearchSubject
from app.services.identity_matching import IdentityMatcher


def matcher() -> IdentityMatcher:
    return IdentityMatcher.from_path(get_settings().matching_config_path)


def make_finding(**kwargs) -> Finding:
    defaults = dict(source="test", category=Category.WEB, title="t")
    defaults.update(kwargs)
    return Finding(**defaults)


def test_exact_name_high_confidence():
    m = matcher()
    subject = SearchSubject(full_name="John Andrew Smith")
    f = make_finding(subject_name="John Andrew Smith")
    assert m.confidence(subject, f) >= 95


def test_name_variant_recognised():
    m = matcher()
    # Bill is a variant of William — should score far higher than a random name.
    variant = m.name_score("William Turner", "Bill Turner")
    unrelated = m.name_score("William Turner", "Sarah Jenkins")
    assert variant >= 95
    assert unrelated < 50


def test_token_order_irrelevant():
    m = matcher()
    assert m.name_score("Smith John", "John Smith") == 100


def test_dob_exact_match_boosts_confidence():
    m = matcher()
    subject = SearchSubject(full_name="Jane Doe", date_of_birth="1980-04-12")
    with_dob = make_finding(subject_name="Jane Doe", date_of_birth="1980-04-12")
    without_dob = make_finding(subject_name="Jane Do")  # slightly off name
    assert m.confidence(subject, with_dob) > m.confidence(subject, without_dob)
    assert m.confidence(subject, with_dob) >= 95


def test_dob_mismatch_caps_confidence():
    m = matcher()
    subject = SearchSubject(full_name="Jane Doe", date_of_birth="1980-04-12")
    f = make_finding(subject_name="Jane Doe", date_of_birth="1969-01-01")
    assert m.confidence(subject, f) <= m.config.dob_mismatch_cap


def test_dob_partial_year_only():
    m = matcher()
    score, mismatch = m.dob_score("1980-04-12", "1980")
    assert score == 60.0
    assert mismatch is False


def test_dob_year_month_match():
    m = matcher()
    score, mismatch = m.dob_score("1980-04-12", "1980-04")
    assert score == 100.0
    assert mismatch is False


def test_country_alias_matching():
    m = matcher()
    assert m.country_score("United Kingdom", "London, England") == 100.0
    assert m.country_score("United Kingdom", "Paris, France") == 0.0


def test_country_contributes_to_confidence():
    m = matcher()
    subject = SearchSubject(full_name="Jane Doe", country="United Kingdom")
    matching = make_finding(subject_name="Jane Doe", location="Manchester, UK")
    mismatching = make_finding(subject_name="Jane Doe", location="Sydney, Australia")
    assert m.confidence(subject, matching) > m.confidence(subject, mismatching)


def test_missing_signals_are_neutral():
    """A record with no DOB/location is scored on name alone, not penalised to 0."""
    m = matcher()
    subject = SearchSubject(
        full_name="Jane Doe", date_of_birth="1980-04-12", country="United Kingdom"
    )
    f = make_finding(subject_name="Jane Doe")
    assert m.confidence(subject, f) >= 95
