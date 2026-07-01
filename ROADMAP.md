# Storefront Builder Roadmap

## P0 — Standalone foundation

- [x] Repository tree runs from root, not from nested scaffold folder.
- [x] Static Angie config without runtime mutation or reload per L3.
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
- [x] README and handoff moved to standalone root layout.
- [x] Tests added for current scaffold acceptance paths.

Evidence required before closing as release-ready:

```bash
python -m pytest
docker compose config -q
docker compose up -d --build
curl -f http://localhost/health
```

## P0/P1 — Cart, checkout and request workflow

- [x] Public cart bound to storefront.
- [x] Prevent adding unpublished lots.
- [x] Prevent mixing lots from another storefront.
- [x] Quantity validation for finite and infinite stock.
- [x] Checkout without payment creates purchase request.
- [x] Snapshot lot title and price on checkout.
- [x] Owner request list/detail.
- [x] Admin can see all requests.
- [x] Owner can see only own storefront requests.
- [x] Request status update for owner/admin.
- [x] Procurement list aggregation for `new`/`confirmed` requests.
- [x] Public cannot read request list/detail.

Evidence for this milestone:

```bash
python -m compileall app tests
python -m pytest -q
# sandbox result: 18 passed
```

Docker smoke must still be run in the target environment:

```bash
docker compose config -q
docker compose up -d --build
curl -f http://localhost/health
```

## P1 — Security hardening before public production

- [ ] Add CSRF protection for all mutating web forms, including public cart/checkout and admin forms.
- [ ] Add login and public checkout rate limiting with trusted proxy handling.
- [ ] Add audit log for auth, storefront, lot, request and settings mutations.
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
- [ ] External object storage adapter.
- [ ] PostgreSQL migration path.
- [ ] Import/export lots CSV.
- [ ] New notification adapter for request events: Telegram, email, webhook.

## Release gate rule

Do not mark a roadmap item closed without evidence. Evidence may be automated tests, manual smoke notes, migration output, or reviewed configuration. Never attach `.env`, secrets, tokens, passwords, or full `docker compose config` output.
