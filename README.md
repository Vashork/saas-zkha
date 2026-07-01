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

Закрыто текущей реализацией:

- FastAPI backend;
- SQLite + SQLAlchemy async;
- Alembic migrations `20260701_0001` и `20260701_0002`;
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
- публичная корзина, привязанная к storefront;
- checkout без оплаты, создающий заявку/предзаказ;
- snapshot title/price/quantity на момент заявки;
- owner/admin список и детали заявок;
- смена статуса заявки;
- закупочный список по статусам `new`/`confirmed`;
- тесты на subdomain validation, reserved names, duplicate subdomain, Host routing, owner access, public page render, upload validation, cart, checkout, request access и procurement aggregation.

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
  versions/20260701_0002_cart_purchase_requests.py
tests/test_mvp.py
.env.example
docker-compose.yml
requirements.txt
requirements-dev.txt
ROADMAP.md
HANDOFF_LOCAL_AI.md
QA_CHECKLIST.md
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
http://knigi.guru.localhost/cart
```

Вариант B, без изменения hosts-файла: публичный dev-view доступен как:

```text
http://localhost/s/knigi
http://localhost/s/knigi/cart
```

Этот route нужен только для локальной проверки. Production path остается Host routing.

## Корзина и заявки

Публичный пользователь без логина может:

1. открыть публичную витрину;
2. добавить опубликованный лот в корзину;
3. указать количество;
4. открыть корзину;
5. изменить количество или удалить позицию;
6. оформить заявку без оплаты;
7. указать имя, телефон или Telegram, опциональный email и комментарий;
8. увидеть публичную страницу “Заявка принята”.

Корзина хранит случайный per-storefront token в signed session cookie, а в БД хранится только `token_hash`. Buyer PII в cookie не кладется. Заявка создается со статусом `new`; остатки автоматически не списываются, чтобы фейковые заявки не блокировали товар.

## Кабинет owner/admin

После логина доступны:

- `Dashboard` / витрины;
- заявки `/requests`;
- детали заявки и смена статуса;
- закупочный список `/procurement`.

Owner видит только заявки своих storefronts. Admin видит все заявки.

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
python -m compileall app migrations tests
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

## Ограничения текущего MVP

- CSRF protection еще не реализован; для production-релиза это следующий security gate.
- Нет durable login/checkout rate limit.
- Нет audit log.
- Нет многофайловой галереи лота.
- Нет отдельной пользовательской админки управления владельцами.
- Нет внешнего object storage/S3.
