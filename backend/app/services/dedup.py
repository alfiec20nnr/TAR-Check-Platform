"""Duplicate removal across connector results.

Two findings are considered duplicates when they share a URL, or when they
share a category and have near-identical titles.
"""

from rapidfuzz import fuzz

from app.connectors.base import Finding

_TITLE_THRESHOLD = 92


def deduplicate(findings: list[Finding]) -> list[Finding]:
    kept: list[Finding] = []
    seen_urls: set[str] = set()
    for finding in findings:
        url = (finding.url or "").strip().rstrip("/")
        if url and url in seen_urls:
            continue
        is_dup = False
        for existing in kept:
            if existing.category != finding.category:
                continue
            if fuzz.token_sort_ratio(existing.title.lower(),
                                     finding.title.lower()) >= _TITLE_THRESHOLD:
                is_dup = True
                break
        if is_dup:
            continue
        if url:
            seen_urls.add(url)
        kept.append(finding)
    return kept
