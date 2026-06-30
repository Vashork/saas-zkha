# P2-14 handoff: link Telegram log with business events

## Context

The first safe helper was added in `app/bot/business_events.py`.

It provides:

- `telegram_text_hash(text)` for privacy-preserving linkage;
- `telegram_message_link_details(message)` for safe Telegram metadata;
- `telegram_payment_business_details(...)` for audit-safe payment event details.

The GitHub connector blocked the larger `app/bot/handlers.py` replacement needed to wire this into the payment handler. Apply the rest locally as a reviewed patch. Do not bypass this with runtime hacks.

## Goal

Close P2-14 by linking Telegram journal rows with business events without a schema migration.

Use existing `audit_log.details` as the bridge:

- when Telegram bot records a payment, write an audit event;
- include `telegram_text_hash`, `telegram_chat_id`, `telegram_user_id`, optional Telegram `message_id`, payment id, contractor id/name, amount, period and whether receipt was saved;
- in `/telegram`, show matching business events next to visible Telegram log rows by matching the row text hash to audit event details.

This avoids adding nullable columns to `telegram_message_log` and avoids a DB migration.

## Local patch tasks

### 1. Wire payment handler

In `app/bot/handlers.py`:

- import `log_admin_action` from `app.audit`;
- import `telegram_payment_business_details` from `app.bot.business_events`;
- after successful `apply_bot_payment(...)` and before `session.commit()`, enqueue audit action:
  - action: `telegram_payment_recorded`;
  - entity_type: `payment`;
  - entity_id: `payment.id`;
  - actor: `None`;
  - details from `telegram_payment_business_details(...)`.

Keep the existing payment confirmation rendering unchanged.

### 2. Show linked events in web UI

In `app/web/routes/telegram.py`:

- import `json` if not already available;
- import `AuditLog`;
- import `telegram_text_hash`;
- for currently visible `TelegramMessageLog` rows, compute the hash for each row text;
- query `AuditLog` for action `telegram_payment_recorded` and details containing those hashes;
- parse details safely;
- pass `telegram_business_events` to the template as a dict keyed by Telegram log row id.

Event display can be compact:

- audit id;
- created_at;
- action;
- contractor name;
- amount;
- period;
- payment id;
- receipt saved flag.

### 3. Render in `app/web/templates/telegram.html`

In the Telegram log table, under the message text or in a small separate block, show linked business events for that row.

Use safe escaped template rendering. Do not render raw JSON.

### 4. Tests

Add `tests/test_telegram_business_events.py` covering:

- `telegram_text_hash` is stable and whitespace-normalized;
- helper details include Telegram ids, hash, payment id, amount, period and receipt flag;
- route-level mapping links a Telegram log row to a matching `telegram_payment_recorded` audit event;
- template/source-level check confirms UI contains business event rendering markers.

Recommended targeted command:

```cmd
python -m pytest tests/test_telegram_business_events.py tests/test_telegram_gui.py tests/test_bot_receipt_upload.py
```

Then full suite:

```cmd
python -m pytest
```

## Evidence needed

Expected evidence before closing P2-14:

- targeted P2-14 tests passed;
- full pytest passed;
- skipped count unchanged or explained;
- warnings summary absent.

## Roadmap update target

After evidence, update `docs/RELEASE_ROADMAP.md`:

```markdown
5. [x] P2-14 Связать Telegram-журнал с бизнес-событиями.
   - Telegram payment confirmations create `telegram_payment_recorded` audit events with Telegram metadata hash and payment context.
   - `/telegram` shows linked business events for visible Telegram log rows without storing full template text or adding a schema migration.
   - validation: targeted P2-14 tests `... passed`; full pytest `... passed, ... skipped`; warnings summary absent.
```
