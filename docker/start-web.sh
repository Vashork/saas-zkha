#!/bin/sh
set -e

mkdir -p /app/data/uploads /app/backups /var/log/zhkh-bot

if [ "$(id -u)" = "0" ]; then
    chown -R zhkh:zhkh /app/data /app/backups /var/log/zhkh-bot 2>/dev/null || true
    exec gosu zhkh python -m uvicorn app.web.main:app --host 0.0.0.0 --port 8000
fi

exec python -m uvicorn app.web.main:app --host 0.0.0.0 --port 8000
