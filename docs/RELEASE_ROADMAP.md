# Release roadmap после аудита main

## Вердикт

1. Internal/private pilot: можно выпускать после успешного test run и ручного QA.
2. Public internet production: основные P1 по коду и P1-AUDIT-1 validation закрыты по локальному evidence; перед публичным выпуском остаются ручной QA и P2-hardening.
3. Перед изменениями backup/restore, permissions и payment transactions нужен backup `data/`.

## Сделано

1. Telegram-бот ограничен allowlist конкретных Telegram user id.
2. Добавлена переменная `TELEGRAM_ALLOWED_USER_IDS=123,456`.
3. `TELEGRAM_ADMIN_ID` автоматически добавляется в allowlist.
4. Сообщения от неразрешённых Telegram user id молча игнорируются.
5. Добавлены unit tests для parsing allowlist и silent ignore middleware.
6. Production validation блокирует `SECRET_KEY=change-me-to-a-random-string` из `.env.example`.
7. Добавлен журнал входящих Telegram-сообщений в БД: user id, username, имя, chat id, тип, текст/caption, allowed/admin flags.
8. Добавлена admin-only команда `/tglog [N]` для просмотра последних Telegram-сообщений; доступна только `TELEGRAM_ADMIN_ID`.
9. Исправлена семантика пустых page permissions: `NULL` оставлен как legacy full access, пустая строка означает no access.
10. Добавлен лимит суммарного распакованного размера backup-архива и повторная проверка лимита во время unpack.
11. Login rate limit теперь учитывает `X-Forwarded-For` / `X-Real-IP` от доверенного nginx/reverse proxy и игнорирует spoofed headers от внешнего peer.
12. `contractors/edit` обрабатывает duplicate name/slug через `IntegrityError` без 500 и показывает ошибку в UI.
13. Dashboard использует общий `payment_helpers` для effective status, labels и CSS, включая `partial` / `partial_overdue`.
14. `/login` включён в CSRF protection: GET выдаёт token до рендера формы, POST требует `_csrf`.
15. Второй проход аудита подтвердил, что local backup/restore имеет lock, path/link validation, unpacked-size limit и rollback через safety backup.
16. Web receipt upload проверяет расширение, размер и magic bytes; скачивание чеков идёт через authenticated route с ownership check.
17. Telegram receipt upload теперь проверяет расширение, заявленный/фактический размер и magic bytes до финального сохранения; invalid/oversized document/photo receipts отклоняются в прямом `#оплачено` workflow и interactive receipt workflow.
18. Full test run на Windows/Python 3.13 зелёный: `251 passed, 8 skipped, 5 warnings` за 69.76s.
19. `app/web/static/css/local-ui-tweaks.css` подключён в `base.html`; добавлен asset wiring test.
20. Timezone доведён до UI/settings: admin-only сохранение `settings.notification_timezone`, IANA validation, применение к backup page и scheduler jobs, route/template tests.
21. Docker web/bot images запускаются под non-root пользователем `zhkh`; существующий `docker/start-web.sh` подключён в web image; README описывает права для bind-mount директорий.
22. Scope темы оформления зафиксирован как admin-only global setting: `/settings/theme` теперь обслуживается hardened route из `system_settings` и не позволяет обычному пользователю менять глобальный `ui_theme`.
23. Добавлен admin-only web UI `/telegram` для журнала входящих Telegram-сообщений с фильтрами по статусу/user/chat/type/search и быстрым обзором effective Telegram access.
24. Добавлены GUI-настройки Telegram-журнала: `telegram_log_mode` (`blocked`/`allowed`/`all`), `telegram_log_retention_days`, `telegram_log_retention_count`; бот применяет режим логирования и retention при записи новых сообщений.
25. Добавлено базовое GUI-управление доступом Telegram: `telegram_admin_id` и `telegram_allowed_user_ids` сохраняются в БД и применяются middleware бота без пересборки; env остаётся fallback.
26. Добавлен P2-13 GUI reply/edit для Telegram: admin может отвечать на inbound log row через Bot API, исходящие ответы сохраняются в `TelegramOutboundMessageLog`, а отправленные ботом сообщения можно редактировать из `/telegram` при наличии `telegram_message_id`.
27. P2-15 role foundation закрыт: добавлены роли `admin/operator/viewer`, legacy `user -> viewer`, UI выбора ролей и regression tests; full pytest 2026-06-29 зелёный: `276 passed, 8 skipped, 4 warnings`.
28. P2-16 action-level permissions закрыт: contractor/payment mutations и sensitive admin routes переведены на named action checks; full pytest 2026-06-29 зелёный: `287 passed, 4 skipped, 7 warnings`.
29. P1-AUDIT-1 dependency audit/Docker smoke validation закрыт по локальному evidence: dependency audit без known vulnerabilities, Docker smoke build/up/health/login/bot/nginx ok.
30. P2-AUDIT-2 README hardened-state alignment закрыт: README обновлён под authenticated receipts, Telegram allowlist/management и production checklist; добавлены README regression tests.
31. P2-AUDIT-3 dependency audit CI gate реализован: добавлен GitHub Actions workflow `dependency-audit.yml`, который запускает `python -m pip_audit -r requirements.txt`, и source-level regression tests для workflow.
32. P2-AUDIT-4 Docker smoke QA закрыт локальным evidence: smoke helper/test добавлены, `docker_smoke_check.py` прошёл build/up/health/login/uploads-block/log checks, ручная проверка dashboard/backups/receipt upload/download успешна.

## P1

1. [x] Исправить семантику пустых page permissions.
2. [x] Запретить все известные дефолтные `SECRET_KEY` в production.
3. [x] Добавить лимит распакованного размера backup-архива.
4. [x] Исправить rate limit login за nginx/reverse proxy.
5. [x] Добавить первичный admin-only контроль входящих сообщений Telegram-бота.
6. [x] Прогнать полный test run и зафиксировать результат перед merge/release.
   - Результат 2026-06-29, Windows/Python 3.13: `python -m pytest` — 259 collected, 251 passed, 8 skipped, 5 warnings, 0 failed, 69.76s.
7. [x] В Telegram receipt workflows добавить такую же проверку размера и magic bytes, как в web upload; сейчас bot document upload доверяет расширению файла.

## P2

6. [x] Унифицировать payment status helpers на dashboard.
7. [x] Обработать duplicate contractor name/slug при редактировании.
8. [x] Решить, нужен ли CSRF на `/login`.
9. [x] Добавить non-root user в Docker images.
10. [x] Добавить web UI для журнала Telegram-сообщений на admin-only странице.
11. [x] Добавить настройки режима Telegram-журнала: логировать только blocked/allowed/all и срок хранения.
12. [x] Довести timezone до конца: поле в UI, сохранение `settings.notification_timezone`, использование на странице бекапов и в scheduler/notifications, где применимо.
13. [x] Подключить `app/web/static/css/local-ui-tweaks.css` в `base.html` или удалить файл, если правки больше не нужны.
14. [x] Решить scope темы оформления: `/settings/theme` оставлен как admin-only global setting; обычные пользователи не могут менять глобальный `ui_theme`.
15. [x] Убрать или подключить `docker/start-web.sh`, чтобы в репозитории не было неиспользуемого runtime-скрипта.
16. [x] P2-15 Расширить модель ролей и прав: role foundation (`admin/operator/viewer`) внедрён и подтверждён full pytest.
17. [x] P2-16 Добавить action-level permissions вместо page-only permissions: named action checks внедрены и подтверждены full pytest.

## Tests

12. Добавить full-stack CSRF tests для POST-форм.
13. [x] Добавить tests для пустых permissions.
14. [x] Добавить tests для production default `SECRET_KEY` из `.env.example`.
15. Добавить route-level tests для fixed overpay и variable top-up.
16. [x] Добавить tests для backup tar-bomb/unpacked-size rejection.
17. [x] Добавить tests для Telegram message log, `/tglog`, web UI `/telegram`, фильтров и настроек журнала.
18. [x] Добавить route-level test для duplicate contractor name при редактировании.
19. [x] Добавить regression test, что dashboard использует shared payment status helpers.
20. [x] Добавить CSRF tests для `/login`.
21. [x] Добавить tests для Telegram receipt upload: invalid extension, spoofed PDF/JPG/PNG magic bytes, oversized document/photo.
22. [x] Добавить route/template tests для сохранения и отображения timezone.
23. [x] Добавить asset wiring test для `local-ui-tweaks.css`.
24. [x] Добавить source-level tests для Docker non-root runtime и документации bind-mount прав.
25. [x] Добавить route/source tests для admin-only global theme scope.
26. [x] Добавить route-level permission tests для role foundation: `admin/operator/viewer`, legacy `user -> viewer`, создание operator и запрет operator admin/business mutations до action-level permissions.
27. [x] Прогнать обновлённый template compatibility test на Starlette 1.x после dependency bump.
28. [x] Добавить source/route tests для action-level permissions: contractor/payment mutations и sensitive admin routes используют named action checks.
29. [x] Добавить README regression tests для hardened release docs: authenticated receipts, production/Compose secret safety и Telegram allowlist management.
30. [x] Добавить source-level tests для CI/security gate dependency audit workflow.
31. [x] Добавить Docker smoke helper/source tests для P2-AUDIT-4: `scripts/docker_smoke_check.py` и `tests/test_docker_smoke_script.py`.

## Расшифровка

1. Internal pilot допустим, потому что session cookie подписан, dangerous actions закрыты admin-only, receipts не отдаются через `/uploads`, backup restore валидирует tar paths и имеет rollback.
2. P1-риски по access-control edge case, production secret defaults, proxy/rate-limit, лимиту распакованного backup и Telegram receipt validation закрыты по коду; full test run зелёный. Для публичного production остаются ручной QA и P2-hardening.
3. Backup обязателен перед изменениями, которые меняют данные или restore-поведение: permissions semantics, backup extraction, payment transaction backfill/schema.
4. Пустые permissions сейчас могут означать полный доступ к страницам. Управляемый пустой список должен означать no access, а legacy full-access отделён через `NULL`.
5. Production validation должна блокировать не только `change-me-in-production`, но и `change-me-to-a-random-string` из `.env.example`.
6. Backup upload ограничивает размер загруженного `.tar.gz`, а backup service дополнительно считает суммарный размер файлов после распаковки.
7. Login rate limit берёт реальный клиентский IP из `X-Forwarded-For` / `X-Real-IP`, только если peer похож на доверенный локальный/private reverse proxy.
8. Telegram-бот теперь принимает команды только от явно разрешённых Telegram user id. Управление несколькими аккаунтами: добавить их числовые id через запятую в `.env`, затем пересоздать контейнер `bot`.
9. Dashboard использует общую status logic из `payment_helpers` и различает `partial` / `partial_overdue` так же, как payments/history.
10. `contractors/edit` ловит `IntegrityError`, как уже сделано в `contractors/add`.
11. `/login` включён в CSRF middleware; форма получает `_csrf` из `request.state.csrf_token`.
12. Docker images запускают web/bot процессы от non-root пользователя `zhkh`; для Linux/WSL bind-mount директорий нужны права на `data/`, `backups/` и `logs/` под UID/GID контейнерного пользователя.
13. Нужны не только helper/source tests, но и ASGI/route tests, которые проходят через middleware, templates и реальные form actions.
14. Telegram receipt upload теперь проверяет allowed extension, размер и magic bytes для документов и фото до финального сохранения файла в прямом и interactive workflows.
15. Full test run 2026-06-29 зелёный: 251 passed, 8 skipped, 0 failed.
16. `local-ui-tweaks.css` оставлен как актуальный UI-fix и подключён после `qa-fixes.css`, чтобы правки select и блока бекапов реально применялись.
17. `notification_timezone` теперь валидируется как IANA timezone, сохраняется отдельным admin-only route и используется при пересборке notification/auto-backup scheduler jobs.
18. `docker/start-web.sh` теперь используется web image как runtime command, поэтому в репозитории не остаётся неподключённого web start script.
19. Тема оформления остаётся глобальной настройкой приложения; менять её через backend может только admin, а пользовательский client-side toggle без admin role не мутирует `settings.ui_theme`.
20. Роли `admin/operator/viewer` внедрены без миграции схемы: новые create/update больше не создают `role=user`, legacy `user` нормализуется в `viewer`, а operator до P2-16/P2-17 не получает business CRUD или доступ к Telegram/backups/users/system settings.
21. Full pytest после P2-15 на Windows: `276 passed, 8 skipped, 4 warnings in 64.53s`.
22. P2-16 закрыл переход от прямых `role == admin` checks к named action permissions для business mutations и sensitive admin routes; operator/viewer всё ещё не получают mutations до P2-17. Full pytest после P2-16: `287 passed, 4 skipped, 7 warnings in 75.47s`.
23. P2-17 дал operator `BUSINESS_ACTION_PERMISSIONS`, оставив Telegram/backups/restore/users/global settings/security за `admin`. Full pytest после P2-17: `287 passed, 4 skipped, 7 warnings in 71.22s`.
24. P2-AUDIT-2 синхронизировал README с фактическим hardened-состоянием: чеки не публичные `/uploads`, production запуск требует безопасных env-настроек, Telegram allowlist/management описаны без раскрытия секретов.
25. P2-AUDIT-3 добавил dependency audit gate в GitHub Actions: low-privilege workflow устанавливает `pip-audit` как CI tooling и проверяет runtime `requirements.txt`; секреты, Docker и полный Compose config не используются.
26. P2-AUDIT-4 закрыт локальным Docker smoke evidence: quiet Compose validation, последовательные web/bot builds, `up -d`, `/health`, `/login`, blocked `/uploads`, bounded logs, manual dashboard/backups/receipt upload/download ok; полный Compose config и секреты не выводились.

## Аудит 2026-06-29 — follow-up перед production

### Вердикт

1. Internal/private pilot: готов при условии ручного smoke QA после сборки контейнеров и заполнения `.env` реальными секретами.
2. Public internet production: P1-AUDIT-1 dependency audit и Docker smoke закрыты локальным evidence; перед публичным production остаются ручной QA и P2-hardening.
3. Telegram-часть безопасна как allowlist-only бот, а базовый Telegram management уже доступен через `/telegram`; полный management block остаётся отдельной P2-задачей ниже.

### Проверено ранее

- `python -m compileall app init_db.py tests` — успешно.
- `pytest -q` — 269 passed, 4 skipped, 8 warnings.
- `docker-compose config` — успешно после локального создания `.env` из `.env.example`.
- Ранее `pip-audit -r requirements.txt` находил 47 known vulnerabilities в 6 пакетах; после dependency bump и локальной проверки P1-AUDIT-1 закрыт без known vulnerabilities.

### Попытка P1-AUDIT-1 2026-06-29 через GitHub connector

- Обновлён `requirements.txt`: `fastapi==0.138.1`, явный `starlette==1.3.1`, `aiogram==3.29.0`, явный `aiohttp==3.14.1`, `jinja2==3.1.6`, `python-multipart==0.0.32`, `python-dotenv==1.2.2`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`.
- Добавлен compatibility adapter в `app/web/template_engine.py`, потому что Starlette 1.x удаляет deprecated `TemplateResponse(name, context)`, а текущие routes ещё используют legacy call shape.
- Добавлен regression assertion в `tests/test_template_engine.py` на наличие compatibility adapter.
- Full pytest после dependency/role/action-permission changes подтверждён локально пользователем: `287 passed, 4 skipped, 7 warnings in 75.47s`.
- `docker-compose config` подтверждён локально пользователем: ok.
- P1-AUDIT-1 закрыт по последующему локальному evidence: dependency audit без known vulnerabilities и Docker smoke build/up/health/login/bot/nginx ok.

### Замечания / follow-up

1. [x] P1-AUDIT-1 Завершить dependency audit validation:
   - `pip-audit -r requirements.txt`;
   - при доступном Docker: `docker compose up -d --build`, `/health`, login smoke, Telegram bot startup logs.
   - закрыто по локальному evidence 2026-06-29; не запрашивать полный `docker compose config`, использовать только `docker compose config -q`.
2. [x] P2-AUDIT-2 Обновить README под фактическое hardened-состояние: receipts больше не должны описываться как публично обслуживаемые `/uploads`, Telegram allowlist и `/tglog` уже есть, production запуск должен явно включать `APP_ENV=production`, уникальный `SECRET_KEY`, реальные пароли и `COOKIE_SECURE` за HTTPS.
   - README обновлён; добавлен `tests/test_readme_release_docs.py`.
3. [x] P2-AUDIT-3 Добавить CI/security gate для dependency audit: `pip-audit -r requirements.txt` или эквивалентный шаг, чтобы новые CVE не всплывали только перед релизом.
   - Добавлен `.github/workflows/dependency-audit.yml`; workflow запускает `python -m pip_audit -r requirements.txt` без app secrets/Docker/full Compose config.
   - Добавлен `tests/test_ci_security_gate.py`.
   - Требуется локальный targeted pytest и подтверждение GitHub Actions run после push.
4. [x] P2-AUDIT-4 Docker smoke QA выполнить в среде с доступным Docker Compose plugin/v1: `docker_smoke_check.py` подтвердил `docker compose config -q`, sequential web/bot builds, `up -d`, `/health`, `/login`, blocked `/uploads`, bounded web/nginx/bot logs; ручная проверка dashboard, `/backups` и receipt upload/download успешна.
5. [ ] P2-AUDIT-5 Разобрать текущие pytest warnings: ошибочные `@pytest.mark.asyncio` на sync tests в receipt source-level tests.
   - Fix prepared: `tests/test_receipt_ownership.py` больше не применяет module-level `pytest.mark.asyncio` к sync source-level tests; SQLAlchemy query compile check переведён в sync test. Нужен targeted/full pytest evidence перед закрытием.

### Permissions and roles block

Цель: заменить бинарную модель `role == admin` + page checkboxes на явные роли и action-level permissions. Admin должен стать отдельной системной сущностью для опасных/технических настроек, а повседневное ведение ЛК должно быть доступно продвинутому пользователю без выдачи ему полного admin.

1. [x] P2-15 Спроектировать и внедрить роли:
   - `admin`: системный администратор приложения; доступ к users/roles/settings, Telegram management, backups/restore, security/audit и всем бизнес-операциям;
   - `operator`: role value и GUI добавлены; business CRUD включён через action-level permissions в P2-17;
   - `viewer`: обычный пользователь только для просмотра разрешённых страниц без мутаций;
   - validation: full pytest 2026-06-29 — `276 passed, 8 skipped, 4 warnings in 64.53s`.
2. [x] P2-16 Добавить action-level permissions вместо page-only permissions.
   - contractor/payment mutations переведены на named action checks;
   - sensitive admin routes покрыты named checks: users, system settings, Telegram, backups/manage и backups/restore;
   - operator/viewer по-прежнему не получают mutations до P2-17;
   - validation: targeted pytest зелёный; full pytest 2026-06-29 — `287 passed, 4 skipped, 7 warnings in 75.47s`.
3. [x] P2-17 Перевести текущие admin-only business routes на operator-capable checks, оставив Telegram/backups/restore/users/global settings/security только для `admin`.
   - operator получает `BUSINESS_ACTION_PERMISSIONS`: contractors CRUD, payments CRUD, payment transactions CRUD и receipt business cleanup;
   - operator по-прежнему не получает `USERS_MANAGE`, `SYSTEM_SETTINGS_MANAGE`, `TELEGRAM_MANAGE`, `BACKUPS_MANAGE`, `BACKUPS_RESTORE`;
   - validation: targeted pytest 30 passed; full pytest 2026-06-29 — `287 passed, 4 skipped, 7 warnings in 71.22s`.
4. [ ] P2-18 Обновить GUI управления пользователями: роли, presets прав, предупреждение о page/action permissions, migration/backfill.
5. [ ] P2-19 Добавить audit и защиту от self-lockout.
6. [ ] P2-20 Добавить тесты матрицы доступа.

### Telegram management block

1. [x] P2-10 Web UI для журнала Telegram-сообщений.
2. [x] P2-11 Настройки режима Telegram-журнала.
3. [ ] P2-12 Полное admin-управление ботом из web UI:
   - [x] просмотр и изменение Telegram admin id / allowed user ids через БД/settings с audit log;
   - включение/выключение бота или отдельных команд без пересборки контейнера, если архитектура будет переведена с env-only на DB/settings;
   - настройка шаблонов ответов `/start`, `/help`, ошибок и подтверждений оплаты;
   - предпросмотр шаблонов и validation placeholders перед сохранением;
   - audit log всех изменений Telegram-настроек.
4. [x] P2-13 Управление ответами на входящие сообщения.
5. [ ] P2-14 Связать Telegram-журнал с бизнес-событиями.
