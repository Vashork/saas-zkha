# P2-14 Telegram business events handoff — applied

This file used to contain the local handoff for linking Telegram journal rows with business events after the GitHub connector blocked a large `app/bot/handlers.py` replacement.

## Current branch state

P2-14 is implemented without a schema migration:

- `app/bot/business_events.py` provides `telegram_text_hash`, safe Telegram metadata extraction and Telegram payment audit details.
- Successful Telegram payment confirmations enqueue `telegram_payment_recorded` audit events from `paid_handler`.
- Audit details include Telegram metadata hash, chat/user metadata, optional Telegram message id, payment id, contractor id/name, amount, year/month and receipt flag.
- `/telegram` maps visible `TelegramMessageLog` rows to `telegram_payment_recorded` audit events using normalized text hashes.
- `telegram.html` renders linked business events under the matching Telegram journal row.
- Regression coverage exists in `tests/test_telegram_business_events.py`.

## Validation evidence

Accepted local Windows/Python 3.13 evidence:

```text
targeted: 24 passed in 11.14s
full pytest: 349 passed, 8 skipped in 99.08s
warnings summary absent
```

## Roadmap note

`docs/RELEASE_ROADMAP.md` already marks P2-14 as closed. If updating the validation line, prefer the latest evidence above rather than older local evidence with different collected/skipped counts.
