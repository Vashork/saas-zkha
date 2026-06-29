# LOCAL MODEL TASKS

Branch: `audit/main-hardening-followup`

This file replaces the old `docs/LOCAL_AI_TODO.md`. The old file may be deleted locally after this file is accepted.

## Current active tasks

### P2-17 operator business CRUD

Status: started.

Already committed:

- `app/web/permissions.py`: operator now gets `BUSINESS_ACTION_PERMISSIONS`.
- `tests/test_action_permissions.py`: operator is expected to have business permissions and no system permissions.

What still needs local work:

1. Update `tests/test_permissions.py`.
   - Replace old test `test_operator_cannot_mutate_contractors_or_payments_until_action_permissions`.
   - New behavior: operator can mutate business contractors/payments.
   - Keep assertion that operator still cannot manage users/settings.

2. Suggested route-level test behavior:
   - operator creates a contractor;
   - operator creates a payment for that contractor;
   - operator adds a payment transaction;
   - assert payment becomes paid or paid_amount is updated;
   - operator tries `auth.create_user(...)` and must get `/settings?error=`;
   - created user must not exist.

3. Keep existing viewer/legacy-user deny tests.

4. Run targeted validation:

`python -m pytest tests/test_action_permissions.py tests/test_permissions.py tests/test_theme_scope.py tests/test_telegram_gui.py`

5. Run full validation:

`python -m compileall app init_db.py tests && python -m pytest`

6. If green, update `docs/RELEASE_ROADMAP.md`:
   - mark P2-17 `[x]`;
   - keep P2-18/P2-19/P2-20 open;
   - record full pytest result.

Boundaries:

- Do not grant operator `USERS_MANAGE`.
- Do not grant operator `SYSTEM_SETTINGS_MANAGE`.
- Do not grant operator `TELEGRAM_MANAGE`.
- Do not grant operator `BACKUPS_MANAGE` or `BACKUPS_RESTORE`.
- Do not change DB schema in P2-17.
- Do not change page permission semantics.

### P1-AUDIT-1 remaining production validation

Still open:

- `pip-audit -r requirements.txt`
- Docker smoke: build/up, `/health`, login smoke, Telegram bot startup logs

Already confirmed by user after P2-16:

- full pytest: `287 passed, 4 skipped, 7 warnings in 75.47s`
- `docker-compose config`: ok
