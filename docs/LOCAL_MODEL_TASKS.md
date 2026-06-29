# LOCAL MODEL TASKS

Branch: `audit/main-hardening-followup`

This file replaces the old `docs/LOCAL_AI_TODO.md`. The old file may be deleted locally after this file is accepted.

## Current active tasks

### P2-17 operator business CRUD

Status: completed locally.

Completed:

- `app/web/permissions.py`: operator gets `BUSINESS_ACTION_PERMISSIONS`.
- `tests/test_action_permissions.py`: operator is expected to have business permissions and no system permissions.
- `tests/test_permissions.py`: operator creates contractor, creates payment, adds transaction, updates paid amount/status, and remains blocked from user management.
- Targeted validation: `30 passed`.
- Full validation: `287 passed, 4 skipped, 7 warnings in 71.22s`.
- `docs/RELEASE_ROADMAP.md`: P2-17 marked `[x]`; P2-18/P2-19/P2-20 remain open.

### P2-DOCKER-1 Docker hardening follow-up

Status: implementation completed through GitHub connector; tests/config validated locally; Docker build/smoke validation still pending because the pinned nginx image cannot be pulled from Docker CDN in the local environment.

Completed in branch:

- Added root `.dockerignore`.
- Split runtime and dev dependencies: runtime `requirements.txt`; dev/test `requirements-dev.txt`.
- Removed `curl` and `gosu` from web/bot runtime images.
- Switched web/bot Dockerfiles to `USER zhkh`.
- Simplified web/bot startup scripts so they no longer perform root-to-user privilege dropping.
- Replaced curl healthcheck with Python stdlib healthcheck.
- Pinned nginx image to `nginx:1.27-alpine`.
- Added OCI labels and `EXPOSE 8000` for the web image.
- Added `no-new-privileges:true` for web, bot, and nginx.
- Updated `tests/test_docker_runtime.py` to assert the new hardened runtime model.
- Updated `docs/DOCKER_HARDENING_TODO.md` with validation, Windows command, and bind-mount ownership notes.

Local validation confirmed by user on Windows cmd.exe, 2026-06-29:

- `python -m pip install -r requirements-dev.txt`: ok.
- `python -m compileall app init_db.py tests && python -m pytest`: `284 passed, 8 skipped, 5 warnings in 60.22s`.
- `docker compose config`: ok; config shows `nginx:1.27-alpine`, Python stdlib healthcheck, `APP_UID`/`APP_GID`, and `no-new-privileges:true`.

Still required before fully closing:

- Successful pull/build with the pinned nginx image: `docker pull nginx:1.27-alpine` and `docker compose up -d --build`.
- Manual smoke on newly built containers: `/health`, login, Telegram bot startup logs, backup page, receipt upload/download, clean `docker compose logs web bot nginx`.

Current blockers observed locally:

- `docker pull nginx:1.27-alpine` fails with `failed to copy ... production.cloudfront.docker.com ... EOF`, so the new pinned nginx image is not available locally yet.
- `docker compose up -d --build` fails for the same image pull reason.
- `docker compose ps` still shows an older running `zhkh-nginx` based on `nginx:alpine`, so the current running stack cannot be used as final Docker hardening smoke evidence.
- Bot logs show `Cannot connect to host api.telegram.org:443` / DNS failures; this is an external network/Telegram reachability issue, not a bind-mount permission or non-root startup error.

### P1-AUDIT-1 remaining production validation

Still open:

- `pip-audit -r requirements.txt`
- Docker smoke: build/up, `/health`, login smoke, Telegram bot startup logs

Already confirmed by user after P2-16:

- full pytest: `287 passed, 4 skipped, 7 warnings in 75.47s`
- `docker-compose config`: ok
