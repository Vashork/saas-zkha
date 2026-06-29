#!/bin/sh
set -e

mkdir -p /app/data/uploads /var/log/zhkh-bot

if [ "$(id -u)" = "0" ]; then
    chown -R zhkh:zhkh /app/data /var/log/zhkh-bot 2>/dev/null || true
    exec gosu zhkh python -m app.bot.main
fi

exec python -m app.bot.main
