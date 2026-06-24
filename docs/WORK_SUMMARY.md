# Work summary for `audit-dashboard-fixes`

Дата: 2026-06-24
Ветка: `audit-dashboard-fixes`
PR: `#1`

Единое самари по работе в ветке.

## 1. Уже исправлено

### Dashboard

- Исправлен список месяцев и выбранный период.
- Исправлен расчёт `Начислено / Оплачено / Всего к оплате / Из них просрочено`.
- Частичная оплата больше не скрывает долг.
- Fixed 3000 ₽ / paid 2000 ₽ показывает остаток 1000 ₽.
- Карточки переименованы: `Всего к оплате` включает просрочку, `Из них просрочено` является подмножеством общего долга.

Файлы:

- `app/web/routes/dashboard.py`
- `app/web/templates/dashboard.html`

### Scheduler

- Генерация платежей стала идемпотентной по каждому подрядчику.
- Если за месяц уже есть один `Payment`, остальные подрядчики больше не пропускаются.
- При старте приложения добавлен одноразовый запуск генерации текущего месяца.

Файл:

- `app/scheduler.py`

### Payments

- Добавлен selector периода.
- Можно открыть прошлый месяц и вернуться в текущий.
- Фильтры работают по effective-status.
- При создании можно выбрать статус: `pending`, `paid`, `overdue`.
- При смене `paid` на `pending/overdue` очищаются `paid_amount` и `paid_date`.
- Чек предлагается только для `paid`.
- Скачивание старого чека показывается только если effective-status = `paid`.
- Добавление, редактирование и удаление возвращают пользователя в тот же период.
- Write-действия закрыты DB-backed admin check.

Файлы:

- `app/web/routes/payments.py`
- `app/web/templates/payments.html`

### History

- История стала read-only по чекам: только скачивание.
- Скачивание чека показывается только для effective-status `paid`.
- История использует effective-status как dashboard/payments.
- Добавлен столбец `Остаток`.
- CSV export использует planned/paid/remaining/effective-status.

Файлы:

- `app/web/routes/history.py`
- `app/web/templates/history.html`

### Auth

- Добавлен подписанный session cookie.
- Пользователь загружается из БД.
- Проверяется `User.is_active`.
- Guards больше не доверяют `user_role` / `page_permissions` из cookies.
- После потери сессии login возвращает на исходную страницу через `next`.

Файлы:

- `app/web/routes/auth.py`
- `app/web/templates/login.html`
- `app/web/templates/settings.html`

### Contractors

- Write routes закрыты DB-backed admin check.
- Доступ больше не решается через cookie role.

Файл:

- `app/web/routes/contractors.py`

### Analytics

- Годовой selector больше не строится от выбранного года.
- После выбора 2024/2022 в списке не пропадает 2026.
- Исправлена single-month логика previous/current.

Файлы:

- `app/web/routes/analytics.py`
- `app/web/templates/analytics.html`

### Telegram bot

- Исправлен Docker entrypoint: `python -m app.bot.main`.
- Telegram document валидируется через `is_allowed_file`.
- Теги читаются и из текста, и из подписи к фото/документу.
- Поддерживается текущий месяц:

```text
#оплачено #slug #сумма:3200
```

- Поддерживается явный период:

```text
#оплачено #slug #сумма:1000 #период:2026-06
```

- Добавлен интерактивный сценарий без тегов: пользователь присылает файл/фото, бот спрашивает подрядчика, сумму, период, подтверждение и сохраняет оплату.
- Добавлена команда `/cancel`.

Файлы:

- `docker/Dockerfile.bot`
- `app/bot/parsers.py`
- `app/bot/handlers.py`
- `app/bot/interactive.py`
- `app/bot/main.py`

## 2. Важное ограничение модели платежей

Сейчас `Payment` — это одна строка на `contractor/year/month`.

Она умеет показать начислено, оплачено, остаток, просрочку и один чек в `receipt_file`.

Для полноценной истории частичных оплат и нескольких чеков нужен следующий этап:

```text
PaymentPeriod
PaymentTransaction
```

## 3. Что можно делать сейчас

### Web UI

- Смотреть долги и просрочки.
- Выбирать месяц на странице `Платежи`.
- Создавать и редактировать платежи за выбранный месяц.
- Менять статус.
- Прикладывать и скачивать чек только для effective-status `paid`.
- Смотреть историю как read-only журнал с фильтрами, остатком, чеками и CSV.
- После логина возвращаться на исходную страницу.

### Telegram

- Оплата текущего месяца тегами.
- Оплата старого периода тегом `#период:YYYY-MM`.
- Интерактивный сценарий без тегов.

## 4. QA текущего пакета

1. `git pull origin audit-dashboard-fixes`.
2. `docker compose up -d --build`.
3. Проверить Web UI: dashboard, payments, history, analytics.
4. Проверить, что чек виден только у paid.
5. Проверить Telegram тегами без файла.
6. Проверить Telegram тегами в подписи к файлу/фото.
7. Проверить Telegram со старым периодом.
8. Проверить Telegram без тегов: файл/фото → подрядчик → сумма → период → подтверждение.
9. Проверить `/cancel`.

## 5. Технический долг

- PaymentTransaction ledger.
- CSRF для POST-форм.
- `COOKIE_SECURE` для production.
- Alembic вместо ручных миграций.
- Автотесты.
