# AGENTS.md — ZhKH Bot

Единый актуальный файл проекта для ветки `audit-dashboard-fixes`.

Старые документы `README.md`, `PLAN.md`, `PLAN_BATCH2.md`, `TODO.md` были объединены сюда и удалены из ветки.

---

## 1. Проект

**ZhKH Bot** — локальная система учёта коммунальных платежей ЖКХ.

Основные функции:

- справочник подрядчиков;
- генерация ежемесячных платежей;
- фиксация оплат через веб-интерфейс;
- загрузка и хранение чеков;
- дашборд;
- история платежей;
- аналитика;
- настройки пользователей и прав;
- локальные бекапы;
- отдельный Telegram-бот для фиксации оплат.

Рабочая ветка: `audit-dashboard-fixes`.

---

## 2. Архитектура

Проект запускается через Docker Compose.

Сервисы:

- `zhkh-web` — FastAPI + Jinja2;
- `zhkh-nginx` — reverse proxy, порт `80:80`, проксирует в `web:8000`;
- `zhkh-bot` — Telegram-бот на aiogram.

Runtime data:

- `./data` монтируется в `/app/data` и содержит SQLite DB + uploads;
- `./backups` монтируется в `/app/backups` и содержит локальные архивы;
- `./logs` монтируется в `/var/log/zhkh-bot`.

---

## 3. Текущее состояние ветки `audit-dashboard-fixes`

Ветка содержит:

- signed session cookie `session`;
- `_require_page()` читает активного пользователя и права из БД;
- display-only legacy cookies не используются для авторизации;
- login проверяет активного пользователя;
- contractor write-actions ограничены admin-only;
- dashboard безопасно парсит `year` и `month`;
- dashboard строит устойчивый selector месяцев;
- dashboard считает planned / paid / remaining amount;
- dashboard учитывает variable payments без суммы;
- dashboard показывает `total` и `paid` за выбранный месяц;
- dashboard показывает открытые долги и просрочки глобально по всем месяцам;
- scheduler запускает генерацию при старте как repair-step;
- scheduler по расписанию обновляет просроченные платежи;
- `/backups` добавлен как admin-only web UI;
- ручной backup создаёт архив каталога `data/`;
- результат backup пишется в `backup_history`;
- history CSV export использует те же фильтры, что страница истории;
- hard delete пользователя убран из UI настроек;
- ручное создание variable payment без суммы разрешено.

---

## 4. Roadmap после аудита

Двигаться сверху вниз. Telegram-бот расположен в самом конце и пока не дорабатывается.

### Этап 1 — критичные исправления запуска и данных

- [ ] Переписать миграции в `init_db.py` без raw `cursor()`, через `conn.execute(text(...))`. Запись через connector блокируется — поправить локально.
- [ ] Проверить, что `Dockerfile.web` успешно выполняет `python init_db.py` перед запуском web.

Локальная подсказка: в `init_db.py` надо убрать `conn_raw.cursor()` и сделать миграцию так же, как уже сделано в `app/database.py`: `from sqlalchemy import text`, затем `conn.execute(text("PRAGMA table_info(users)"))`, `conn.execute(text("ALTER TABLE ..."))`.

### Этап 2 — `/backups` UI

- [x] Добавить кнопку получения backup-файла в `backups.html`.
- [x] Исправить текст страницы: архивы сохраняются в `./backups` на хосте через Docker volume.
- [x] Проверить, что download route остаётся admin-only.

### Этап 3 — навигация

- [ ] Добавить ссылку `💾 Бекапы` для admin во все navbar-шаблоны. Сделано: dashboard, history, payments, contractors, settings. Осталось: analytics. Запись `analytics.html` через connector блокируется — поправить локально.
- [ ] В будущем вынести navbar в общий include, чтобы не дублировать меню в каждом шаблоне.

Локальная подсказка для `analytics.html`: после ссылки `📈 Аналитика` добавить `{% if user_role == 'admin' %}<a class="nav-link-custom" href="/backups">💾 Бекапы</a>{% endif %}` и заменить logout button на обычную ссылку по аналогии с dashboard/payments.

### Этап 4 — пользователи и безопасность операций

- [x] Убрать hard delete пользователя из UI.
- [x] Оставить основной сценарий управления пользователями через деактивацию.
- [ ] Позже добавить CSRF-токены для POST-форм.

### Этап 5 — деньги и фильтры

- [ ] Заменить `float` на `Decimal` при работе с `fixed_amount` подрядчиков. Запись `contractors.py` через connector блокируется — поправить локально.
- [x] Разрешить ручное создание variable payment без суммы.
- [x] Привести CSV export истории к тем же фильтрам, что страница истории: год, месяц, подрядчик, статус.

Локальная подсказка для `contractors.py`: добавить `from decimal import Decimal, InvalidOperation`, сделать helper для разбора `fixed_amount`, для `variable` сохранять `None`, для `fixed` сохранять `Decimal`, отрицательные значения запрещать.

### Этап 6 — production hardening

- [ ] Проверить поведение при дефолтном `SECRET_KEY` и дефолтных паролях.
- [ ] Добавить warning или fail-fast для production-сценария.
- [x] Описать restore-процедуру для backup.

Restore из backup:

```bash
docker compose down
mkdir -p data
# заменить имя архива на нужный файл из ./backups
tar -xzf ./backups/zhkh-data-backup-YYYYMMDD-HHMMSS.tar.gz -C .
docker compose up -d --build
docker logs zhkh-web --tail=100
```

Перед restore лучше сделать копию текущей папки `data/`.

### Этап 7 — Telegram-бот, позже

- [ ] Проверка разрешённого Telegram-пользователя.
- [ ] Связка web user ↔ Telegram user.
- [ ] Подключение scheduler к отправке уведомлений.
- [ ] История отправленных уведомлений.

---

## 5. Проверки перед коммитом

```bash
python3 -m py_compile $(find app -name '*.py') init_db.py
python -m pytest tests/ -v
docker compose up -d --build
docker ps
docker logs zhkh-web --tail=100
docker logs zhkh-bot --tail=100
```

---

## 6. Правила разработки

1. Работать в ветке `audit-dashboard-fixes`, если пользователь явно не сказал другое.
2. Перед правкой сверяться с фактическим кодом.
3. Не использовать `request.form.get()` в FastAPI handlers. Использовать явные `Form(...)`.
4. Не использовать `conn.cursor()` в миграциях SQLAlchemy async.
5. Если добавляешь миграцию, менять оба файла: `app/database.py` и `init_db.py`.
6. Делать null-safe расчёт сумм.
7. Query params парсить через `try/except`.
8. Каждый `<select>` должен иметь уникальный `id`.
9. Commit messages писать в стиле Conventional Commits.

---

# 7. Telegram-бот

Этот раздел намеренно расположен в конце файла. По текущей задаче Telegram-бот не дорабатывается.

## Назначение

Telegram-бот фиксирует оплату без захода в веб-интерфейс.

Формат сообщения:

```text
#оплачено #мосэнергосбыт #сумма:3200
```

## Файлы

```text
app/bot/
├── main.py
├── handlers.py
├── parsers.py
└── notifications.py
```

## Ограничения

- Нет полноценной проверки разрешённого Telegram-пользователя.
- Связка web user ↔ Telegram user не завершена.
- Уведомления в `app/bot/notifications.py` есть, но scheduler пока их не вызывает.
- Нужно решить защиту от дублей уведомлений.
