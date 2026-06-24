# Work summary for `audit-dashboard-fixes`

Дата: 2026-06-24
Ветка: `audit-dashboard-fixes`
PR: `#1`

Этот файл является единым самари по моей работе в ветке. Он заменяет отдельные файлы `AGENT_FIX_LOG.md` и `SECOND_PASS_REVIEW.md`.

## 1. Что было сделано в этой ветке

### Dashboard

Исправлены проблемы дашборда:

- некорректный список месяцев;
- выбранный месяц не подсвечивался;
- backend не передавал `month`, хотя шаблон его использовал;
- долг и неоплаченные счета считались неправильно;
- для variable-платежей добавлена безопасная логика отображения сумм;
- таблица дашборда показывает начислено, оплачено и остаток;
- частичная оплата теперь не скрывает долг.

Файлы:

- `app/web/routes/dashboard.py`
- `app/web/templates/dashboard.html`

#### Новое бизнес-правило по долгу

Если у подрядчика фиксированный платеж 3000 ₽, а оплачено или внесено по счету 2000 ₽, то на дашборде должен отображаться остаток 1000 ₽.

Для fixed-подрядчиков ожидаемая сумма считается так:

- берем `Contractor.fixed_amount` как базовый план;
- если `Payment.amount` больше фиксированной суммы, используем большее значение;
- если `Payment.paid_amount` больше обоих значений, используем его;
- остаток считается как `planned_amount - paid_amount`, но не меньше нуля.

Пример:

```text
Contractor.fixed_amount = 3000
Payment.amount = 2000
Payment.paid_amount = 2000
Остаток = 1000
```

Важно: статус `paid` больше не обнуляет долг автоматически. Если платеж помечен `paid`, но `paid_amount` меньше плановой суммы, такой платеж все равно остается в списке долгов.

### Scheduler / monthly payment generation

Исправлена логика генерации платежей за месяц.

Раньше scheduler работал неправильно:

```text
если за месяц есть хотя бы один Payment — генерация полностью пропускалась
```

Из-за этого могла появиться ситуация:

```text
10 активных подрядчиков
1 payment уже есть
scheduler видит count > 0
scheduler пропускает генерацию
9 подрядчиков не попадают на dashboard
```

Теперь генерация идемпотентная по каждому подрядчику:

```text
для каждого активного подрядчика:
    если Payment за текущий год/месяц уже есть — пропустить только этого подрядчика
    если Payment нет — создать pending Payment
```

Также добавлен одноразовый запуск генерации при старте приложения. После перезапуска контейнера текущий месяц должен дозаполниться недостающими строками платежей.

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

Улучшена авторизация:

- добавлен подписанный cookie `session`;
- пользователь загружается из БД;
- проверяется `User.is_active`;
- `user_role` и `page_permissions` в cookies больше не должны использоваться для принятия решений доступа;
- деактивированный пользователь больше не проходит login/session guard;
- исправлена путаница `theme` / `ui_theme`;
- исправлена форма смены имени;
- исправлена форма смены пароля, добавлено поле `confirm_password`.

Файлы:

- `app/web/routes/auth.py`
- `app/web/templates/settings.html`

### History

Исправлен URL скачивания чеков.

Было смешение путей:

- `/static/uploads/...`
- `/uploads/...`

Теперь history использует `/uploads/{{ p.receipt_file }}`.

Файл:

- `app/web/templates/history.html`

## 2. Ошибки агента, которые были найдены

1. В dashboard была неправильная работа с месяцами.
2. Backend не передавал `month`, хотя шаблон его использовал.
3. Долг считался только по `Payment.amount`, что ломало variable-платежи и частичные оплаты.
4. Fixed-подрядчик с планом 3000 ₽ и оплатой 2000 ₽ мог выглядеть как полностью закрытый.
5. Dashboard слепо доверял `status='paid'` и мог скрывать остаток.
6. Scheduler создавал платежи по принципу `если за месяц есть хоть один платеж — ничего не делать`, из-за чего пропадали платежи остальных подрядчиков.
7. Bot container запускался через неправильный module entrypoint.
8. Auth доверял клиентским cookies.
9. Login не проверял `User.is_active`.
10. Settings сохранял тему в разные ключи.
11. Form field смены имени не совпадал с backend.
12. Form field смены пароля не совпадал с backend.
13. History использовал неправильный путь к uploaded receipts.
14. Scheduler содержал мертвую переменную с потенциальным багом даты.

## 3. Второй проход ревью по моей же ветке

После первого пакета правок был выполнен повторный проход по ветке `audit-dashboard-fixes`.

Вывод: ветка стала лучше, но пока не готова к merge без дополнительных исправлений.

## 4. Что еще осталось исправить агенту

### P0 / P1 security blockers

#### 4.1. Contractors write routes

Файл:

- `app/web/routes/contractors.py`

Проблемы:

- `toggle_contractor` не принимает `Request`;
- `toggle_contractor` не вызывает `_require_page`;
- `toggle_contractor` не проверяет admin;
- `delete_contractor` проверяет admin через `request.cookies.get('user_role')`;
- `add_contractor` и `edit_contractor` проверяют только доступ к странице, но не admin.

Что сделать:

- все write-действия подрядчиков закрыть через DB-backed admin check;
- использовать `get_current_user(request, db)`;
- не использовать display cookies для решений доступа.

#### 4.2. Payments write routes

Файл:

- `app/web/routes/payments.py`

Проблема:

`add_payment`, `edit_payment`, `delete_payment` проверяют только доступ к странице `payments`. Если обычному пользователю разрешен просмотр страницы, backend позволяет write-действия.

Что сделать:

- добавить отдельную backend-проверку admin или право `edit_payments`;
- не полагаться на скрытие кнопок в HTML.

#### 4.3. UI context still reads display cookies

Файлы:

- `app/web/routes/dashboard.py`
- `app/web/routes/payments.py`
- `app/web/routes/history.py`
- `app/web/routes/analytics.py`
- `app/web/routes/contractors.py`

Проблема:

После перехода на signed session часть route-файлов все еще передает в шаблоны `username` и `user_role` из cookies.

Это не главный bypass доступа, но UI может показывать неверную роль.

Что сделать:

- после `_require_page` получать пользователя из БД через `get_current_user(request, db)`;
- передавать в шаблон `current_user.username` и `current_user.role`.

#### 4.4. CSRF

Проблема:

Во всех POST-формах нет CSRF-token.

Что сделать:

- добавить CSRF-token для HTML-форм;
- проверять token на POST;
- минимум: double-submit cookie или server-side session token.

#### 4.5. Session cookie secure flag

Файл:

- `app/web/routes/auth.py`

Проблема:

Session cookie выставляется с `httponly=True` и `samesite='lax'`, но без `secure=True`.

Что сделать:

- добавить setting `COOKIE_SECURE`;
- включать `secure=True` в production.

### P2 / code quality

#### 4.6. Analytics single-month logic

Файл:

- `app/web/routes/analytics.py`

Проблемы:

- `vals_curr` создается, но не используется;
- в single-month режиме массив previous/current формируется некорректно.

Что сделать:

- убрать `vals_curr`;
- считать previous и current отдельно;
- для одного выбранного месяца должен быть один label и одно значение в каждом dataset.

#### 4.7. Payments `_context()`

Файл:

- `app/web/routes/payments.py`

Проблема:

При ошибке `_context()` возвращает пустые `payments` и `contractors`, из-за чего страница может потерять таблицу и список подрядчиков.

Что сделать:

- заменить на async helper, который реально загружает payments/contractors.

#### 4.8. Bot handlers

Файл:

- `app/bot/handlers.py`

Проблемы:

- `Decimal` импортируется, но не используется;
- `is_allowed_file` импортирован, но не применяется для Telegram document;
- variable-платеж получает `paid_amount`, но если `amount` пустой, он не заполняется.

Что сделать:

```python
if payment.amount is None:
    payment.amount = amount
```

И добавить проверку `message.document.file_name` через `is_allowed_file`.

#### 4.9. Database migrations

Файл:

- `app/database.py`

Проблема:

Миграции идут вручную через `PRAGMA table_info` и `ALTER TABLE`.

Что сделать:

- подключить Alembic;
- перенести schema changes в нормальные миграции.

## 5. Рекомендуемый порядок следующих правок

1. Проверить после перезапуска контейнера, что scheduler дозаполнил текущий месяц недостающими `Payment`-строками.
2. Проверить кейс: fixed contractor 3000 ₽, оплачено 2000 ₽, на dashboard отображается остаток 1000 ₽.
3. Закрыть `contractors.py` write routes.
4. Закрыть `payments.py` write routes.
5. Убрать UI-зависимость от display cookies.
6. Добавить CSRF.
7. Исправить bot handlers.
8. Исправить analytics single-month chart.
9. Добавить тесты на dashboard/auth/settings/scheduler.
10. Потом уже думать про merge.

## 6. Статус PR

PR `#1` пока лучше считать рабочим PR, а не готовым к merge.

Dashboard и scheduler стали заметно ближе к правильной бизнес-логике по долгам, но в проекте еще остаются backend security blockers в `contractors.py` и `payments.py`.
