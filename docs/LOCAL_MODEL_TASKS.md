# LOCAL MODEL TASKS

Branch: `audit/main-hardening-followup`

This file replaces the old `docs/LOCAL_AI_TODO.md`. The old file may be deleted locally after this file is accepted.

## Current active tasks

### P2-AUDIT-2 README hardened-state alignment

Status: completed via GitHub connector.

Completed:

- `README.md`: aligned with current hardened release state.
- Public `/uploads` wording was removed; receipt downloads are documented through authenticated `/payments/receipts/{path}` with safe path and ownership checks.
- Telegram allowlist, `/tglog [N]`, `/telegram`, DB settings over env fallback, and rotation guidance for leaked bot credentials are documented.
- Production startup checklist now covers production env, unique app secret, non-default passwords, secure cookies behind HTTPS, and quiet Compose validation only.
- `tests/test_readme_release_docs.py`: added README regression tests for receipt docs, production/Compose guidance, and Telegram allowlist management docs.

Connector limitation:

- Tests were not executed by the GitHub connector. Run locally:
  - `python -m pytest tests/test_readme_release_docs.py -v`
  - `python -m pytest tests/test_docker_runtime.py -v`
  - optionally full `python -m pytest`

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

Status: completed locally.

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
- Updated `docs/DOCKER_HARDENING_TODO.md` with validation, Windows command, bind-mount ownership notes, and final smoke result.

Local validation confirmed by user on Windows cmd.exe, 2026-06-29:

- `python -m pip install -r requirements-dev.txt`: ok.
- `python -m compileall app init_db.py tests && python -m pytest`: `284 passed, 8 skipped, 5 warnings in 59.09s`.
- `docker compose config`: ok; config shows `nginx:1.27-alpine`, Python stdlib healthcheck, `APP_UID`/`APP_GID`, and `no-new-privileges:true`.
- `docker pull python:3.11-slim`: ok.
- `docker pull nginx:1.27-alpine`: ok.
- `docker compose build --no-cache web bot`: ok.
- `docker compose up -d --build`: ok.
- `docker compose ps`: web healthy, nginx up on `nginx:1.27-alpine`, bot up.
- `curl -f http://localhost/health`: health ok.
- `docker compose exec -T web id`: `uid=1000(zhkh) gid=1000(zhkh)`.
- `docker compose exec -T bot id`: `uid=1000(zhkh) gid=1000(zhkh)`.
- web logs: no startup or permission errors.
- nginx logs: startup ok.
- bot logs: polling started.

### P1-AUDIT-1 remaining production validation

Status: completed locally.

Completed:

- Dependency audit through `pip-audit -r requirements.txt`: no known vulnerabilities found.
- Docker smoke: build/up, `/health`, login redirect/page evidence in web logs, bot startup logs, nginx startup logs.

Already confirmed by user after P2-16:

- full pytest: `287 passed, 4 skipped, 7 warnings in 75.47s`
- quiet Compose validation: ok
