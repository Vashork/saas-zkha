# Second pass review of `audit-dashboard-fixes`

Дата: 2026-06-24
Ветка: `audit-dashboard-fixes`

Цель: повторное ревью уже измененной ветки после первого пакета исправлений. Проверялись уязвимости, мертвый код, регрессии от правок и оставшиеся задачи для агента.

## Критичные и важные находки

### 1. REGRESSION: UI context still reads display cookies

Статус: найдено, не исправлено.

После перехода на подписанный `session` часть route-файлов все еще передает в шаблоны `username` и `user_role` из cookies. Это не основной bypass авторизации, потому что `_require_page` теперь проверяет БД, но UI может показывать неверную роль или скрывать/показывать элементы некорректно.

Затронутые файлы:

- `app/web/routes/dashboard.py`
- `app/web/routes/payments.py`
- `app/web/routes/history.py`
- `app/web/routes/analytics.py`
- `app/web/routes/contractors.py`

Что сделать агенту:

- после `_require_page` получать текущего пользователя из `get_current_user(request, db)`;
- в шаблон передавать `current_user.username` и `current_user.role`;
- убрать зависимость UI от display cookies.

---

### 2. SECURITY: contractors write routes still unsafe

Статус: найдено ранее, подтверждено повторным ревью.

`toggle_contractor` не принимает `Request`, не вызывает `_require_page` и не проверяет admin. `delete_contractor` проверяет admin по `request.cookies.get('user_role')`, что после перехода на display cookies является неправильной моделью. `add_contractor` и `edit_contractor` проверяют только доступ к странице, но не admin role.

Файл:

- `app/web/routes/contractors.py`

Что сделать агенту:

- все write-действия подрядчиков закрыть на DB-backed admin check;
- использовать `get_current_user(request, db)`;
- не использовать `request.cookies.get('user_role')` для решений доступа.

---

### 3. SECURITY: payments write routes allow non-admin modifications

Статус: найдено повторным ревью.

`add_payment`, `edit_payment`, `delete_payment` проверяют только доступ к странице `payments`. Если обычному пользователю разрешен просмотр `payments`, он может выполнять write-действия. В UI кнопки редактирования скрываются для не-admin, но backend не должен полагаться на UI.

Файл:

- `app/web/routes/payments.py`

Что сделать агенту:

- добавить отдельную проверку admin или отдельное право `edit_payments`;
- backend должен запрещать add/edit/delete без права редактирования;
- не полагаться на скрытие кнопок в HTML.

---

### 4. SECURITY: no CSRF protection for POST forms

Статус: не исправлено.

Во всех HTML-формах POST нет CSRF-token. После появления cookie-based session это становится отдельным риском.

Затронутые зоны:

- settings user management;
- contractor CRUD;
- payment CRUD;
- upload receipt;
- theme/settings save.

Что сделать агенту:

- внедрить CSRF-token для форм;
- проверять token на POST;
- минимум: double-submit cookie или серверная session-token модель.

---

### 5. SECURITY: session cookie lacks `secure=True`

Статус: частично допустимо для localhost, но риск для production.

Подписанный session-cookie выставляется с `httponly=True` и `samesite='lax'`, но без `secure=True`. Для локальной разработки это допустимо, для HTTPS production надо включать `secure=True` через настройку окружения.

Файл:

- `app/web/routes/auth.py`

Что сделать агенту:

- добавить setting `COOKIE_SECURE=true/false`;
- включать `secure=True` в production.

---

### 6. AUTH DESIGN: legacy users with empty permissions get full access

Статус: осознанная совместимость, но потенциальный риск.

В `_require_page`, если `user.page_permissions` пустой, пользователь получает полный доступ. Это было оставлено для legacy compatibility, но с точки зрения безопасности лучше различать `NULL` как legacy migration и пустую строку как `no permissions`.

Файл:

- `app/web/routes/auth.py`

Что сделать агенту:

- мигрировать существующих пользователей явно;
- для новых пользователей пустой список прав должен означать отсутствие прав, а не полный доступ.

---

## Мертвый код / подозрительная логика

### 7. Analytics: dead variable and wrong month comparison array

Статус: найдено, не исправлено.

В single-month ветке создается `vals_curr`, но не используется. Также цикл по `[prev_year, target_year]` пишет оба значения в `vals_prev`, после чего `monthly_previous = vals_prev`. Это делает массив previous шире, чем ожидаемый one-month label.

Файл:

- `app/web/routes/analytics.py`

Что сделать агенту:

- убрать `vals_curr`;
- считать previous и current отдельно;
- для single-month labels должен быть один label и по одному значению в каждом dataset.

---

### 8. Payments: `_context()` returns incomplete page state

Статус: найдено, не исправлено.

При ошибке upload/add/edit `_context()` возвращает пустые списки `payments` и `contractors`. После ошибки страница может потерять таблицу и список подрядчиков.

Файл:

- `app/web/routes/payments.py`

Что сделать агенту:

- заменить `_context()` на async helper, который реально загружает payments/contractors;
- использовать его для error rendering.

---

### 9. Payments: unused imports

Статус: найдено, не исправлено.

`ALLOWED_EXTENSIONS` импортируется в `payments.py`, но не используется.

Файл:

- `app/web/routes/payments.py`

Что сделать агенту:

- удалить неиспользуемый импорт.

---

### 10. Bot handlers: unused import and incomplete validation

Статус: найдено, не исправлено.

`Decimal` импортируется в `app/bot/handlers.py`, но не используется. `is_allowed_file` импортирован, но документ Telegram не проверяется через него.

Файл:

- `app/bot/handlers.py`

Что сделать агенту:

- удалить unused `Decimal`;
- использовать `is_allowed_file` для `message.document.file_name`.

---

### 11. Bot handlers: variable payment source data remains incomplete

Статус: найдено, не исправлено.

При оплате через Telegram заполняется `paid_amount`, но если `Payment.amount` пустой, он не заполняется. Dashboard теперь это компенсирует, но правильнее исправить источник данных.

Файл:

- `app/bot/handlers.py`

Что сделать агенту:

- если `payment.amount is None`, присвоить ему сумму оплаты.

---

### 12. Database migrations are still manual

Статус: архитектурный долг.

`init_db()` использует ручные `PRAGMA table_info` и `ALTER TABLE`. Для дальнейшего развития нужна Alembic migration history.

Файл:

- `app/database.py`

Что сделать агенту:

- добавить Alembic;
- перенести текущие schema changes в миграции.

---

## Итог второго прохода

Ветка стала лучше по dashboard и auth, но еще не готова к merge без доработок. Самые важные блокеры:

1. закрыть contractor write routes;
2. закрыть payment write routes;
3. убрать UI-зависимость от display cookies;
4. добавить CSRF;
5. исправить bot handlers;
6. поправить analytics single-month logic.
