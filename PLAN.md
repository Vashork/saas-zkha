# План работ: Система учета платежей ЖКХ (MVP)

> **Цель:** MVP-версия — всё необходимое для работы системы без DRP v2 (страница настроек, страница бекапов, VPN, WireGuard, Duplicity). Всё масштабируемо.

---

## ✅ Этапы

| # | Этап | Статус | Комментарий |
|---|------|--------|-------------|
| **0** | **Подготовка проекта** | ✅ | Завершено 2025-06-24 |
| 0.1 | Создать приватный репозиторий на GitHub | ✅ | https://github.com/Vashork/saas-zkha |
| 0.2 | Инициализировать git + .gitignore (Python, Docker) | ✅ | first commit: f925509 |
| 0.3 | Создать структуру директорий проекта | ✅ | app/, docker/, scripts/, data/, backups/ |
| **1** | **Docker-основа** | ✅ | Завершено 2025-06-24 |
| 1.1 | `docker-compose.yml` — 3 сервиса: web, bot, nginx | ✅ | |
| 1.2 | `docker/Dockerfile.web` + `Dockerfile.bot` | ✅ | multi-stage, user www-data |
| 1.3 | `docker/nginx.conf` — reverse proxy | ✅ | / → web:8000, /bot → bot:8001, static, /uploads |
| 1.4 | `requirements.txt` — Python-зависимости | ✅ | FastAPI, aiogram, SQLAlchemy, APScheduler |
| 1.5 | `.env.example` — шаблон переменных | ✅ | 17 переменных |
| **2** | **База данных и модели** | ✅ | Завершено 2025-06-24 |
| 2.1 | `app/database.py` — асинхронная SQLite (aiosqlite) | ✅ | async_session_factory, get_db, init_db |
| 2.2 | `app/models.py` — SQLAlchemy 2.0 модели (users, contractors, payments, settings, backup_history) | ✅ | 5 таблиц |
| 2.3 | `app/schemas.py` — Pydantic схемы | ✅ | ContractorCreate/Update, PaymentCreate/Update, UserLogin/Create |
| 2.4 | `init_db.py` — создание таблиц + seed данных | ✅ | default users + 16 settings |
| **3** | **FastAPI — ядро** | ✅ | Завершено 2025-06-24 |
| 3.1 | `app/config.py` — загрузка настроек из .env + БД | ✅ | Settings class + load_from_db |
| 3.2 | `app/web/main.py` — инициализация FastAPI, middleware, static files | ✅ | lifespan, routers, static mount |
| 3.3 | `app/scheduler.py` — APScheduler (авто-генерация платежей + уведомления) | ✅ | generate_payments, check_notifications |
| 3.4 | `app/utils.py` — утилиты (хэширование, генерация UUID, валидация) | ✅ | hash/verify, month_name, payment_color_class, file validation |
| **4** | **FastAPI — маршруты (6 страниц)** | ✅ | Завершено 2025-06-24 |
| 4.1 | `routes/auth.py` — логин, сессия, logout | ✅ | cookie-based, 7-day session |
| 4.2 | `routes/dashboard.py` — дашборд (статистика + ближайшие платежи) | ✅ | chart data included |
| 4.3 | `routes/payments.py` — платежи текущего месяца (CRUD, фильтры) | ✅ | manual add + receipt upload |
| 4.4 | `routes/history.py` — история всех платежей (фильтры, экспорт CSV) | ✅ | year/month/contractor/status filters |
| 4.5 | `routes/contractors.py` — справочник подрядчиков (CRUD) | ✅ | toggle/delete for admin |
| 4.6 | `routes/analytics.py` — аналитика + 4 типа графиков | ✅ | monthly, top5, trends, YoY |
| **5** | **Фронтенд — шаблоны и стили** | ✅ | Завершено 2025-06-24 |
| 5.1 | `templates/base.html` — общий layout (navbar, sidebar, CSS-переменные) | ✅ | dark theme, Quicksand font |
| 5.2 | `templates/login.html` | ✅ | centered card, error display |
| 5.3 | `templates/dashboard.html` | ✅ | stat cards, table, Chart.js bar |
| 5.4 | `templates/payments.html` | ✅ | filters, table, manual add modal |
| 5.5 | `templates/history.html` | ✅ | multi-filter, CSV export |
| 5.6 | `templates/contractors.html` | ✅ | CRUD table, add modal |
| 5.7 | `templates/analytics.html` (Chart.js) | ✅ | 3 charts: bar, horiz-bar, line |
| 5.8 | `static/css/style.css` — адаптация из proto.html | ✅ | CSS variables, responsive |
| 5.9 | `static/js/main.js` — интерактивность (модальные окна, графики) | ✅ | modal close, escape key |
| **6** | **Telegram-бот** | ✅ | Завершено 2025-06-24 |
| 6.1 | `app/bot/__init__.py` — инициализация бота (aiogram 3.x) | ✅ | |
| 6.2 | `app/bot/parsers.py` — парсинг тегов `#оплачено #slug #сумма:X` | ✅ | regex-based, flexible format |
| 6.3 | `app/bot/handlers.py` — обработчики команд (оплата, /start, /contractors) | ✅ | receipt download support |
| 6.4 | `app/bot/notifications.py` — отправка уведомлений (просрочка, генерация) | ✅ | async send to chat_id |
| **7** | **Загрузка файлов** | ✅ | Завершено 2025-06-24 |
| 7.1 | Endpoint загрузки чеков (PDF/JPG/PNG, ≤10MB) | ✅ | in payments.py route |
| 7.2 | Сохранение в `/data/uploads/YYYY/MM/` | ✅ | get_upload_path() helper |
| 7.3 | Скачивание чеков через веб | ✅ | nginx /uploads location |
| **8** | **Локальный бекап (Режим C, MVP)** | ✅ | Завершено 2025-06-24 |
| 8.1 | Простой скрипт `scripts/backup.sh` — tar.gz БД + uploads | ✅ | auto-cleanup 7 days |
| 8.2 | Кнопка "Создать бекап" на дашборде | ⬜ | Вызывает скрипт (отложено до v2) |
| **9** | **Тестирование и запуск** | ⬜ | Следующий этап |
| 9.1 | Запуск `docker compose up -d` — проверка всех 3 контейнеров | ⬜ | |
| 9.2 | Проверка веб-интерфейса (все 6 страниц) | ⬜ | |
| 9.3 | Проверка Telegram-бота (команда оплаты) | ⬜ | |
| 9.4 | Проверка авто-генерации платежей | ⬜ | |
| 9.5 | Проверка уведомлений | ⬜ | |
| **10** | **Финализация** | ✅ | Завершено 2025-06-24 |
| 10.1 | `README.md` — инструкция по запуску на WSL | ✅ | quick start, structure, bot commands |
| 10.2 | Первым коммитом запушить всё в GitHub | ⬜ | push pending (needs user action) |

---

## 📊 Сводка

- **Этапов:** 11 (0–10)
- **Подзадач:** ~45
- **Ожидаемое время:** 2-3 дня непрерывной разработки

## 🚧 Что отложено до v2

- Страница `/settings` (настройки пользователей, уведомлений, UI)
- Страница `/backups` (мониторинг бекапов, DRP-интерфейс)
- Duplicity + GPG шифрование
- WireGuard VPN + SMB-шары Synology
- Режимы A/B бекапов
- Self-contained backup bundles
- Systemd-юниты для VPS
- VPN healthcheck

## 🔑 Масштабируемость

- **БД:** все таблицы `backup_history` и `settings` уже созданы — достаточно добавить UI
- **Настройки:** key-value модель `settings` — легко добавлять новые параметры
- **Бот:** модульная структура `bot/` — новые обработчики не ломают существующие
- **Скрипты:** `scripts/` уже выделены отдельно — DRP-скрипты добавляются без изменений кода
- **Docker:** compose-файл поддерживает `prod` override — миграция на VPS = заменить файл
