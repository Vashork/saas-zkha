# Production DNS/TLS roadmap

Branch: `docker/angie-dns-tls-roadmap`

Goal: publish the application behind a DNS name, terminate HTTPS on Angie, and support certificate auto-renewal without leaking secrets or relying on runtime hacks.

## Current state

- The application has `web`, `bot`, and reverse-proxy containers.
- Reverse proxy migration target: Angie image `docker.angie.software/angie:1.11.8-minimal`.
- Current safe baseline remains HTTP on port `80` until a real DNS name and production host are available.
- Do not add fake certificates, self-signed production placeholders, or startup scripts that mutate config at runtime.

## Phase 1 — Angie reverse proxy baseline

- [x] Add `docker/angie.conf` as the Angie reverse proxy config.
- [x] Update Docker smoke helper to treat `angie` as the proxy service.
- [x] Update Docker runtime tests for Angie config/service expectations.
- [x] Update `docker-compose.yml` to replace the `nginx` service with `angie`.
- [x] Remove `docker/nginx.conf` after Compose uses `docker/angie.conf`.
- [ ] Update README architecture and runtime directory docs from nginx to Angie.
- [ ] Run targeted tests and Docker smoke evidence.

## Phase 2 — DNS publication prerequisites

Before enabling HTTPS in Compose, the deploy operator must provide:

- production FQDN, for example `zhkh.example.com`;
- public DNS `A`/`AAAA` record pointing to the production host;
- inbound firewall/NAT for TCP `80` and `443` to the host;
- decision about HTTP-to-HTTPS redirect policy;
- production `.env` with secure cookie settings enabled;
- backup of `data/`, `backups/`, and current Compose config before rollout.

Validation evidence:

```cmd
docker compose config -q
curl -I http://<FQDN>/health
```

Do not paste full `docker compose config` output because it can contain secrets.

## Phase 3 — TLS design

Preferred production design:

1. Use Angie for HTTP/HTTPS termination.
2. Use a persistent certificate volume, not container-local certificate files.
3. Use ACME HTTP-01 only when port `80` is reachable from the public Internet.
4. Use DNS-01 only when HTTP-01 is impossible; keep DNS provider credentials outside the repository.
5. Reload Angie after successful renewal, not on every cron run.

Two acceptable implementation options:

### Option A — Certbot webroot sidecar

- Add shared ACME webroot volume, for example `./certbot/www:/var/www/certbot`.
- Add certificate volume, for example `./certbot/conf:/etc/letsencrypt`.
- Add Angie location for `/.well-known/acme-challenge/` served from the webroot.
- Add HTTPS server block using `/etc/letsencrypt/live/<FQDN>/fullchain.pem` and `privkey.pem`.
- Run initial issue manually after DNS points to the host.
- Configure renewal with a host timer or a Compose-managed certbot renewal command.
- Reload Angie only after successful renewal.

### Option B — Angie ACME module

- Use Angie ACME only after confirming the selected Angie image includes the required ACME module and certificate storage path.
- Mount ACME storage persistently, for example `/var/lib/angie/acme`.
- Do not enable this in the default Compose file until it is tested against a real domain or Let's Encrypt staging.

## Phase 4 — HTTPS rollout checks

Target checks:

```cmd
docker compose config -q
docker compose up -d
curl -I http://<FQDN>/health
curl -I https://<FQDN>/health
curl -I http://<FQDN>/uploads/docker-smoke-missing.txt
curl -I https://<FQDN>/login
```

Expected:

- HTTP either redirects to HTTPS or serves only ACME challenge plus health during transition.
- HTTPS `/health` returns 200.
- `/uploads/...` is not public.
- `/login` is reachable over HTTPS.
- cookies are secure in production.

## Phase 5 — Renewal drill

- Run staging dry-run first.
- Confirm renewal exits successfully.
- Confirm deploy/reload hook reloads Angie.
- Confirm cert expiry date changes or remains valid.
- Capture bounded logs from `web`, `angie`, and `bot`.

Evidence commands:

```cmd
certbot renew --dry-run
docker compose logs --tail=120 angie
docker compose logs --tail=120 web
docker compose logs --tail=120 bot
```

## Release gate

Do not mark DNS/TLS production-ready until these pass:

```cmd
python -m pytest tests/test_docker_runtime.py tests/test_docker_smoke_script.py tests/test_readme_release_docs.py
python -m pytest
python scripts/docker_smoke_check.py
docker compose config -q
```

Manual evidence still required:

- DNS record resolves to production host.
- HTTPS certificate is valid for the selected FQDN.
- renewal dry-run passes.
- backup and restore drill has been run before production rollout.
