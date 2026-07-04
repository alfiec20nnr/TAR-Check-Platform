"""Report generator and AI-fallback summary tests."""

import re

from app.config import Settings
from app.connectors.base import Category, Finding, SearchSubject
from app.services import report_generator
from app.services.ai_summary import AiSummariser, fallback_summary

SUBJECT = SearchSubject(full_name="Jane Doe", country="United Kingdom")


def sample_report() -> dict:
    return report_generator.build_report_content(
        reference="AIP-20260704-ABC123",
        subject={"full_name": "Jane Doe", "date_of_birth": None, "country": "United Kingdom"},
        risk={"score": 66.5, "level": "high", "factors": [
            {"title": "Bankruptcy order", "category": "insolvency", "source": "insolvency_register",
             "confidence": 95.0, "base_weight": 70, "weighted_score": 66.5, "escalated": False},
        ]},
        ai={"is_fallback": True, "model": "template-fallback", "content": fallback_summary(
            SUBJECT,
            [(Finding(source="insolvency_register", category=Category.INSOLVENCY,
                      title="Bankruptcy order", date="2021-08-20"), 95.0)],
        )},
        results=[{"source_name": "insolvency_register", "category": "insolvency",
                  "title": "Bankruptcy order", "description": "desc",
                  "url": "https://example.com", "event_date": "2021-08-20",
                  "confidence": 95.0}],
        sources_searched=["insolvency_register"],
        connector_stats=[{"connector": "insolvency_register", "status": "success",
                          "findings": 1, "duration_ms": 12}],
        duration_ms=1200,
    )


def test_reference_format():
    ref = report_generator.make_reference()
    assert re.fullmatch(r"AIP-\d{8}-[0-9A-F]{6}", ref)


def test_report_json_contains_required_sections():
    report = sample_report()
    for key in ("reference", "generated_at", "subject", "risk", "ai", "results",
                "sources_searched", "connector_stats"):
        assert key in report


def test_html_render_includes_key_content():
    report = sample_report()
    html = report_generator.render_html(report)
    assert "AIP-20260704-ABC123" in html
    assert "Jane Doe" in html
    assert "Bankruptcy order" in html
    assert "HIGH" in html
    assert "Executive Summary" in html
    # AI-generated vs verified records must be visibly separated.
    assert "non-AI" in html or "AI-generated" in html


async def test_summariser_falls_back_without_api_key():
    summariser = AiSummariser(Settings(anthropic_api_key=""))
    result = await summariser.summarise(SUBJECT, [])
    assert result.is_fallback is True
    assert result.model == "template-fallback"
    assert "executive_summary" in result.content


def test_fallback_summary_flags_adverse_findings():
    findings = [
        (Finding(source="uk_sanctions", category=Category.SANCTIONS,
                 title="Sanctions match", date="2023-04-05"), 92.0),
        (Finding(source="google_search", category=Category.WEB,
                 title="Conference talk"), 90.0),
    ]
    content = fallback_summary(SUBJECT, findings)
    assert len(content["key_concerns"]) == 1
    assert "Sanctions match" in content["key_concerns"][0]
    assert content["timeline"][0]["date"] == "2023-04-05"
    assert content["recommendations"]


def test_fallback_summary_clean_subject():
    content = fallback_summary(SUBJECT, [])
    assert "No adverse findings" in content["executive_summary"]
    assert content["key_concerns"] == []
