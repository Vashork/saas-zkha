#!/bin/sh
set -e
mkdir -p /app/data/uploads /var/log/zhkh-bot
python init_db.py
python -m uvicorn app.web.main:app --host 0.0.0.0 --port 8000
