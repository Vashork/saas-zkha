# Local AI implementation summary

Branch: `audit/main-hardening-followup`

This file consolidates completed local-AI and connector-handoff work. It replaces temporary handoff notes that were used while some large patches had to be applied locally.

## Completed areas

### Release/docs and CI

- README aligned with hardened release state.
- Dependency audit workflow added.
- Docker smoke helper and tests added.
- Pytest warning cleanup completed.

### Docker hardening

- Runtime/dev dependencies split.
- Runtime images hardened and simplified.
- Non-root web/bot runtime model added.
- Docker smoke validation completed locally.

### Roles, permissions and audit guardrails

- Role foundation added: `admin`, `operator`, `viewer`.
- Action-level permissions added for business/system/sensitive operations.
- Operator business CRUD completed while system/admin actions remain restricted.
- User-management presets and UI guidance added.
- Self-lockout/user-management audit guardrails added.
- Access matrix tests added for helpers and route-level behavior.

### Telegram management

- Admin-only Telegram journal UI added.
- Telegram journal settings and retention added.
- Telegram admin id and allowlist editable through DB-backed web settings.
- Runtime bot toggle added.
- Managed command toggles added for `/start`, `/help`, `/balance`, `/contractors`, `/tglog`.
- DB-backed Telegram response templates added.
- Template editor UI, preview and placeholder validation added.
- Telegram reply/edit UI added.
- Telegram payment confirmations linked to business audit events without a schema migration.

## Latest accepted validation evidence

```text
P2-12 template UI targeted: 36 passed in 8.05s
P2-12 full pytest: 345 passed, 8 skipped in 100.12s

P2-14 targeted: 24 passed in 11.14s
P2-14 full pytest: 349 passed, 8 skipped in 99.08s
warnings summary absent
```

Earlier accepted evidence is preserved in `docs/RELEASE_ROADMAP.md` for P2-AUDIT, P2-16, P2-17, P2-18, P2-19 and P2-20.

## Key files added or heavily changed

- `app/web/permissions.py`
- `app/bot/management.py`
- `app/bot/response_templates.py`
- `app/bot/business_events.py`
- `app/bot/security.py`
- `app/bot/handlers.py`
- `app/web/routes/telegram.py`
- `app/web/templates/telegram.html`
- `app/web/templates/settings.html`
- `tests/test_action_permissions.py`
- `tests/test_role_matrix.py`
- `tests/test_route_permission_matrix.py`
- `tests/test_user_management_audit.py`
- `tests/test_telegram_runtime_management.py`
- `tests/test_telegram_response_templates.py`
- `tests/test_telegram_template_gui.py`
- `tests/test_telegram_business_events.py`
- `scripts/docker_smoke_check.py`

## Temporary notes superseded by this file

These files were temporary and can be removed after this summary is committed:

- `docs/LOCAL_MODEL_TASKS.md`
- `docs/P2_16_NEXT.md`
- `docs/P2_18_LOCAL_PATCH.md`
- `docs/P2_20_LOCAL_ROUTE_MATRIX.md`
- `docs/P2_12_TELEGRAM_RUNTIME_TOGGLE_HANDOFF.md`
- `docs/P2_12_TELEGRAM_TEMPLATES_HANDOFF.md`
- `docs/P2_14_TELEGRAM_BUSINESS_EVENTS_HANDOFF.md`
- `docs/TELEGRAM_MANAGEMENT_IMPLEMENTATION_SUMMARY.md`

## Roadmap cleanup still needed

`docs/RELEASE_ROADMAP.md` should be updated so the Telegram management block uses the latest evidence:

```markdown
3. [x] P2-12 Полное admin-управление ботом из web UI:
   - [x] просмотр и изменение Telegram admin id / allowed user ids через БД/settings с audit log;
   - [x] runtime включение/выключение бота через DB/settings без пересборки контейнера;
   - [x] включение/выключение отдельных managed-команд без пересборки контейнера: `/start`, `/help`, `/balance`, `/contractors`, `/tglog`;
   - [x] настройка шаблонов ответов `/start`, `/help`, ошибок и подтверждений оплаты;
   - [x] предпросмотр шаблонов и validation placeholders перед сохранением;
   - [x] audit log изменений runtime/access/command-toggle/template Telegram-настроек;
   - validation: template UI targeted 2026-06-30 — `36 passed in 8.05s`; full pytest 2026-06-30 — `345 passed, 8 skipped in 100.12s`; warnings summary absent.
5. [x] P2-14 Связать Telegram-журнал с бизнес-событиями.
   - validation: targeted P2-14 tests `24 passed in 11.14s`; full pytest `349 passed, 8 skipped in 99.08s`; warnings summary absent.
```
