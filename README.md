# 🏠 ZhKH Bot — Система учета платежей ЖКХ

Локальное веб-приложение для учета коммунальных платежей с интеграцией Telegram-бота.

## Функционал

- ✅ Ежемесячная авто-генерация платежей по справочнику подрядчиков
- ✅ Фиксация оплаты через Telegram-бот (`#оплачено #slug #сумма:X`)
- ✅ Уведомления о приближающихся и просроченных платежах
- ✅ Веб-интерфейс: дашборд, платежи, история, подрядчики, аналитика, настройки
- ✅ Загрузка и хранение чеков (PDF, JPG, PNG)
- ✅ Редактирование и удаление платежей
- ✅ Редактирование подрядчиков
- ✅ Селектор месяцев на дашборде
- ✅ Смена имени пользователя и пароля
- ✅ Аналитика расходов с графиками (Chart.js)
- ✅ Темная тема с пастельными тонами
- ✅ Экспорт истории в CSV
- ✅ Локальные бекапы

## Архитектура

### Три контейнера


┌────────────────────────────────────────────────────────────┐
│ Docker Network: zhkh-bot-network │
│ │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│ │ nginx │──►│ web │ │ bot │ │
│ │ (reverse │ │ (FastAPI) │ │ (aiogram) │ │
│ │ proxy) │ │ :8000 │ │ │ │
│ │ :80/:443 │ └──────────────┘ └──────────────┘ │
│ └──────────────┘ │
│ │
│ Volumes: │
│ - data/ → /app/data (БД + чеки) │
│ - logs/ → /var/log/zhkh-bot │
└────────────────────────────────────────────────────────────┘


| Контейнер | Назначение | Порт |
|-----------|-----------|------|
| `zhkh-nginx` | Reverse proxy, ждет `web` healthy | 80 → 8000 |
| `zhkh-web` | FastAPI + Jinja2 + статики | 8000 (внутри сети) |
| `zhkh-bot` | aiogram 3.x, APScheduler | — |

**Статики** (`/static`, `/uploads`) обслуживает FastAPI, Nginx проксирует все запросы.

## Стек

- **Python 3.11+**, FastAPI, aiogram 3.x
- **SQLite** + SQLAlchemy 2.0 (async via aiosqlite)
- **Jinja2** + Bootstrap 5 + Chart.js
- **Docker Compose** (3 контейнера: web, bot, nginx)

## Предварительные требования

### WSL2 (Ubuntu / Debian)

1. Установите **Docker Engine**:
   ```bash
   sudo apt update
   sudo apt install -y docker.io
   sudo service docker start

Добавьте пользователя в группу docker (чтобы не писать sudo):

sudo usermod -aG docker $USER

⚠️ Перезайдите в терминал после этой команды (или выполните newgrp docker)

Установите docker-compose (если ещё нет):

sudo apt install -y docker-compose

Проверьте, что Docker работает:

docker info
macOS / Windows (Docker Desktop)

Скачайте и установите Docker Desktop. Убедитесь, что Docker запущен (значок кита в трее).

Быстрый старт
1. Клонировать и настроить
git clone https://github.com/Vashork/saas-zkha.git zhkh-bot
cd zhkh-bot
cp .env.example .env

Откройте .env и заполните:

TELEGRAM_BOT_TOKEN — токен вашего бота от @BotFather
SECRET_KEY — любой случайный строка
ADMIN_PASSWORD / USER_PASSWORD — пароли по умолчанию

2. Подготовить runtime-директории для non-root контейнеров

Образы `web` и `bot` запускают приложение не от root, а напрямую от пользователя `zhkh` с UID/GID `1000:1000` через Dockerfile `USER zhkh`. Startup-скрипты больше не делают `chown` и не используют `gosu`; они только создают ожидаемые директории и запускают Python-процесс. Поэтому для Linux/WSL подготовьте права bind-mount директорий перед первым запуском:

```bash
mkdir -p data/uploads backups logs/nginx logs
sudo chown -R 1000:1000 data backups logs
```

Если на хосте нужен другой UID/GID, передайте build args `APP_UID` и `APP_GID` в `docker-compose.yml` и выставьте такие же права на `data/`, `backups/` и `logs/`.

3. Запустить
docker compose up -d --build

Если используете старый docker-compose (v1): docker-compose up -d --build

4. Проверить контейнеры
docker ps
# Должно показать 3 контейнера: zhkh-web, zhkh-bot, zhkh-nginx
5. Открыть в браузере
http://localhost
Логин: admin / <ваш пароль>
6. Остановить
docker compose down
Структура проекта
zhkh-bot/
├── app/                      # Исходный код
│   ├── bot/                  # Telegram-бот (aiogram)
│   ├── web/                  # FastAPI приложение
│   │   ├── routes/           # Маршруты (7 страниц)
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
Telegram-бот

Команды:

/start — приветствие и инструкции
/contractors — список подрядчиков
/tglog [N] — последние N входящих сообщений боту, только для TELEGRAM_ADMIN_ID

Фиксация оплаты:

Перешлите боту чек и напишите:
#оплачено #мосэнергосбыт #сумма:3200
Настройки пользователя

На странице ⚙️ Настройки (/settings) можно:

Сменить имя пользователя (вместо admin / user)
Сменить пароль
Посмотреть список пользователей (для админа)
Бекап
# Создать бекап вручную
./scripts/backup.sh

# Бекапы сохраняются в ./backups/
# Старые бекапы (7+ дней) очищаются автоматически
Тесты
pip install pytest pytest-asyncio
python -m pytest tests/ -v
Troubleshooting
Ошибка	Решение
Permission denied при docker-compose	sudo usermod -aG docker $USER + перезайдите; для non-root контейнеров также проверьте `sudo chown -R 1000:1000 data backups logs`
Container is unhealthy	docker logs zhkh-web — проверьте логи
Порт 80 занят	Поменяйте в docker-compose.yml: "8080:80"
Бот не отвечает	Проверьте TELEGRAM_BOT_TOKEN в .env, docker logs zhkh-bot
Белая страница	Nginx не дождётся web — проверьте depends_on: condition: service_healthy
CSS не загружается	FastAPI монтирует /static, Nginx проксирует — проверьте nginx.conf
