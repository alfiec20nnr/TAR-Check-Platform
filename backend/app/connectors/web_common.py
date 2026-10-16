"""Shared logic for web-search connectors (Google, Brave, future providers).

Web results are unstructured mentions, not attributed records, so every
provider applies the same rules:

- results must actually name the subject (mention filter): the forename and
  surname must appear together as a name — "John Smith", "John A. Smith",
  "John Paul Smith" or "Smith, John" — not merely somewhere in the text
  ("John Brown met Sarah Smith" is discarded)
- results containing adverse terms are categorised as adverse media so the
  risk scorer's keyword escalation applies; everything else stays in the
  low-weight web category
- ``subject_name`` is never set — identity matching treats web results as
  unstructured mentions with a low confidence ceiling
"""

import functools
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from app.connectors.base import Category
from app.connectors.name_variants import expand_full_name

# Up to this many middle names/initials may sit between forename and surname
# ("John Paul Smith", "John A. B. Smith") and still count as the subject.
_MAX_MIDDLE_TOKENS = 2

# Terms that mark a result as adverse media rather than a neutral web mention.
# Aligned with (a superset of) the serious keywords in config/risk_weights.yaml,
# which the risk scorer uses for escalation.
ADVERSE_TERMS = [
    "fraud", "money laundering", "bribery", "corruption", "embezzlement",
    "terrorism", "trafficking", "sanctions violation", "insider trading",
    "tax evasion", "convicted", "conviction", "charged", "arrested",
    "investigation", "lawsuit", "tribunal", "misconduct", "scandal",
    "allegations", "banned", "disqualified", "fined", "penalty",
    # Deceptive conduct and personal misconduct terms:
    "liar", "lied", "lying", "deceit", "deceiv", "deception",
    "manipulat", "scam", "exploit", "abuse", "victim",
    "false claim", "fake",
]

# The OR-query sent to the provider alongside the plain name query — the
# standard adverse-media screening query.
ADVERSE_QUERY_TERMS = (
    'fraud OR corruption OR "money laundering" OR convicted OR lawsuit '
    "OR scandal OR investigation OR misconduct OR fined "
    'OR liar OR deception OR scam OR abuse OR "false claim"'
)

# Personal-conduct terms used by the social-media connector on top of the
# financial-crime vocabulary above. Stems ("extremis", "misogyn") match all
# their inflections via substring comparison.
CONDUCT_TERMS = [
    "racist", "racism", "hate speech", "harassment", "abusive", "threat",
    "violence", "violent", "assault", "extremis", "slur", "misogyn",
    "homophob", "offensive", "bullying", "doxx", "drugs",
]


def query_names(full_name: str, matching_config_path: Path) -> list[str]:
    """The name forms to query with: the name as given, plus nickname/variant
    forms (e.g. "William Smith" -> also "Bill Smith", "Will Smith") so a
    source that only ever uses a nickname is still found."""
    return [full_name, *expand_full_name(full_name, matching_config_path)]


def _normalise_text(text: str) -> str:
    """Lowercase, strip HTML tags (Brave wraps hits in <strong>) and accents,
    and reduce punctuation to spaces — keeping the commas, apostrophes,
    hyphens and full stops that name forms rely on."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s,'.-]", " ", text.lower())
    return " ".join(text.split())


@functools.lru_cache(maxsize=64)
def _name_pattern(subject_name: str) -> re.Pattern[str] | None:
    tokens = [re.escape(t.strip(".,")) for t in _normalise_text(subject_name).split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return None
    # Name boundaries: not inside another word, and not the first half of a
    # hyphenated double-barrelled name ("Smith-Jones" is someone else).
    start, end = r"(?<![\w-])", r"(?![\w]|-\w)"
    if len(tokens) == 1:
        return re.compile(start + tokens[0] + end)
    first, last = tokens[0], tokens[-1]
    middle = r"\s+(?:[\w'.-]+\s+){0," + str(_MAX_MIDDLE_TOKENS) + "}"
    forward = start + first + middle + last + end  # John (Paul) Smith
    reverse = start + last + r"\s*,\s*" + first + end  # Smith, John
    return re.compile(f"{forward}|{reverse}")


def mentions_subject(subject_name: str, text: str) -> bool:
    """Whether `text` names the subject — forename and surname together as a
    name, not just both words appearing somewhere. Results that fail this are
    about someone else (or no one) and are discarded."""
    pattern = _name_pattern(subject_name)
    return bool(pattern and pattern.search(_normalise_text(text)))


def on_site(url: str, site: str) -> bool:
    """Whether `url` is hosted on `site` or one of its subdomains."""
    host = (urlparse(url).netloc or "").lower()
    return host == site or host.endswith("." + site)


def parse_sites(value: str) -> list[str]:
    """A comma-separated hostname setting as a clean list."""
    return [s.strip().lower() for s in value.split(",") if s.strip()]


def categorise(
    text: str,
    default: str = Category.WEB,
    extra_terms: list[str] | None = None,
) -> str:
    lowered = text.lower()
    terms = ADVERSE_TERMS if extra_terms is None else ADVERSE_TERMS + extra_terms
    if any(term in lowered for term in terms):
        return Category.ADVERSE_MEDIA
    return default
