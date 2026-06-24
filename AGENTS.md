# AGENTS.md — Context for AI Agents working on ZhKH Bot

> Этот файл создан для быстрого онбординга любого AI-агента (Claude, Cursor, Gemini и т.д.) на проект.
> Читай его целиком, чтобы понять архитектуру, историю решений и текущее состояние.

---

## 1. Что это за проект

**ZhKH Bot** — локальная система учёта коммунальных платежей (ЖКХ) с веб-интерфейсом и Telegram-ботом.

- Пользователь управляет списком подрядчиков (энергосбыт, водоканал, УК и т.д.)
- Каждые 6-е число генерируются платежи на следующий месяц
- Оплата фиксируется через Telegram-бот (`#оплачено #slug #сумма:X`) или через веб-интерфейс
- Веб-интерфейс показывает дашборд, платежи, историю, подрядчиков, аналитику расходов
- Есть система пользователей с ролями (admin/user) и гранулярными правами доступа к страницам

**Репозиторий:** https://github.com/Vashork/saas-zkha
**Локальный клон:** `/home/gdyupin@diasoft.ru/project/zhkh-bot/`
**Второй клон (деплой):** `/home/gdyupin@diasoft.ru/project/saszhka/saas-zkha/`

---

## 2. Архитектура

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   nginx      │──►│   web        │   │   bot        │
│  (reverse    │   │  (FastAPI)   │   │  (aiogram)   │
│   proxy)     │   │  :8000       │   │              │
│  :80/:443    │   └──────────────┘   └──────────────┘
└──────────────┘

Volumes:
  data/     → /app/data (SQLite БД + загруженные чеки)
  logs/     → /var/log/zhkh-bot
```

| Компонент | Стек | Описание |
|-----------|------|----------|
| **Web** | FastAPI + Jinja2 + Uvicorn | Веб-интерфейс, маршруты, шаблоны, статики |
| **Bot** | aiogram 3.x + APScheduler | Telegram-бот, фиксация оплат, уведомления |
| **DB** | SQLite + aiosqlite + SQLAlchemy 2.0 | Асинхронный доступ к БД |
| **Nginx** | nginx:alpine | Reverse proxy, ждёт web healthy |

---

## 3. Структура кода

```
app/
├── web/
│   ├── main.py              # FastAPI app, lifecycle, mount статики
│   ├── routes/
│   │   ├── auth.py          # Логин/логин, _require_page(), настройки пользователя
│   │   ├── dashboard.py     # Главная страница, статистика, upcoming payments
│   │   ├── payments.py      # CRUD платежей, загрузка чеков
│   │   ├── history.py       # История с фильтрами и CSV-экспортом
│   │   ├── contractors.py   # CRUD подрядчиков
│   │   └── analytics.py     # Графики расходов (Chart.js), YoY сравнение
│   ├── templates/           # Jinja2 шаблоны (base.html + 7 страниц)
│   └── static/
│       ├── css/style.css    # CSS variables (--bg-main, --text, etc.), светлая/тёмная тема
│       └── js/main.js       # Модальные окна, селектор месяцев, toggleTheme()
├── bot/
│   ├── main.py              # aiogram bot entrypoint
│   ├── handlers.py          # Команды /start, /contractors, парсинг #оплачено
│   ├── parsers.py           # Парсинг хештегов из сообщений
│   └── notifications.py     # Уведомления о просроченных платежах
├── models.py                # SQLAlchemy модели: User, Payment, Contractor, Setting
├── database.py              # get_db(), init_db() с миграциями
├── scheduler.py             # APScheduler: генерация платежей, уведомления
├── config.py                # Настройки из .env
├── schemas.py               # Pydantic схемы
└── utils.py                 # month_name(), payment_color_class()
```

---

## 4. Модели данных

### User
| Поле | Тип | Описание |
|------|-----|----------|
| `username` | str | Имя входа |
| `password_hash` | str | Хеш пароля |
| `role` | str | "admin" или "user" |
| `is_active` | bool | Деактивирован ли пользователь (soft delete) |
| `page_permissions` | str | Запятая через slug: "dashboard,payments,history,contractors,analytics" |
| `ui_theme` | str | "dark" или "light" |

### Payment
| Поле | Тип | Описание |
|------|-----|----------|
| `contractor_id` | FK | Ссылка на подрядчика |
| `year, month` | int | Период платежа |
| `amount` | Decimal | Сумма платежа |
| `paid_amount` | Decimal | Оплаченная сумма (NULL если не оплачено) |
| `status` | str | "pending", "paid", "overdue" |
| `due_date` | Date | Дата оплаты |
| `paid_date` | Date | Дата фактической оплаты (NULL) |
| `receipt_file` | str | Имя файла чека в `/uploads/` |

### Contractor
| Поле | Тип |
|------|-----|
| `name` | str (unique) |
| `slug` | str (unique) |
| `monthly_amount` | Decimal |
| `due_day` | int (день месяца, по умолчанию 25) |
| `is_active` | bool |
| `payment_category` | str |

### Setting
| Поле | Тип |
|------|-----|
| `key` | str (unique) |
| `value` | str |

---

## 5. Ключевые паттерны и правила

### 5.1 Доступ к страницам (permissions)
- Функция `_require_page(request, slug)` в `auth.py` проверяет cookie `page_permissions`
- Админы bypass'ят все проверки
- Каждая route-страница вызывает `_require_page(request, "<slug>")` первым делом

### 5.2 FastAPI Form handling
- **Важно:** когда в функции есть параметры `Form(...)`, `request.form` — это функция-зависимость, НЕ dict
- Всегда используй явные `Form("")` параметры, а не `request.form.get()`
- Поля с `default=""` предотвращают перезапись данных при мультипарт-загрузке только файла

### 5.3 SQLAlchemy 2.0
- Используй `conn.execute(text("..."))` вместо `conn.cursor()`
- `run_sync()` для синхронных миграций в асинхронном контексте

### 5.4 Mиграции
- Вручную, через `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`
- Есть ДВА места с миграциями: `app/database.py` (init_db при старте) И `init_db.py` (при инициализации)
- **Оба должны содержать одинаковый набор миграций!**

### 5.5 Статус платежей
- `_effective_status(payment)` в `dashboard.py`: если `due_date <= today` и статус != paid → "overdue"
- `payment_color_class()` в `utils.py`: та же логика для CSS-классов
- В шаблонах показывай "просрочено" вместо "pending" если `payment_color_class() == 'overdue'`

### 5.6 Null-безопасность
- `p.amount or 0`, `p.paid_amount or 0` — везде, где используются суммы
- SQL `SUM()` может вернуть NULL — всегда `result.scalar() or Decimal("0")`
- Query params (`request.query_params.get("year")`) могут быть `"undefined"` из JS — всегда оборачивай `int()` в `try/except ValueError`

### 5.7 Темы
- CSS variables в `:root` (тёмная) и `[data-theme="light"]` (светлая)
- `:root` ДОЛЖЕН быть ПЕРЕД `[data-theme="light"]` в CSS
- Тема сохраняется в `localStorage` и через AJAX в БД (`/settings/theme`)
- `base.html` загружает тему из `localStorage` через inline-скрипт до рендера

### 5.8 Селекторы и ID
- Каждый `<select>` на странице должен иметь **уникальный id** (не `monthSelect` для всех)
- Дашборд: `monthSelect` с inline `onchange`, читает `options[selectedIndex].dataset.y/m`
- Аналитика: `analyticsYearSelect` + `analyticsMonthSelect`, JS функция `updateAnalytics()`
- НЕ используй глобальные обработчики в `main.js` для элементов, которые имеют inline `onchange`

### 5.8 Статические файлы
- FastAPI монтирует `/static` и `/uploads` через `StaticFiles`
- Nginx проксирует всё на `http://web:8000` (НЕ использует alias)

### 5.9 Docker
- Контейнеры запускаются как root (для bind-mount совместимости)
- `mkdir -p` в CMD для гарантии создания директорий
- Nginx healthcheck убран (вызывал проблемы с legacy docker-compose v1)
- **Legacy docker-compose v1.29.2:** требует `docker-compose down` перед `up -d --build`

---

## 6. Маршруты веб-интерфейса

| URL | Файл | Описание |
|-----|------|----------|
| `/login` | `auth.py` | GET: форма, POST: авторизация |
| `/logout` | `auth.py` | Выход |
| `/` | `dashboard.py` | Дашборд: статистика месяца, upcoming payments, график |
| `/payments` | `payments.py` | Текущие платежи, CRUD |
| `/history` | `history.py` | История с фильтрами, CSV-экспорт |
| `/contractors` | `contractors.py` | CRUD подрядчиков |
| `/analytics` | `analytics.py` | Графики расходов, YoY сравнение |
| `/settings` | `auth.py` | Настройки: профиль, система, управление пользователями |
| `/settings/users/...` | `auth.py` | CRUD пользователей, toggle-active, hard delete, change password |
| `/settings/save` | `auth.py` | Сохранение системных настроек |
| `/settings/theme` | `auth.py` | AJAX: сохранение темы |

---

## 7. Что реализовано (по версии)

### v2.0 (базовый функционал)
- CRUD подрядчиков, авто-генерация платежей
- Фиксация оплаты через Telegram
- Дашборд, история, аналитика
- Экспорт CSV

### v2.1
- Загрузка чеков (PDF/JPG/PNG)
- Редактирование/удаление платежей
- Редактирование подрядчиков
- Селектор месяцев на дашборде
- Смена имени/пароля

### v2.2
- Управление пользователями (CRUD)
- Гранулярные права доступа к страницам
- Деактивация/удаление пользователей
- Системные настройки (due_day, уведомления, тема)
- Аналитика с выбором года

### v2.3 (текущее состояние)
- Светлая тема (CSS variables + localStorage + AJAX)
- Изменение пароля пользователя администратором
- Селектор года в Аналитике
- Мобильная адаптивность (768px, 480px)
- Улучшенный UI настроек
- Hard delete + soft delete (toggle-active) для пользователей
- Отображение "оплачено / остаток" в таблице платежей
- Фикс access control: `_require_page()` на всех страницах
- Аналитика с выбором месяца (YoY сравнение месяца)
- Расширенный селектор месяцев в дашборде (24 месяца)

---

## 8. Известные ограничения

- **Нет Alembic** — миграции вручную через PRAGMA + ALTER TABLE
- **SQLite** — не для multi-writer (но бот и web пишут последовательно через queue)
- **Права в cookie** — могут быть подделаны клиентом; `_require_page` проверяет cookie, но для production стоит использовать session tokens
- **Docker Compose v1** — на пользовательской машине v1.29.2, требует `down` перед `up --build`
- **Тема без серверной валидации** — AJAX-save бросает ошибку если юзер не залогинен, но UI работает

---

## 9. Как запустить

```bash
cd /home/gdyupin@diasoft.ru/project/zhkh-bot
cp .env.example .env   # заполнить TELEGRAM_BOT_TOKEN, SECRET_KEY, пароли
docker compose up -d --build
# или для legacy: docker-compose down && docker-compose up -d --build
```

Доступ: `http://localhost`, логин `admin` / пароль из `.env`

---

## 10. Технические спецификации

Полное ТЗ (Terms of Reference) находится в:
`/home/gdyupin@diasoft.ru/project/terms of reference/terms of reference.md`

---

## 11. Конвенции для AI-агентов

1. **Всегда читай AGENTS.md** перед началом работы
2. **Не используй `request.form.get()`** — используй явные `Form(...)` параметры
3. **Не используй `conn.cursor()`** — используй `conn.execute(text(...))`
4. **Проверяй null** при работе с `amount`, `paid_amount`
5. **Не используй кастомные Jinja2 фильтры** если они не зарегистрированы
6. **Тестируй шаблоны:** `python3 -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/web/templates')).get_template('X.html')"`
7. **Компилируй Python:** `python3 -m py_compile <file>` перед коммитом
8. **Миграции добавляй в ДВА файла:** `app/database.py` и `init_db.py`
9. **CSS variables:** `:root` ДОЛЖЕН быть перед `[data-theme="light"]`
- **Jinja2:** `max()`, `min()` и другие Python builtins НЕ доступны. Используй `{% set var = ... %}` + тернарные выражения.
10. **Git:** commit messages в Conventional Commits формате
