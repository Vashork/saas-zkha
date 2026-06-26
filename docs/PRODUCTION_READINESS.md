# Production readiness audit

Branch: `audit/ui-backup-delete-button`

This file tracks architecture and production-readiness work that could not be fully verified from the GitHub connector session.

## Current verdict

Status: **internal pilot ready after local rebuild**.

The branch is suitable for local/private testing behind VPN after rebuilding containers. Internet-facing production still needs the P1 hardening items below.

## Fixed in this branch session

- Added shared template configuration in `app/web/template_engine.py`.
- Moved route template globals wiring out of ad-hoc inline setup in `app/web/main.py`.
- Migrated `dashboard`, `history`, `analytics`, `backups` and `contractors` routes to use the shared template engine directly.
- Migrated remaining legacy `auth` and `payments` routes to the shared template engine directly.
- Removed the temporary `payments.payment_color_class = payment_color_class` compatibility assignment from `app/web/main.py`.
- Added a guard for `GET /settings` so page-level permissions are enforced while legacy routes are being refactored.
- Fixed `/backups/settings`: it imported `parse_retention`, `parse_frequency`, `parse_time` but called missing `_parse_retention`, `_parse_frequency`, `_parse_time` functions.
- Added a detailed manual QA plan in `docs/QA_PLAN.md`.
- Added GitHub Actions CI in `.github/workflows/ci.yml`, `pytest.ini` and `docs/CI_SETUP.md`.
- Confirmed CI completed successfully after workflow setup.
- Kept the earlier CSRF fixes for urlencoded and multipart form submissions.
- Added automated permission tests for unauthenticated redirects, settings page denial, admin-only user management, contractor/payment mutation denial and admin positive paths.
- Added automated CSRF middleware regression tests for urlencoded forms, multipart forms and AJAX `X-CSRF-Token` requests.
- Added `docs/ROADMAP.md` and placed remote backup work before Telegram bot work.
- Added partial payments with `PaymentTransaction` rows, grouped receipts, partial statuses and variable-payment top-up support.
- Added restore rollback in `app/backup_service.py`: if restore fails after the safety backup is created, the original `data/` is restored from that safety backup.
- Added backup service regression tests for successful restore, failed restore rollback and unsafe archive rejection.
- Manual QA confirmed backup/restore on a real Docker volume: local restore works without container restart, and downloaded backup upload/restore works.
- Added mounted remote backup first phase: UI settings, local/remote destination validation, manual copy to mounted remote path, scheduler support and separate local/remote history rows.

## Remaining blockers before production

### P0 — must fix before production

No known P0 blockers for local/private pilot after the latest manual backup/restore QA.

### P1 — should fix before public deployment

1. Add production configuration flags for secure cookies when HTTPS is enabled.
2. Make `SECRET_KEY`, `ADMIN_PASSWORD` and `USER_PASSWORD` fail-fast in production if left at defaults.
3. Add structured audit logs for admin actions: user creation, permission updates, backup create/delete/restore.
4. Add DB migration tooling such as Alembic before future schema changes are made in future releases.
5. Add health checks that validate database access, not only HTTP process liveness.
6. Add security headers in nginx or FastAPI middleware: HSTS behind HTTPS, CSP, X-Frame-Options, Referrer-Policy.
7. Validate uploaded receipt MIME/content in addition to extension and size.
8. Add true SFTP/SMB transport code after migration tooling exists. Current remote backup phase expects the remote target to be mounted outside the application.

## CI status

CI is active and currently covers:

- dependency installation from `requirements.txt`;
- syntax check with `python -m compileall app tests`;
- minimal FastAPI app import check;
- unit tests with `python -m pytest tests/ -v`, including CSRF, permission, payment and backup-service regressions.

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
- Partial payment transactions and separate receipts work.
- Variable payment top-up above current balance increases the monthly charge.
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
- Restore valid backup works without container restart.
- Downloaded backup can be uploaded and restored.
- Mounted remote backup copies archives to the configured path when that path is available to the container.

Check as non-admin:

- Hidden admin buttons are not visible.
- Direct POST to admin-only endpoints is rejected.
- Page permissions are respected for dashboard, payments, history, contractors, analytics and settings.

## Notes

The application is a solid MVP for local/private use. Public internet-facing production should wait until the P1 hardening items above are closed.
