"""Report Generator.

Assembles the final report in three formats:
- JSON  — structured content, stored in the reports table
- HTML  — rendered from a Jinja2 template, stored alongside
- PDF   — generated on demand from the stored HTML (WeasyPrint)

Each report carries a unique reference number and generation timestamp.
"""

import logging
import os
import secrets
import shutil
import subprocess
import tempfile
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


# Chromium-family browsers that can print HTML to PDF headlessly. Edge ships
# with every Windows 10/11 machine, so the Python-only install needs nothing
# extra; the names cover Linux/macOS dev machines too.
_CHROMIUM_CANDIDATES = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    "msedge",
    "google-chrome",
    "chromium",
    "chromium-browser",
]


# Memoised WeasyPrint import: the failed import is noisy (it prints its own
# installation advice to stderr), so it is attempted only once per process.
_weasyprint_html: type | None = None
_weasyprint_checked = False


def _get_weasyprint() -> type | None:
    global _weasyprint_html, _weasyprint_checked
    if not _weasyprint_checked:
        _weasyprint_checked = True
        try:
            from weasyprint import HTML  # imported lazily — heavy native deps

            _weasyprint_html = HTML
        except Exception:  # environment dependent
            _weasyprint_html = None
    return _weasyprint_html


def _find_chromium() -> str | None:
    for candidate in _CHROMIUM_CANDIDATES:
        if os.path.sep in candidate or (os.path.altsep and os.path.altsep in candidate):
            if os.path.isfile(candidate):
                return candidate
        elif shutil.which(candidate):
            return shutil.which(candidate)
    return None


def _render_pdf_chromium(html: str, browser: str) -> bytes:
    """Print HTML to PDF with a headless Chromium-family browser."""
    with tempfile.TemporaryDirectory(prefix="aip-report-") as tmp:
        src = Path(tmp) / "report.html"
        out = Path(tmp) / "report.pdf"
        src.write_text(html, encoding="utf-8")
        # A private user-data-dir keeps the run isolated from (and working
        # alongside) any interactive browser session. Both header/footer
        # switches are passed — Chromium ignores whichever it doesn't know.
        subprocess.run(
            [
                browser,
                "--headless",
                "--disable-gpu",
                f"--user-data-dir={Path(tmp) / 'profile'}",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                f"--print-to-pdf={out}",
                src.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return out.read_bytes()


def render_pdf(html: str) -> bytes:
    """Convert stored report HTML to PDF.

    Preferred engine is WeasyPrint (native Pango/Cairo libraries — always
    present inside the Docker image). On bare Windows machines those libraries
    are usually missing, so a headless Chromium-family browser (Edge is
    preinstalled on Windows) is used instead. Callers surface the final
    RuntimeError as a 501.
    """
    weasy_html = _get_weasyprint()
    if weasy_html is not None:
        return weasy_html(string=html).write_pdf()

    browser = _find_chromium()
    if browser:
        try:
            return _render_pdf_chromium(html, browser)
        except (subprocess.SubprocessError, OSError) as exc:
            logger.error("Headless-browser PDF generation failed: %s", exc)

    raise RuntimeError(
        "PDF generation is unavailable in this environment (WeasyPrint native "
        "dependencies missing and no Edge/Chrome browser found). Use the HTML "
        "or JSON format instead."
    )
