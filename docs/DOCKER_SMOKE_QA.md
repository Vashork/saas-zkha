# Docker smoke QA

Branch: `audit/main-hardening-followup`

Purpose: make P2-AUDIT-4 reproducible without printing secrets or full Compose output.

## Boundaries

- Do not run or paste full `docker compose config`; it may expose `.env` values.
- Use only quiet Compose validation: `docker compose config -q`.
- If a Telegram token or other secret appears in logs, chat, screenshots, or artifacts, treat it as compromised and rotate it.
- This QA is runtime evidence, so it must be executed locally or in a CI runner with Docker Compose available; the GitHub connector cannot execute it.

## Automated baseline smoke

Recommended command:

```bash
python scripts/docker_smoke_check.py
```

The script detects Docker Compose plugin or legacy `docker-compose` and performs:

1. quiet Compose validation with `config -q`;
2. `docker compose build --no-cache web bot`;
3. `docker compose up -d --build`;
4. `docker compose ps`;
5. `/health` through nginx until it returns healthy JSON;
6. `/login` reachability;
7. `/uploads/...` blocked as `401`, `403`, or `404`;
8. bounded `web`, `nginx`, and `bot` log tails scanned for smoke-blocking terms such as `permission denied`, `traceback`, and `startup failed`.

Useful options:

```bash
python scripts/docker_smoke_check.py --skip-build
python scripts/docker_smoke_check.py --skip-up
python scripts/docker_smoke_check.py --base-url http://localhost:8080
python scripts/docker_smoke_check.py --skip-logs
```

## Manual authenticated smoke evidence

The baseline script is intentionally non-destructive and does not require app credentials. Capture these manual checks after the baseline passes:

1. Login page:
   - open `/login`;
   - authenticate with local smoke credentials;
   - confirm dashboard loads.
2. Backup page:
   - open `/backups`;
   - confirm the page loads without 500;
   - if safe for the environment, create a backup and confirm it appears in the list.
3. Receipt upload/download:
   - upload a small valid PDF/JPG/PNG receipt through the payment UI;
   - confirm upload succeeds;
   - open the receipt through `/payments/receipts/{path}` while authenticated;
   - confirm direct `/uploads/...` access is not public.
4. Telegram bot startup:
   - confirm `docker compose logs --tail=120 bot` shows polling startup when a token is configured;
   - if no token is configured in a local smoke environment, confirm the bot container stays up with the expected warning and no crash loop.
5. Logs:
   - confirm `web`, `nginx`, and `bot` logs contain no startup errors, permission errors, tracebacks, or secret dumps.

## Evidence format for closing P2-AUDIT-4

Paste a concise result like this:

```text
python scripts/docker_smoke_check.py: SUCCESS
/manual login: ok
/backups page: ok
receipt upload/download: ok
bot logs: polling started / or expected no-token warning, no crash loop
web/nginx/bot logs: no startup/permission errors
```

Do not include full Compose config output or secret values.
