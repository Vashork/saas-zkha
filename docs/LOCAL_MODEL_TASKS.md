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

Status: audit findings recorded in `docs/DOCKER_HARDENING_TODO.md`; implementation not started.

Do not combine this with P2-17 unless explicitly requested. Docker build and smoke must be confirmed before closing this item.

### P1-AUDIT-1 remaining production validation

Still open:

- `pip-audit -r requirements.txt`
- Docker smoke: build/up, `/health`, login smoke, Telegram bot startup logs

Already confirmed by user after P2-16:

- full pytest: `287 passed, 4 skipped, 7 warnings in 75.47s`
- `docker-compose config`: ok
