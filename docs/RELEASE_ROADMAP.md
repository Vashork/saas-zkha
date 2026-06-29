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
10. Добавить web UI для журнала Telegram-сообщений на admin-only странице.
11. Добавить настройки режима Telegram-журнала: логировать только blocked/allowed/all и срок хранения.
12. [x] Довести timezone до конца: поле в UI, сохранение `settings.notification_timezone`, использование на странице бекапов и в scheduler/notifications, где применимо.
13. [x] Подключить `app/web/static/css/local-ui-tweaks.css` в `base.html` или удалить файл, если правки больше не нужны.
14. Решить scope темы оформления: сейчас `/settings/theme` доступен любому authenticated user, но пишет глобальный `ui_theme`; для multi-user лучше сделать per-user preference или admin-only global setting.
15. [x] Убрать или подключить `docker/start-web.sh`, чтобы в репозитории не было неиспользуемого runtime-скрипта.

## Tests

12. Добавить full-stack CSRF tests для POST-форм.
13. [x] Добавить tests для пустых permissions.
14. [x] Добавить tests для production default `SECRET_KEY` из `.env.example`.
15. Добавить route-level tests для fixed overpay и variable top-up.
16. [x] Добавить tests для backup tar-bomb/unpacked-size rejection.
17. Добавить tests для Telegram message log и `/tglog`.
18. [x] Добавить route-level test для duplicate contractor name при редактировании.
19. [x] Добавить regression test, что dashboard использует shared payment status helpers.
20. [x] Добавить CSRF tests для `/login`.
21. [x] Добавить tests для Telegram receipt upload: invalid extension, spoofed PDF/JPG/PNG magic bytes, oversized document/photo.
22. [x] Добавить route/template tests для сохранения и отображения timezone.
23. [x] Добавить asset wiring test для `local-ui-tweaks.css`.
24. [x] Добавить source-level tests для Docker non-root runtime и документации bind-mount прав.

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
