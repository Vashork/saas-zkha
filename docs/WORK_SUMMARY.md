# Work summary for `audit-dashboard-fixes`

Дата: 2026-06-24
Ветка: `audit-dashboard-fixes`
PR: `#1`

Этот файл является единым самари по работе в ветке. Он заменяет отдельные файлы `AGENT_FIX_LOG.md` и `SECOND_PASS_REVIEW.md`.

## 1. Что исправлено

### Dashboard

Исправлено:

- список месяцев;
- подсветка выбранного месяца;
- передача `month` в шаблон;
- расчёт начислено / оплачено / остаток / просрочено;
- отображение variable-платежей;
- отображение частичной оплаты как долга;
- таблица дашборда теперь показывает `Начислено`, `Оплачено`, `Остаток`, `Срок`, `Статус`.

#### Бизнес-правило по долгу

Если у fixed-подрядчика плановый платёж 3000 ₽, а оплачено или внесено по счёту 2000 ₽, на дашборде должен отображаться долг 1000 ₽.

```text
Contractor.fixed_amount = 3000
Payment.amount = 2000
Payment.paid_amount = 2000
Остаток = 1000
```

Правило расчёта:

- для fixed-подрядчика `Contractor.fixed_amount` считается базовым планом;
- если `Payment.amount` больше fixed amount, используется большее значение;
- если `Payment.paid_amount` больше обоих значений, используется оно;
- остаток = `planned_amount - paid_amount`, но не меньше нуля;
- `status='paid'` больше не обнуляет долг автоматически, если есть остаток.

Файлы:

- `app/web/routes/dashboard.py`
- `app/web/templates/dashboard.html`

### Scheduler / monthly payment generation

Исправлено:

- генерация платежей больше не останавливается, если за месяц уже есть хотя бы один `Payment`;
- генерация стала идемпотентной по каждому подрядчику;
- при старте приложения добавлен одноразовый запуск генерации, чтобы дозаполнить текущий месяц.

Раньше:

```text
если за месяц есть хотя бы один Payment — генерация полностью пропускалась
```

Теперь:

```text
для каждого активного подрядчика:
    если Payment за текущий год/месяц уже есть — пропустить только этого подрядчика
    если Payment нет — создать pending Payment
```

Файл:

- `app/scheduler.py`

### Payments: период, долги, статусы и ручное редактирование

Исправлено:

- страница `Платежи` получила selector периода, как dashboard;
- можно открыть прошлый месяц и вернуться в текущий;
- фильтры статусов сохраняют выбранный год/месяц;
- фильтры теперь работают по effective-status, а не только по сырому `Payment.status` из БД;
- запись, которая визуально просрочена из-за остатка и прошедшего срока, теперь попадает в фильтр `Просрочено`;
- при создании платежа можно выбрать статус: `Ожидает оплаты`, `Оплачено`, `Просрочено`;
- можно создать платёж за прошлый месяц ещё не оплаченным;
- при смене статуса с `paid` на `pending/overdue` очищаются `paid_amount` и `paid_date`, поэтому статус реально меняется;
- ручное добавление платежа создаёт запись именно за выбранный период, а не всегда за текущий месяц;
- редактирование и удаление после сохранения возвращают пользователя в тот же период;
- таблица `Платежи` теперь считает `Начислено / Оплачено / Остаток` по той же логике, что dashboard;
- fixed 3000 ₽ / paid 2000 ₽ теперь показывает остаток 1000 ₽ и на странице `Платежи`;
- write-действия `add_payment`, `edit_payment`, `delete_payment` закрыты DB-backed admin check;
- ошибки формы больше не рендерят пустой контекст без payments/contractors;
- суммы и даты валидируются аккуратнее;
- UI context страницы платежей берётся из пользователя БД, а не из display cookies.

Файлы:

- `app/web/routes/payments.py`
- `app/web/templates/payments.html`

### Auth / login return

Исправлено:

- если сессия слетела или контейнер перезапущен, protected pages редиректят на `/login?next=<текущая-страница>`;
- после успешного логина пользователь возвращается на ту страницу, которую открывал, например `/payments?year=2026&month=5`, а не всегда на dashboard;
- login redirect защищён от внешних URL: разрешены только локальные относительные пути.

Файлы:

- `app/web/routes/auth.py`
- `app/web/templates/login.html`

### Contractors security

Исправлено:

- `add_contractor`, `edit_contractor`, `delete_contractor`, `toggle_contractor` закрыты DB-backed admin check;
- `toggle_contractor` теперь принимает `Request`;
- решения доступа больше не принимаются по `request.cookies.get('user_role')`;
- UI context для страницы подрядчиков берётся из пользователя БД, а не из display cookies.

Файл:

- `app/web/routes/contractors.py`

### Bot Dockerfile

Исправлена точка входа Telegram-бота.

```text
python -m app.bot  ->  python -m app.bot.main
```

Файл:

- `docker/Dockerfile.bot`

### Auth / settings

Исправлено:

- добавлен подписанный cookie `session`;
- пользователь загружается из БД;
- проверяется `User.is_active`;
- access guards больше не доверяют `user_role` / `page_permissions` из cookies;
- деактивированный пользователь не проходит login/session guard;
- исправлена путаница `theme` / `ui_theme`;
- исправлена форма смены имени;
- исправлена форма смены пароля, добавлено поле `confirm_password`.

Файлы:

- `app/web/routes/auth.py`
- `app/web/templates/settings.html`

### History

Исправлено:

- URL чеков переведён на `/uploads/{{ p.receipt_file }}`;
- UI context страницы истории берётся из пользователя БД, а не из display cookies.

Файлы:

- `app/web/templates/history.html`
- `app/web/routes/history.py`

### Analytics

Исправлено:

- годовой selector больше не строится как `[year, year-1, year-2, year-3, year-4]` от выбранного года;
- после выбора 2024/2022 в списке теперь не пропадает 2026;
- backend отдаёт стабильный `year_options`: текущий год, выбранный год, последние годы и годы, которые есть в платежах;
- исправлена single-month логика: previous/current считаются отдельно, без мёртвой переменной `vals_curr`;
- UI context страницы аналитики берётся из пользователя БД, а не из display cookies.

Файлы:

- `app/web/routes/analytics.py`
- `app/web/templates/analytics.html`

### Telegram bot handlers

Исправлено:

- удалён неиспользуемый `Decimal` import;
- Telegram document теперь валидируется через `is_allowed_file`;
- variable-платёж теперь заполняет `Payment.amount`, если он был пустой;
- `receipt_file` больше не затирается `None`, если чек не был приложен;
- бот ищет pending и overdue платежи текущего месяца.

Файл:

- `app/bot/handlers.py`

## 2. Ошибки агента, которые были найдены

1. Dashboard неправильно работал с месяцами.
2. Backend не передавал `month`, хотя шаблон его использовал.
3. Долг считался только по `Payment.amount`, что ломало variable-платежи и частичные оплаты.
4. Fixed-подрядчик с планом 3000 ₽ и оплатой 2000 ₽ мог выглядеть как полностью закрытый.
5. Dashboard слепо доверял `status='paid'` и мог скрывать остаток.
6. Scheduler пропускал генерацию остальных подрядчиков, если за месяц уже был один платёж.
7. Страница `Платежи` была привязана только к текущему месяцу.
8. Страница `Платежи` считала остаток не так, как dashboard.
9. При создании платежа нельзя было выбрать статус.
10. Платёж с визуальным статусом `просрочено` мог отсутствовать в фильтре `Просрочено`, потому что фильтр смотрел только на сырой DB status.
11. При смене статуса с `paid` на `pending/overdue` могли оставаться `paid_amount/paid_date`, из-за чего визуально ничего не менялось.
12. После истечения/сброса сессии login всегда возвращал на dashboard, а не на исходную вкладку.
13. Bot container запускался через неправильный module entrypoint.
14. Auth доверял клиентским cookies.
15. Login не проверял `User.is_active`.
16. Settings сохранял тему в разные ключи.
17. Form field смены имени не совпадал с backend.
18. Form field смены пароля не совпадал с backend.
19. History использовал неправильный путь к uploaded receipts.
20. Contractors write routes были защищены слабо или не защищены.
21. Payments write routes были защищены только доступом к странице.
22. Analytics терял 2026 после выбора 2024/2022.
23. Analytics single-month branch содержал мёртвую переменную и неверный current/previous dataset.
24. Bot handlers не валидировали Telegram document и не заполняли `Payment.amount` для variable-платежей.

## 3. Важное ограничение текущей модели платежей

Сейчас модель `Payment` — это одна строка на `contractor/year/month`.

Она умеет показать:

- начислено;
- оплачено;
- остаток;
- просрочку;
- один чек в `receipt_file`.

Но она ещё не является полноценным журналом частичных оплат. Если один долг закрывается несколькими платежами и несколькими чеками, текущая модель хранит это с ограничениями: по сути обновляется одна строка, а не создаётся история отдельных оплат.

Лучшее долгосрочное решение — отдельная таблица операций:

```text
PaymentPeriod
- contractor_id
- year
- month
- planned_amount
- due_date
- status

PaymentTransaction
- payment_period_id
- paid_amount
- paid_date
- receipt_file
- source: web | telegram
- comment
```

## 4. Что можно делать сейчас

### Web UI

Можно:

- смотреть долги и просрочки на dashboard;
- выбрать месяц на странице `Платежи`;
- создать платёж за выбранный месяц со статусом `pending/paid/overdue`;
- редактировать платёж за выбранный месяц;
- менять статус платежа;
- видеть долг fixed 3000 ₽ / paid 2000 ₽ / remaining 1000 ₽;
- фильтровать по effective-status;
- после логина возвращаться на исходную страницу.

### Telegram bot

Сейчас бот фиксирует оплату по тегам текущего месяца:

```text
#оплачено #slug #сумма:3200
```

Для старого долга следующий шаг — добавить явный период:

```text
#оплачено #slug #сумма:1000 #период:2026-06
```

## 5. Что ещё осталось как технический долг

### Telegram bot period targeting

Нужно добавить поддержку периода в Telegram-тегах, чтобы бот мог закрывать старые долги, а не только текущий месяц.

### Payment transaction ledger

Нужно добавить отдельный журнал оплат, если требуется корректная история нескольких частичных оплат и нескольких чеков.

### CSRF

Во всех POST-формах пока нет CSRF-token.

### Session cookie secure flag

Session cookie выставляется с `httponly=True` и `samesite='lax'`, но без `secure=True`. Для production надо добавить настройку `COOKIE_SECURE=true/false`.

### Database migrations

Миграции всё ещё идут вручную через `PRAGMA table_info` и `ALTER TABLE`. Нужно вынести schema changes в Alembic.

### Tests

Нужны тесты на:

- dashboard debt logic;
- fixed 3000 / paid 2000 / remaining 1000;
- payments period selector;
- payment status create/edit;
- effective-status filters;
- login return after session reset;
- scheduler per-contractor generation;
- auth/session guards;
- contractors admin-only writes;
- payments admin-only writes;
- analytics year selector;
- telegram payment with explicit period.

## 6. Рекомендуемый порядок QA текущего пакета

1. `git pull origin audit-dashboard-fixes`.
2. `docker compose up -d --build`.
3. Открыть `Платежи`, выбрать прошлый месяц.
4. Создать платёж за прошлый месяц со статусом `Ожидает оплаты`.
5. Создать/изменить платёж со статусом `Оплачено`.
6. Изменить `Оплачено` обратно на `Ожидает` или `Просрочено` и проверить, что `Оплачено` обнуляется.
7. Проверить фильтр `Просрочено`: визуально просроченная запись должна появиться там.
8. Открыть `/payments?year=2026&month=5`, сбросить/потерять сессию, залогиниться и убедиться, что вернуло обратно на майские платежи.
9. Проверить старое: dashboard, analytics year selector, contractors/payments admin-only writes.

## 7. Следующий безопасный кусок после QA

Добавить поддержку периода в Telegram-тегах:

```text
#оплачено #ростелеком #сумма:1000 #период:2026-06
```

## 8. Статус PR

PR стал заметно ближе к рабочему состоянию. Для локального использования и дальнейшего ручного тестирования ветка уже полезна.

Перед production merge я бы ещё добавил Telegram period targeting, PaymentTransaction ledger, CSRF, production secure-cookie setting, Alembic и тесты.
