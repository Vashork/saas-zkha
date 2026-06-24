# Agent fix log

Дата: 2026-06-24
Ветка: `audit-dashboard-fixes`
PR: `#1`

Файл фиксирует замечания к работе агента, исправления в ветке и оставшиеся задачи.

## Исправлено и закоммичено

### 1. Dashboard: список месяцев

Проблема: список месяцев строился некорректно при смещении больше чем на 12 месяцев назад.

Симптомы:

- даты в дашборде отображались криво;
- выбор периода работал нестабильно.

Исправление:

- добавлен `_shift_month(year, month, offset)`;
- список месяцев строится через нормализованный индекс месяца;
- в список входят месяцы из БД, диапазон вокруг текущей даты и выбранный месяц.

Файл: `app/web/routes/dashboard.py`

---

### 2. Dashboard: выбранный месяц

Проблема: шаблон проверял `m == month`, но backend не передавал `month`.

Исправление:

- `month` добавлен в template context.

Файлы:

- `app/web/routes/dashboard.py`
- `app/web/templates/dashboard.html`

---

### 3. Dashboard: долг и неоплаченные счета

Проблема: суммы считались только по `Payment.amount`. Для variable-платежей `amount` может быть пустым.

Исправление:

- добавлены `_planned_amount`, `_paid_amount`, `_remaining_amount`;
- добавлены `unpaid_amount`, `unpaid_count`;
- таблица показывает начислено и остаток.

Файлы:

- `app/web/routes/dashboard.py`
- `app/web/templates/dashboard.html`

---

### 4. Bot Dockerfile: точка входа

Проблема:

```bash
python -m app.bot
```

Пакет `app.bot` не содержит `__main__.py`.

Исправление:

```bash
python -m app.bot.main
```

Файл: `docker/Dockerfile.bot`

---

### 5. Auth: проверка прав

Проблема: права доступа брались из cookies `user_role` и `page_permissions`.

Исправление:

- добавлен подписанный cookie `session`;
- пользователь загружается из БД;
- проверяется `User.is_active`;
- display cookies оставлены только для UI-совместимости.

Файл: `app/web/routes/auth.py`

---

### 6. Auth: активность пользователя

Проблема: логин не проверял `User.is_active`.

Исправление:

- `/login` ищет только активного пользователя;
- session guard тоже принимает только активного пользователя.

Файл: `app/web/routes/auth.py`

---

### 7. Settings: тема

Проблема: один обработчик использовал `ui_theme`, другой сохранял `theme`.

Исправление:

- сохранение пишет `ui_theme`;
- при чтении есть fallback со старого `theme`.

Файл: `app/web/routes/auth.py`

---

### 8. Settings: смена имени

Проблема: форма отправляла `new_username`, а route ждал другое имя поля.

Исправление:

- route принимает `new_username`;
- форма требует текущий пароль.

Файлы:

- `app/web/routes/auth.py`
- `app/web/templates/settings.html`

---

### 9. Settings: смена пароля

Проблема: route ждал `confirm_password`, но форма его не отправляла.

Исправление:

- в форму добавлено поле `confirm_password`.

Файл: `app/web/templates/settings.html`

---

### 10. History: URL чеков

Проблема: history использовал `/static/uploads/...`, а остальной код — `/uploads/...`.

Исправление:

- history использует `/uploads/{{ p.receipt_file }}`.

Файл: `app/web/templates/history.html`

---

### 11. Scheduler: `due_day`

Проблема: вычислялся `due_day = min(c.due_day, 28)`, но дальше не использовался.

Исправление:

- `due_day` используется для `due_date`;
- убраны лишние импорты.

Файл: `app/scheduler.py`

---

## Найдено, но осталось агенту

### 12. Contractors: write actions

Проблема: `toggle_contractor` не принимает `Request`, поэтому в нем нет нормального route-level guard.

Что сделать:

- добавить `request: Request`;
- загрузить текущего пользователя через `get_current_user(request, db)`;
- разрешить add/edit/toggle/delete только admin;
- не полагаться на display cookies.

Файл: `app/web/routes/contractors.py`

---

### 13. Bot handlers: variable amount

Проблема: при оплате через Telegram variable-платеж может получить `paid_amount`, но `amount` останется пустым.

Что сделать:

```python
if payment.amount is None:
    payment.amount = amount
```

Файл: `app/bot/handlers.py`

---

### 14. Bot handlers: file validation

Проблема: `is_allowed_file` импортирован, но документ от Telegram не проверяется через этот helper.

Что сделать:

- проверять `message.document.file_name` через `is_allowed_file`;
- принимать только PDF/JPG/PNG;
- не сохранять неподходящие документы.

Файл: `app/bot/handlers.py`

---

## Следующий этап

1. CSRF для POST-форм.
2. Сервисный слой.
3. Alembic.
4. Telegram notification service.
5. Unit/integration tests.
6. Общий navbar partial.
