# Release roadmap после аудита main

## Вердикт

1. Internal/private pilot: можно выпускать после ручного QA.
2. Public internet production: P1 закрыт по коду, перед выпуском нужны успешные тесты и ручной QA.
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

## P1

1. [x] Исправить семантику пустых page permissions.
2. [x] Запретить все известные дефолтные `SECRET_KEY` в production.
3. [x] Добавить лимит распакованного размера backup-архива.
4. [x] Исправить rate limit login за nginx/reverse proxy.
5. [x] Добавить первичный admin-only контроль входящих сообщений Telegram-бота.

## P2

6. [x] Унифицировать payment status helpers на dashboard.
7. [x] Обработать duplicate contractor name/slug при редактировании.
8. [x] Решить, нужен ли CSRF на `/login`.
9. Добавить non-root user в Docker images.
10. Добавить web UI для журнала Telegram-сообщений на admin-only странице.
11. Добавить настройки режима Telegram-журнала: логировать только blocked/allowed/all и срок хранения.

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

## Расшифровка

1. Internal pilot допустим, потому что session cookie подписан, dangerous actions закрыты admin-only, receipts не отдаются через `/uploads`, backup restore валидирует tar paths и имеет rollback.
2. P1-риски по access-control edge case, production secret defaults, proxy/rate-limit и лимиту распакованного backup закрыты по коду; выпуск наружу всё ещё требует успешного полного test run и ручного QA.
3. Backup обязателен перед изменениями, которые меняют данные или restore-поведение: permissions semantics, backup extraction, payment transaction backfill/schema.
4. Пустые permissions сейчас могут означать полный доступ к страницам. Нужно сделать управляемый пустой список равным no access, а legacy full-access отделить явно.
5. Production validation должна блокировать не только `change-me-in-production`, но и `change-me-to-a-random-string` из `.env.example`.
6. Backup upload ограничивает размер загруженного `.tar.gz`, но не суммарный размер файлов после распаковки.
7. Login rate limit берёт реальный клиентский IP из `X-Forwarded-For` / `X-Real-IP`, только если peer похож на доверенный локальный/private reverse proxy.
8. Telegram-бот теперь принимает команды только от явно разрешённых Telegram user id. Управление несколькими аккаунтами: добавить их числовые id через запятую в `.env`, затем пересоздать контейнер `bot`.
9. Dashboard использует общую status logic из `payment_helpers` и различает `partial` / `partial_overdue` так же, как payments/history.
10. `contractors/edit` ловит `IntegrityError`, как уже сделано в `contractors/add`.
11. `/login` включён в CSRF middleware; форма получает `_csrf` из `request.state.csrf_token`.
12. Docker images сейчас запускают процессы от root; для public production нужен non-root runtime user.
13. Нужны не только helper/source tests, но и ASGI/route tests, которые проходят через middleware, templates и реальные form actions.
