# Release roadmap после аудита main

## Вердикт

1. Internal/private pilot: можно выпускать после успешного test run и ручного QA.
2. Public internet production: основные P1 по коду закрыты, но перед публичным выпуском остаётся ручной QA и P2-hardening.
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
16. [ ] P2-15 Расширить модель ролей и прав: role foundation (`admin/operator/viewer`) закоммичен, но не закрыт до локального test run.

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
26. [ ] Добавить route-level permission tests для viewer/operator/admin: role-foundation tests добавлены, но полная matrix для action-level permissions остаётся в P2-16/P2-20.
27. [ ] Прогнать обновлённый template compatibility test на Starlette 1.x после dependency bump.

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

## Аудит 2026-06-29 — follow-up перед production

### Вердикт

1. Internal/private pilot: готов при условии ручного smoke QA после сборки контейнеров и заполнения `.env` реальными секретами.
2. Public internet production: пока не выпускать без закрытия P1-AUDIT-1. Функциональные P1 по коду закрыты, полный test run зелёный, но dependency audit показывает известные CVE в runtime-зависимостях.
3. Telegram-часть безопасна как allowlist-only бот, но для полного управления ботом и удобного разбора сообщений нужен отдельный Telegram management block ниже.

### Проверено ранее

- `python -m compileall app init_db.py tests` — успешно.
- `pytest -q` — 269 passed, 4 skipped, 8 warnings.
- `docker-compose config` — успешно после локального создания `.env` из `.env.example`.
- `pip-audit -r requirements.txt` — найдено 47 known vulnerabilities в 6 пакетах.

### Попытка P1-AUDIT-1 2026-06-29 через GitHub connector

- Обновлён `requirements.txt`: `fastapi==0.138.1`, явный `starlette==1.3.1`, `aiogram==3.29.0`, явный `aiohttp==3.14.1`, `jinja2==3.1.6`, `python-multipart==0.0.32`, `python-dotenv==1.2.2`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`.
- Добавлен compatibility adapter в `app/web/template_engine.py`, потому что Starlette 1.x удаляет deprecated `TemplateResponse(name, context)`, а текущие routes ещё используют legacy call shape.
- Добавлен regression assertion в `tests/test_template_engine.py` на наличие compatibility adapter.
- P1-AUDIT-1 НЕ отмечен `[x]`: текущая sandbox-среда не смогла получить локальный checkout (`Could not resolve host: github.com`), поэтому здесь не были достоверно выполнены `compileall`, `pytest`, `pip-audit`, `docker compose config` и Docker smoke.

### Замечания / follow-up

1. [ ] P1-AUDIT-1 Обновить runtime/development dependencies и повторить full test run:
   - `jinja2 3.1.5` -> минимум `3.1.6`;
   - `python-multipart 0.0.20` -> минимум `0.0.31`;
   - `python-dotenv 1.0.1` -> минимум `1.2.2`;
   - `aiohttp 3.11.18` приходит транзитивно через `aiogram`, нужен compatible upgrade `aiogram`/`aiohttp` до версии без CVE;
   - `starlette 0.41.3` приходит через `fastapi`, нужен compatible upgrade `fastapi`/`starlette`;
   - `pytest 8.3.4` -> `9.0.3` или актуальная безопасная версия для dev-зависимости;
   - после текущего dependency bump обязательно прогнать: `python -m compileall app init_db.py tests`, `python -m pytest`, `pip-audit -r requirements.txt`, `docker compose config`.
2. [ ] P2-AUDIT-2 Обновить README под фактическое hardened-состояние: receipts больше не должны описываться как публично обслуживаемые `/uploads`, Telegram allowlist и `/tglog` уже есть, production запуск должен явно включать `APP_ENV=production`, уникальный `SECRET_KEY`, реальные пароли и `COOKIE_SECURE` за HTTPS.
3. [ ] P2-AUDIT-3 Добавить CI/security gate для dependency audit: `pip-audit -r requirements.txt` или эквивалентный шаг, чтобы новые CVE не всплывали только перед релизом.
4. [ ] P2-AUDIT-4 Docker smoke QA выполнить в среде с доступным Docker Compose plugin/v1: `docker compose up -d --build`, `/health`, login, Telegram bot startup logs, backup page, receipt upload/download.
5. [ ] P2-AUDIT-5 Разобрать текущие pytest warnings: deprecated Starlette `TemplateResponse(...)` signature и ошибочные `@pytest.mark.asyncio` на sync tests. Текущий adapter закрывает совместимость со Starlette 1.x, но предупреждения/полный test run нужно подтвердить фактическим `pytest`.

### Permissions and roles block

Цель: заменить бинарную модель `role == admin` + page checkboxes на явные роли и action-level permissions. Admin должен стать отдельной системной сущностью для опасных/технических настроек, а повседневное ведение ЛК должно быть доступно продвинутому пользователю без выдачи ему полного admin.

1. [ ] P2-15 Спроектировать и внедрить роли:
   - `admin`: системный администратор приложения; доступ к users/roles/settings, Telegram management, backups/restore, security/audit и всем бизнес-операциям;
   - `operator`: продвинутый пользователь для полноценного ведения ЛК; role value и GUI уже добавлены, но бизнес-CRUD пока не расширен без P2-16 action-level permissions;
   - `viewer`: обычный пользователь только для просмотра разрешённых страниц без мутаций;
   - validation pending: `python -m pytest tests/test_permissions.py tests/test_theme_scope.py tests/test_telegram_gui.py`.
2. [ ] P2-16 Добавить action-level permissions вместо page-only permissions.
3. [ ] P2-17 Перевести текущие admin-only business routes на operator-capable checks, оставив Telegram/backups/restore/users/global settings/security только для `admin`.
4. [ ] P2-18 Обновить GUI управления пользователями: роли, presets прав, предупреждение о page/action permissions, migration/backfill.
5. [ ] P2-19 Добавить audit и защиту от self-lockout.
6. [ ] P2-20 Добавить тесты матрицы доступа.

### P2-15 attempt 2026-06-29 через GitHub connector

- Добавлены роли `admin`, `operator`, `viewer` на существующем поле `users.role`, без миграции схемы.
- Legacy `role == "user"` сохраняется как читаемый legacy state, но новые create/update нормализуют `user -> viewer`.
- User management UI теперь показывает выбор `admin/operator/viewer` и предупреждает, что page permissions дают только видимость страниц, а action-level permissions будут отдельным блоком.
- Operator не получил доступ к Telegram/backups/users/system settings и не получил business CRUD до P2-16/P2-17.
- Добавлены tests в `tests/test_permissions.py` на роли, legacy normalization, создание operator и запрет operator admin/business mutations.
- P2-15 НЕ отмечен `[x]` до локального test run.

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
