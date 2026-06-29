#!/bin/sh
set -e

mkdir -p /app/data/uploads /var/log/zhkh-bot

exec python -m app.bot.main
