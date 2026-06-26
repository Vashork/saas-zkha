# Main audit remediation roadmap

Branch: `audit/main-hardening-followup`
Base: `main`

This roadmap is based on the independent senior code/security audit of `main` after the audit/security fixes, partial payments, backup/restore rollback, mounted remote backup, audit log, health check and production hardening work.

## Release verdict

- Private/internal pilot: acceptable only behind VPN/local network, after a fresh backup of `data/` and focused manual QA.
- Public internet production: not ready until the High findings below are closed.

## Rules for this branch

- Keep commits small and reviewable.
- Do not change production data schema without an explicit migration/backfill commit and a backup plan.
- Do not run destructive restore/cleanup changes without documenting manual QA.
- Prefer tests before behavior fixes when the bug can be isolated safely.

## Phase 1 — safe hardening, no DB migration

1. Fix documentation drift.
   - Update roadmap/readiness notes so they refer to `main` / this follow-up branch, not the old audit branch.
   - Make the go/no-go criteria match the current code.

2. Add payment invariant regression tests.
   - Parent `Payment.paid_amount` must equal the sum of `PaymentTransaction.amount` after transaction add/edit/delete.
   - Legacy parent edit must not desync existing child transactions.
   - Fixed payments must reject overpayment through every route, including direct POST flows.
   - Variable payments may top up above the current planned amount and must increase the planned amount.

3. Fix legacy `edit_payment` partial-payment behavior.
   - Do not directly mark a parent as paid when child transactions already exist.
   - Create a child transaction for the missing remainder or require the transaction flow.
   - Always recompute parent aggregate fields from transactions.

4. Harden remote mounted backup path handling.
   - Reject empty paths.
   - Reject paths inside app source, local backups, data, uploads or static directories.
   - Keep mounted remote backup as first phase; do not add SMB/SFTP credentials to SQLite.

5. Add audit rows for payment and contractor mutations.
   - Payment create/edit/delete.
   - Transaction add/edit/delete.
   - Receipt upload/delete.
   - Contractor create/edit/archive/delete.

## Phase 2 — migration and data safety

6. Add explicit migration/backfill for partial payments.
   - Existing paid `payments.paid_amount`, `paid_date`, `receipt_file` become one initial `PaymentTransaction` when no transactions exist.
   - Migration must be idempotent.
   - Manual backup is mandatory before running this on real data.

7. Add migration tooling.
   - Prefer Alembic.
   - Add a schema version trail.
   - Convert ad-hoc `_run_migrations()` into versioned migrations over time.

8. Serialize backup and restore operations.
   - Add a process/file lock shared by manual backup, scheduled backup, local restore and upload restore.
   - Prevent scheduled backup from archiving half-restored `data/`.

## Phase 3 — public production blockers

9. Protect receipts.
   - Validate file content with magic bytes, not only extension.
   - Serve receipts through authenticated download endpoints instead of public `/uploads`.

10. Harden Docker/nginx public deployment.
    - Add HTTPS deployment documentation.
    - Add HTTP to HTTPS redirect.
    - Add HSTS only behind HTTPS.
    - Run containers as non-root where practical.

11. Improve rate limiting.
    - Account-aware throttling.
    - Reverse-proxy-safe client IP handling.
    - Optional nginx `limit_req` for public deployments.

## Manual QA gate before merging this branch

- Login/logout/session cookies.
- CSRF on all POST forms.
- Non-admin direct POST rejection.
- Fixed and variable payments.
- Partial payment add/edit/delete recalculation.
- Receipts attached to transactions and parent payments.
- Local backup create/download/delete.
- Restore from local backup without manual Docker restart.
- Upload restore validation.
- Remote mounted backup success and remote failure mode.
- Audit log rows for backup/user/payment/contractor actions.
- Production config fail-fast with unsafe defaults.

## Dangerous changes that require backup first

- Any DB migration or backfill.
- Any restore/upload restore work.
- Any mass orphan receipt cleanup.
- Any change to `backup_history` constraints or storage enum.
- Any change that deletes or rewrites files under `data/`.
