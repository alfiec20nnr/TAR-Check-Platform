"""Shared logic for web-search connectors (Google, Brave, future providers).

Web results are unstructured mentions, not attributed records, so every
provider applies the same rules:

- results must actually name the subject (mention filter): the forename and
  surname must appear together as a name — "John Smith", "John A. Smith",
  "John Paul Smith" or "Smith, John" — not merely somewhere in the text
  ("John Brown met Sarah Smith" is discarded)
- results containing any term from the shared adverse-keyword list
  (config/adverse_keywords.yaml) are categorised as adverse media so the risk
  scorer's keyword escalation applies; everything else stays in the
  low-weight web category
- ``subject_name`` is never set — identity matching treats web results as
  unstructured mentions with a low confidence ceiling
"""

import functools
import html
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from app.connectors.base import Category
from app.connectors.name_variants import expand_full_name

# Up to this many middle names/initials may sit between forename and surname
# ("John Paul Smith", "John A. B. Smith") and still count as the subject.
_MAX_MIDDLE_TOKENS = 2

# The OR-query sent to the provider alongside the plain name query — the
# standard adverse-media screening query.
ADVERSE_QUERY_TERMS = (
    'fraud OR corruption OR "money laundering" OR convicted OR lawsuit '
    "OR scandal OR investigation OR misconduct OR fined "
    'OR liar OR deception OR scam OR abuse OR "false claim"'
)

def query_names(full_name: str, matching_config_path: Path) -> list[str]:
    """The name forms to query with: the name as given, plus nickname/variant
    forms (e.g. "William Smith" -> also "Bill Smith", "Will Smith") so a
    source that only ever uses a nickname is still found."""
    return [full_name, *expand_full_name(full_name, matching_config_path)]


def clean_snippet(text: str) -> str:
    """Search-API snippet as plain text: decode HTML entities (Brave sends
    O'Neill as "O&#x27;Neill") and drop markup (it wraps hits in <strong>)."""
    text = re.sub(r"<[^>]+>", "", html.unescape(text or ""))
    return " ".join(html.unescape(text).split())


def _normalise_text(text: str) -> str:
    """Lowercase, strip HTML tags (Brave wraps hits in <strong>) and accents,
    and reduce punctuation to spaces — keeping the commas, apostrophes,
    hyphens and full stops that name forms rely on."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s,'.-]", " ", text.lower().replace("’", "'"))
    return " ".join(text.split())


# Irish/Scottish surname prefixes written several ways: O'Neill, O Neill,
# O-Neill, O’Neill, ONeill (and Mc). Joined into one word so they compare
# equal. "Mac" is only joined across an apostrophe — "Mac" followed by a
# space is too often an unrelated word.
_PARTICLE_RE = re.compile(r"(?<![\w'-])(o|mc)(?:'\s*|\s+|-)(?=[a-z])|(?<![\w'-])(mac)'(?=[a-z])")


def compact_name_particles(text: str) -> str:
    """Join surname prefixes to their surname ("o neill" -> "oneill").
    Expects lowercase text."""
    return _PARTICLE_RE.sub(lambda m: m.group(1) or m.group(2), text)


def normalise_for_names(text: str) -> str:
    """Text normalised for name matching (see :func:`mentions_subject`)."""
    return compact_name_particles(_normalise_text(text))


def _token_regex(token: str) -> str:
    """A name token that tolerates single/double letter spellings:
    Neil = Neill, Philip = Phillip, Jon = Jonn."""
    token = re.sub(r"(.)\1+", r"\1", token)
    return "".join(re.escape(ch) + ("{1,2}" if ch.isalpha() else "") for ch in token)


@functools.lru_cache(maxsize=64)
def _name_pattern(subject_name: str) -> re.Pattern[str] | None:
    tokens = [_token_regex(t.strip(".,")) for t in normalise_for_names(subject_name).split()]
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
    return bool(pattern and pattern.search(normalise_for_names(text)))


def on_site(url: str, site: str) -> bool:
    """Whether `url` is hosted on `site` or one of its subdomains."""
    host = (urlparse(url).netloc or "").lower()
    return host == site or host.endswith("." + site)


def parse_sites(value: str) -> list[str]:
    """A comma-separated hostname setting as a clean list."""
    return [s.strip().lower() for s in value.split(",") if s.strip()]


def categorise(text: str, default: str = Category.WEB) -> str:
    """Adverse media if `text` contains any term from the shared adverse-keyword
    list (config/adverse_keywords.yaml), otherwise `default`. The pipeline
    re-screens every finding from every source against the same list."""
    from app.services.keyword_screening import default_screener  # avoid import cycle

    return Category.ADVERSE_MEDIA if default_screener().screen(text) else default
