"""Shared logic for web-search connectors (Google, Brave, future providers).

Web results are unstructured mentions, not attributed records, so every
provider applies the same rules:

- results must actually mention the subject's name (mention filter)
- results containing adverse terms are categorised as adverse media so the
  risk scorer's keyword escalation applies; everything else stays in the
  low-weight web category
- ``subject_name`` is never set — identity matching treats web results as
  unstructured mentions with a low confidence ceiling
"""

from pathlib import Path

from rapidfuzz import fuzz

from app.connectors.base import Category
from app.connectors.name_variants import expand_full_name

# A result must actually mention the subject's name in its title/snippet;
# anything below this partial-match score is provider noise, not evidence.
MENTION_THRESHOLD = 70

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


def mentions_subject(subject_name: str, text: str) -> bool:
    return fuzz.token_set_ratio(subject_name.lower(), text.lower()) >= MENTION_THRESHOLD


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
