"""Date-of-birth evidence from unstructured text.

Most sources (web pages, news, court and police reports, Gazette notices) do
not hand back a structured date of birth, but formal records often print one
in the text: "Date of birth: 2 March 1975", "DOB 02/03/1975", "born on
1975-03-02". When the user supplied a DOB, this module reads the finding's
text and reports one of:

- ``exact``    — the subject's full DOB appears in the record: strong
                 corroboration that the record is about them
- ``year``     — a labelled birth year/month ("born in 1975") agrees
- ``age``      — a stated age ("John Smith, 49," / "aged 49") agrees with the
                 DOB at the record's date (court/police reporting style)
- ``conflict`` — a *labelled* DOB ("born on", "DOB", "date of birth")
                 disagrees: almost certainly a different person
- ``None``     — nothing usable in the text

Unlabelled dates that differ are ignored (they are usually event dates), and
a differing age is ignored too — it is weak evidence and the platform prefers
keeping a result to losing it.
"""

import re
from dataclasses import dataclass
from datetime import date

from app.services.keyword_screening import normalise_text

EXACT, YEAR, AGE, CONFLICT = "exact", "year", "age", "conflict"

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(\d{4})"

# Full-date formats, each yielding (kind, regex). UK numeric dates are
# day-first.
_DATE_PATTERNS: list[tuple[str, str]] = [
    ("ymd", rf"{_YEAR}[-/.](\d{{1,2}})[-/.](\d{{1,2}})"),
    ("dmy_num", rf"(\d{{1,2}})[-/.](\d{{1,2}})[-/.]{_YEAR}"),
    ("dmy_text", rf"{_DAY}\s+(?:of\s+)?({_MONTH_RE})\.?,?\s+{_YEAR}"),
    ("mdy_text", rf"({_MONTH_RE})\.?\s+{_DAY},?\s+{_YEAR}"),
]
_DATE_RE = re.compile(
    "|".join(f"(?P<{k}>{p})" for k, p in _DATE_PATTERNS)
)
_LABEL = r"(?<!\w)(?:date\s+of\s+birth|d\.?\s?o\.?\s?b\.?|birth\s+details|born(?:\s+on)?)\s*[:\-]?\s*"
_LABELLED_FULL_RE = re.compile(_LABEL + rf"(?:on\s+)?(?P<date>{_DATE_RE.pattern})")
_LABELLED_PARTIAL_RE = re.compile(
    _LABEL + rf"(?:in\s+)?(?:(?P<month>{_MONTH_RE})\.?,?\s+)?(?P<year>(?:19|20)\d{{2}})\b"
)
_AGED_RE = re.compile(r"\b(?:aged|age)\s+(\d{1,3})\b")


@dataclass
class DobEvidence:
    status: str | None
    detail: str | None = None


def _to_date(match: re.Match) -> date | None:
    groups = match.groupdict()
    try:
        if groups.get("ymd"):
            y, m, d = re.match(rf"{_YEAR}[-/.](\d{{1,2}})[-/.](\d{{1,2}})", groups["ymd"]).groups()
        elif groups.get("dmy_num"):
            d, m, y = re.match(rf"(\d{{1,2}})[-/.](\d{{1,2}})[-/.]{_YEAR}",
                               groups["dmy_num"]).groups()
        elif groups.get("dmy_text"):
            d, mon, y = re.match(rf"{_DAY}\s+(?:of\s+)?({_MONTH_RE})\.?,?\s+{_YEAR}",
                                 groups["dmy_text"]).groups()
            m = _MONTHS[mon]
        elif groups.get("mdy_text"):
            mon, d, y = re.match(rf"({_MONTH_RE})\.?\s+{_DAY},?\s+{_YEAR}",
                                 groups["mdy_text"]).groups()
            m = _MONTHS[mon]
        else:
            return None
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError, KeyError):
        return None


def extract_dates(text: str) -> list[date]:
    """Every full calendar date written in `text`."""
    normalised = normalise_text(text)
    return [d for m in _DATE_RE.finditer(normalised) if (d := _to_date(m))]


def _parse_dob(dob: str) -> date | None:
    try:
        return date.fromisoformat(dob.strip()[:10])
    except ValueError:
        return None


def _age_on(dob: date, when: date) -> int:
    return when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))


def _stated_ages(text: str, subject_name: str | None) -> list[int]:
    ages = [int(a) for a in _AGED_RE.findall(text)]
    if subject_name:
        # Court/police reporting style: "John Smith, 49, of Leeds".
        from app.connectors.web_common import _name_pattern, normalise_for_names

        pattern = _name_pattern(subject_name)
        if pattern:
            named = normalise_for_names(text)
            for m in pattern.finditer(named):
                after = re.match(r"\s*,\s*(\d{1,3})\b", named[m.end():])
                if after:
                    ages.append(int(after.group(1)))
    return [a for a in ages if 0 < a < 120]


def assess(
    text: str,
    subject_dob: str,
    *,
    record_date: str | None = None,
    subject_name: str | None = None,
) -> DobEvidence:
    """Compare the DOB the user supplied against what `text` says."""
    dob = _parse_dob(subject_dob)
    if dob is None or not text:
        return DobEvidence(None)
    normalised = normalise_text(text)

    # 1. The full DOB written anywhere in the record.
    if dob in extract_dates(normalised):
        return DobEvidence(EXACT, f"date of birth {dob.isoformat()} appears in the record")

    # 2. A labelled DOB that disagrees -> a different person.
    for m in _LABELLED_FULL_RE.finditer(normalised):
        stated = _to_date(_DATE_RE.match(m.group("date")))
        if stated and stated != dob:
            return DobEvidence(CONFLICT, f"record gives date of birth {stated.isoformat()}")

    # 3. A labelled partial DOB ("born in March 1975" / "born 1975").
    for m in _LABELLED_PARTIAL_RE.finditer(normalised):
        year = int(m.group("year"))
        month = _MONTHS.get(m.group("month") or "")
        if year != dob.year or (month and month != dob.month):
            return DobEvidence(CONFLICT, f"record says '{m.group(0).strip()}'")
        return DobEvidence(YEAR, f"record says '{m.group(0).strip()}'")

    # 4. A stated age consistent with the DOB at the record's date.
    when = _parse_dob(record_date) if record_date else None
    if when:
        expected = _age_on(dob, when)
        for age in _stated_ages(normalised, subject_name):
            if abs(age - expected) <= 1:
                return DobEvidence(AGE, f"stated age {age} matches date of birth")

    return DobEvidence(None)
