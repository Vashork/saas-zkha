# Local AI handoff — Angie reverse proxy and DNS/TLS rollout

Branch: `docker/angie-dns-tls-roadmap`

This handoff exists because the GitHub connector cannot run local Docker/pytest evidence and blocked a full README rewrite. Do not add runtime hacks or fake TLS placeholders. Apply only deterministic source changes and validate locally.

## Already applied in this branch

- Added `docker/angie.conf`.
- Replaced the Compose reverse proxy service with `angie` using image `docker.angie.software/angie:1.11.8-minimal`.
- Removed `docker/nginx.conf`.
- Updated `scripts/docker_smoke_check.py` to collect logs from `angie`.
- Updated Docker runtime/smoke tests for Angie.
- Added `docs/PRODUCTION_DNS_TLS_ROADMAP.md`.

## Required local fixes before PR can be marked ready

### 1. README update

Update `README.md` to replace reverse-proxy references from nginx to Angie.

Required semantic changes:

- Architecture diagram: `nginx` -> `angie`.
- Container table: `zhkh-nginx` -> `zhkh-angie`.
- Text: `Nginx проксирует` -> `Angie проксирует`.
- Stack line: Docker Compose services should be `web`, `bot`, `angie`.
- Runtime directory example: `logs/nginx` -> `logs/angie`.
- Add a short DNS/TLS readiness note pointing to `docs/PRODUCTION_DNS_TLS_ROADMAP.md`.

Preserve existing required README test phrases:

```text
`/uploads` не монтируется как публичная статика
`/payments/receipts/{path}`
ownership check
APP_ENV=production
SECRET_KEY=<unique-random-secret>
ADMIN_PASSWORD=<strong-admin-password>
USER_PASSWORD=<strong-user-password>
COOKIE_SECURE=true
docker compose config -q
Не прикладывайте полный вывод `docker compose config`
перевыпустите у BotFather
TELEGRAM_ADMIN_ID
TELEGRAM_ALLOWED_USER_IDS
`TELEGRAM_ADMIN_ID` автоматически входит в allowlist
`/tglog [N]`
Admin-only web UI `/telegram`
DB-настройки Telegram имеют приоритет над env fallback
```

### 2. Release roadmap update

Update `docs/RELEASE_ROADMAP.md`:

- Replace the Docker hardening statement `Nginx image pinned to nginx:1.27-alpine` with `Angie image pinned to docker.angie.software/angie:1.11.8-minimal`.
- Replace Docker key-file reference `docker/nginx.conf`, if present, with `docker/angie.conf`.
- Add `docs/PRODUCTION_DNS_TLS_ROADMAP.md` under current deployment/production follow-up documentation.
- Do not mark DNS/TLS production-ready until real DNS, certificate issuance, and renewal dry-run are captured.

### 3. Validate Angie config locally

Run from repository root:

```cmd
git switch docker/angie-dns-tls-roadmap
docker compose config -q
python -m pytest tests/test_docker_runtime.py tests/test_docker_smoke_script.py tests/test_readme_release_docs.py
```

If those pass, run:

```cmd
python -m pytest
python scripts/docker_smoke_check.py
docker compose config -q
```

Do not paste full Compose output. Only record `docker compose config -q: ok`.

### 4. Manual smoke evidence

After `python scripts/docker_smoke_check.py`, capture bounded evidence only:

```text
python scripts/docker_smoke_check.py: SUCCESS: Docker smoke QA baseline passed
docker compose config -q: ok
```

Manual UI checks still required:

- login page reachable;
- dashboard reachable after login;
- `/uploads/...` is not public;
- receipt upload/download still works;
- backup page still works;
- Telegram management page still works for admin.

## DNS/TLS next block — do not implement blindly

Do not enable HTTPS in default Compose until these are known:

- final FQDN;
- whether port 80 is publicly reachable;
- whether HTTP-01 or DNS-01 will be used;
- where certificates will be stored persistently;
- how Angie will be reloaded after successful renewal.

For a clean next PR, prefer one of these designs:

1. Certbot webroot sidecar with persistent `certbot/www` and `certbot/conf` directories.
2. Angie ACME module with persistent `/var/lib/angie/acme`, only after confirming the selected image includes the required module.

No self-signed production placeholders. No entrypoint sed/template mutation. No secrets in repository.
