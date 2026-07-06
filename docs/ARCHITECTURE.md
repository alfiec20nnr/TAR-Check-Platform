# Architecture Overview

## Shape: modular monolith + worker

One deployable FastAPI application composed of isolated internal modules, plus
a background worker process running the same codebase. No microservices, no
message broker — the PostgreSQL database is the only shared infrastructure.

```
┌──────────┐     ┌───────────────────────────────┐
│  React   │     │  nginx (static SPA + proxy)   │
│  SPA     ├────▶│  :8080                        │
└──────────┘     └───────────────┬───────────────┘
                                 │ /api, /docs, /health
                 ┌───────────────▼───────────────┐
                 │  FastAPI (app.main)  :8000    │
                 │  - Search module (routes)     │
                 │  - Report retrieval           │
                 │  - Dashboard / audit          │
                 └───────────────┬───────────────┘
                                 │ INSERT search (status=pending)
                 ┌───────────────▼───────────────┐
                 │  PostgreSQL (single DB)       │
                 └───────────────▲───────────────┘
                                 │ SELECT ... FOR UPDATE SKIP LOCKED
                 ┌───────────────┴───────────────┐
                 │  Worker (app.worker)          │
                 │  runs the search pipeline     │
                 └───────────────────────────────┘
```

## Modules

| Module | Location | Responsibility |
|---|---|---|
| Search Module | `app/api/routes/searches.py` | Validates input, creates the job, exposes status |
| Connector Framework | `app/connectors/` | `BaseConnector` (retries, rate limiting, timing, failure logging) + registry; concurrent execution via `asyncio.gather` |
| Identity Matching Engine | `app/services/identity_matching.py` | Weighted name/DOB/country matching → confidence % per record, with evidence-tier ceilings (unstructured mention 55%, uncorroborated name 72%, DOB mismatch 30%) |
| Risk Scoring Engine | `app/services/risk_scoring.py` | Configurable category weights + media-keyword escalation → 0-100 score and level |
| AI Summarisation | `app/services/ai_summary.py` | Claude structured-output summary; template fallback without a key |
| Report Generator | `app/services/report_generator.py` | JSON + HTML stored; PDF rendered on demand (WeasyPrint) |
| Search History & Audit | `app/services/audit.py`, `app/models/audit.py` | Append-only audit log; never updated or deleted |
| Pipeline Orchestrator | `app/services/pipeline.py` | Runs the 11-step workflow and finalises job state |

## The search pipeline

1. Validate input (Pydantic) → create `searches` row → **202 + search ID**.
2. Worker claims the job (`FOR UPDATE SKIP LOCKED` — safe with multiple workers).
3. Enabled connectors run **concurrently**; each is independently retried,
   rate-limited, timed, and failure-logged. One slow source never blocks the rest.
4. Findings arrive already normalised to the common `Finding` shape.
5. Duplicates removed (URL identity + fuzzy title matching per category).
6-7. Identity matching assigns a confidence % to every record.
8. Risk scoring aggregates weighted findings above the confidence threshold.
9. AI summary generated (or template fallback), never stating allegations as fact.
10. Report assembled (JSON + HTML persisted; PDF on demand) with a unique
    `AIP-YYYYMMDD-XXXXXX` reference.
11. Append-only audit entry written with sources, duration, counts, reference.

The frontend polls `GET /api/v1/searches/{id}` every 2 s until the status is
terminal.

## Extending with a new connector

1. Subclass `BaseConnector` in `app/connectors/your_source.py` — implement
   `fetch()` (and optionally `mock_findings()` / `is_configured()` /
   `applies_to()` for identifier-driven checks like the DVLA licence lookup,
   which skip subjects that did not supply the identifier).
2. Append the class to `CONNECTOR_CLASSES` in `app/connectors/registry.py`.
3. Restart; the seed step registers it in the `sources` table automatically.

No core pipeline, schema, or API changes are required.

## Data model

- `searches` — job + denormalised dashboard fields (status, risk level, counts).
  `full_name`/`date_of_birth` are encrypted at rest (Fernet TypeDecorator).
- `search_results` — normalised findings with confidence & risk contribution.
- `sources` — connector registry (enable/disable per source).
- `reports` — one per search: reference, JSON content, HTML content.
- `ai_summaries` — model used, fallback flag, structured content.
- `risk_scores` — score, level, factor breakdown.
- `audit_logs` — append-only, exempt from retention deletion.

## Key design decisions

- **Postgres-backed job queue** instead of Redis/celery: one fewer service, and
  `SKIP LOCKED` gives safe multi-worker semantics at MVP scale.
- **Mock-connector mode** (`MOCK_CONNECTORS`) makes the entire pipeline runnable
  and testable with zero external credentials; fixtures are deterministic per name,
  ~70% of names are clean (adverse findings are the exception, mirroring reality),
  and the UI/reports carry a demo-mode banner so simulated data is never mistaken
  for real records (`/health` exposes the flag).
- **Evidence-tier confidence ceilings** — web/news connectors never attribute the
  searched name back onto a result (`subject_name` stays unset); such records are
  scored as unstructured mentions with a low confidence ceiling, and even a perfect
  name match is capped unless independent signals (DOB, country) corroborate it.
  A name alone is never proof of identity.
- **Weightings in YAML** (`backend/config/*.yaml`) so risk and matching models are
  tunable without code changes or admin UI.
- **SQLite for tests** — models avoid Postgres-only types so the test suite runs
  anywhere; CI additionally applies migrations against real PostgreSQL.
- **AI text is quarantined** — stored separately (`ai_summaries`), flagged when
  fallback, and visually separated from verified records in every report format.
