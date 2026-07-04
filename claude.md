# Senior Software Architect & Lead Developer Prompt — Adverse Intelligence Platform (MVP)

You are an expert software architect, senior full-stack developer, DevOps engineer, AI engineer, UX designer, and application-security specialist.

Design and build a production-ready web application called **Adverse Intelligence Platform (AIP)**, delivered as a focused **MVP**.

The application is intended for legitimate business due diligence, compliance, KYC, AML support, supplier vetting, recruitment screening (where legally permitted), and reputational risk assessment.

The platform must be **modular, maintainable, and secure**, and is designed to run **locally or within a single organisation**. It is not a multi-tenant SaaS product at this stage.

---

## MVP Scope & Guiding Principles

This build targets a first working version for a small business. The following principles apply throughout:

- **Individuals only.** The platform searches for people. There is no company search, company profile, or company-centric functionality.
- **No authentication or user accounts.** The application runs locally or inside a trusted organisation network. There is no login, JWT, OAuth, MFA, roles, permissions, or user management anywhere in the system.
- **Modular monolith.** A single deployable application composed of clear internal modules, not a set of microservices.
- **Lean infrastructure.** Docker Compose, a single PostgreSQL database, and background workers only where they add real value.
- **Extensible by design.** The connector framework must remain modular so new data sources can be added later without touching core logic.

Features explicitly deferred to Phase 2 are listed at the end of this document.

---

## Primary Objective

The software allows a user to search for an **individual** and automatically gathers publicly available information from a defined set of sources, normalises the results, removes duplicates, performs identity matching, calculates a risk score, summarises findings using AI, and generates a professional report.

Each search produces and stores a single report. There is no case management in the MVP.

---

## Technology Stack

**Backend**

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL (single database)
- httpx (async HTTP for connectors)
- A lightweight background worker for the search pipeline (see Architecture)

**Frontend**

- React
- TypeScript
- Material UI
- React Query
- React Router

**Infrastructure**

- Docker Compose
- Nginx reverse proxy
- GitHub Actions CI/CD

There is **no** authentication stack, no Elasticsearch/OpenSearch, no Kubernetes, and no cloud-provider-specific deployment (AWS/Azure) in the MVP. The application is designed to run via Docker Compose on a local machine or a single host.

---

## Application Architecture

Design the project as a **modular monolith**: one FastAPI application with clearly separated internal modules and a background worker for longer-running work. Each module has a well-defined interface so it can evolve or be extracted later.

Modules:

- **Search Module** — accepts and validates search input, orchestrates the search pipeline, tracks search status.
- **Connector Framework** — the modular interface all data-source connectors implement, plus the registry that discovers and runs them.
- **Identity Matching Engine** — compares returned records against the search subject and assigns confidence scores.
- **Risk Scoring Engine** — applies configurable weightings to matched findings and produces an overall risk level.
- **AI Summarisation Module** — uses an LLM to summarise, deduplicate, and structure findings.
- **Report Generator** — assembles the final report (PDF / HTML / JSON) and stores it.
- **Search History & Audit Module** — records an append-only history of every search and its metadata.

Each module should be isolated, dependency-injected where appropriate, and easily extendable.

---

## Search Interface

The search form is deliberately simple:

- **Full Name** (required)
- **Date of Birth** (optional)
- **Country** (optional)

No other identifiers are collected as input. In keeping with data minimisation, no national identifiers (such as National Insurance numbers) are collected or stored.

---

## Search Sources (Connectors)

The MVP ships with a reduced, UK-focused connector set. The connector framework remains modular so additional sources can be added later without modifying core logic.

Initial connectors:

- **Google Search** — general public web results.
- **News API** — adverse media / news coverage.
- **UK Companies House** — used only to surface a person's **directorships** (officer appointments), not for company search.
- **UK Insolvency Register** — bankruptcies and insolvency records.
- **UK Sanctions List** — sanctions matches.
- **FCA Warning List** — regulatory warnings.

Each connector must:

- run independently
- support retries
- support rate limiting
- log failures
- record execution time
- return structured JSON in a common normalised shape

Connectors call external APIs and are run concurrently (async) so one slow source does not block the others.

---

## Search Workflow

When a user submits a search:

1. Validate input (Full Name required; DOB and Country optional).
2. Create a search job and return a search ID immediately.
3. Run the enabled connectors concurrently in the background.
4. Normalise results into a common structure.
5. Remove duplicates.
6. Perform identity matching against the search subject.
7. Assign a confidence score to each candidate record.
8. Calculate the overall risk score.
9. Generate an AI summary.
10. Generate and store a downloadable report.
11. Write an append-only audit entry.

The API exposes the search's status throughout, so the frontend can poll until the report is ready.

---

## Identity Matching

Implement a confidence-scoring engine that never assumes two records belong to the same person. Use weighted matching across the signals available in this MVP:

- Full name (including obvious variants)
- Date of birth (where provided)
- Country
- Directorship records (from Companies House)
- Addresses / locations where surfaced by a source

Produce a confidence percentage per candidate record (for example 98%, 92%, 84%, 61%) and expose it in the report so the user can judge relevance. Weightings are defined in configuration.

---

## Risk Scoring

Create a configurable scoring engine. Weightings live in a config file (there are no admin accounts to edit them at runtime in the MVP). Factors map to the MVP connector set, for example:

| Finding | Example weight |
|---|---|
| Sanctions list match | 100 |
| Director disqualification | 90 |
| Bankruptcy / insolvency | 70 |
| FCA regulatory warning | 70 |
| Serious adverse media (e.g. fraud, money laundering) | 60 |
| General negative media | 20 |

Risk levels:

- Low
- Medium
- High
- Critical

Weightings and thresholds must be configurable so the model can be tuned without code changes.

---

## AI Analysis

Use an LLM to:

- summarise findings
- remove duplicate information
- highlight key concerns
- produce an executive summary
- generate a chronological timeline
- identify recurring themes or allegations
- highlight legal outcomes
- suggest areas for further investigation

The AI must **not** make definitive legal conclusions or state allegations as facts. It must clearly distinguish between allegations, investigations, and proven outcomes, and the report must separate verified records from AI-generated summary text.

---

## Reporting

Each search generates and stores a single report. Support the following formats:

- PDF
- HTML
- JSON

Each report includes:

- Executive Summary
- Search Parameters
- Confidence Scores
- Risk Score
- Timeline
- Sources
- Supporting Links
- AI Summary
- Recommendations
- Appendices

Reports include a timestamp and a unique reference number.

---

## Dashboard

Provide a clean, modern dashboard showing:

- **Recent Searches**
- **Search Status**
- **High Risk Searches**
- **Quick Search**

---

## Search History & Audit

Maintain a complete, append-only history of searches. For each search, record:

- Timestamp
- Search parameters (Full Name, DOB, Country)
- Sources searched
- Duration
- Results found
- Report reference / version

Audit entries must not be deletable. Because there are no user accounts, no user or organisation identity is recorded.

---

## Public API

Expose a documented REST API covering the minimum needed to drive the MVP:

- **Submit Search** — accept a search request, return a search ID.
- **Search Status** — return the current status of a search by ID.
- **Retrieve Report** — return the stored report for a completed search.

Generate OpenAPI documentation automatically.

---

## Database Design

Create a normalised PostgreSQL schema in a **single database**. Suggested tables:

- Searches
- Search Results
- Sources (connector registry / metadata)
- Reports
- AI Summaries
- Risk Scores
- Audit Logs

There are no Users, Roles, Permissions, Cases, Monitoring Jobs, or Notifications tables in the MVP.

---

## Frontend Requirements

- Responsive
- Modern UI
- Dark Mode
- Light Mode
- Accessibility compliant
- Fast loading
- Results filtering, sorting, and pagination
- Export functionality (download reports)

---

## Security

The application runs locally or within a trusted organisation network, so authentication is out of scope. Sensible application-level protections still apply because the system processes personal data:

- HTTPS in transit
- Input validation
- Rate limiting (API and outbound connectors)
- Encryption at rest for stored personal data
- SQL injection protection
- XSS protection
- CSRF protection
- Secrets management (API keys for connectors and the LLM)
- Audit logging

There is no JWT, role-based access, session management, or account lockout, as there are no accounts.

---

## Performance

Sized for a small business, not enterprise scale:

- Background processing for the search pipeline so the API stays responsive
- Concurrent (async) execution of connectors
- Caching where it clearly helps
- Retry queues for flaky external sources

Enterprise concerns (100,000-search targets, horizontal scaling, high concurrent-user counts) are out of scope for the MVP.

---

## Compliance

Design the application to support compliance with applicable privacy and data-protection laws (such as UK GDPR). Requirements:

- Auditability (append-only search history)
- Configurable data retention
- Data minimisation (only Full Name, optional DOB, optional Country are collected)
- Lawful processing of personal data
- Clear distinction between verified records and AI-generated summaries
- Links back to original sources
- Support for licensed data providers
- Respect for website terms of service; avoid unauthorised scraping

---

## Testing

Provide:

- Unit tests
- API tests
- Basic integration tests

Target **70–80% code coverage**.

---

## DevOps

Provide:

- Docker Compose
- Production Dockerfiles
- GitHub Actions CI
- Environment variables / example env file
- Database migrations
- Seed data
- Health checks
- Logging
- A basic backup note (e.g. `pg_dump`)

Kubernetes, cloud-provider deployment targets, and disaster-recovery tooling are out of scope for the MVP.

---

## Documentation

Produce:

- README
- Architecture Overview
- API Documentation
- Deployment Guide

---

## Code Quality

- Follow SOLID principles.
- Use dependency injection where appropriate.
- Write clean, maintainable, well-documented code.
- Avoid duplication.
- Design the application so additional connectors can be added without modifying the core application.

---

## Deliverables

Produce the project incrementally. For each stage provide:

1. Folder structure
2. Source code
3. Database schema
4. API endpoints
5. Frontend components
6. Tests
7. Docker configuration
8. Documentation

Do not skip implementation details or replace them with placeholders. Where functionality depends on external providers, implement the connector interface with working example implementations and clear configuration points for API keys and licensed data sources. Build the project in logical phases, ensuring each phase is complete, tested, and ready before moving to the next.

---

## Phase 2 (Out of MVP Scope)

The following are deliberately excluded from the MVP and planned for a later phase. The MVP architecture should not prevent them:

- **Continuous Monitoring** — daily/weekly/monthly monitoring of individuals, detection of new adverse media, and comparison reports.
- **Alerts & Notifications** — email, webhook, Microsoft Teams, Slack, and (future) SMS.
- **Case Management** — cases, notes, owners, status tracking, document uploads, and case export.
- **Additional Connectors** — e.g. PEP datasets, wider sanctions/court/regulatory sources, and non-UK jurisdictions.
- **Authentication & Multi-Tenancy** — accounts, roles, and permissions, if the platform is later offered beyond a single trusted environment.
