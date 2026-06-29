# 🏠 ZhKH Bot — система учета платежей ЖКХ

Локальное FastAPI + SQLite приложение для учета коммунальных платежей с веб-интерфейсом и Telegram-ботом.

## Функционал

- ✅ Ежемесячная авто-генерация платежей по справочнику подрядчиков.
- ✅ Фиксация оплаты через Telegram-бот (`#оплачено #slug #сумма:X`).
- ✅ Уведомления о приближающихся и просроченных платежах.
- ✅ Веб-интерфейс: дашборд, платежи, история, подрядчики, аналитика, настройки, бекапы, Telegram-журнал.
- ✅ Загрузка и хранение чеков PDF/JPG/PNG с проверкой расширения, размера и magic bytes.
- ✅ Authenticated download чеков через `/payments/receipts/{path}` с проверкой безопасного пути и ownership check.
- ✅ Редактирование и удаление платежей, транзакций и подрядчиков.
- ✅ Роли `admin`, `operator`, `viewer` и action-level permissions для опасных операций.
- ✅ Telegram allowlist, журнал входящих сообщений, `/tglog [N]` и admin-only web UI `/telegram`.
- ✅ Аналитика расходов с графиками, CSV-экспорт истории, темная тема, локальные бекапы.

## Архитектура

### Три контейнера

```text
┌────────────────────────────────────────────────────────────┐
│ Docker Network: zhkh-bot-network                          │
│                                                            │
│ ┌──────────────┐      ┌──────────────┐   ┌──────────────┐ │
│ │ nginx        │ ───► │ web          │   │ bot          │ │
│ │ reverse      │      │ FastAPI      │   │ aiogram      │ │
│ │ proxy :80    │      │ :8000        │   │ polling      │ │
│ └──────────────┘      └──────────────┘   └──────────────┘ │
│                                                            │
│ Volumes:                                                   │
│ - data/    → /app/data              # SQLite DB + receipts │
│ - backups/ → /app/backups           # local backups        │
│ - logs/    → /var/log/zhkh-bot      # app logs             │
└────────────────────────────────────────────────────────────┘
```

| Контейнер | Назначение | Порт |
|-----------|------------|------|
| `zhkh-nginx` | Reverse proxy, ждет `web` healthy | `80 → web:8000` |
| `zhkh-web` | FastAPI + Jinja2 + static assets | `8000` внутри сети |
| `zhkh-bot` | aiogram 3.x + APScheduler jobs | — |

Статики (`/static`) обслуживает FastAPI, Nginx проксирует все запросы к web. `/uploads` не монтируется как публичная статика: сохраненные чеки лежат в `data/uploads`, но скачиваются только через authenticated route `/payments/receipts/{path}` после проверки сессии, page permission, безопасного пути и ownership check в БД.

## Стек

- Python 3.11+, FastAPI, Starlette, aiogram 3.x.
- SQLite + SQLAlchemy 2.0 async + aiosqlite.
- Jinja2 + Bootstrap 5 + Chart.js.
- Docker Compose: `web`, `bot`, `nginx`.

## Предварительные требования

### WSL2 / Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo service docker start
sudo usermod -aG docker "$USER"
```

Перезайдите в терминал после добавления пользователя в группу `docker` или выполните `newgrp docker`.

Проверка:

```bash
docker info
```

### macOS / Windows

Установите Docker Desktop и убедитесь, что Docker запущен.

## Быстрый старт для локального запуска

```bash
git clone https://github.com/Vashork/saas-zkha.git zhkh-bot
cd zhkh-bot
cp .env.example .env
```

Откройте `.env` и заполните значения под свою среду:

```dotenv
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_ID=123456789
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
SECRET_KEY=<unique-random-secret>
ADMIN_PASSWORD=<strong-admin-password>
USER_PASSWORD=<strong-user-password>
```

`TELEGRAM_ADMIN_ID` автоматически входит в allowlist. Если allowlist пустой, бот будет молча игнорировать входящие сообщения от всех пользователей.

### Runtime-директории для non-root контейнеров

Образы `web` и `bot` запускают приложение не от root, а напрямую от пользователя `zhkh` с UID/GID `1000:1000` через Dockerfile `USER zhkh`. Startup-скрипты больше не делают `chown` и не используют `gosu`; они только создают ожидаемые директории и запускают Python-процесс. Поэтому для Linux/WSL подготовьте права bind-mount директорий перед первым запуском:

```bash
mkdir -p data/uploads backups logs/nginx
sudo chown -R 1000:1000 data backups logs
```

Если на хосте нужен другой UID/GID, передайте build args `APP_UID` и `APP_GID` в `docker-compose.yml` и выставьте такие же права на `data/`, `backups/` и `logs/`.

### Запуск

```bash
docker compose up -d --build
```

Для старого Docker Compose v1:

```bash
docker-compose up -d --build
```

Проверка контейнеров:

```bash
docker compose ps
curl -f http://localhost/health
```

Откройте приложение: `http://localhost`.

## Production checklist

Перед production запуском заполните `.env` реальными значениями и не публикуйте его содержимое:

```dotenv
APP_ENV=production
SECRET_KEY=<unique-random-secret>
ADMIN_PASSWORD=<strong-admin-password>
USER_PASSWORD=<strong-user-password>
COOKIE_SECURE=true
COOKIE_HTTPONLY=true
COOKIE_SAMESITE=lax
TELEGRAM_BOT_TOKEN=<real-bot-token>
TELEGRAM_ADMIN_ID=<numeric-telegram-user-id>
TELEGRAM_ALLOWED_USER_IDS=<comma-separated-numeric-user-ids>
```

Production startup блокирует известные небезопасные значения `SECRET_KEY`, дефолтный `ADMIN_PASSWORD=admin`, дефолтный `USER_PASSWORD=user`, а также `COOKIE_SAMESITE=none` без `COOKIE_SECURE=true`.

Для проверки Compose используйте только quiet validation, чтобы не вывести секреты из `.env`:

```bash
docker compose config -q
```

Не прикладывайте полный вывод `docker compose config`, потому что он может содержать `TELEGRAM_BOT_TOKEN` и другие секреты. Если Telegram token попал в лог, чат или публичный артефакт, считайте его скомпрометированным и перевыпустите у BotFather.

За HTTPS-терминацией держите `COOKIE_SECURE=true`. Если приложение временно запускается только локально по `http://localhost`, используйте development environment и отдельные тестовые секреты.

## Telegram-бот

Основные команды:

- `/start` — приветствие и инструкции.
- `/help` — подсказка по оплате и доступным командам.
- `/balance` — остатки по платежам за текущий месяц.
- `/contractors` — список подрядчиков и slug-тегов.
- `/tglog [N]` — последние N входящих сообщений боту, только для Telegram admin.

Фиксация оплаты:

```text
#оплачено #мосэнергосбыт #сумма:3200
```

Чек можно отправить документом или фото. Web и Telegram workflows проверяют разрешенное расширение, размер и magic bytes до сохранения файла.

Admin-only web UI `/telegram` позволяет смотреть входящий Telegram-журнал, фильтровать сообщения, менять `telegram_admin_id`, `telegram_allowed_user_ids`, режим логирования и retention. DB-настройки Telegram имеют приоритет над env fallback; `TELEGRAM_ADMIN_ID` добавляется в effective allowlist.

## Роли и доступы

- `admin` — системный администратор приложения: пользователи, роли, settings, Telegram management, backups/restore, security/audit и все бизнес-операции.
- `operator` — повседневное ведение ЛК: business CRUD для подрядчиков, платежей, транзакций и чеков; без доступа к users, global settings, Telegram management и restore.
- `viewer` — просмотр разрешенных страниц без action-level мутаций.
- Legacy role `user` нормализуется в `viewer` без мутации БД.

Page permissions управляют видимостью/чтением страниц, action-level permissions управляют мутациями и чувствительными системными операциями.

## Настройки пользователя

На странице `/settings` можно:

- сменить имя текущего пользователя;
- сменить пароль;
- управлять пользователями и ролями, если текущая роль имеет системное право управления пользователями;
- настроить timezone уведомлений и глобальную тему, если текущая роль имеет право управления системными настройками.

## Бекапы

Локальные бекапы сохраняются в `./backups/`.

```bash
./scripts/backup.sh
```

Перед изменениями backup/restore, permissions и платежных транзакций сделайте отдельную копию `data/`.

## Структура проекта

```text
zhkh-bot/
├── app/                      # исходный код
│   ├── bot/                  # Telegram-бот
│   ├── web/                  # FastAPI web app
│   │   ├── routes/           # маршруты
│   │   ├── templates/        # Jinja2 templates
│   │   └── static/           # CSS/JS/assets
│   ├── models.py             # SQLAlchemy модели
│   ├── database.py           # подключение к БД
│   ├── scheduler.py          # APScheduler
│   └── config.py             # env/settings validation
├── docker/                   # Docker-конфигурация
├── data/                     # SQLite DB + uploads volume
├── backups/                  # локальные бекапы
├── logs/                     # runtime logs
├── tests/                    # тесты
├── docker-compose.yml
├── requirements.txt          # runtime dependencies
├── requirements-dev.txt      # test/dev dependencies
├── .env.example
├── init_db.py
└── README.md
```

## Тесты и локальная проверка

```bash
python -m pip install -r requirements-dev.txt
python -m compileall app init_db.py tests
python -m pytest
python -m pytest tests/test_docker_runtime.py -v
```

Security/dependency check перед release:

```bash
python -m pip_audit -r requirements.txt
```

Docker smoke:

```bash
docker compose config -q
docker compose build --no-cache web bot
docker compose up -d --build
docker compose ps
curl -f http://localhost/health
docker compose logs --tail=120 web
docker compose logs --tail=120 nginx
docker compose logs --tail=120 bot
```

## Troubleshooting

| Ошибка | Решение |
|--------|---------|
| `Permission denied` при Docker bind mounts | Проверьте `sudo chown -R 1000:1000 data backups logs` или согласуйте `APP_UID`/`APP_GID` с UID/GID на хосте. |
| `Container is unhealthy` | Проверьте `docker compose logs --tail=120 web` и `/health`. |
| Порт 80 занят | Поменяйте mapping в `docker-compose.yml`, например `8080:80`. |
| Бот не отвечает | Проверьте, что `TELEGRAM_BOT_TOKEN` задан, пользователь есть в allowlist, и в логах `zhkh-bot` нет startup errors. |
| Чек не открывается | Чеки не доступны через `/uploads`; используйте ссылку из UI на `/payments/receipts/{path}` после входа в систему. |
| CSS не загружается | Проверьте `/static` и `docker/nginx.conf`; `/uploads` не должен быть static mount. |
