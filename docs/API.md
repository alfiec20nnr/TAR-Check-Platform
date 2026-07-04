# API Documentation

Base URL: `/api/v1`. Interactive OpenAPI docs are generated automatically at
`/docs` (Swagger UI) and `/redoc`. There is no authentication (single trusted
environment); requests are rate-limited per client IP (`API_RATE_LIMIT`,
default 60/minute).

## Submit a search

```
POST /api/v1/searches
Content-Type: application/json

{
  "full_name": "John Smith",          // required, 2-200 chars
  "date_of_birth": "1975-03-02",      // optional, ISO date, not in future
  "country": "United Kingdom"          // optional
}
```

**202 Accepted** — returns immediately with the job:

```json
{
  "id": "6c1f...",
  "full_name": "John Smith",
  "status": "pending",
  "created_at": "2026-07-04T12:00:00Z",
  "results_count": 0,
  "risk_level": null
}
```

`422` on validation failure.

## Poll search status / results

```
GET /api/v1/searches/{id}
```

Returns the search with `status` (`pending → running → completed | failed`),
denormalised risk fields, `report_reference`, and — once completed — the full
`results` array:

```json
{
  "status": "completed",
  "risk_score_value": 66.5,
  "risk_level": "high",
  "report_reference": "AIP-20260704-1A2B3C",
  "results": [
    {
      "source_name": "insolvency_register",
      "category": "insolvency",
      "title": "Bankruptcy order — John Smith",
      "url": "https://...",
      "event_date": "2021-08-20",
      "confidence": 95.0,
      "risk_contribution": 66.5
    }
  ]
}
```

## Retrieve the report

```
GET /api/v1/searches/{id}/report?format=json   (default)
GET /api/v1/searches/{id}/report?format=html
GET /api/v1/searches/{id}/report?format=pdf
```

- `json` — the structured report body (subject, risk, AI summary, results,
  sources, connector stats, reference, timestamp).
- `html` — the stored, self-contained report page.
- `pdf` — generated on demand from the stored HTML (`Content-Disposition:
  attachment`). Returns `501` if the host lacks WeasyPrint native libraries
  (never the case in Docker).
- `404` until the search completes.

## History

```
GET /api/v1/searches?page=1&page_size=20&status=completed&risk_level=high
```

Paginated (`items`, `total`, `page`, `page_size`); filterable by `status` and
`risk_level`.

## Dashboard

```
GET /api/v1/dashboard/stats
```

Counts (total / running / completed / failed / high-risk) plus the ten most
recent searches and ten most recent high-risk searches.

## Sources

```
GET /api/v1/sources
```

The connector registry: name, display name, description, enabled flag.
Disable a source by setting `enabled=false` on its row (no API mutation is
exposed by design).

## Audit log (read-only)

```
GET /api/v1/audit?search_id={id}&limit=100
```

Append-only entries: `search_submitted`, `search_completed` (with sources
searched, duration, results found, report reference), `search_failed`.

## Health

```
GET /health   →  {"status": "ok", "version": "0.1.0"}
```
