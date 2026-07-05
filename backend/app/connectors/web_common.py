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

from rapidfuzz import fuzz

from app.connectors.base import Category

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
]

# The OR-query sent to the provider alongside the plain name query — the
# standard adverse-media screening query.
ADVERSE_QUERY_TERMS = (
    'fraud OR corruption OR "money laundering" OR convicted OR lawsuit '
    "OR scandal OR investigation OR misconduct OR fined"
)


def mentions_subject(subject_name: str, text: str) -> bool:
    return fuzz.token_set_ratio(subject_name.lower(), text.lower()) >= MENTION_THRESHOLD


def categorise(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ADVERSE_TERMS):
        return Category.ADVERSE_MEDIA
    return Category.WEB
