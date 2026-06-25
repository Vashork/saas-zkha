# Production readiness audit

Branch: `audit/ui-backup-delete-button`

This file tracks architecture and production-readiness work that could not be fully verified from the GitHub connector session.

## Current verdict

Status: **internal pilot only**.

The branch is not yet ready for an internet-facing production deployment. It can be tested locally or behind VPN after rebuilding containers and running manual QA.

## Fixed in this branch session

- Added shared template configuration in `app/web/template_engine.py`.
- Moved route template globals wiring out of ad-hoc inline setup in `app/web/main.py`.
- Migrated `dashboard`, `history`, `analytics`, `backups` and `contractors` routes to use the shared template engine directly.
- Added a guard for `GET /settings` so page-level permissions are enforced while legacy routes are being refactored.
- Fixed `/backups/settings`: it imported `parse_retention`, `parse_frequency`, `parse_time` but called missing `_parse_retention`, `_parse_frequency`, `_parse_time` functions.
- Added a detailed manual QA plan in `docs/QA_PLAN.md`.
- Kept the earlier CSRF fixes for urlencoded and multipart form submissions.

## Remaining blockers before production

### P0 — must fix before production

1. Finish route template refactor for remaining legacy modules: `auth`, `payments`.
2. Remove the temporary `payments.payment_color_class = payment_color_class` compatibility assignment from `app/web/main.py` by refactoring `payments.py` directly.
3. Add automated tests for CSRF on normal forms, multipart forms and AJAX theme save.
4. Add automated tests for page permissions, especially `/settings`, admin-only user management and contractor/payment mutations.
5. Run backup/restore QA on a real Docker volume with an existing SQLite database.
6. Verify restore rollback behavior when recovery fails after the safety backup is created.
7. Add CI that runs syntax checks, unit tests and at least a minimal app import test.

### P1 — should fix before public deployment

1. Add production configuration flags for secure cookies when HTTPS is enabled.
2. Make `SECRET_KEY`, `ADMIN_PASSWORD` and `USER_PASSWORD` fail-fast in production if left at defaults.
3. Add structured audit logs for admin actions: user creation, permission updates, backup create/delete/restore.
4. Add DB migration tooling such as Alembic before schema changes are made in future releases.
5. Add health checks that validate database access, not only HTTP process liveness.
6. Add security headers in nginx or FastAPI middleware: HSTS behind HTTPS, CSP, X-Frame-Options, Referrer-Policy.
7. Validate uploaded receipt MIME/content in addition to extension and size.

## CI files

The CI workflow could not be committed by the connector safety filter during this session. Add the generated files manually from the provided `ci_files_for_project.zip` archive:

- `.github/workflows/ci.yml`
- `pytest.ini`
- `docs/CI_SETUP.md`

## Manual QA checklist

The detailed QA procedure is in `docs/QA_PLAN.md`.

Quick smoke check after `git pull` and rebuild:

```bash
docker compose up -d --build
docker logs zhkh-web -f
```

Check as admin:

- Login works.
- `/payments` opens without 500.
- Add payment works.
- Edit payment works.
- Upload receipt works.
- Delete payment works.
- `/settings/save` works without 403.
- Create user works without 403.
- Edit user permissions works.
- Create contractor works without 403.
- Edit contractor works.
- Archive/delete contractor works.
- Create backup works.
- Save backup settings works.
- Delete backup works.
- Upload invalid backup is rejected.
- Restore valid backup works and app should be restarted after restore.

Check as non-admin:

- Hidden admin buttons are not visible.
- Direct POST to admin-only endpoints is rejected.
- Page permissions are respected for dashboard, payments, history, contractors, analytics and settings.

## Notes

The application is a solid MVP for local/private use, but production release should wait until the P0 items above are closed and QA is performed against the actual deployment environment.
