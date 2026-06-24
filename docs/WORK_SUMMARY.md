# Work summary for `audit-dashboard-fixes`

Дата: 2026-06-24
Ветка: `audit-dashboard-fixes`
PR: `#1`

Этот файл является единым самари по моей работе в ветке. Он заменяет отдельные файлы `AGENT_FIX_LOG.md` и `SECOND_PASS_REVIEW.md`.

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

Файлы:

- `app/web/routes/dashboard.py`
- `app/web/templates/dashboard.html`

#### Бизнес-правило по долгу

Если у fixed-подрядчика плановый платёж 3000 ₽, а оплачено или внесено по счёту 2000 ₽, на дашборде должен отображаться долг 1000 ₽.

Пример:

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

### Bot Dockerfile

Исправлена точка входа Telegram-бота.

Было:

```bash
python -m app.bot
```

Стало:

```bash
python -m app.bot.main
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

### Contractors security

Исправлено:

- `add_contractor`, `edit_contractor`, `delete_contractor`, `toggle_contractor` закрыты DB-backed admin check;
- `toggle_contractor` теперь принимает `Request`;
- решения доступа больше не принимаются по `request.cookies.get('user_role')`;
- UI context для страницы подрядчиков берётся из пользователя БД, а не из display cookies.

Файл:

- `app/web/routes/contractors.py`

### Payments security and error context

Исправлено:

- `add_payment`, `edit_payment`, `delete_payment` закрыты DB-backed admin check;
- убран неиспользуемый `ALLOWED_EXTENSIONS` import;
- ошибки формы больше не рендерят пустой контекст без payments/contractors;
- суммы и даты валидируются аккуратнее;
- UI context страницы платежей берётся из пользователя БД, а не из display cookies.

Файл:

- `app/web/routes/payments.py`

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
- после выбора 2024 в списке теперь не пропадает 2026;
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
- бот ищет pending и overdue платежи.

Файл:

- `app/bot/handlers.py`

## 2. Ошибки агента, которые были найдены

1. Dashboard неправильно работал с месяцами.
2. Backend не передавал `month`, хотя шаблон его использовал.
3. Долг считался только по `Payment.amount`, что ломало variable-платежи и частичные оплаты.
4. Fixed-подрядчик с планом 3000 ₽ и оплатой 2000 ₽ мог выглядеть как полностью закрытый.
5. Dashboard слепо доверял `status='paid'` и мог скрывать остаток.
6. Scheduler пропускал генерацию остальных подрядчиков, если за месяц уже был один платёж.
7. Bot container запускался через неправильный module entrypoint.
8. Auth доверял клиентским cookies.
9. Login не проверял `User.is_active`.
10. Settings сохранял тему в разные ключи.
11. Form field смены имени не совпадал с backend.
12. Form field смены пароля не совпадал с backend.
13. History использовал неправильный путь к uploaded receipts.
14. Contractors write routes были защищены слабо или не защищены.
15. Payments write routes были защищены только доступом к странице.
16. Analytics терял 2026 после выбора 2024.
17. Analytics single-month branch содержал мёртвую переменную и неверный current/previous dataset.
18. Bot handlers не валидировали Telegram document и не заполняли `Payment.amount` для variable-платежей.

## 3. Важное ограничение текущей модели платежей

Сейчас модель `Payment` — это одна строка на `contractor/year/month`.

Она умеет показать:

- начислено;
- оплачено;
- остаток;
- просрочку;
- один чек в `receipt_file`.

Но она ещё не является полноценным журналом частичных оплат. Если один долг закрывается несколькими платежами и несколькими чеками, текущая модель хранит это с ограничениями: по сути обновляется одна строка, а не создаётся история отдельных оплат.

Пример текущего поведения:

```text
Июнь
Начислено: 3000
Оплачено: 2000
Остаток: 1000
```

Дашборд это уже показывает правильно.

Но если потом доплатить ещё 1000 ₽, лучшее долгосрочное решение — не просто перезаписать `paid_amount`, а завести отдельную таблицу платежных операций.

Рекомендуемая будущая модель:

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

Тогда можно будет видеть:

- начисление за месяц;
- все частичные оплаты;
- несколько чеков;
- кто и когда внёс оплату;
- остаток на любую дату;
- историю закрытия долга.

## 4. Что можно делать сейчас

### Просмотр долгов и просрочек

Дашборд уже показывает долги и просрочки по всем платежам с ненулевым остатком.

История позволяет смотреть платежи за прошлые периоды и скачивать чеки.

Аналитика позволяет возвращаться к предыдущим годам и обратно к текущему году.

### Оплата долга за текущий месяц

Если долг за июнь находится в текущем месяце, его можно закрыть через страницу `Платежи`:

1. открыть `Платежи`;
2. найти нужного подрядчика;
3. нажать редактирование;
4. указать итоговую оплаченную сумму и дату оплаты;
5. при необходимости загрузить чек.

Но важно: сейчас форма редактирования работает как обновление одной строки платежа, а не как добавление отдельной доплаты.

### Оплата долга за прошлый месяц

Этого пока не хватает как полноценного UX.

Нужно добавить:

- selector периода на странице `Платежи`, как на dashboard;
- кнопку `Оплатить долг` из dashboard/history;
- возможность редактировать платежи за выбранный прошлый месяц;
- желательно отдельную модель `PaymentTransaction` для частичных оплат и нескольких чеков.

## 5. Что всё ещё осталось как технический долг

### Historical debt payment UX

Нужно сделать полноценный сценарий возврата к прошлым долгам:

- выбрать прошлый месяц на странице `Платежи`;
- увидеть долги за этот месяц;
- оплатить долг полностью или частично;
- приложить чек именно к этой оплате;
- увидеть обновлённый остаток на dashboard/history/analytics.

### Payment transaction ledger

Нужно добавить отдельный журнал оплат, если требуется корректная история нескольких частичных оплат.

Без этого система сможет показывать долг, но история оплаты будет ограниченной.

### Telegram bot period targeting

Сейчас бот фиксирует оплату за текущий месяц по тегам:

```text
#оплачено #slug #сумма:3200
```

Для оплаты старого долга нужно добавить поддержку периода:

```text
#оплачено #slug #сумма:1000 #период:2026-06
```

или коротко:

```text
#оплачено #slug #сумма:1000 #июнь2026
```

### CSRF

Во всех POST-формах пока нет CSRF-token.

Что нужно сделать следующим этапом:

- добавить CSRF-token для HTML-форм;
- проверять token на POST;
- минимум: double-submit cookie или server-side session token.

### Session cookie secure flag

Session cookie выставляется с `httponly=True` и `samesite='lax'`, но без `secure=True`.

Для localhost это допустимо, для production надо добавить настройку:

```text
COOKIE_SECURE=true/false
```

И включать `secure=True` в production.

### Database migrations

Миграции всё ещё идут вручную через `PRAGMA table_info` и `ALTER TABLE`.

Нужно вынести schema changes в Alembic.

### Tests

Нужны тесты на:

- dashboard debt logic;
- fixed 3000 / paid 2000 / remaining 1000;
- scheduler per-contractor generation;
- auth/session guards;
- contractors admin-only writes;
- payments admin-only writes;
- analytics year selector;
- historical debt payment;
- telegram payment with explicit period.

## 6. Рекомендуемый порядок дальнейших правок

1. Добавить selector периода на страницу `Платежи`.
2. Добавить оплату долга за выбранный прошлый месяц.
3. Добавить поддержку периода в Telegram-тегах.
4. Решить, нужна ли отдельная таблица `PaymentTransaction` для нескольких частичных оплат и нескольких чеков.
5. Добавить CSRF.
6. Добавить production secure-cookie setting.
7. Добавить Alembic.
8. Добавить тесты.

## 7. Рекомендуемый порядок проверки текущей ветки

1. `git pull origin audit-dashboard-fixes`.
2. `docker compose up -d --build`.
3. Проверить dashboard за текущий месяц.
4. Проверить кейс fixed 3000 ₽ / оплачено 2000 ₽ / остаток 1000 ₽.
5. Проверить, что scheduler после старта дозаполняет недостающие payments.
6. Проверить, что обычный user не может POST add/edit/delete для contractors/payments.
7. Проверить analytics: выбрать 2024 или 2022, затем убедиться, что 2026 остаётся в списке годов.
8. Проверить Telegram payment для variable-подрядчика.

## 8. Статус PR

PR стал заметно ближе к рабочему состоянию: dashboard, scheduler, auth, contractors, payments, analytics и bot handlers получили исправления.

Для локального использования и дальнейшего ручного тестирования ветка уже полезна.

Перед production merge я бы ещё добавил historical debt UX, поддержку периода в Telegram-тегах, CSRF, production secure-cookie setting, Alembic и тесты.
