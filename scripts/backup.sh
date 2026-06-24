#!/bin/bash
# Simple backup script for Mode C (local/WSL)
# Creates a tar.gz of database and uploads

set -euo pipefail

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/zhkh-backup-${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "📦 Creating backup: ${BACKUP_FILE}"

tar -czf "${BACKUP_FILE}" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='backups' \
    --exclude='logs' \
    --exclude='*.log' \
    app/ \
    data/ \
    docker/ \
    docker-compose.yml \
    requirements.txt \
    init_db.py \
    .env 2>/dev/null || true

SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "✅ Backup created: ${BACKUP_FILE} (${SIZE})"

# Cleanup backups older than 7 days
find "${BACKUP_DIR}" -name "zhkh-backup-*.tar.gz" -mtime +7 -delete 2>/dev/null || true
echo "🧹 Old backups cleaned up"
