# Storefront Builder MVP

Standalone MVP конструктора страниц/витрин на L3-поддоменах. Проект запускается из корня репозитория и подготовлен к переносу в отдельный чистый GitHub repo.

Стек: FastAPI, SQLite, SQLAlchemy async, Alembic, Jinja2, Docker Compose и Angie-compatible reverse proxy.

## Архитектурное решение

Production-вариант: wildcard DNS + Host routing.

```text
DNS:
  guru.com      -> public IP reverse proxy
  *.guru.com    -> public IP reverse proxy

Angie:
  server_name guru.com *.guru.com;
  proxy_set_header Host $host;
  proxy_pass http://web:8000;

FastAPI:
  Host: knigi.guru.com
  base_domain: guru.com
  subdomain: knigi
  DB lookup: storefronts.subdomain = 'knigi'
```

Создание `knigi.guru.com` не меняет Angie config и не требует reload reverse proxy. Приложение создает строку в БД, а публичный рендер выбирается по `Host` header. Runtime `sed`/template mutation, reload reverse proxy на каждый L3 и fake TLS production-заглушки не используются.

## MVP scope сейчас

Закрыто scaffold-реализацией:

- FastAPI backend;
- SQLite + SQLAlchemy async;
- Alembic migration `20260701_0001`;
- Jinja2 UI;
- Docker Compose;
- Angie reverse proxy config под wildcard/host routing;
- session auth;
- роли `admin`, `owner`, `viewer`;
- создание L3 subdomain-страницы;
- публичный рендер по `Host`;
- dev public route `/s/{subdomain}` для локальной проверки без wildcard DNS;
- CRUD лотов: create/read/update/delete;
- безопасная загрузка изображений лотов и баннера:
  - whitelist расширений `.jpg`, `.jpeg`, `.png`, `.webp`;
  - лимит размера;
  - magic bytes check;
  - UUID stored filename;
  - запрет path traversal;
  - отдача только через DB-backed `/uploads/{image_id}`;
- тесты на subdomain validation, reserved names, duplicate subdomain, Host routing, owner access, public page render и upload validation.

## Структура

```text
app/
  main.py
  static/app.css
  templates/
docker/
  Dockerfile.web
  angie.conf
migrations/
  env.py
  versions/20260701_0001_initial.py
tests/test_mvp.py
.env.example
docker-compose.yml
requirements.txt
requirements-dev.txt
ROADMAP.md
HANDOFF_LOCAL_AI.md
```

## Локальный запуск

```bash
cp .env.example .env
```

Отредактируйте `.env` и задайте уникальные значения:

```dotenv
SECRET_KEY=...
ADMIN_PASSWORD=...
BASE_DOMAIN=guru.localhost
ALLOWED_HOSTS=guru.localhost,*.guru.localhost,localhost,*.localhost,127.0.0.1,testserver
```

Подготовьте директорию данных для non-root контейнера:

```bash
mkdir -p data/uploads
sudo chown -R 1000:1000 data
```

Проверка Compose только без вывода секретов:

```bash
docker compose config -q
```

Запуск:

```bash
docker compose up -d --build
```

Health check:

```bash
curl -f http://localhost/health
```

## Локальная работа без настоящего wildcard DNS

Вариант A, предпочтительный для проверки Host routing:

```text
127.0.0.1 guru.localhost
127.0.0.1 knigi.guru.localhost
```

После этого:

```text
http://guru.localhost/login
http://knigi.guru.localhost/
```

Вариант B, без изменения hosts-файла: публичный dev-view доступен как:

```text
http://localhost/s/knigi
```

Этот route нужен только для локальной проверки. Production path остается Host routing.

## Production checklist

- Настроить реальные DNS записи `guru.com` и `*.guru.com`.
- Настроить реальную TLS-терминацию на boundary/reverse proxy. Fake TLS и self-signed production-заглушки не используются.
- В `.env` задать `APP_ENV=production`.
- Задать уникальный `SECRET_KEY`.
- Задать сильный `ADMIN_PASSWORD`.
- Обновить `BASE_DOMAIN` и `ALLOWED_HOSTS` под реальный домен.
- Прогнать миграции через контейнер startup или вручную: `alembic upgrade head`.
- Не публиковать `.env`, секреты и полный вывод `docker compose config`.

## Команды проверки

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
docker compose config -q
docker compose up -d --build
curl -f http://localhost/health
```

Если Docker недоступен:

```bash
python -m compileall app migrations tests
python -m pytest
```

## Уведомления

Старый доменно-специфичный bot runtime не переносится. Для нового проекта допустимо добавить отдельный notification adapter позже: например уведомления owner/admin о новых заявках и смене статуса.

## Ограничения текущего scaffold

- Корзина и checkout-заявки еще не влиты в ветку.
- Нет многофайловой галереи лота.
- Нет отдельной пользовательской админки управления владельцами.
- Нет внешнего object storage/S3.
- Нет rate limit на login.
- Нет CSRF middleware; для production-релиза это следующий security gate.
