"""Report retrieval endpoints (JSON / HTML / PDF)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Report
from app.services.report_generator import render_pdf

router = APIRouter(prefix="/searches", tags=["reports"])


@router.get("/{search_id}/report")
async def get_report(
    search_id: str,
    format: str = Query("json", pattern="^(json|html|pdf)$"),
    db: AsyncSession = Depends(get_db),
):
    """Return the stored report for a completed search."""
    report = (
        await db.execute(select(Report).where(Report.search_id == search_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report not found — the search may still be running.",
        )

    filename = f"{report.reference}"
    if format == "json":
        return JSONResponse(content=report.json_content)
    if format == "html":
        return HTMLResponse(content=report.html_content)

    # PDF: generated on demand from the stored HTML. Rendering shells out to a
    # browser / native libraries, so it runs in a thread off the event loop.
    try:
        pdf_bytes = await asyncio.to_thread(render_pdf, report.html_content)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )
