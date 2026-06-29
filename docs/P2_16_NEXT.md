# P2-16 NEXT — local model handoff

Branch: `audit/main-hardening-followup`

Goal: finish action-level permissions. Keep runtime behavior safe: admin works as before, operator/viewer do not get mutations yet.

## 1. Already done

- Added `app/web/permissions.py`.
- Added `tests/test_action_permissions.py`.
- Converted contractor create/update/delete/toggle to named action checks.
- Operator is modeled, but mutation actions are still disabled until P2-17.

## 2. First local check

Run before editing payments:

`python -m pytest tests/test_action_permissions.py tests/test_permissions.py`

Fix failures before continuing.

## 3. Convert payments route

File: `app/web/routes/payments.py`

Replace the mutation-only role gate with a named action gate using `has_action_permission` from `app.web.permissions`.

Map routes to actions:

- add payment: `PAYMENTS_CREATE`
- edit payment: `PAYMENTS_UPDATE`
- delete payment: `PAYMENTS_DELETE`
- add transaction: `PAYMENT_TRANSACTIONS_CREATE`
- edit transaction: `PAYMENT_TRANSACTIONS_UPDATE`
- delete transaction: `PAYMENT_TRANSACTIONS_DELETE`
- cleanup orphan receipts: `PAYMENTS_RECEIPTS_CLEANUP`

Keep receipt download unchanged unless adding tests: it already uses page access, safe path check and ownership check.

## 4. Update tests

Extend `tests/test_action_permissions.py`:

- assert payments route imports/uses `has_action_permission`;
- assert payments route uses the payment and transaction action names above;
- assert payments route no longer has direct `current_user.role != "admin"` mutation gate.

Keep `tests/test_permissions.py` behavior:

- admin can still mutate contractors/payments;
- operator still cannot mutate contractors/payments in P2-16;
- viewer and legacy user still cannot mutate contractors/payments.

## 5. Sensitive admin areas

After payments is green, add named checks or source-level coverage for sensitive areas:

- users/settings: `USERS_MANAGE`, `SYSTEM_SETTINGS_MANAGE`
- Telegram: `TELEGRAM_MANAGE`
- backups/restore: `BACKUPS_MANAGE`, `BACKUPS_RESTORE`

Do not give these actions to operator.

## 6. Validation

Run targeted:

`python -m pytest tests/test_action_permissions.py tests/test_permissions.py tests/test_theme_scope.py tests/test_telegram_gui.py`

Run full:

`python -m pytest`

## 7. Close criteria

Close P2-16 only when:

- contractor actions use named checks;
- payments actions use named checks;
- sensitive admin areas are covered by named checks or tests;
- targeted pytest is green;
- full pytest is green.

Then update `docs/RELEASE_ROADMAP.md`: mark P2-16 `[x]`, keep P2-17 open.

## 8. Boundaries

- No DB schema change in P2-16.
- No page permission semantic change in P2-16.
- No operator CRUD until P2-17.
- No weakening Telegram, backups, users or system settings.
