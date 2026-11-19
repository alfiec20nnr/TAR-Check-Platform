"""Tests for adverse-keyword screening and DOB evidence in record text."""

from app.config import get_settings
from app.connectors.base import Category, Finding, SearchSubject
from app.services import dob_evidence
from app.services.identity_matching import IdentityMatcher
from app.services.keyword_screening import KeywordScreener
from app.services.risk_scoring import RiskScorer


def screener() -> KeywordScreener:
    return KeywordScreener.from_path(get_settings().adverse_keywords_path)


def test_list_is_large():
    assert screener().term_count >= 300


def test_matches_words_and_word_endings():
    hits = screener().screen("John Smith jailed for drug-dealing and fraudulent claims")
    assert {"jailed", "fraudulent", "drug-dealing"} <= set(hits.terms)
    assert hits.tier == "serious"
    assert hits.weight == 60


def test_whole_words_only():
    # "ban" must not match "bank"/"urban"; "rape" must not match "rapeseed".
    assert not screener().screen("Smith opens urban bank branch selling rapeseed oil")


def test_strips_html_and_matches_hyphenated_phrases():
    hits = screener().screen("<strong>Smith</strong> admits drink-driving")
    assert "drink-driving" in hits.terms


def test_general_tier():
    hits = screener().screen("Smith faces employment tribunal claim")
    assert hits.tier == "general"


def test_flag_annotates_and_recategorises_without_discarding():
    s = screener()
    web = Finding(source="brave_search", category=Category.WEB, title="Smith charged with theft")
    assert s.flag(web)
    assert web.category == Category.ADVERSE_MEDIA
    assert "theft" in web.raw["flagged_terms"]
    # Structured records keep their category but are still flagged.
    insolvency = Finding(source="x", category=Category.INSOLVENCY, title="Bankruptcy order")
    s.flag(insolvency)
    assert insolvency.category == Category.INSOLVENCY
    assert insolvency.raw["flagged_terms"]
    neutral = Finding(source="x", category=Category.WEB, title="Smith joins charity board")
    assert not s.flag(neutral)
    assert neutral.category == Category.WEB


def test_risk_escalates_web_findings_by_tier():
    scorer = RiskScorer.from_path(get_settings().risk_config_path)
    drugs = Finding(source="x", category=Category.WEB, title="Smith convicted of cocaine supply")
    neutral = Finding(source="x", category=Category.WEB, title="Smith opens bakery")
    assert scorer.per_finding_contribution(drugs, 100) == 60
    assert scorer.per_finding_contribution(neutral, 100) == 5


# -- date of birth in record text --------------------------------------------

DOB = "1975-03-02"


def test_dob_formats_found():
    for text in [
        "Date of Birth: 2 March 1975",
        "DOB 02/03/1975",
        "born on 1975-03-02",
        "born 2nd of March, 1975",
        "born March 2, 1975",
    ]:
        assert dob_evidence.assess(text, DOB).status == dob_evidence.EXACT, text


def test_labelled_different_dob_is_conflict():
    conflict = dob_evidence.CONFLICT
    assert dob_evidence.assess("John Smith, born 4 June 1980", DOB).status == conflict
    assert dob_evidence.assess("John Smith (born 1980)", DOB).status == conflict


def test_unlabelled_other_dates_are_ignored():
    assert dob_evidence.assess("Hearing held on 4 June 2021", DOB).status is None


def test_stated_age_consistent_with_dob():
    ev = dob_evidence.assess(
        "John Smith, 49, of Leeds was jailed",
        DOB,
        record_date="2024-06-01",
        subject_name="John Smith",
    )
    assert ev.status == dob_evidence.AGE
    # A different age is not held against the record.
    other = dob_evidence.assess(
        "John Smith, 23, of Leeds", DOB, record_date="2024-06-01", subject_name="John Smith"
    )
    assert other.status is None


def test_dob_in_text_lifts_confidence_and_conflict_discards():
    m = IdentityMatcher.from_path(get_settings().matching_config_path)
    subject = SearchSubject(full_name="John Smith", date_of_birth=DOB)
    plain = Finding(source="x", category=Category.WEB, title="John Smith sentenced")
    verified = Finding(
        source="x",
        category=Category.WEB,
        title="John Smith sentenced",
        description="John Smith, date of birth 02/03/1975",
    )
    other = Finding(
        source="x",
        category=Category.WEB,
        title="John Smith sentenced",
        description="John Smith, DOB 04/06/1980",
    )
    assert m.confidence(subject, plain) <= m.config.mention_cap
    assert m.confidence(subject, verified) > m.config.mention_cap
    assert not m.is_subject(m.confidence(subject, other))
