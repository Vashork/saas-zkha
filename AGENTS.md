# AGENTS.md — ZhKH Bot

Единый актуальный файл проекта для ветки `audit-dashboard-fixes`.

В этот файл сведены актуальные сведения из старых документов:

- `README.md`
- `PLAN.md`
- `PLAN_BATCH2.md`
- `TODO.md`
- старого `AGENTS.md`

Старые отдельные документы после объединения считаются устаревшими.

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
- `./logs` монтируется в `/var/log/zhkh-bot`.

Стек:

- Python 3.11;
- FastAPI;
- Jinja2;
- Chart.js;
- aiogram 3.x;
- SQLAlchemy async;
- SQLite / aiosqlite;
- APScheduler;
- Docker Compose;
- nginx.

---

## 3. Запуск

```bash
git clone https://github.com/Vashork/saas-zkha.git zhkh-bot
cd zhkh-bot
git checkout audit-dashboard-fixes
cp .env.example .env
docker compose up -d --build
```

Проверка:

```bash
docker ps
docker logs zhkh-web --tail=100
docker logs zhkh-bot --tail=100
```

Веб-интерфейс:

```text
http://localhost
```

---

## 4. Структура

```text
app/
├── web/
│   ├── main.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── payments.py
│   │   ├── history.py
│   │   ├── contractors.py
│   │   └── analytics.py
│   ├── templates/
│   └── static/
├── models.py
├── schemas.py
├── database.py
├── scheduler.py
├── config.py
└── utils.py

docker/
├── Dockerfile.web
├── Dockerfile.bot
└── nginx.conf
```

Блок по Telegram-боту находится в конце файла.

---

## 5. Текущее состояние ветки `audit-dashboard-fixes`

Ветка уже содержит важные исправления:

- signed session cookie `session`;
- `_require_page()` читает активного пользователя и права из БД;
- display-only legacy cookies не используются для авторизации;
- login проверяет активного пользователя;
- contractor write-actions ограничены admin-only;
- dashboard безопасно парсит `year` и `month`;
- dashboard строит устойчивый selector месяцев;
- dashboard считает planned / paid / remaining amount;
- dashboard учитывает variable payments без суммы;
- scheduler запускает генерацию при старте как repair-step;
- scheduler по расписанию обновляет просроченные платежи.

---

## 6. Актуальный технический долг

### Dashboard UX

Нужно вручную проверить, как должны работать карточки:

- `total` и `paid` относятся к выбранному месяцу;
- `pending` и `overdue` сейчас тоже считаются по выбранному месяцу;
- список ближайших платежей берётся из всех открытых платежей.

Открытый вопрос: `pending/overdue` должны быть глобальными или только за выбранный месяц.

### Security

- POST-формы пока без CSRF-защиты.
- Signed session cookie подходит для локального MVP.
- Для production лучше server-side sessions или устойчивый session store.

### Миграции

Миграции сейчас в двух местах:

- `app/database.py`;
- `init_db.py`.

Если добавляешь колонку — добавляй миграцию в оба файла.

### Backup UI

Есть backup script и таблица `backup_history`, но страницы `/backups` пока нет.

---

## 7. Актуальный TODO

### Проверка ветки

- [ ] Запустить `docker compose up -d --build`.
- [ ] Проверить вход активным пользователем.
- [ ] Проверить, что деактивированный пользователь не входит.
- [ ] Проверить права обычного пользователя после изменения `page_permissions`.
- [ ] Проверить admin-only действия в `/contractors`.
- [ ] Проверить dashboard selector.
- [ ] Проверить dashboard по месяцам с fixed и variable подрядчиками.
- [ ] Проверить variable payment без суммы.
- [ ] Проверить загрузку чека и последующую аналитику.

### Dashboard

- [ ] Решить, должны ли `pending/overdue` карточки быть глобальными или по выбранному месяцу.
- [ ] Проверить подписи `unpaid_subtext` и `overdue_subtext`.
- [ ] Проверить график последних 6 месяцев относительно выбранного месяца.

### Уведомления

- [ ] Подключить реальную отправку уведомлений из scheduler.
- [ ] Определить получателей уведомлений.
- [ ] Не слать дубли уведомлений без истории отправки.
- [ ] Добавить настройки уведомлений из БД.

### Backup UI

- [ ] Добавить страницу `/backups`.
- [ ] Добавить кнопку ручного backup.
- [ ] Писать результат backup в `backup_history`.

---

## 8. Правила разработки

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

## 9. Что удалено как неактуальное

Не перенесены устаревшие утверждения:

- `PLAN.md`: приватный репозиторий;
- `PLAN.md`: `www-data` в Dockerfile;
- `PLAN.md`: nginx route `/bot -> bot:8001`;
- `PLAN.md`: `/settings` отложена до v2;
- `PLAN.md`: `push pending`;
- `PLAN_BATCH2.md`: задачи, уже закрытые в ветке `audit-dashboard-fixes`;
- `TODO.md`: проблема cookie permissions в исходном виде уже закрыта через signed session cookie и DB-based access control;
- `README.md`: уведомления описаны оптимистичнее, чем реализовано фактически.

---

# 10. Telegram-бот

Этот раздел намеренно расположен в конце файла.

## Назначение

Telegram-бот фиксирует оплату без захода в веб-интерфейс.

Формат сообщения:

```text
#оплачено #мосэнергосбыт #сумма:3200
```

Можно приложить чек как фото или документ.

## Файлы

```text
app/bot/
├── main.py
├── handlers.py
├── parsers.py
└── notifications.py
```

## Команды

```text
/start
/contractors
```

## Ограничения

- Нет полноценной проверки разрешённого Telegram-пользователя.
- Связка web user ↔ Telegram user не завершена.
- Уведомления в `app/bot/notifications.py` есть, но scheduler пока их не вызывает.
- Нужно решить защиту от дублей уведомлений.

## TODO по боту

- [ ] Добавить проверку отправителя.
- [ ] Связать Telegram user с web user.
- [ ] Подключить scheduler к отправке уведомлений.
- [ ] Добавить историю отправленных уведомлений.
- [ ] Добавить тесты на `parse_payment_message()`.
