# QA plan for `audit/ui-backup-delete-button`

This checklist is intended for manual verification after pulling the branch and rebuilding Docker containers.

## 0. Preparation

```bash
git checkout audit/ui-backup-delete-button
git pull
docker compose down
docker compose up -d --build
docker logs zhkh-web -f
```

Expected result:

- `zhkh-web` starts without traceback.
- `/health` returns `{"status":"ok"}`.
- No repeating CSRF, import, scheduler or DB errors in logs.

## 1. Smoke test

Open the web UI and verify:

- `/login` opens.
- Admin login works.
- `/` dashboard opens.
- `/payments` opens without HTTP 500.
- `/history` opens.
- `/contractors` opens.
- `/analytics` opens.
- `/settings` opens for admin.
- `/backups` opens for admin.

Stop immediately if any page returns 500. Save the last 100 lines from `docker logs zhkh-web`.

## 2. CSRF checks

The previous bug was `CSRF token missing`, so verify all POST forms.

As admin:

- Save settings on `/settings`.
- Create a user on `/settings`.
- Update user permissions.
- Change a user's password.
- Create a contractor.
- Edit contractor.
- Archive or delete contractor.
- Add payment.
- Edit payment.
- Delete payment.
- Upload receipt on a payment.
- Cleanup orphan receipts.
- Save backup settings.
- Create backup.
- Delete backup.

Expected result:

- No HTTP 403 for valid forms.
- No `CSRF token missing` warning in logs for valid forms.
- Invalid/direct POST without `_csrf` should still return 403.

## 3. Permissions checks

Create a non-admin user with limited page access.

### User with only dashboard access

Expected:

- `/` opens.
- `/payments`, `/history`, `/contractors`, `/analytics`, `/settings` redirect or deny access.
- Direct POST to `/payments/add`, `/contractors/add`, `/settings/save`, `/backups/create` must be rejected.

### User with settings access but non-admin role

Expected:

- `/settings` opens if the page permission includes settings.
- Admin-only blocks should not be usable.
- Direct user-management POST must redirect with admin-only error.

## 4. Payments checks

As admin:

- Create fixed contractor.
- Create variable contractor.
- Add fixed monthly payment without manually entering amount.
- Add variable pending payment without amount.
- Try marking variable payment as paid without amount.
- Enter amount and mark it as paid.
- Change status back to pending.
- Upload PDF receipt under 10 MB.
- Try uploading unsupported extension.
- Try uploading file above configured max size.
- Delete payment and confirm receipt file is removed from `data/uploads`.

Expected:

- Status labels and amounts are consistent.
- No payment page 500.
- Uploaded receipts are stored under `data/uploads/YYYY/MM/` only.

## 5. Contractors checks

As admin:

- Create contractor with fixed amount.
- Create contractor with variable payment type.
- Edit name, due day, payment type and fixed amount.
- Try invalid amount.
- Try duplicate contractor name if unique constraint exists.
- Archive/deactivate contractor.

Expected:

- Validation errors are visible in UI.
- No database integrity traceback is exposed to user.

## 6. Backup and restore checks

Before this block, make a copy of the whole project directory or at least `data/`.

As admin:

- Open `/backups`.
- Save backup settings.
- Create backup.
- Download created backup.
- Delete one backup.
- Upload invalid `.tar.gz` without `data/zhkh.db`.
- Upload archive with unsafe paths such as `../` in a test-only environment.
- Restore from a valid backup.
- Restart containers after restore.

Expected:

- Invalid archives are rejected.
- Valid restore creates a safety backup first.
- After restore, login and core pages still work.
- No data outside `data/` is overwritten.

## 7. Browser/UI checks

Check in normal browser and incognito/private window:

- Theme switch works.
- Logout clears session.
- Back button after logout does not allow protected actions.
- Mobile width does not hide critical actions.
- Forms show human-readable errors.

## 8. Security checks

Using browser dev tools or curl:

- Session cookie is HttpOnly.
- CSRF cookie exists.
- Admin-only endpoints reject non-admin session.
- Direct upload URL access is acceptable for the deployment model; if receipts are private, `/uploads` must be protected before production.
- Security headers from nginx are present if the deployment uses nginx.

## 9. Final go/no-go criteria

Ready for internal pilot if:

- All smoke tests pass.
- All valid POST forms avoid 403.
- Permissions checks pass.
- Backup create/delete works.
- Restore was tested at least once on a copy of real data.
- No unhandled traceback appears in logs during QA.

Not ready for public production if any P0 item in `docs/PRODUCTION_READINESS.md` is still open.
