#!/bin/sh
set -e

mkdir -p /app/data/uploads /app/backups /var/log/zhkh-bot

exec python -m uvicorn app.web.main:app --host 0.0.0.0 --port 8000
