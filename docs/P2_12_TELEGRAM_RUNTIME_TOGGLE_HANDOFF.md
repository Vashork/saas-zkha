# P2-12 handoff: Telegram runtime bot toggle

## Context

Branch: `audit/main-hardening-followup`.

GitHub connector accepted the safe runtime part:

- `app/bot/management.py` was added.
- `app/bot/security.py` now reads DB-backed `telegram_bot_enabled` on every inbound Telegram message and silently stops handler execution when it is disabled.
- Inbound messages are still written through the existing Telegram message log path before the disabled-bot return.

The connector blocked a larger full-file replacement for `app/web/routes/telegram.py`, so the remaining web UI / route patch is intentionally handed off here instead of applying a risky runtime workaround.

## Already applied behavior

New DB setting key:

- `telegram_bot_enabled`
- default: `1`
- accepted true-ish values: `1`, `true`, `yes`, `on`, `enabled`
- accepted false-ish values: `0`, `false`, `no`, `off`, `disabled`

Runtime behavior in middleware:

1. Load effective Telegram allowlist/admin id as before.
2. Load `telegram_bot_enabled` from DB settings.
3. Log inbound message according to current Telegram log settings.
4. If bot is disabled, return `None` before command/payment handlers.

## Remaining local patch to apply

### 1. `app/web/routes/telegram.py`

Import from `app.bot.management`:

```python
from app.bot.management import (
    DEFAULT_TELEGRAM_BOT_ENABLED,
    TELEGRAM_BOT_ENABLED_KEY,
    is_telegram_setting_enabled,
    normalize_telegram_enabled_value,
)
```

In `_settings_dict`, add default:

```python
values.setdefault(TELEGRAM_BOT_ENABLED_KEY, DEFAULT_TELEGRAM_BOT_ENABLED)
```

In `telegram_page`, pass template flag:

```python
"telegram_bot_enabled": is_telegram_setting_enabled(settings.get(TELEGRAM_BOT_ENABLED_KEY)),
```

In `save_telegram_settings`, change form params to optional values so separate forms do not reset omitted settings:

```python
telegram_log_mode: str | None = Form(None)
telegram_log_retention_days: str | None = Form(None)
telegram_log_retention_count: str | None = Form(None)
telegram_admin_id: str | None = Form(None)
telegram_allowed_user_ids: str | None = Form(None)
telegram_feature_settings_submitted: str | None = Form(None)
telegram_bot_enabled: str | None = Form(None)
```

At the beginning of the handler after permission checks, load current settings and use them as fallback for omitted fields:

```python
current_settings = await _settings_dict(db)
```

Use current values when form fields are `None` for log mode, retention, admin id and allowed ids. This fixes the current multi-form reset risk.

Add bot setting normalization:

```python
bot_enabled = current_settings.get(TELEGRAM_BOT_ENABLED_KEY, DEFAULT_TELEGRAM_BOT_ENABLED)
if telegram_feature_settings_submitted is not None:
    bot_enabled = normalize_telegram_enabled_value(telegram_bot_enabled, default=False)
```

Upsert the setting:

```python
await _upsert_setting(
    db,
    TELEGRAM_BOT_ENABLED_KEY,
    bot_enabled,
    "DB-backed Telegram bot kill switch; 1 включён, 0 выключен",
)
```

Add it to audit details:

```python
"telegram_bot_enabled": bot_enabled,
```

### 2. `app/web/templates/telegram.html`

In the Telegram settings form, add a marker and checkbox:

```html
<input type="hidden" name="telegram_feature_settings_submitted" value="1">

<div style="margin-top:18px;padding-top:18px;border-top:1px solid var(--border);">
    <h4 style="margin-bottom:12px;">🟢 Runtime-управление ботом</h4>
    <label style="display:flex;align-items:center;gap:10px;">
        <input type="checkbox" name="telegram_bot_enabled" value="1" {% if telegram_bot_enabled %}checked{% endif %}>
        <span>Бот включён</span>
    </label>
    <small style="color:var(--text-muted);display:block;margin-top:6px;">Сохраняется в БД и применяется middleware бота без пересборки контейнера. Если выключить, входящие сообщения продолжают логироваться по выбранному режиму, но обработчики команд и оплат не вызываются.</small>
</div>
```

In the status block, add:

```html
<div><strong>Runtime статус бота:</strong> {{ 'включён' if telegram_bot_enabled else 'выключен' }}</div>
```

### 3. `tests/test_ui_assets.py`

Add source-level regression tests confirming:

- template contains `telegram_feature_settings_submitted`;
- template contains `telegram_bot_enabled`;
- template shows runtime bot status;
- `app/bot/security.py` imports/uses `telegram_bot_runtime_settings` and `is_telegram_bot_enabled`;
- `app/web/routes/telegram.py` preserves `current_settings = await _settings_dict(db)`;
- route audit details include `"telegram_bot_enabled": bot_enabled`.

## Validation commands

Run targeted first:

```cmd
python -m pytest tests/test_ui_assets.py
```

Then full suite before considering any roadmap update:

```cmd
python -m pytest
```

Do not mark P2-12 complete from this patch alone. This only starts the runtime enable/disable part. Individual command toggles and response template management remain open.
