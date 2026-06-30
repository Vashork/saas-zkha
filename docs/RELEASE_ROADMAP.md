# Release roadmap and implementation summary

Branch: `docker/angie-dns-tls-roadmap`

This file is the single source of truth for the audit/release roadmap, local AI changes, Docker hardening evidence, permissions work, and Telegram management work.

## Release verdict

Internal/private pilot is acceptable after the latest green test run and manual QA.

Public internet production still requires operational checks:

* production `.env`;
* unique app secret;
* non-default passwords;
* HTTPS / secure cookies;
* backup before restore/data operations;
* Docker runtime smoke validation;
* no secrets, tokens, passwords, `.env` content, or full `docker compose config` output in review evidence.

Use quiet Compose validation only:

```cmd
docker compose config -q
```

## Latest accepted validation evidence

```text
Angie README/docs targeted re-run 2026-06-30: 14 passed in 0.14s
Angie README/docs full pytest re-run 2026-06-30: 354 passed, 4 skipped, 3 warnings in 128.79s
Docker Compose/smoke validation not captured in this local run: Docker CLI has no Compose v2 plugin, Docker Compose v1 requires Docker socket access, and current user is not in the docker group, so Docker socket access fails with PermissionError(13, 'Permission denied').

P2-12 Telegram template UI targeted: 36 passed in 8.05s
P2-12 full pytest: 345 passed, 8 skipped in 100.12s

P2-14 Telegram business events targeted: 24 passed in 11.14s
P2-14 full pytest: 349 passed, 8 skipped in 99.08s

warnings summary absent
```

Earlier accepted milestones:

```text
P2-AUDIT-5 warnings cleanup: 295 passed, 8 skipped in 72.32s, warnings summary absent
P2-18 user management GUI: 298 passed, 8 skipped in 75.95s
P2-19 audit/self-lockout guardrails: targeted 4 passed; full pytest 302 passed, 8 skipped
P2-20 access matrix tests: 328 passed, 8 skipped in 109.06s
```

## Completed P1 / production hardening

* [x] Empty page permissions semantics fixed:

  * legacy `NULL` remains legacy full access;
  * managed empty value means no page access.
* [x] Production validation blocks known unsafe default app secret values.
* [x] Backup restore has:

  * path/link validation;
  * unpacked-size limits;
  * lock;
  * rollback through safety backup.
* [x] Login rate limiting uses trusted reverse-proxy client IP headers only when the peer is trusted/private.
* [x] `/login` is covered by CSRF protection.
* [x] Receipt upload/download hardened:

  * web upload validates extension, size and magic bytes;
  * receipt download goes through authenticated route with ownership/safe-path checks;
  * Telegram receipt workflows validate extension, declared/actual size and magic bytes.
* [x] Dashboard payment status logic uses shared helpers.
* [x] Duplicate contractor name/slug edit errors are handled without 500.

## Completed audit/release docs and CI work

* [x] README aligned with hardened release state.
* [x] Dependency audit GitHub Actions workflow added.
* [x] Docker smoke helper added.
* [x] Docker smoke source tests added.
* [x] Pytest warning cleanup completed.

Key files:

```text
.github/workflows/dependency-audit.yml
tests/test_ci_security_gate.py
scripts/docker_smoke_check.py
tests/test_docker_smoke_script.py
tests/test_readme_release_docs.py
```

## Docker hardening

Completed:

* [x] Root `.dockerignore` added.
* [x] Runtime/dev dependencies split:

  * runtime: `requirements.txt`;
  * dev/test: `requirements-dev.txt`.
* [x] Web/bot images run as non-root `zhkh`.
* [x] `gosu` and runtime `curl` removed from web/bot images.
* [x] Startup scripts simplified; no root-to-user privilege dropping.
* [x] Healthcheck uses Python stdlib.
* [x] Angie image pinned to `docker.angie.software/angie:1.11.8-minimal`.
* [x] OCI labels and `EXPOSE 8000` added where applicable.
* [x] `no-new-privileges:true` added for services.
* [x] Docker runtime tests updated.
* [x] Angie/DNS/TLS follow-up is documented in `docs/PRODUCTION_DNS_TLS_ROADMAP.md`; DNS/TLS is not production-ready until real DNS, certificate issuance, and renewal dry-run evidence are captured.

Key files:

```text
.dockerignore
docker/Dockerfile.web
docker/Dockerfile.bot
docker-compose.yml
docker/start-web.sh
docker/start-bot.sh
tests/test_docker_runtime.py
```

Accepted Docker evidence:

```text
python -m pip install -r requirements-dev.txt: ok
python -m compileall app init_db.py tests && python -m pytest: 284 passed, 8 skipped, 5 warnings in 59.09s
docker compose config: ok
docker compose build --no-cache web bot: ok
docker compose up -d --build: ok
/health: ok
web/bot run as uid=1000(zhkh)
```

## Roles, permissions and audit guardrails

Completed:

* [x] Role foundation added:

  * `admin`;
  * `operator`;
  * `viewer`.
* [x] Legacy `user` maps to viewer-style behavior.
* [x] Action-level permissions added for business/system/sensitive operations.
* [x] Operator business CRUD enabled.
* [x] Operator remains blocked from system/admin actions.
* [x] User-management GUI presets added.
* [x] UI explains role/action/page permission split.
* [x] Self-lockout and user-management guardrails added.
* [x] Denied sensitive user-management attempts create audit log entries.
* [x] Role/action/route access matrix tests added.

Key files:

```text
app/web/permissions.py
app/web/routes/auth.py
app/web/routes/contractors.py
app/web/routes/payments.py
app/web/routes/backups.py
app/web/routes/system_settings.py
app/web/templates/settings.html
tests/test_action_permissions.py
tests/test_permissions.py
tests/test_role_matrix.py
tests/test_route_permission_matrix.py
tests/test_user_management_audit.py
tests/test_ui_assets.py
```

## Telegram management block

1. [x] P2-10 Web UI для журнала Telegram-сообщений.
2. [x] P2-11 Настройки режима Telegram-журнала.
3. [x] P2-12 Полное admin-управление ботом из web UI.
4. [x] P2-13 Управление ответами на входящие сообщения.
5. [x] P2-14 Связать Telegram-журнал с бизнес-событиями.

### P2-10 / P2-11 Telegram journal and settings

Completed:

* [x] Admin-only `/telegram` UI added for inbound Telegram log.
* [x] Filters added:

  * status;
  * user id;
  * username;
  * chat id;
  * message type;
  * text search;
  * limit.
* [x] Effective Telegram admin/allowlist information is shown.
* [x] DB-backed log settings added:

  * `telegram_log_mode`: `blocked`, `allowed`, `all`;
  * `telegram_log_retention_days`;
  * `telegram_log_retention_count`.
* [x] Bot applies log mode and retention when writing inbound messages.

### P2-12 Full admin bot management

Completed:

* [x] Telegram admin id and allowed user ids are editable from `/telegram`.
* [x] Telegram admin id and allowed user ids are stored in DB-backed settings.
* [x] Runtime bot enable/disable is stored as `telegram_bot_enabled`.
* [x] Runtime bot enable/disable is applied without rebuilding containers.
* [x] Managed command toggles are stored in DB-backed settings.
* [x] Managed command toggles are applied without rebuilding containers for:

  * `/start`;
  * `/help`;
  * `/balance`;
  * `/contractors`;
  * `/tglog`.
* [x] DB-backed response templates are implemented for:

  * `/start`;
  * `/help`;
  * invalid payment format error;
  * invalid receipt file error;
  * payment confirmation.
* [x] `/telegram` has admin UI for editing response templates.
* [x] Preview rendering is shown before saving templates.
* [x] Server-side placeholder validation rejects unsupported placeholders before DB writes.
* [x] Audit log records runtime/access/command/template changes.
* [x] Audit log does not store full template text.

Validation:

```text
template UI targeted 2026-06-30: 36 passed in 8.05s
full pytest 2026-06-30: 345 passed, 8 skipped in 100.12s
warnings summary absent
```

### P2-13 Telegram reply/edit

Completed:

* [x] Admin can reply to an inbound Telegram log row through Bot API.
* [x] Outbound replies are stored in `TelegramOutboundMessageLog`.
* [x] Bot-sent messages can be edited from `/telegram` when `telegram_message_id` is available.
* [x] Send/edit actions are audit logged.

### P2-14 Telegram journal linked with business events

Completed without schema migration:

* [x] `app/bot/business_events.py` added.
* [x] Successful Telegram payment confirmations create `telegram_payment_recorded` audit events.
* [x] Audit details include:

  * normalized `telegram_text_hash`;
  * Telegram chat/user metadata;
  * optional Telegram message id;
  * payment id;
  * contractor id/name;
  * amount;
  * year/month;
  * receipt saved flag.
* [x] `/telegram` maps visible Telegram journal rows to matching `telegram_payment_recorded` audit events by normalized text hash.
* [x] `telegram.html` renders compact linked business events under the matching Telegram journal row.
* [x] Raw audit JSON is not rendered in UI.

Validation:

```text
targeted P2-14 tests: 24 passed in 11.14s
full pytest: 349 passed, 8 skipped in 99.08s
warnings summary absent
```

Key Telegram files:

```text
app/bot/management.py
app/bot/response_templates.py
app/bot/business_events.py
app/bot/security.py
app/bot/handlers.py
app/web/routes/telegram.py
app/web/templates/telegram.html
tests/test_telegram_runtime_management.py
tests/test_telegram_response_templates.py
tests/test_telegram_template_gui.py
tests/test_telegram_business_events.py
tests/test_telegram_gui.py
```

## Current recommended validation command

```cmd
python -m pytest tests/test_action_permissions.py tests/test_permissions.py tests/test_role_matrix.py tests/test_route_permission_matrix.py tests/test_user_management_audit.py tests/test_telegram_business_events.py tests/test_telegram_response_templates.py tests/test_telegram_template_gui.py tests/test_telegram_runtime_management.py tests/test_telegram_gui.py tests/test_ui_assets.py tests/test_bot_receipt_upload.py && python -m pytest
```

## Docs replaced by this file

This file replaces:

```text
docs/LOCAL_AI_IMPLEMENTATION_SUMMARY.md
docs/DOCKER_HARDENING_TODO.md
docs/DOCKER_SMOKE_QA.md
```

Temporary handoff notes were already removed:

```text
docs/P2_12_TELEGRAM_RUNTIME_TOGGLE_HANDOFF.md
docs/P2_12_TELEGRAM_TEMPLATES_HANDOFF.md
docs/P2_14_TELEGRAM_BUSINESS_EVENTS_HANDOFF.md
docs/P2_16_NEXT.md
docs/P2_18_LOCAL_PATCH.md
docs/P2_20_LOCAL_ROUTE_MATRIX.md
docs/LOCAL_MODEL_TASKS.md
docs/TELEGRAM_MANAGEMENT_IMPLEMENTATION_SUMMARY.md
```

## Still open before merge

* [x] Re-run validation after Angie doc cleanup:

  * targeted handoff tests: `tests/test_docker_runtime.py tests/test_docker_smoke_script.py tests/test_readme_release_docs.py`;
  * full pytest suite.
* [ ] Merge/rebase `audit/main-hardening-followup` with latest `main`, because the branch is ahead but also behind `main` by one commit.
* [ ] Run manual smoke check:

  * login;
  * dashboard;
  * backups;
  * receipt upload/download;
  * Telegram management UI.
* [ ] For Docker validation, prefer:

```cmd
python scripts/docker_smoke_check.py
docker compose config -q
```
