# Project roadmap

Branch: `audit/main-hardening-followup`
Base: `main`

This roadmap keeps the remaining work ordered after the independent audit of `main`. Prefer small commits and run CI after risky changes.

For the detailed remediation plan, see `docs/AUDIT_REMEDIATION_ROADMAP.md`.

## 1. Production blockers

- [x] Finish automated CSRF regression tests:
  - normal urlencoded forms with valid `_csrf` pass;
  - normal urlencoded forms without/invalid `_csrf` fail;
  - multipart forms with valid `_csrf` pass;
  - multipart forms without/invalid `_csrf` fail;
  - AJAX `/settings/theme` with valid `X-CSRF-Token` passes;
  - AJAX `/settings/theme` without/invalid `X-CSRF-Token` fails.
- [x] Run backup/restore QA on a real Docker volume with an existing SQLite database.
  - Manual QA previously confirmed: local restore works without container restart.
  - Manual QA previously confirmed: downloaded backup can be uploaded and restored.
- [x] Verify or implement restore rollback if recovery fails after safety backup creation.
  - `recover_from_backup()` creates a safety backup and attempts automatic rollback if restore fails after `data/` was touched.
  - Regression tests cover successful restore, rollback after copy failure and unsafe archive rejection.
- [x] Add production cookie flags and startup validation.
  - `APP_ENV=production` rejects default `SECRET_KEY`, `ADMIN_PASSWORD` and `USER_PASSWORD`.
  - `COOKIE_SAMESITE=none` requires `COOKIE_SECURE=true`.
- [ ] Add explicit migration/backfill for legacy paid payments into `PaymentTransaction` rows.
- [ ] Add backup/restore locking so scheduled backup cannot archive half-restored data.
- [ ] Protect receipts before public internet deployment.

## 2. Partial payments and multiple receipts

Current `Payment` rows are unique per contractor/month. Do not allow duplicate monthly parent payments. Keep one monthly charge with multiple payment transactions/receipts.

- [x] Add a child model for payment transactions:
  - parent `payment_id`;
  - paid amount;
  - paid date;
  - receipt file;
  - notes;
  - created/updated timestamps.
- [x] Keep one parent monthly charge per `contractor_id + year + month`.
- [x] Calculate parent paid amount as the sum of child transactions in normal transaction add/edit/delete flows.
- [x] Show grouped transactions directly under the parent charge, so payments like `4500 + 500` stay next to each other.
- [x] Keep one receipt per transaction, not one receipt per whole monthly charge.
- [x] Add effective statuses:
  - `partial` / `partially paid` while there is remaining debt and the due date has not passed;
  - `partial_overdue` / `partially paid, overdue` when there is remaining debt and the due date has passed;
  - `paid` when the transaction sum covers the planned amount.
- [x] Update filters and badges so `partial` and `partial_overdue` are visible without hiding them inside plain `overdue`.
- [ ] Add regression tests for parent aggregate invariants across all mutation routes.
- [ ] Fix legacy `/payments/{payment_id}/edit` so it cannot desync parent aggregate fields from child transactions.
- [ ] Add migration/backfill path: existing `paid_amount`, `paid_date`, `receipt_file` should become the first transaction during migration.

Implementation note: `payments.paid_amount` remains as a compatibility aggregate for dashboard/history while `payment_transactions` stores per-receipt payment rows.

## 3. Backup improvements — before Telegram bot work

- [x] Keep local backup enabled by default.
- [x] Add a collapsed UI block like `Remote backup` on the Backups page.
- [x] In `Remote backup`, add remote target type selection:
  - `SFTP`;
  - `SMB`.
- [x] Add a checkbox for remote backup mode: `Also keep a local backup copy`.
- [x] Add scheduler destination checkboxes:
  - `local`;
  - `remote-sftp`;
  - `remote-smb`.
- [x] Enforce that at least one scheduler destination is always enabled.
- [x] Prefer mounted SMB folder support first, then add true SFTP/SMB transport code.
  - First phase implemented: copy the local archive to an already-mounted remote folder, for example `/mnt/zhkh-backups`.
- [x] Store secrets outside normal SQLite settings where possible: environment variables, mounted secret files, or deployment-level secret storage.
  - First phase stores no SMB/SFTP credentials in the app; credentials stay in the external mount configuration.
- [x] Record separate local/remote result states in backup history so a local success with remote failure is visible.
  - Existing SQLite constraint supports `local` and `synology`; the UI displays `synology` history rows as `remote` until a future migration broadens the storage enum.
- [x] Reject remote mounted backup targets inside local app/data/backup/source directories.
- [ ] Add a shared backup/restore lock.
- [ ] Add true SFTP/SMB transport code after migration tooling exists.

## 4. Production hardening

- [x] Add production configuration flags for secure cookies when HTTPS is enabled.
- [x] Fail fast in production if `SECRET_KEY`, `ADMIN_PASSWORD` or `USER_PASSWORD` are left at defaults.
- [x] Add structured audit logs for admin actions: user creation, permission updates, backup create/delete/restore.
- [x] Add database-backed health checks, not only HTTP process liveness.
- [ ] Add structured audit logs for contractor/payment mutations.
- [ ] Add migration tooling such as Alembic before future schema changes.
- [ ] Validate uploaded receipt MIME/content in addition to extension and size.
- [ ] Serve private receipts through authenticated download endpoints before public internet deployment.
- [ ] Add public production nginx/TLS documentation and HSTS behind HTTPS.

## 5. Telegram bot — last

- [ ] Return to Telegram bot improvements only after production blockers, partial payments, backup hardening and remote backup roadmap items above are handled.
