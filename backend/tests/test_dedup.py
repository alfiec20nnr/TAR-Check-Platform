"""Unit tests for duplicate removal."""

from app.connectors.base import Category, Finding
from app.services.dedup import deduplicate


def make(title: str, url: str | None = None, category: str = Category.WEB) -> Finding:
    return Finding(source="test", category=category, title=title, url=url)


def test_same_url_is_deduplicated():
    findings = [
        make("Article A", url="https://example.com/a"),
        make("Completely different title", url="https://example.com/a/"),
    ]
    assert len(deduplicate(findings)) == 1


def test_near_identical_titles_same_category_deduplicated():
    findings = [
        make("John Smith investigated over fraud"),
        make("John Smith investigated over fraud!"),
    ]
    assert len(deduplicate(findings)) == 1


def test_same_title_different_category_kept():
    findings = [
        make("John Smith record", category=Category.WEB),
        make("John Smith record", category=Category.INSOLVENCY),
    ]
    assert len(deduplicate(findings)) == 2


def test_distinct_findings_kept():
    findings = [
        make("Bankruptcy order", url="https://example.com/1"),
        make("Conference appearance", url="https://example.com/2"),
    ]
    assert len(deduplicate(findings)) == 2
