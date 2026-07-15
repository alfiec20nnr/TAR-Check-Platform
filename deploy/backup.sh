#!/usr/bin/env bash
# Nightly database backup for the hosted stack. Install as a host cron job:
#
#   0 2 * * * /srv/aip/app/deploy/backup.sh >> /srv/aip/backups/backup.log 2>&1
#
# Dumps PostgreSQL, keeps 30 days locally, and (when rclone is configured
# with a remote named `aip-backups`) copies the dump off-site. Dumps contain
# Fernet-encrypted personal data — unreadable without ENCRYPTION_KEY, which
# must be kept separately (password manager), never alongside the backups.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/aip/backups}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date +%F)"
OUT="$BACKUP_DIR/aip-$STAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

cd "$REPO_DIR"
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T db pg_dump -U "${POSTGRES_USER:-aip}" "${POSTGRES_DB:-aip}" \
  | gzip > "$OUT"

# Prune local dumps older than 30 days.
find "$BACKUP_DIR" -name 'aip-*.sql.gz' -mtime +30 -delete

# Off-site copy (optional): configure once with `rclone config`.
if command -v rclone >/dev/null && rclone listremotes | grep -q '^aip-backups:'; then
  rclone copy "$OUT" aip-backups:aip/
fi

echo "$(date -Is) backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
