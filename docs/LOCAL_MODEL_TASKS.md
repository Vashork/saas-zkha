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

Status: implementation completed through GitHub connector; Docker build/smoke validation still pending.

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
- Updated `docs/DOCKER_HARDENING_TODO.md` with validation and bind-mount ownership notes.

Still required before fully closing:

- `python -m pip install -r requirements-dev.txt`
- `python -m compileall app init_db.py tests && python -m pytest`
- `docker compose config`
- `APP_UID=$(id -u) APP_GID=$(id -g) docker compose up -d --build`
- Manual smoke: `/health`, login, Telegram bot startup logs, backup page, receipt upload/download, clean `docker compose logs web bot nginx`.

### P1-AUDIT-1 remaining production validation

Still open:

- `pip-audit -r requirements.txt`
- Docker smoke: build/up, `/health`, login smoke, Telegram bot startup logs

Already confirmed by user after P2-16:

- full pytest: `287 passed, 4 skipped, 7 warnings in 75.47s`
- `docker-compose config`: ok
