"""AI Summarisation Module.

Uses Anthropic Claude to summarise findings, highlight key concerns, build a
timeline and suggest further investigation. The model is instructed to never
state allegations as fact and to distinguish allegations, investigations and
proven outcomes. Reports always separate verified records from this
AI-generated text.

If no API key is configured (or the API call fails) a deterministic template
summary is produced instead and flagged with ``is_fallback=True`` so the report
clearly labels it as non-AI.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.connectors.base import Finding, SearchSubject

logger = logging.getLogger(__name__)

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "key_concerns": {"type": "array", "items": {"type": "string"}},
        "timeline": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "event": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["date", "event", "source"],
                "additionalProperties": False,
            },
        },
        "recurring_themes": {"type": "array", "items": {"type": "string"}},
        "legal_outcomes": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "executive_summary",
        "key_concerns",
        "timeline",
        "recurring_themes",
        "legal_outcomes",
        "recommendations",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are a due-diligence analyst assistant for a compliance platform. You are
given normalised findings about an individual from public data sources, each
with an identity-match confidence percentage.

Rules you must follow:
- Never state allegations as facts. Clearly distinguish between allegations,
  ongoing investigations, and proven/legal outcomes.
- Do not make definitive legal conclusions or accusations.
- Attribute claims to their sources ("according to press reports...").
- Note identity-match confidence where relevant — a record may belong to a
  different person with a similar name.
- Deduplicate overlapping information across sources.
- Keep the executive summary factual, neutral and under 250 words.
- recommendations should suggest concrete areas for further investigation.
- If there are no adverse findings, say so plainly."""


@dataclass
class SummaryResult:
    content: dict
    model: str
    is_fallback: bool


def _findings_payload(
    subject: SearchSubject, findings: list[tuple[Finding, float]]
) -> str:
    rows = []
    for finding, confidence in findings:
        rows.append(
            {
                "source": finding.source,
                "category": finding.category,
                "title": finding.title,
                "description": finding.description,
                "url": finding.url,
                "date": finding.date,
                "identity_match_confidence_pct": confidence,
            }
        )
    return json.dumps(
        {
            "subject": {
                "full_name": subject.full_name,
                "date_of_birth": subject.date_of_birth,
                "country": subject.country,
            },
            "findings": rows,
        },
        indent=2,
    )


def fallback_summary(
    subject: SearchSubject, findings: list[tuple[Finding, float]]
) -> dict:
    """Deterministic non-AI summary used when Claude is unavailable."""
    adverse = [
        (f, c)
        for f, c in findings
        if f.category in {"sanctions", "disqualification", "insolvency", "regulatory",
                          "adverse_media"}
    ]
    by_category: dict[str, int] = {}
    for f, _ in findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1

    if adverse:
        categories = ", ".join(sorted({f.category.replace("_", " ") for f, _ in adverse}))
        summary = (
            f"The search for {subject.full_name} returned {len(findings)} record(s) "
            f"across {len(by_category)} categorie(s), including potential adverse "
            f"findings in: {categories}. Identity-match confidence varies by record — "
            "review each finding and its source before drawing conclusions. This "
            "summary was generated without AI assistance; findings listed are "
            "records returned by data sources, not established facts."
        )
    else:
        summary = (
            f"The search for {subject.full_name} returned {len(findings)} record(s). "
            "No adverse findings were identified in the sources searched. This "
            "summary was generated without AI assistance."
        )

    timeline = sorted(
        (
            {"date": f.date, "event": f.title, "source": f.source}
            for f, _ in findings
            if f.date
        ),
        key=lambda item: item["date"],
    )
    return {
        "executive_summary": summary,
        "key_concerns": [f"{f.title} ({f.source}, {c:.0f}% match)" for f, c in adverse],
        "timeline": timeline,
        "recurring_themes": [],
        "legal_outcomes": [],
        "recommendations": (
            ["Manually verify each adverse finding against the original source.",
             "Confirm subject identity (date of birth / address) for records with "
             "confidence below 80%."]
            if adverse
            else ["No further investigation indicated by the sources searched."]
        ),
    }


class AiSummariser:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def summarise(
        self, subject: SearchSubject, findings: list[tuple[Finding, float]]
    ) -> SummaryResult:
        if not self.settings.anthropic_api_key:
            return SummaryResult(
                content=fallback_summary(subject, findings),
                model="template-fallback",
                is_fallback=True,
            )
        try:
            return await self._summarise_with_claude(subject, findings)
        except Exception:  # noqa: BLE001 — any AI failure degrades to fallback
            logger.exception("AI summarisation failed; using template fallback")
            return SummaryResult(
                content=fallback_summary(subject, findings),
                model="template-fallback",
                is_fallback=True,
            )

    async def _summarise_with_claude(
        self, subject: SearchSubject, findings: list[tuple[Finding, float]]
    ) -> SummaryResult:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        response = await client.messages.create(
            model=self.settings.ai_model,
            max_tokens=self.settings.ai_max_tokens,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarise the following due-diligence findings:\n\n"
                        + _findings_payload(subject, findings)
                    ),
                }
            ],
        )
        if response.stop_reason == "refusal":
            logger.warning("Claude declined the summarisation request; using fallback")
            return SummaryResult(
                content=fallback_summary(subject, findings),
                model="template-fallback",
                is_fallback=True,
            )
        text = next(b.text for b in response.content if b.type == "text")
        return SummaryResult(
            content=json.loads(text),
            model=self.settings.ai_model,
            is_fallback=False,
        )
