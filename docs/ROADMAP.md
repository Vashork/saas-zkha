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

## 2. Backup improvements — before Telegram bot work

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

## 3. Production hardening

- [ ] Add production configuration flags for secure cookies when HTTPS is enabled.
- [ ] Fail fast in production if `SECRET_KEY`, `ADMIN_PASSWORD` or `USER_PASSWORD` are left at defaults.
- [ ] Add structured audit logs for admin actions: user creation, permission updates, backup create/delete/restore.
- [ ] Add database-backed health checks, not only HTTP process liveness.
- [ ] Add migration tooling such as Alembic before future schema changes.
- [ ] Validate uploaded receipt MIME/content in addition to extension and size.

## 4. Telegram bot — last

- [ ] Return to Telegram bot improvements only after production blockers, backup hardening and remote backup roadmap items above are handled.
