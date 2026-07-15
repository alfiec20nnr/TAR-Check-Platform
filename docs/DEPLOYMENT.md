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
| Accounts | Live in the database, so they survive container recreation. Either let the UI create the first account on first launch, or create accounts up front: `docker compose exec api python -m app.users add <username>` |
| `LICENCE_KEY` | Machine activation code from the software provider (the UI shows the machine code and asks for it on first launch; in Docker set it here so it survives container recreation) |
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
- **Accounts:** `docker compose exec api python -m app.users add|list|reset|disable|remove <username>`
  (`add`/`reset` print a one-time password; users change it from the account menu).

## 7. Hosted on a VPS (internet-facing, multi-user)

One organisation's employees and clients share a single instance behind
HTTPS. Everything below assumes Ubuntu 24.04 on a small VPS (2 vCPU / 4 GB —
e.g. Hetzner CX22) with a DNS A record for your chosen hostname pointing at
it.

### 7.1 Harden the host (once)

```bash
adduser aip && usermod -aG sudo aip            # then copy your SSH key
# /etc/ssh/sshd_config: PasswordAuthentication no, PermitRootLogin no
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
apt install -y unattended-upgrades fail2ban
# Docker Engine + Compose v2 (v2.24+ needed): https://docs.docker.com/engine/install/ubuntu/
```

> Note: published container ports bypass ufw (Docker programs iptables
> directly). The prod override therefore publishes **only** Caddy's 80/443 —
> do not add host ports to other services.

Add Docker log rotation in `/etc/docker/daemon.json`:

```json
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
```

### 7.2 Configure

```bash
git clone <repo> /srv/aip/app && cd /srv/aip/app
cp .env.example .env
```

On top of the section-2 minimums, set the hosted-mode block in `.env`:

| Variable | Value |
|---|---|
| `AIP_DOMAIN` | Your hostname, e.g. `aip.client.co.uk` |
| `SESSION_COOKIE_SECURE` | `true` |
| `AUTH_ALLOW_SETUP` | `false` (accounts are seeded by CLI below) |
| `EXPOSE_API_DOCS` | `false` |
| `CORS_ORIGINS` | `https://<AIP_DOMAIN>` |
| `MOCK_CONNECTORS` | `false` + real connector keys |

### 7.3 Go live

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# Licence: the api logs print the machine code (stable — the host's
# /etc/machine-id is mounted in). Get an activation code issued for it and
# set LICENCE_KEY in .env, then restart the api service.
docker compose logs api | grep -i "machine code"

# Seed accounts BEFORE announcing the URL (setup is disabled):
docker compose exec api python -m app.users add jane.smith
```

Caddy obtains and renews the Let's Encrypt certificate automatically; verify
with `curl -fsS https://<AIP_DOMAIN>/health`.

### 7.4 Operate

- **Updates:** `./deploy/deploy.sh` (git pull + rebuild; migrations run on boot).
- **Backups:** install `deploy/backup.sh` as a nightly cron; keep
  `ENCRYPTION_KEY`, `AUTH_SECRET` and a copy of `.env` in a password manager —
  never alongside the dumps. Test a restore quarterly (section 5).
- **Monitoring:** point an uptime checker (e.g. UptimeRobot) at
  `https://<AIP_DOMAIN>/health`.
- **Joiners/leavers:** `python -m app.users add` / `remove` (or `disable` to
  keep the account); removal takes effect on the user's next request.
