# Handoff for local AI / release reviewer

Branch: `feature/storefront-mvp-guru-20260701`
Project state: standalone storefront/page-builder from repository root.

## Mission

Review and validate the MVP scaffold for a subdomain-based storefront/page builder. Treat it as a new project seed that will move into a separate clean repository.

## Removed from runtime

The legacy billing/domain-specific runtime must not be present in the standalone tree:

- old payment/contractor/receipt logic;
- old scheduler;
- old domain-specific bot runtime;
- old containers/networks/docs unrelated to storefront builder.

Notifications may be added later as a new clean adapter for purchase requests, not by carrying over old domain-specific code.

## Do not do

- Do not print `.env`.
- Do not print full `docker compose config`.
- Do not request or expose secrets.
- Do not add fake TLS/self-signed production placeholders.
- Do not add runtime sed/template mutation for Angie config.
- Do not make Angie reload per new L3 subdomain.

## Required local validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
docker compose config -q
docker compose up -d --build
curl -f http://localhost/health
```

If Docker is unavailable, at minimum run:

```bash
python -m compileall app migrations tests
python -m pytest
```

## Manual smoke scenario

1. Copy `.env.example` to `.env` and set unique local `SECRET_KEY` and `ADMIN_PASSWORD`.
2. Set `BASE_DOMAIN=guru.localhost`.
3. Add hosts entries if needed:

   ```text
   127.0.0.1 guru.localhost
   127.0.0.1 knigi.guru.localhost
   ```

4. Start Docker.
5. Open `http://guru.localhost/login`.
6. Login as admin.
7. Create storefront `knigi`.
8. Edit title to `Книги` and description.
9. Add a lot with PNG/JPEG/WEBP image.
10. Open `http://knigi.guru.localhost/` and confirm public render.
11. Confirm `http://localhost/s/knigi` works as dev fallback.

## Review focus

- `validate_subdomain` rejects reserved/invalid names.
- Storefront subdomain uniqueness is enforced in DB and handled without 500.
- Owner cannot read/edit someone else's storefront.
- `Host` maps only one-level L3 labels under configured base domain.
- Uploaded files never use user filename as stored path.
- Uploaded files are served only by DB-backed `image_id`.
- `ensure_child_path` blocks traversal.
- `APP_ENV=production` blocks unsafe secret/default password combinations.
- Angie preserves original `Host` header.

## Known gaps intentionally not closed yet

- Public cart and checkout request workflow is not merged into the branch yet.
- CSRF protection is not implemented yet.
- Login/checkout rate limit is not implemented yet.
- Audit log is not implemented yet.
- User-management UI is not implemented yet.
- Real TLS termination is deployment-level and not faked in this scaffold.
- Angie image tag must be verified in the target environment with `docker pull`/build smoke; do not replace it with nginx unless the product decision changes.
