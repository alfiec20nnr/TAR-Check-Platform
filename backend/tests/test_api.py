"""API integration tests — full pipeline via the inline worker + mock connectors."""

import asyncio

import pytest

from app.database import get_session_factory
from app.seed import seed_sources


async def submit_and_wait(client, payload: dict, timeout: float = 15.0) -> dict:
    resp = await client.post("/api/v1/searches", json=payload)
    assert resp.status_code == 202, resp.text
    search_id = resp.json()["id"]

    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        detail = (await client.get(f"/api/v1/searches/{search_id}")).json()
        if detail["status"] in ("completed", "failed"):
            return detail
        if asyncio.get_event_loop().time() > deadline:
            pytest.fail(f"search did not finish in time: {detail['status']}")
        await asyncio.sleep(0.2)


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # The test env runs with MOCK_CONNECTORS=true; the flag must be surfaced
    # so the UI can display the demo-mode banner.
    assert body["mock_connectors"] is True


async def test_submit_search_returns_id_immediately(client):
    resp = await client.post("/api/v1/searches", json={"full_name": "Alice Example"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"]
    assert body["status"] == "pending"
    assert body["full_name"] == "Alice Example"


async def test_validation_rejects_bad_input(client):
    assert (await client.post("/api/v1/searches", json={})).status_code == 422
    assert (
        await client.post("/api/v1/searches", json={"full_name": "1234 5678"})
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/searches",
            json={"full_name": "Jane Doe", "date_of_birth": "2999-01-01"},
        )
    ).status_code == 422


async def test_full_pipeline_completes(client):
    detail = await submit_and_wait(
        client,
        {"full_name": "John Smith", "date_of_birth": "1975-03-02",
         "country": "United Kingdom"},
    )
    assert detail["status"] == "completed"
    assert detail["results_count"] == len(detail["results"])
    assert detail["results_count"] >= 2  # google mock always returns results
    assert detail["risk_level"] in ("low", "medium", "high", "critical")
    assert detail["report_reference"]
    assert detail["sources_searched"]
    # Every result carries a confidence percentage.
    assert all(0 <= r["confidence"] <= 100 for r in detail["results"])


async def test_report_retrieval_json_and_html(client):
    detail = await submit_and_wait(client, {"full_name": "Report Subject"})
    search_id = detail["id"]

    json_resp = await client.get(f"/api/v1/searches/{search_id}/report?format=json")
    assert json_resp.status_code == 200
    report = json_resp.json()
    assert report["reference"] == detail["report_reference"]
    assert report["subject"]["full_name"] == "Report Subject"
    assert "risk" in report and "ai" in report and "results" in report

    html_resp = await client.get(f"/api/v1/searches/{search_id}/report?format=html")
    assert html_resp.status_code == 200
    assert "Adverse Intelligence Report" in html_resp.text

    bad = await client.get(f"/api/v1/searches/{search_id}/report?format=docx")
    assert bad.status_code == 422


async def test_report_404_before_completion(client):
    resp = await client.post("/api/v1/searches", json={"full_name": "Zed Pending"})
    search_id = resp.json()["id"]
    # May or may not have completed yet, but a bogus ID must 404 either way.
    missing = await client.get("/api/v1/searches/does-not-exist/report")
    assert missing.status_code == 404
    missing2 = await client.get("/api/v1/searches/does-not-exist")
    assert missing2.status_code == 404
    # Let the background task finish before the test's DB teardown.
    await submit_and_wait_by_id(client, search_id)


async def submit_and_wait_by_id(client, search_id: str, timeout: float = 15.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        detail = (await client.get(f"/api/v1/searches/{search_id}")).json()
        if detail.get("status") in ("completed", "failed"):
            return detail
        await asyncio.sleep(0.2)
    return None


async def test_history_pagination_and_filters(client):
    await submit_and_wait(client, {"full_name": "Person One"})
    await submit_and_wait(client, {"full_name": "Person Two"})

    page = (await client.get("/api/v1/searches?page=1&page_size=1")).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1

    completed = (await client.get("/api/v1/searches?status=completed")).json()
    assert completed["total"] == 2

    none = (await client.get("/api/v1/searches?status=failed")).json()
    assert none["total"] == 0


async def test_dashboard_stats(client):
    await submit_and_wait(client, {"full_name": "Dash Person"})
    stats = (await client.get("/api/v1/dashboard/stats")).json()
    assert stats["total_searches"] == 1
    assert stats["completed_searches"] == 1
    assert len(stats["recent_searches"]) == 1


async def test_sources_registry(client):
    await seed_sources()
    sources = (await client.get("/api/v1/sources")).json()
    names = {s["name"] for s in sources}
    assert names == {
        "brave_search",
        "google_search",
        "social_media",
        "news_api",
        "companies_house",
        "insolvency_register",
        "uk_sanctions",
        "fca_warning_list",
        "dvla_add",
    }
    assert all(s["enabled"] for s in sources)


async def test_licence_number_requires_consent(client):
    resp = await client.post(
        "/api/v1/searches",
        json={"full_name": "Jane Doe", "driving_licence_number": "DOE99801045JA9AB"},
    )
    assert resp.status_code == 422
    assert "consent" in resp.text.lower()

    bad_format = await client.post(
        "/api/v1/searches",
        json={
            "full_name": "Jane Doe",
            "driving_licence_number": "??!",
            "licence_check_consent": True,
        },
    )
    assert bad_format.status_code == 422


async def test_dvla_check_runs_when_licence_supplied(client):
    """Mock-mode pipeline: DVLA findings appear only with a licence number,
    and the consent attestation is audited (never the number itself)."""
    with_licence = await submit_and_wait(
        client,
        {
            "full_name": "Jane Doe",
            "date_of_birth": "1980-04-12",
            "driving_licence_number": "DOE 998010 45JA 9AB",  # normalised server-side
            "licence_check_consent": True,
        },
    )
    assert with_licence["status"] == "completed"
    dvla_results = [r for r in with_licence["results"] if r["source_name"] == "dvla_add"]
    assert dvla_results, "expected DVLA findings when a licence number is supplied"
    assert any(r["category"].startswith("driving_") for r in dvla_results)

    without_licence = await submit_and_wait(client, {"full_name": "Jane Doe"})
    assert not any(
        r["source_name"] == "dvla_add" for r in without_licence["results"]
    )

    entries = (await client.get(f"/api/v1/audit?search_id={with_licence['id']}")).json()
    submitted = next(e for e in entries if e["action"] == "search_submitted")
    assert submitted["details"]["licence_check_requested"] is True
    assert submitted["details"]["licence_check_consent"] is True
    assert "DOE99801045JA9AB" not in str(submitted["details"])


async def test_audit_trail_written(client):
    detail = await submit_and_wait(client, {"full_name": "Audit Person"})
    entries = (await client.get(f"/api/v1/audit?search_id={detail['id']}")).json()
    actions = [e["action"] for e in entries]
    assert "search_submitted" in actions
    assert "search_completed" in actions
    completed = next(e for e in entries if e["action"] == "search_completed")
    for key in ("sources_searched", "duration_ms", "results_found", "report_reference"):
        assert key in completed["details"]


async def test_delete_single_search(client):
    detail = await submit_and_wait(client, {"full_name": "Delete Me"})
    keep = await submit_and_wait(client, {"full_name": "Keep Me"})

    resp = await client.delete(f"/api/v1/searches/{detail['id']}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/v1/searches/{detail['id']}")).status_code == 404
    # The stored report is gone with it.
    assert (
        await client.get(f"/api/v1/searches/{detail['id']}/report")
    ).status_code == 404
    # Other searches are untouched.
    assert (await client.get(f"/api/v1/searches/{keep['id']}")).status_code == 200

    # Deleting is itself audited; the original submission entry survives.
    entries = (await client.get(f"/api/v1/audit?search_id={detail['id']}")).json()
    actions = [e["action"] for e in entries]
    assert "search_deleted" in actions
    assert "search_submitted" in actions

    missing = await client.delete("/api/v1/searches/does-not-exist")
    assert missing.status_code == 404


async def test_clear_history(client):
    await submit_and_wait(client, {"full_name": "Person One"})
    await submit_and_wait(client, {"full_name": "Person Two"})

    resp = await client.delete("/api/v1/searches")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    assert (await client.get("/api/v1/searches")).json()["total"] == 0

    # The clearance is audited; prior audit entries are never deleted.
    entries = (await client.get("/api/v1/audit")).json()
    actions = [e["action"] for e in entries]
    assert "history_cleared" in actions
    assert actions.count("search_submitted") == 2


async def test_personal_data_encrypted_at_rest(client, monkeypatch):
    """With a key configured, raw DB storage must not contain the plain name."""
    from cryptography.fernet import Fernet
    from sqlalchemy import text

    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "encryption_key", Fernet.generate_key().decode())
    detail = await submit_and_wait(client, {"full_name": "Secret Name"})

    async with get_session_factory()() as session:
        raw = (
            await session.execute(
                text("SELECT full_name FROM searches WHERE id = :id"),
                {"id": detail["id"]},
            )
        ).scalar_one()
    assert "Secret" not in raw
    assert raw.startswith("enc::")
    # But the API decrypts transparently.
    assert detail["full_name"] == "Secret Name"
