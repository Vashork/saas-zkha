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
- результат backup пишется в `backup_history`.

---

## 4. Актуальный технический долг без Telegram

### CSRF

POST-формы пока без CSRF-защиты. Для локального MVP терпимо, для публикации в сеть нужно добавить CSRF-токены.

### Sessions

Signed session cookie подходит для локального MVP. Для production лучше server-side sessions или устойчивый session store.

### Backup

Базовый `/backups` UI добавлен. Дальнейшие улучшения:

- автоочистка старых backup через web-логику;
- restore-инструкция;
- проверка целостности архива;
- более полный архив проекта при необходимости.

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
