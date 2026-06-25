# AGENTS.md — единый актуальный файл проекта ZhKH Bot

> Единый источник правды для продолжения разработки.  
> В этот файл объединены актуальные части из `README.md`, `PLAN.md`, `PLAN_BATCH2.md`, `TODO.md` и старого `AGENTS.md`.  
> Устаревшие утверждения удалены. Сегмент Telegram-бота вынесен в отдельный раздел в самый конец.

---

## 1. Что это за проект

**ZhKH Bot** — локальная система учёта коммунальных платежей ЖКХ.

Проект нужен, чтобы:

- вести справочник подрядчиков: энергосбыт, водоканал, газ, управляющая компания, интернет и т.д.;
- автоматически создавать ежемесячные платежи по активным подрядчикам;
- фиксировать оплату через веб-интерфейс;
- хранить чеки: PDF, JPG, JPEG, PNG;
- видеть дашборд, историю платежей, аналитику расходов и настройки пользователей;
- в отдельном контейнере запускать Telegram-бота для фиксации оплат и будущих уведомлений.

**Репозиторий:** `https://github.com/Vashork/saas-zkha`  
**Основная ветка:** `main`  
**Текущий формат:** Docker Compose, локальный запуск, SQLite в volume `./data`.

---

## 2. Текущая архитектура

Проект запускается тремя контейнерами:

```text
┌────────────────────────────────────────────────────────────┐
│ Docker network: zhkh-bot-network                          │
│                                                            │
│ ┌──────────────┐        ┌──────────────┐                  │
│ │   nginx      │ ─────► │    web       │                  │
│ │ reverse proxy│        │ FastAPI      │                  │
│ │ host :80     │        │ internal:8000│                  │
│ └──────────────┘        └──────────────┘                  │
│                                                            │
│ ┌──────────────┐                                          │
│ │    bot       │                                          │
│ │ aiogram      │                                          │
│ └──────────────┘                                          │
│                                                            │
│ Volumes:                                                   │
│ ./data → /app/data              SQLite DB + uploads        │
│ ./logs → /var/log/zhkh-bot      app logs                  │
└────────────────────────────────────────────────────────────┘
```

| Контейнер | Назначение | Важные детали |
|---|---|---|
| `zhkh-web` | FastAPI + Jinja2 + статика | `uvicorn app.web.main:app --host 0.0.0.0 --port 8000` |
| `zhkh-nginx` | Reverse proxy | Публикует `80:80`, проксирует в `web:8000` |
| `zhkh-bot` | Telegram-бот | aiogram polling, отдельный процесс |

Фактические volume и переменные из `docker-compose.yml`:

```text
DATABASE_URL=sqlite+aiosqlite:////app/data/zhkh.db
UPLOAD_DIR=/app/data/uploads
LOG_DIR=/var/log/zhkh-bot
```

---

## 3. Стек

- Python 3.11
- FastAPI
- Uvicorn
- Jinja2
- Bootstrap 5 / CSS / Chart.js
- aiogram 3.x
- SQLAlchemy 2.0 async
- SQLite + aiosqlite
- APScheduler
- bcrypt
- Docker Compose
- nginx:alpine

---

## 4. Быстрый запуск в WSL / Ubuntu

```bash
git clone https://github.com/Vashork/saas-zkha.git zhkh-bot
cd zhkh-bot
cp .env.example .env
nano .env
```

Минимально заполнить в `.env`:

```env
SECRET_KEY=change-me-to-random-long-string
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_ID=
ADMIN_PASSWORD=admin
USER_PASSWORD=user
GENERATION_DAY=1
GENERATION_TIME=00:05
GENERATION_ENABLED=true
NOTIFICATION_TIME=09:00
NOTIFICATION_TIMEZONE=Europe/Moscow
```

Запуск:

```bash
docker compose up -d --build
```

Для старого `docker-compose` v1 лучше делать так:

```bash
docker-compose down
docker-compose up -d --build
```

Проверка:

```bash
docker ps
docker logs zhkh-web --tail=100
docker logs zhkh-bot --tail=100
```

Открыть:

```text
http://localhost
```

Логин по умолчанию:

```text
admin / пароль из ADMIN_PASSWORD
```

Остановка:

```bash
docker compose down
```

---

## 5. Структура проекта

```text
zhkh-bot/
├── app/
│   ├── web/
│   │   ├── main.py              FastAPI app, lifespan, static/uploads mount
│   │   ├── routes/
│   │   │   ├── auth.py          login/logout/settings/users/permissions
│   │   │   ├── dashboard.py     dashboard, stats, month selector, chart
│   │   │   ├── payments.py      current-month payments CRUD, receipt upload
│   │   │   ├── history.py       filters, payment history, CSV export
│   │   │   ├── contractors.py   contractor CRUD
│   │   │   └── analytics.py     analytics, YoY, charts
│   │   ├── templates/           Jinja2 templates
│   │   └── static/              CSS/JS
│   ├── models.py                SQLAlchemy models
│   ├── schemas.py               Pydantic schemas
│   ├── database.py              async DB engine/session + migrations
│   ├── scheduler.py             APScheduler jobs
│   ├── config.py                env settings
│   └── utils.py                 helpers: password/hash/date/upload/status
├── docker/
│   ├── Dockerfile.web
│   ├── Dockerfile.bot
│   └── nginx.conf
├── scripts/
│   └── backup.sh
├── data/                        runtime volume: DB + uploads
├── backups/                     local backup output
├── logs/                        runtime logs
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── init_db.py
└── AGENTS.md                    this file
```

Подробности по Telegram-боту намеренно вынесены в конец документа.

---

## 6. Модели данных

### `User`

| Поле | Назначение |
|---|---|
| `id` | integer primary key |
| `username` | логин, unique |
| `password_hash` | bcrypt hash |
| `telegram_user_id` | пока опционально, unique |
| `role` | `admin` или `user` |
| `page_permissions` | строка со slug страниц через запятую |
| `is_active` | активен/деактивирован |
| `created_at` | дата создания |

Важное ограничение: сейчас часть прав и роли хранится/читается через cookie. Это удобно для MVP, но небезопасно для публикации в интернет.

### `Contractor`

| Поле | Назначение |
|---|---|
| `id` | UUID string primary key |
| `name` | название подрядчика, unique |
| `slug` | короткий slug для бота и UI, unique |
| `payment_type` | `fixed` или `variable` |
| `fixed_amount` | сумма для фиксированного платежа |
| `due_day` | день месяца, 1–31 |
| `account_number` | лицевой счёт, optional |
| `description` | описание, optional |
| `is_active` | участвует ли в генерации платежей |

### `Payment`

| Поле | Назначение |
|---|---|
| `id` | string primary key |
| `contractor_id` | FK на подрядчика |
| `year`, `month` | период платежа |
| `amount` | начисленная сумма |
| `paid_amount` | фактически оплаченная сумма |
| `due_date` | срок оплаты |
| `paid_date` | дата оплаты |
| `status` | `pending`, `paid`, `overdue` |
| `receipt_file` | путь к чеку внутри `/uploads/` |
| `notes` | заметки |

Unique constraint: один платеж на подрядчика за год/месяц.

### `Setting`

Key-value таблица для системных настроек.

### `BackupHistory`

Таблица подготовлена под будущий мониторинг бекапов и DRP-режимы.

---

## 7. Веб-интерфейс

| URL | Файл | Назначение |
|---|---|---|
| `/login` | `app/web/routes/auth.py` | вход |
| `/logout` | `app/web/routes/auth.py` | выход |
| `/` | `app/web/routes/dashboard.py` | дашборд |
| `/payments` | `app/web/routes/payments.py` | платежи текущего месяца |
| `/history` | `app/web/routes/history.py` | история + CSV export |
| `/contractors` | `app/web/routes/contractors.py` | подрядчики |
| `/analytics` | `app/web/routes/analytics.py` | графики и аналитика |
| `/settings` | `app/web/routes/auth.py` | настройки, пользователи, права |
| `/settings/theme` | `app/web/routes/auth.py` | AJAX сохранения темы |
| `/health` | `app/web/main.py` | healthcheck |

---

## 8. Что уже реализовано

### Базовый функционал

- Docker Compose из трёх сервисов: web, bot, nginx.
- FastAPI веб-интерфейс.
- SQLite база в volume `./data`.
- Инициализация БД через `init_db.py`.
- Миграции вручную через `PRAGMA table_info` и `ALTER TABLE`.
- Seed пользователей `admin` и `user`.
- Seed дефолтных подрядчиков.
- CRUD подрядчиков.
- CRUD платежей текущего месяца.
- Загрузка чеков PDF/JPG/JPEG/PNG до 10 MB.
- История платежей с фильтрами.
- CSV export.
- Аналитика через Chart.js.
- Тёмная/светлая тема.
- Управление пользователями.
- Гранулярные права страниц.
- Деактивация/активация пользователей.
- Смена пароля пользователем.
- Смена пароля пользователя администратором.
- Локальный backup script `scripts/backup.sh`.

### Планировщик

`app/scheduler.py` уже содержит:

- `generate_monthly_payments()` — создаёт платежи для активных подрядчиков;
- `check_notifications()` — проверяет просрочки и помечает `overdue`.

Важно: фактическая отправка Telegram-уведомлений из scheduler пока не доведена до конца. Функция отправки есть в `app/bot/notifications.py`, но scheduler сейчас только логирует `TODO`.

---

## 9. Актуальные ограничения и технический долг

### 9.1 Авторизация и права доступа

Сейчас при логине сервер выставляет cookies:

```text
user_id
username
user_role
page_permissions
```

Проблемы:

- `user_role` и `page_permissions` можно подделать на клиенте;
- `_require_page()` проверяет права из cookie, а не из БД;
- если админ меняет права пользователю, у уже залогиненного пользователя cookie не обновляется;
- `login` должен проверять `is_active`, чтобы деактивированный пользователь не мог войти;
- для production нужен переход на server-side sessions или подписанные secure tokens.

Минимальный быстрый фикс:

1. В `_require_page()` читать пользователя и права из БД по `user_id`.
2. Проверять `is_active` на каждом защищённом запросе.
3. Не доверять `user_role` и `page_permissions` из cookie.
4. Cookie `username` оставить только для отображения или тоже подтягивать из БД.

Правильный фикс:

- server-side session table или signed session token;
- cookie только с session id;
- все права/роль/active — только из БД.

### 9.2 CSRF

Все POST-формы сейчас без CSRF-защиты. Для локального MVP терпимо, для публикации в сеть — нет.

### 9.3 Dashboard statistics

Текущая логика карточек `pending` и `overdue` считает платежи выбранного месяца. Практически удобнее сделать так:

- `total` и `paid` — за выбранный месяц;
- `pending` и `overdue` — глобально по всем неоплаченным платежам;
- список ближайших платежей уже берётся из всех неоплаченных платежей.

Файл: `app/web/routes/dashboard.py`.

### 9.4 `/contractors/{contractor_id}/toggle`

В `contractors.py` route toggle должен явно проверять авторизацию и права. Сейчас у функции нет `request` и нет вызова `_require_page()`.

Нужно привести к тому же стилю, что `delete_contractor()` и `edit_contractor()`:

- добавить `request: Request`;
- вызвать `_require_page(request, "contractors")`;
- решить, кто имеет право toggle: любой пользователь с доступом к странице или только admin.

### 9.5 Миграции

Миграции сейчас в двух местах:

- `app/database.py`;
- `init_db.py`.

Правило: если добавляешь колонку — добавляй миграцию в оба файла.

Долг на будущее: перейти на Alembic.

### 9.6 SQLite

SQLite подходит для локального MVP, но не для активной multi-user/multi-writer эксплуатации.

Если проект станет сетевым сервисом — рассмотреть PostgreSQL.

### 9.7 Бекапы

Есть `scripts/backup.sh` и таблица `backup_history`, но полноценной страницы `/backups` пока нет.

Будущие задачи:

- `/backups` UI;
- ручной запуск backup из веба;
- история backup в `backup_history`;
- автоочистка старых backup;
- Duplicity + GPG;
- Synology / SMB / WireGuard сценарий.

---

## 10. Актуальный TODO для ближайшей разработки

### Приоритет 1 — безопасность доступа

- [ ] Переписать `_require_page()` так, чтобы права читались из БД, а не из cookie.
- [ ] Добавить проверку `User.is_active` при логине.
- [ ] Добавить проверку `User.is_active` в protected routes.
- [ ] Исправить `/contractors/{contractor_id}/toggle`: добавить `_require_page()`.
- [ ] Определить модель: `admin` only или page permission для операций с подрядчиками/платежами.

### Приоритет 2 — dashboard

- [ ] Сделать `pending`/`overdue` глобальными по всем неоплаченным платежам.
- [ ] Оставить `total`/`paid` привязанными к выбранному месяцу.
- [ ] Проверить month selector на `undefined` после изменений.
- [ ] Защитить query params `year`/`month` от мусорных значений.

### Приоритет 3 — уведомления

- [ ] Связать `scheduler.check_notifications()` с `app.bot.notifications.send_notification()`.
- [ ] Определить получателей: `TELEGRAM_ADMIN_ID`, пользователи с `telegram_user_id`, или оба варианта.
- [ ] Не слать дубли уведомлений каждый день без истории отправки.
- [ ] Добавить настройки включения/выключения уведомлений из БД.

### Приоритет 4 — тестирование

- [ ] Проверить запуск `docker compose up -d --build`.
- [ ] Проверить все страницы веб-интерфейса.
- [ ] Проверить создание/редактирование/деактивацию пользователя.
- [ ] Проверить права обычного пользователя после перелогина.
- [ ] Проверить загрузку чека.
- [ ] Проверить аналитику после загрузки чека.
- [ ] Проверить backup script.

### Приоритет 5 — backup UI / v2

- [ ] Добавить страницу `/backups`.
- [ ] Добавить кнопку ручного backup.
- [ ] Писать результат backup в `backup_history`.
- [ ] Добавить systemd units для VPS.
- [ ] Добавить OCR/Vision API для парсинга чеков.

---

## 11. Правила разработки для AI-агентов

1. Всегда читай этот файл перед изменениями.
2. Не доверяй старым планам, если они противоречат текущему коду.
3. Перед правкой сверяйся с фактическими файлами в `app/`, `docker-compose.yml`, `docker/`.
4. Не используй `request.form.get()` в FastAPI handlers. Используй явные параметры `Form(...)`.
5. Не используй `conn.cursor()` в миграциях SQLAlchemy async. Используй `conn.execute(text(...))`.
6. Если добавляешь миграцию, меняй оба файла: `app/database.py` и `init_db.py`.
7. Всегда делай null-safe суммы: `p.amount or Decimal("0")`, `result.scalar() or Decimal("0")`.
8. Query params `year`, `month` парсить через `try/except ValueError`.
9. В Jinja2 не рассчитывать на Python builtins `max()`, `min()` и т.п.
10. Каждый `<select>` должен иметь уникальный `id`.
11. CSS variables: `:root` должен идти перед `[data-theme="light"]`.
12. Для Docker Compose v1 сначала делать `down`, потом `up -d --build`.
13. Commit messages писать в стиле Conventional Commits.

---

## 12. Проверки перед коммитом

Python syntax:

```bash
python3 -m py_compile $(find app -name '*.py') init_db.py
```

Jinja2 template syntax, пример:

```bash
python3 - <<'PY'
from jinja2 import Environment, FileSystemLoader
for name in [
    'base.html', 'login.html', 'dashboard.html', 'payments.html',
    'history.html', 'contractors.html', 'analytics.html', 'settings.html'
]:
    Environment(loader=FileSystemLoader('app/web/templates')).get_template(name)
    print('ok', name)
PY
```

Pytest:

```bash
python -m pytest tests/ -v
```

Docker smoke test:

```bash
docker compose up -d --build
docker ps
docker logs zhkh-web --tail=100
docker logs zhkh-bot --tail=100
```

---

## 13. Troubleshooting

| Симптом | Что проверить |
|---|---|
| `Permission denied` при Docker | `sudo usermod -aG docker $USER`, затем перелогин или `newgrp docker` |
| `Container is unhealthy` | `docker logs zhkh-web --tail=100` |
| Порт 80 занят | заменить `"80:80"` на `"8080:80"` в `docker-compose.yml` |
| 502 от nginx | проверить health web, `docker logs zhkh-web`, `docker logs zhkh-nginx` |
| CSS не грузится | FastAPI монтирует `/static`, nginx проксирует всё в web |
| БД не открывается | права на `./data`, наличие директории, volume mount |
| Пользователь видит лишние страницы | проблема cookie permissions; нужно читать права из БД |
| Аналитика показывает 0 | проверить `status='paid'` и `paid_amount` |
| Бот не отвечает | см. финальный раздел про Telegram-бота |

---

## 14. Что удалено как неактуальное при объединении

Из старых документов не перенесены устаревшие утверждения:

- `PLAN.md`: «репозиторий приватный» — сейчас репозиторий публичный.
- `PLAN.md`: `Dockerfile` с `www-data` — сейчас контейнеры запускаются как root для bind-mount совместимости.
- `PLAN.md`: nginx route `/bot → bot:8001` — фактически такого route в `docker/nginx.conf` нет.
- `PLAN.md`: `/settings` отложена до v2 — фактически страница настроек уже реализована.
- `PLAN.md`: «push pending» — проект уже находится в GitHub.
- `PLAN_BATCH2.md`: задачи про `is_active`, деактивацию и часть настроек в основном уже реализованы.
- `README.md`: блок про уведомления был слишком оптимистичным; фактическая Telegram-отправка из scheduler ещё не подключена.

---

# 15. Telegram-бот — отдельный сегмент

Этот раздел намеренно расположен в конце документа.

## 15.1 Назначение

Telegram-бот нужен для фиксации оплаты без захода в веб-интерфейс.

Формат сообщения:

```text
#оплачено #мосэнергосбыт #сумма:3200
```

Можно приложить чек как фото или документ.

## 15.2 Файлы

```text
app/bot/
├── main.py              entrypoint aiogram polling
├── handlers.py          /start, /contractors, #оплачено
├── parsers.py           парсинг хештегов и суммы
└── notifications.py     отправка Telegram-сообщений
```

Связанные файлы:

```text
app/config.py            TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID
app/scheduler.py         check_notifications(), пока без реальной отправки
app/models.py            Contractor, Payment, User.telegram_user_id
```

## 15.3 Команды

```text
/start
/contractors
```

`/contractors` показывает активных подрядчиков и их slug.

## 15.4 Как работает фиксация оплаты

1. Бот получает сообщение с `#оплачено`.
2. `parse_payment_message()` достаёт slug и сумму.
3. `paid_handler()` ищет `Contractor.slug`.
4. Ищет `Payment` за текущий месяц со статусом `pending`.
5. Если подрядчик `fixed` и сумма не указана — берёт `fixed_amount`.
6. Если подрядчик `variable` и сумма не указана — просит указать сумму.
7. Если приложен чек — сохраняет его в `/app/data/uploads/YYYY/MM/`.
8. Ставит:
   - `paid_amount`;
   - `paid_date`;
   - `status='paid'`;
   - `receipt_file`.

## 15.5 Текущие ограничения бота

- Если `TELEGRAM_BOT_TOKEN` пустой, контейнер бота не падает, а уходит в бесконечный sleep.
- Нет жёсткой проверки, что пишет именно разрешённый Telegram-пользователь.
- `TELEGRAM_ADMIN_ID` есть в `.env.example`, но логика доступа по нему не завершена.
- `User.telegram_user_id` есть в модели, но полноценная связка web user ↔ Telegram user не реализована.
- Уведомления в `app/bot/notifications.py` есть, но scheduler пока их не вызывает.
- Нужно решить, как предотвращать дубли уведомлений.

## 15.6 TODO по боту

- [ ] Добавить проверку отправителя по `TELEGRAM_ADMIN_ID` или `User.telegram_user_id`.
- [ ] Связать Telegram user с web user.
- [ ] Подключить `check_notifications()` к `send_notification()`.
- [ ] Добавить историю отправленных уведомлений, чтобы не спамить.
- [ ] Добавить обработку оплаты не только текущего месяца, а выбранного/последнего pending платежа.
- [ ] Улучшить UX ошибок: подрядчик не найден, платеж не найден, сумма неверная.
- [ ] Добавить тесты на `parse_payment_message()`.
