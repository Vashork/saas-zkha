# Project roadmap

Branch: `audit/ui-backup-delete-button`

This roadmap keeps the remaining work ordered. Prefer small commits and run CI after risky changes.

## 1. Production blockers

- [x] Finish automated CSRF regression tests:
  - normal urlencoded forms with valid `_csrf` pass;
  - normal urlencoded forms without/invalid `_csrf` fail;
  - multipart forms with valid `_csrf` pass;
  - multipart forms without/invalid `_csrf` fail;
  - AJAX `/settings/theme` with valid `X-CSRF-Token` passes;
  - AJAX `/settings/theme` without/invalid `X-CSRF-Token` fails.
- [ ] Run backup/restore QA on a real Docker volume with an existing SQLite database.
- [ ] Verify or implement restore rollback if recovery fails after safety backup creation.

## 2. Partial payments and multiple receipts — before remote backup

Current `Payment` rows are unique per contractor/month. Do not simply allow duplicate monthly payments. Implement this as one monthly charge with multiple payment transactions/receipts.

- [ ] Add a child model for payment transactions, for example `PaymentTransaction`:
  - parent `payment_id`;
  - paid amount;
  - paid date;
  - receipt file;
  - notes;
  - created/updated timestamps.
- [ ] Keep one parent monthly charge per `contractor_id + year + month`.
- [ ] Calculate parent paid amount as the sum of child transactions.
- [ ] Show grouped transactions directly under the parent charge, so payments like `4500 + 500` stay next to each other.
- [ ] Allow adding another transaction only while the parent charge still has remaining debt.
- [ ] Keep one receipt per transaction, not one receipt per whole monthly charge.
- [ ] Add effective statuses:
  - `partial` / `partially paid` while there is remaining debt and the due date has not passed;
  - `partial_overdue` / `partially paid, overdue` when there is remaining debt and the due date has passed;
  - `paid` when the transaction sum covers the planned amount.
- [ ] Update filters and badges so `partial` and `partial_overdue` are visible without hiding them inside plain `overdue`.
- [ ] Add migration/backfill path: existing `paid_amount`, `paid_date`, `receipt_file` should become the first transaction during migration.
- [ ] Add tests for partial payments, grouped receipt visibility and remaining debt calculation.

## 3. Backup improvements — before Telegram bot work

- [ ] Keep local backup enabled by default.
- [ ] Add a collapsed UI block like `Remote backup` on the Backups page.
- [ ] In `Remote backup`, add remote target type selection:
  - `SFTP`;
  - `SMB`.
- [ ] Add a checkbox for remote backup mode: `Also keep a local backup copy`.
- [ ] Add scheduler destination checkboxes:
  - `local`;
  - `remote-sftp`;
  - `remote-smb`.
- [ ] Enforce that at least one scheduler destination is always enabled.
- [ ] Prefer mounted SMB folder support first, then add true SFTP/SMB transport code.
- [ ] Store secrets outside normal SQLite settings where possible: environment variables, mounted secret files, or deployment-level secret storage.
- [ ] Record separate local/remote result states in backup history so a local success with remote failure is visible.

## 4. Production hardening

- [ ] Add production configuration flags for secure cookies when HTTPS is enabled.
- [ ] Fail fast in production if `SECRET_KEY`, `ADMIN_PASSWORD` or `USER_PASSWORD` are left at defaults.
- [ ] Add structured audit logs for admin actions: user creation, permission updates, backup create/delete/restore.
- [ ] Add database-backed health checks, not only HTTP process liveness.
- [ ] Add migration tooling such as Alembic before future schema changes.
- [ ] Validate uploaded receipt MIME/content in addition to extension and size.

## 5. Telegram bot — last

- [ ] Return to Telegram bot improvements only after production blockers, partial payments, backup hardening and remote backup roadmap items above are handled.
