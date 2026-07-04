"""Report Generator.

Assembles the final report in three formats:
- JSON  — structured content, stored in the reports table
- HTML  — rendered from a Jinja2 template, stored alongside
- PDF   — generated on demand from the stored HTML (WeasyPrint)

Each report carries a unique reference number and generation timestamp.
"""

import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def make_reference() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return f"AIP-{stamp}-{secrets.token_hex(3).upper()}"


def build_report_content(
    *,
    reference: str,
    subject: dict,
    risk: dict,
    ai: dict,
    results: list[dict],
    sources_searched: list[str],
    connector_stats: list[dict],
    duration_ms: int,
    mock_mode: bool = False,
) -> dict:
    """The canonical JSON report body (also feeds the HTML template)."""
    return {
        "reference": reference,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mock_mode": mock_mode,
        "subject": subject,
        "risk": risk,
        "ai": ai,
        "results": results,
        "sources_searched": sources_searched,
        "connector_stats": connector_stats,
        "duration_ms": duration_ms,
    }


def render_html(report: dict) -> str:
    template = _env.get_template("report.html")
    return template.render(**report)


def render_pdf(html: str) -> bytes:
    """Convert stored report HTML to PDF.

    WeasyPrint needs native libraries (Pango/Cairo); inside the Docker image it
    is always available. On bare Windows dev machines it may not be — callers
    should surface the RuntimeError as a 501.
    """
    try:
        from weasyprint import HTML  # imported lazily — heavy native deps
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PDF generation is unavailable in this environment (WeasyPrint native "
            "dependencies missing). Use the HTML or JSON format instead."
        ) from exc
    return HTML(string=html).write_pdf()
