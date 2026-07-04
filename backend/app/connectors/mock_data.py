"""Deterministic fixture data for mock-connector mode.

Mock mode lets the entire pipeline run end-to-end with no external API keys.
The profile returned for a subject is deterministic (hash of the name), so the
same search always produces the same results — useful for demos and tests.

A given name lands in one of four demo risk profiles:
  0: clean          — only web/press mentions
  1: media          — adverse media coverage
  2: insolvency     — bankruptcy + directorships + media
  3: severe         — sanctions match + disqualification + serious media
"""

import hashlib

from app.connectors.base import Category, Finding, SearchSubject


def profile_for(subject: SearchSubject) -> int:
    digest = hashlib.sha256(subject.full_name.strip().lower().encode()).hexdigest()
    return int(digest, 16) % 4


def _country(subject: SearchSubject) -> str:
    return subject.country or "United Kingdom"


def google_mock(subject: SearchSubject) -> list[Finding]:
    name = subject.full_name
    findings = [
        Finding(
            source="google_search",
            category=Category.WEB,
            title=f"{name} — LinkedIn profile",
            description=f"Professional profile page for {name}.",
            url="https://www.linkedin.com/in/example",
            subject_name=name,
            location=_country(subject),
            raw={"mock": True},
        ),
        Finding(
            source="google_search",
            category=Category.WEB,
            title=f"{name} speaks at industry conference",
            description=f"{name} appeared as a panellist at a trade conference.",
            url="https://example.com/conference",
            date="2024-06-12",
            subject_name=name,
            raw={"mock": True},
        ),
    ]
    if profile_for(subject) >= 2:
        findings.append(
            Finding(
                source="google_search",
                category=Category.WEB,
                title=f"Court listing mentions {name}",
                description=f"A county court listing includes the name {name}.",
                url="https://example.com/court-listing",
                date="2023-11-02",
                subject_name=name,
                raw={"mock": True},
            )
        )
    return findings


def news_mock(subject: SearchSubject) -> list[Finding]:
    name = subject.full_name
    p = profile_for(subject)
    findings: list[Finding] = []
    if p >= 1:
        findings.append(
            Finding(
                source="news_api",
                category=Category.ADVERSE_MEDIA,
                title=f"Regulator scrutinises firm linked to {name}",
                description=(
                    f"Reports allege that a company associated with {name} is under "
                    "regulatory scrutiny. No charges have been brought."
                ),
                url="https://news.example.com/regulator-scrutiny",
                date="2024-03-18",
                subject_name=name,
                raw={"mock": True},
            )
        )
    if p == 3:
        findings.append(
            Finding(
                source="news_api",
                category=Category.ADVERSE_MEDIA,
                title=f"{name} investigated over alleged money laundering scheme",
                description=(
                    f"{name} is reported to be under investigation in connection with an "
                    "alleged money laundering scheme. The investigation is ongoing and no "
                    "verdict has been reached."
                ),
                url="https://news.example.com/aml-investigation",
                date="2024-09-30",
                subject_name=name,
                raw={"mock": True},
            )
        )
    return findings


def companies_house_mock(subject: SearchSubject) -> list[Finding]:
    name = subject.full_name
    p = profile_for(subject)
    findings = []
    if p >= 1:
        findings.append(
            Finding(
                source="companies_house",
                category=Category.DIRECTORSHIP,
                title=f"Director appointment — {name}",
                description=f"{name} is/was a director of Example Trading Ltd (active).",
                url="https://find-and-update.company-information.service.gov.uk/",
                date="2019-05-01",
                subject_name=name,
                location=_country(subject),
                date_of_birth=subject.date_of_birth,
                raw={"mock": True, "company": "Example Trading Ltd", "role": "director"},
            )
        )
    if p == 3:
        findings.append(
            Finding(
                source="companies_house",
                category=Category.DISQUALIFICATION,
                title=f"Director disqualification — {name}",
                description=(
                    f"{name} appears on the register of disqualified directors "
                    "(disqualified for 6 years)."
                ),
                url="https://find-and-update.company-information.service.gov.uk/",
                date="2022-01-15",
                subject_name=name,
                date_of_birth=subject.date_of_birth,
                raw={"mock": True},
            )
        )
    return findings


def insolvency_mock(subject: SearchSubject) -> list[Finding]:
    name = subject.full_name
    if profile_for(subject) >= 2:
        return [
            Finding(
                source="insolvency_register",
                category=Category.INSOLVENCY,
                title=f"Bankruptcy order — {name}",
                description=f"A bankruptcy order was recorded against {name}.",
                url="https://www.gov.uk/search-bankruptcy-insolvency-register",
                date="2021-08-20",
                subject_name=name,
                location=_country(subject),
                date_of_birth=subject.date_of_birth,
                raw={"mock": True, "order_type": "bankruptcy"},
            )
        ]
    return []


def sanctions_mock(subject: SearchSubject) -> list[Finding]:
    name = subject.full_name
    if profile_for(subject) == 3:
        return [
            Finding(
                source="uk_sanctions",
                category=Category.SANCTIONS,
                title=f"UK Sanctions List match — {name}",
                description=(
                    f"A name closely matching {name} appears on the UK Sanctions List "
                    "(asset freeze)."
                ),
                url="https://www.gov.uk/government/publications/the-uk-sanctions-list",
                date="2023-04-05",
                subject_name=name,
                date_of_birth=subject.date_of_birth,
                raw={"mock": True, "regime": "Global Anti-Corruption"},
            )
        ]
    return []


def fca_mock(subject: SearchSubject) -> list[Finding]:
    name = subject.full_name
    if profile_for(subject) >= 2:
        return [
            Finding(
                source="fca_warning_list",
                category=Category.REGULATORY,
                title=f"FCA warning — unauthorised firm linked to {name}",
                description=(
                    f"The FCA has issued a warning about an unauthorised firm associated "
                    f"with {name}."
                ),
                url="https://www.fca.org.uk/consumers/warning-list-unauthorised-firms",
                date="2023-02-10",
                subject_name=name,
                raw={"mock": True},
            )
        ]
    return []
