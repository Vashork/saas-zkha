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

## Предварительные требования

### WSL2 (Ubuntu / Debian)

1. Установите **Docker Engine**:
   ```bash
   sudo apt update
   sudo apt install -y docker.io
   sudo service docker start
   ```

2. Добавьте пользователя в группу `docker` (чтобы не писать `sudo`):
   ```bash
   sudo usermod -aG docker $USER
   ```
   > ⚠️ **Перезайдите в терминал** после этой команды (или выполните `newgrp docker`)

3. Установите **docker-compose** (если ещё нет):
   ```bash
   sudo apt install -y docker-compose
   ```

4. Проверьте, что Docker работает:
   ```bash
   docker info
   ```

### macOS / Windows (Docker Desktop)

Скачайте и установите [Docker Desktop](https://www.docker.com/products/docker-desktop/). Убедитесь, что Docker запущен (значок кита в трее).

## Быстрый старт

### 1. Клонировать и настроить

```bash
git clone https://github.com/Vashork/saas-zkha.git zhkh-bot
cd zhkh-bot
cp .env.example .env
```

Откройте `.env` и заполните:
- `TELEGRAM_BOT_TOKEN` — токен вашего бота от @BotFather
- `SECRET_KEY` — любой случайный строка
- `ADMIN_PASSWORD` / `USER_PASSWORD` — пароли по умолчанию

### 2. Запустить

```bash
docker compose up -d --build
```

> Если используете старый `docker-compose` (v1): `docker-compose up -d --build`

### 3. Проверить контейнеры

```bash
docker ps
# Должно показать 3 контейнера: zhkh-web, zhkh-bot, zhkh-nginx
```

### 4. Открыть в браузере

```
http://localhost
Логин: admin / <ваш пароль>
```

### 5. Остановить

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
│   ├── Dockerfile.web        # Образ веб-сервера
│   ├── Dockerfile.bot        # Образ бота
│   └── nginx.conf            # Nginx reverse proxy
├── scripts/                  # Скрипты (бекап и т.д.)
├── data/                     # Данные (volume: БД + чеки)
├── backups/                  # Локальные бекапы
├── tests/                    # Юнит-тесты
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

## Тесты

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -v
```

## Troubleshooting

| Ошибка | Решение |
|--------|---------|
| `Permission denied` при `docker-compose` | `sudo usermod -aG docker $USER` + перезайдите |
| Container is unhealthy | `docker logs zhkh-web` — проверьте логи |
| Порт 80 занят | Поменяйте в `docker-compose.yml`: `"8080:80"` |
| Бот не отвечает | Проверьте `TELEGRAM_BOT_TOKEN` в `.env`, `docker logs zhkh-bot` |

## Будущие итерации (v2)

- Страница настроек (`/settings`)
- Страница мониторинга бекапов (`/backups`)
- Duplicity + GPG шифрование
- WireGuard VPN + SMB-шары (Synology)
- Self-contained backup bundles
- Systemd-юниты для VPS
