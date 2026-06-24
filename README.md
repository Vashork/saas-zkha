# 🏠 ZhKH Bot — Система учета платежей ЖКХ

Локальное веб-приложение для учета коммунальных платежей с интеграцией Telegram-бота.

## Функционал

- ✅ Ежемесячная авто-генерация платежей по справочнику подрядчиков
- ✅ Фиксация оплаты через Telegram-бот (`#оплачено #slug #сумма:X`)
- ✅ Уведомления о приближающихся и просроченных платежах
- ✅ Веб-интерфейс: дашборд, платежи, история, подрядчики, аналитика
- ✅ Загрузка и хранение чеков (PDF, JPG, PNG)
- ✅ Аналитика расходов с графиками (Chart.js)
- ✅ Темная тема с пастельными тонами
- ✅ Экспорт истории в CSV
- ✅ Локальные бекапы

## Стек

- **Python 3.11+**, FastAPI, aiogram 3.x
- **SQLite** + SQLAlchemy 2.0 (async)
- **Jinja2** + Bootstrap 5 + Chart.js
- **Docker Compose** (3 контейнера: web, bot, nginx)

## Быстрый старт (WSL / Linux)

### 1. Клонировать и настроить

```bash
git clone https://github.com/Vashork/saas-zkha.git zhkh-bot
cd zhkh-bot
cp .env.example .env
```

Откройте `.env` и заполните:
- `TELEGRAM_BOT_TOKEN` — токен вашего бота от @BotFather
- `SECRET_KEY` — любой случайный字符串
- `ADMIN_PASSWORD` / `USER_PASSWORD` — пароли по умолчанию

### 2. Запустить

```bash
docker compose up -d
```

### 3. Открыть в браузере

```
http://localhost
Логин: admin / <ваш пароль>
```

### 4. Остановить

```bash
docker compose down
```

## Структура проекта

```
zhkh-bot/
├── app/                      # Исходный код
│   ├── bot/                  # Telegram-бот (aiogram)
│   ├── web/                  # FastAPI приложение
│   │   ├── routes/           # Маршруты (6 страниц)
│   │   ├── templates/        # Jinja2 шаблоны
│   │   └── static/           # CSS, JS
│   ├── models.py             # SQLAlchemy модели
│   ├── schemas.py            # Pydantic схемы
│   ├── database.py           # Подключение к БД
│   ├── scheduler.py          # APScheduler
│   ├── config.py             # Настройки
│   └── utils.py              # Утилиты
├── docker/                   # Docker-конфигурация
├── scripts/                  # Скрипты (бекап и т.д.)
├── data/                     # Данные (volume: БД + чеки)
├── backups/                  # Локальные бекапы
├── docker-compose.yml        # Docker Compose
├── requirements.txt          # Python-зависимости
├── .env.example              # Шаблон переменных
├── init_db.py                # Инициализация БД
└── README.md
```

## Telegram-бот

Команды:
- `/start` — приветствие и инструкции
- `/contractors` — список подрядчиков

Фиксация оплаты:
```
Перешлите боту чек и напишите:
#оплачено #мосэнергосбыт #сумма:3200
```

## Бекап

```bash
# Создать бекап вручную
./scripts/backup.sh

# Бекапы сохраняются в ./backups/
# Старые бекапы (7+ дней) очищаются автоматически
```

## Будущие итерации (v2)

- Страница настроек (`/settings`)
- Страница мониторинга бекапов (`/backups`)
- Duplicity + GPG шифрование
- WireGuard VPN + SMB-шары (Synology)
- Self-contained backup bundles
- Systemd-юниты для VPS
