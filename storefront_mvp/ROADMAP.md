# Storefront Builder Roadmap

## P0 — MVP foundation

- [x] Архитектурное решение: wildcard DNS + Host routing.
- [x] Статичный Angie config, без runtime mutation и reload на каждый L3.
- [x] FastAPI scaffold.
- [x] SQLite + SQLAlchemy async.
- [x] Alembic initial migration.
- [x] Jinja2 UI.
- [x] Session auth.
- [x] Roles: `admin`, `owner`, `viewer`.
- [x] Storefront model with unique L3 subdomain.
- [x] Subdomain validation and reserved names.
- [x] Host header mapping to public storefront.
- [x] Owner access checks.
- [x] Lot CRUD.
- [x] Image upload validation.
- [x] Docker Compose + Angie.
- [x] README and handoff.
- [x] Tests added for MVP acceptance paths.

Evidence required before closing as release-ready:

```bash
python -m pytest
docker compose config -q
docker compose up -d --build
curl -f http://localhost/health
```

## P1 — Security hardening before public production

- [ ] Add CSRF protection for all mutating web forms.
- [ ] Add login rate limiting with trusted proxy handling.
- [ ] Add audit log for auth, storefront, lot and settings mutations.
- [ ] Add admin UI for user management and owner assignment.
- [ ] Add stronger password policy and password change flow.
- [ ] Add strict security headers at Angie/app layer.
- [ ] Add backup/restore policy with safe restore guardrails.
- [ ] Decide whether `/s/{subdomain}` remains dev-only or is disabled in production.
- [ ] Add CI dependency audit gate.
- [ ] Add Docker smoke script with no secret leakage.

## P2 — Product expansion

- [ ] Storefront themes/layout presets.
- [ ] Multiple images per lot.
- [ ] Draft preview links.
- [ ] SEO sitemap/robots controls.
- [ ] Custom owner profile/contact settings.
- [ ] Public contact/order request form with anti-spam controls.
- [ ] External object storage adapter.
- [ ] PostgreSQL migration path.
- [ ] Import/export lots CSV.

## Release gate rule

Do not mark a roadmap item closed without evidence. Evidence may be automated tests, manual smoke notes, migration output, or reviewed configuration. Never attach `.env`, secrets, tokens, passwords, or full `docker compose config` output.
