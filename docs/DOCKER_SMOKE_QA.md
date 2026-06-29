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
2. sequential `web` and `bot` image builds with `--no-cache` and one retry per service;
3. `docker compose up -d` without forcing a second parallel rebuild;
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
python scripts/docker_smoke_check.py --build-attempts 3
python scripts/docker_smoke_check.py --skip-logs
```

## P2-AUDIT-4 evidence

Status: completed locally.

2026-06-29, Windows/Python 3.13.14, user-provided local run:

```text
python -m pytest tests/test_docker_smoke_script.py -v: 5 passed in 0.17s
python scripts/docker_smoke_check.py: SUCCESS
Docker Compose command: docker compose
quiet Compose validation: ok
web image build: ok
bot image build: ok
docker compose up -d: web healthy, nginx running, bot started
/health: {"status":"ok","database":"ok","scheduler":"running"}
/login: reachable
/uploads public access: blocked with HTTP 404
web logs: startup complete, scheduler started, no smoke-blocking errors
nginx logs: configuration complete, ready for start up
bot logs: polling started
manual login/dashboard: ok
/backups page: ok
receipt upload/download: ok
```

P2-AUDIT-4 is closed by this evidence. Do not include full Compose config output or secret values in future smoke evidence.
