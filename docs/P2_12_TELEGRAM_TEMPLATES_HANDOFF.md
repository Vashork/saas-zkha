# P2-12 handoff: Telegram response templates

## Why this exists

The GitHub connector blocked the first attempt to add the backend template helper as a large code patch. Do not bypass this by scattering runtime workarounds. Apply this locally as one reviewed patch.

## Scope

Implement DB-backed Telegram response templates for the next P2-12 subtask:

- `/start` response;
- `/help` response;
- invalid payment format error;
- invalid receipt file error;
- payment confirmation response.

Do not close P2-12 yet. This block is only the backend/template foundation plus minimal wiring. Preview UI and full admin editing UI can be a follow-up patch unless included with tests.

## Proposed files

### Add `app/bot/response_templates.py`

Implement:

- managed template names in stable order;
- default template text matching current bot behavior;
- DB setting key format: `telegram_template_<name>`;
- allowed placeholder map;
- placeholder extraction for single-brace placeholders like `{amount}`;
- validation that rejects placeholders not allowed for that template;
- safe rendering using a context dict;
- async DB load from existing `Setting` rows with defaults as fallback.

Recommended managed names:

- `start`
- `help`
- `error_invalid_payment_format`
- `error_invalid_receipt_file`
- `payment_confirmation`

Recommended placeholders for `payment_confirmation` only:

- `contractor_name`
- `amount`
- `period`
- `receipt_saved_line`

All other templates should reject placeholders for now.

### Update `app/bot/handlers.py`

Wire the helper into:

- `start_handler`: answer rendered `start` template with `parse_mode="HTML"`;
- `help_handler`: answer rendered `help` template with `parse_mode="HTML"`;
- invalid `#оплачено` format branch: answer rendered `error_invalid_payment_format`;
- invalid receipt file branch: answer rendered `error_invalid_receipt_file`;
- successful payment confirmation: answer rendered `payment_confirmation`.

For `payment_confirmation`, pass context:

- escaped `contractor_name` for HTML safety;
- `amount`;
- `period`, for example `month_name(target_month) target_year`;
- `receipt_saved_line`, either empty string or newline plus receipt saved text.

Keep existing `parse_mode="HTML"` behavior.

### Add tests

Add `tests/test_telegram_response_templates.py` covering:

- default template names and setting key generation;
- placeholder extraction;
- invalid placeholder rejection;
- valid payment confirmation rendering;
- source-level wiring in `app/bot/handlers.py` for the five template names.

Run targeted first:

```cmd
python -m pytest tests/test_telegram_response_templates.py tests/test_bot_receipt_upload.py
```

Then full suite:

```cmd
python -m pytest
```

## Evidence needed before roadmap update

Expected evidence format:

- targeted template tests passed;
- full pytest passed;
- skipped count unchanged or explained;
- warnings summary absent.

After evidence, update `docs/RELEASE_ROADMAP.md` under P2-12, but do not mark the full P2-12 complete until admin editing UI, preview, placeholder validation through UI, and audit log for template changes are also covered.
