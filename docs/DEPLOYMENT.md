# Deployment Guide

The platform deploys with Docker Compose on a local machine or a single host.
Kubernetes and cloud-specific targets are deliberately out of MVP scope.

> **No Docker?** For a single machine or a small team, the one-click
> `start.bat` / `start.sh` at the repo root runs the entire platform as one
> Python process with SQLite — see "Easiest start" in the README. Docker
> remains the recommended path for a shared server (PostgreSQL, separate
> worker, nginx, PDF export).

## 1. Prerequisites

- Docker Engine + Compose v2
- Two open ports (default: 8080 for the web UI; 5432 stays internal)

## 2. Configure

```bash
cp .env.example .env
```

Minimum production edits in `.env`:

| Variable | Action |
|---|---|
| `POSTGRES_PASSWORD` | Set a strong password |
| `ENCRYPTION_KEY` | Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `AUTH_SECRET` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` (signs login cookies) |
| `AUTH_USERNAME` / `AUTH_PASSWORD_HASH` | Run `python -m app.set_password` from `backend/` (writes both). If left empty, the UI asks on first launch — but in Docker that choice only lasts until the container is recreated, so set them here for anything long-lived |
| `MOCK_CONNECTORS` | `false` for real sources |
| Connector keys | See README table |
| `ANTHROPIC_API_KEY` | For AI summaries (optional — falls back to template) |
| `DATA_RETENTION_DAYS` | Your retention policy (default 365) |

> ⚠️ Set `ENCRYPTION_KEY` **before** first use and treat it like a secret: it
> encrypts subject names/DOBs at rest, and losing it makes existing rows
> unreadable. Store a copy in your password manager.

## 3. Run

```bash
docker compose up --build -d
docker compose ps          # db healthy, api healthy, worker + web running
```

Migrations (`alembic upgrade head`) and source seeding run automatically when
the API container starts. The stack:

| Service | Image | Role |
|---|---|---|
| `db` | postgres:16-alpine | Single database (volume `pgdata`) |
| `api` | backend Dockerfile | REST API :8000 (internal) |
| `worker` | backend Dockerfile | Search pipeline + retention job |
| `web` | frontend Dockerfile | nginx: SPA + reverse proxy :8080 |

## 4. HTTPS

Traffic inside the compose network is private; expose only `web`. For HTTPS,
terminate TLS at nginx:

1. Obtain a certificate (internal CA, or self-signed for a LAN tool):
   ```bash
   openssl req -x509 -newkey rsa:4096 -nodes -days 825 \
     -keyout aip.key -out aip.crt -subj "/CN=aip.internal"
   ```
2. Mount the pair into the `web` service and add a TLS server block to
   `frontend/nginx.conf`:
   ```nginx
   server {
       listen 443 ssl;
       ssl_certificate     /etc/nginx/certs/aip.crt;
       ssl_certificate_key /etc/nginx/certs/aip.key;
       # ...same locations as the port-80 server...
   }
   server { listen 80; return 301 https://$host$request_uri; }
   ```
3. In `docker-compose.yml`, publish `443:443` and mount `./certs:/etc/nginx/certs:ro`.

Alternatively put Caddy or Traefik in front for automatic certificates.

## 5. Backups

The only state is PostgreSQL. Nightly dump example (host cron):

```bash
docker compose exec -T db pg_dump -U aip aip | gzip > backups/aip-$(date +%F).sql.gz
```

Restore:

```bash
gunzip -c backups/aip-2026-07-04.sql.gz | docker compose exec -T db psql -U aip aip
```

Keep backups and the `ENCRYPTION_KEY` together — a dump without the key does
not contain readable personal data (which is also why off-site copies of the
dump alone are low-risk).

## 6. Operations

- **Logs:** `docker compose logs -f api worker`
- **Health:** `GET /health`; compose healthchecks gate startup ordering.
- **Scale workers:** `docker compose up -d --scale worker=2` (safe — job claims
  use `FOR UPDATE SKIP LOCKED`).
- **Upgrade:** `git pull && docker compose up --build -d` (migrations run on boot).
- **Retention:** the worker purges completed searches older than
  `DATA_RETENTION_DAYS` every 6 hours; audit entries are never purged.
- **Tuning risk/matching:** edit `backend/config/*.yaml` and restart `api`+`worker`.
