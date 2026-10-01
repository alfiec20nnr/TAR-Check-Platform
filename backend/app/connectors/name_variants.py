"""Name-variant expansion for connector queries.

Reuses the nickname/variant map from matching_weights.yaml — the same map the
identity-matching engine uses for scoring — to generate extra full-name forms
to *query* with. A subject searched as "William Smith" is also queried as
"Bill Smith", "Will Smith", etc., so a source that only ever refers to them by
a nickname is still found instead of silently missed.

Only the first (given-name) token is varied; surname variants are not
modelled. Bounded by `limit` to keep the fan-out sane for very common names
with many recorded variants (e.g. "Samuel").
"""

import functools
from pathlib import Path

import yaml


@functools.lru_cache(maxsize=4)
def _variant_map(path_str: str) -> dict[str, list[str]]:
    data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8")) or {}
    raw: dict[str, list[str]] = data.get("name_variants", {}) or {}
    groups: dict[str, set[str]] = {}
    for canonical, variants in raw.items():
        group = {canonical, *variants}
        for token in group:
            groups.setdefault(token, set()).update(group)
    return {token: sorted(forms - {token}) for token, forms in groups.items()}


def expand_full_name(full_name: str, config_path: Path, limit: int = 5) -> list[str]:
    """Alternative full-name forms with the first token swapped for a known
    nickname/variant. Returns an empty list when the first token has none."""
    tokens = full_name.strip().split()
    if len(tokens) < 2:
        return []
    first = tokens[0].lower()
    variants = _variant_map(str(config_path)).get(first, [])
    return [
        " ".join([variant.capitalize(), *tokens[1:]]) for variant in variants[:limit]
    ]
