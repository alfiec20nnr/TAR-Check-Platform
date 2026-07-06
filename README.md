# Adverse Intelligence Platform (AIP) — MVP

A self-hosted due-diligence tool for **individuals**: submit a name (plus
optional date of birth and country), and the platform concurrently queries a
set of UK-focused public data sources, matches identities with confidence
scores, calculates a configurable risk score, produces an AI summary, and
generates a professional report (PDF / HTML / JSON).

Intended for legitimate business due diligence, compliance, KYC/AML support,
supplier vetting, recruitment screening (where legally permitted), and
reputational risk assessment. Runs locally or inside a single trusted
organisation network — **no accounts, no authentication, not multi-tenant**.

## Quick start (Docker Compose)

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, ENCRYPTION_KEY, and any API keys you have.
# With MOCK_CONNECTORS=true (default) no API keys are needed — every connector
# returns realistic fixture data so you can try the full pipeline immediately.

docker compose up --build
```

> ⚠️ **Demo mode**: while `MOCK_CONNECTORS=true`, every result is *simulated
> fixture data* — nothing shown relates to any real person. The UI and every
> generated report display a demo-mode banner. Roughly 70% of names produce a
> clean profile and 30% land in one of three deterministic adverse demo
> profiles. To search real sources, follow "Going live" below.

Then open:

| URL | What |
|---|---|
| http://localhost:8080 | Web UI (dashboard, search, history, reports) |
| http://localhost:8080/docs | Interactive OpenAPI documentation |
| http://localhost:8080/health | Health check |

Submit a search from the dashboard; the status updates live and the report
becomes downloadable when the pipeline finishes.

### Going live with real sources

Set `MOCK_CONNECTORS=false` and provide keys in `.env`:

| Connector | Credentials | Where to get them |
|---|---|---|
| Brave Web Search | `BRAVE_API_KEY` | [api-dashboard.search.brave.com](https://api-dashboard.search.brave.com/register) — recommended web source, free tier |
| Google Search | `GOOGLE_API_KEY`, `GOOGLE_CSE_ID` | ⚠ Closed to new customers since Jan 2026 — grandfathered keys only |
| News API | `NEWSAPI_KEY` | newsapi.org |
| UK Companies House | `COMPANIES_HOUSE_API_KEY` | developer.company-information.service.gov.uk |
| FCA register | `FCA_API_EMAIL`, `FCA_API_KEY` | register.fca.org.uk/Developer |
| UK Sanctions List | **none — works out of the box** | Live FCDO XML feed (default URL); a licensed provider JSON endpoint also works |
| Insolvency Register | `INSOLVENCY_API_URL`, `INSOLVENCY_API_KEY` | licensed data provider of your choice |
| DVLA Driving Licence (ADD) | `DVLA_USERNAME`, `DVLA_PASSWORD`, `DVLA_API_KEY` (+ `DVLA_API_BASE_URL` for prod) | Commercial agreement with DVLA ([developer portal](https://developer-portal.driver-vehicle-licensing.api.gov.uk/)); UAT is the default environment |

Connectors without credentials are skipped gracefully; the rest still run.

**DVLA driving licence check** — optional per search: supply a driving licence
number (plus a mandatory driver-consent attestation, recorded in the audit
log) and the DVLA connector verifies validity and surfaces entitlements,
endorsements, and disqualifications as weighted findings. Searches without a
licence number are completely unaffected. The licence number is encrypted at
rest and never appears in logs, audit entries, or error messages; the driver's
address returned by DVLA is deliberately not stored. Note DVLA passwords
expire every 90 days.

For AI summaries set `ANTHROPIC_API_KEY` (model configurable via `AI_MODEL`,
default `claude-opus-4-8`). Without a key, a clearly-labelled non-AI template
summary is used instead.

## Local development (without Docker)

Backend:

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements-dev.txt
# Uses SQLite + inline worker for a zero-dependency dev loop:
set DATABASE_URL=sqlite+aiosqlite:///./dev.sqlite3   # export on POSIX
set INLINE_WORKER=true
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload
```

Frontend (proxies `/api` to `localhost:8000`):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

## Tests

```bash
cd backend && pytest --cov=app          # 56 tests, ~87% coverage
cd frontend && npm test                 # component tests (vitest)
```

## Identity-match accuracy

Every result carries a confidence percentage with an honest ceiling per
evidence tier — a name similarity alone is never presented as a confirmed
identity:

| Band | Confidence | Meaning |
|---|---|---|
| Strong | 85%+ | Corroborated by independent signals (e.g. DOB, country) |
| Probable | 65–84% | Good match, limited corroboration |
| Possible | 40–64% | Name-only or text-mention match — may be a different person |
| Weak | < 40% | Excluded from risk scoring |

Records that merely *mention* the name in unstructured text (web pages, news
articles) are capped at 55%; records with a source-attributed name but no
corroborating DOB/country are capped at 72%; a hard DOB mismatch caps at 30%.
All ceilings are tunable in `backend/config/matching_weights.yaml`.

## Tuning without code changes

- `backend/config/risk_weights.yaml` — category severity weights, adverse-media
  keyword escalation, confidence threshold, aggregation, and Low/Medium/High/
  Critical thresholds.
- `backend/config/matching_weights.yaml` — identity-matching signal weights,
  confidence ceilings (`caps`), DOB-mismatch cap, and name-variant equivalences.

## Documentation

- [Architecture overview](docs/ARCHITECTURE.md)
- [API documentation](docs/API.md) (plus live OpenAPI at `/docs`)
- [Deployment guide](docs/DEPLOYMENT.md) — including HTTPS and backups

## Project layout

```
backend/            FastAPI modular monolith + background worker
  app/connectors/     connector framework + 6 UK sources
  app/services/       identity matching, risk scoring, AI summary, reports, pipeline
  app/api/            REST endpoints
  config/             tunable YAML weightings
  alembic/            database migrations
  tests/              unit + API tests
frontend/           React + TypeScript + MUI single-page app
docs/               architecture / API / deployment guides
docker-compose.yml  Postgres + API + worker + nginx web
```

## Compliance notes

- **Data minimisation** — only full name, optional DOB, optional country are collected.
- **Encryption at rest** — subject name/DOB encrypted with Fernet (`ENCRYPTION_KEY`).
- **Append-only audit** — every search is recorded; audit entries are never
  deleted, including by the retention job.
- **Configurable retention** — `DATA_RETENTION_DAYS` purges old search results
  and reports (default 365 days).
- **AI separation** — reports visibly separate verified source records from
  AI-generated summary text; the AI is instructed never to state allegations
  as fact.
- Respect source terms of service; the insolvency connector expects a licensed
  provider rather than scraping.

## Phase 2 (out of scope for this MVP)

Continuous monitoring, alerts/notifications, case management, additional
connectors (PEP data, non-UK jurisdictions), and authentication/multi-tenancy.
The modular-monolith and connector-registry design deliberately leaves room
for all of these.
