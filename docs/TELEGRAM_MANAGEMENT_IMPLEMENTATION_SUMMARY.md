# Telegram management implementation summary

This document consolidates the Telegram work that was split across temporary handoff notes and local AI patches on branch `audit/main-hardening-followup`.

## Scope covered

The Telegram management block now covers:

- P2-10 web UI for Telegram inbound journal;
- P2-11 Telegram journal settings and retention;
- P2-12 full admin management of the bot from web UI;
- P2-13 admin reply/edit for Telegram messages;
- P2-14 linking Telegram journal rows with business events.

## Final status

### P2-12 Full admin management from web UI

Completed:

- Telegram admin id and allowed user ids can be edited from `/telegram` and are stored in DB-backed `settings`.
- Runtime bot enable/disable is stored as `telegram_bot_enabled` and applied without rebuilding containers.
- Managed command toggles are stored in DB-backed settings and applied without rebuilding containers for:
  - `/start`;
  - `/help`;
  - `/balance`;
  - `/contractors`;
  - `/tglog`.
- DB-backed response templates are implemented for:
  - `/start`;
  - `/help`;
  - invalid payment format error;
  - invalid receipt file error;
  - payment confirmation.
- `/telegram` exposes admin UI for editing response templates.
- Preview rendering is shown before saving templates.
- Server-side placeholder validation rejects unsupported placeholders before DB writes.
- Audit log records runtime/access/command/template changes without storing full template text in audit details.

Key files:

- `app/bot/management.py`
- `app/bot/response_templates.py`
- `app/bot/security.py`
- `app/bot/handlers.py`
- `app/web/routes/telegram.py`
- `app/web/templates/telegram.html`
- `tests/test_telegram_runtime_management.py`
- `tests/test_telegram_response_templates.py`
- `tests/test_telegram_template_gui.py`
- `tests/test_telegram_gui.py`
- `tests/test_ui_assets.py`

Accepted validation evidence:

```text
template foundation targeted: 19 passed in 25.69s
full pytest after template foundation: 341 passed, 8 skipped in 108.92s

template UI targeted: 36 passed in 8.05s
full pytest after template UI: 345 passed, 8 skipped in 100.12s
warnings summary absent
```

### P2-14 Telegram journal linked with business events

Completed without a schema migration:

- `app/bot/business_events.py` provides helper functions for safe linkage.
- Telegram payment confirmations create `telegram_payment_recorded` audit events.
- Audit details include:
  - normalized `telegram_text_hash`;
  - Telegram chat/user metadata;
  - optional Telegram message id;
  - payment id;
  - contractor id/name;
  - amount;
  - year/month;
  - receipt saved flag.
- `/telegram` maps visible Telegram journal rows to matching `telegram_payment_recorded` audit events by normalized text hash.
- `telegram.html` renders compact linked business events under the matching Telegram journal row.
- No raw audit JSON is rendered in UI.

Key files:

- `app/bot/business_events.py`
- `app/bot/handlers.py`
- `app/web/routes/telegram.py`
- `app/web/templates/telegram.html`
- `tests/test_telegram_business_events.py`

Accepted validation evidence:

```text
targeted P2-14: 24 passed in 11.14s
full pytest after P2-14: 349 passed, 8 skipped in 99.08s
warnings summary absent
```

## Local AI patches included

Local AI applied the patches that were too large or blocked for the GitHub connector:

- backend Telegram response template foundation;
- handler wiring for DB-backed Telegram response templates;
- template editor UI and preview wiring;
- Telegram business-event linkage in `paid_handler`;
- `/telegram` route mapping from Telegram log rows to business audit events;
- UI rendering for linked business events;
- regression tests for the above.

## Temporary handoff files removed after consolidation

The following files were temporary implementation notes and are superseded by this summary:

- `docs/P2_12_TELEGRAM_RUNTIME_TOGGLE_HANDOFF.md`
- `docs/P2_12_TELEGRAM_TEMPLATES_HANDOFF.md`
- `docs/P2_14_TELEGRAM_BUSINESS_EVENTS_HANDOFF.md`

## Roadmap cleanup still needed

`docs/RELEASE_ROADMAP.md` should be made consistent with the latest evidence.

Recommended Telegram management block:

```markdown
### Telegram management block

1. [x] P2-10 Web UI для журнала Telegram-сообщений.
2. [x] P2-11 Настройки режима Telegram-журнала.
3. [x] P2-12 Полное admin-управление ботом из web UI:
   - [x] просмотр и изменение Telegram admin id / allowed user ids через БД/settings с audit log;
   - [x] runtime включение/выключение бота через DB/settings без пересборки контейнера;
   - [x] включение/выключение отдельных managed-команд без пересборки контейнера: `/start`, `/help`, `/balance`, `/contractors`, `/tglog`;
   - [x] настройка шаблонов ответов `/start`, `/help`, ошибок и подтверждений оплаты;
   - [x] предпросмотр шаблонов и validation placeholders перед сохранением;
   - [x] audit log изменений runtime/access/command-toggle/template Telegram-настроек;
   - validation: template UI targeted 2026-06-30 — `36 passed in 8.05s`; full pytest 2026-06-30 — `345 passed, 8 skipped in 100.12s`; warnings summary absent.
4. [x] P2-13 Управление ответами на входящие сообщения.
5. [x] P2-14 Связать Telegram-журнал с бизнес-событиями.
   - Telegram payment confirmations create `telegram_payment_recorded` audit events with Telegram metadata hash and payment context.
   - `/telegram` shows linked business events for visible Telegram log rows without storing full template text or adding a schema migration.
   - validation: targeted P2-14 tests `24 passed in 11.14s`; full pytest `349 passed, 8 skipped in 99.08s`; warnings summary absent.
```

## Validation command for release reviewer

```cmd
python -m pytest tests/test_telegram_business_events.py tests/test_telegram_response_templates.py tests/test_telegram_template_gui.py tests/test_telegram_runtime_management.py tests/test_telegram_gui.py tests/test_ui_assets.py tests/test_bot_receipt_upload.py && python -m pytest
```

Do not print secrets or full Compose config during validation. Use `docker compose config -q` only if Compose validation is needed.
