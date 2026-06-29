# Docker hardening TODO

Branch: `audit/main-hardening-followup`

Status: audit findings recorded, implementation not started.

Reviewed files:

- `docker/Dockerfile.web`
- `docker/Dockerfile.bot`
- `docker-compose.yml`
- `docker/start-web.sh`
- `docker/start-bot.sh`
- `docker/nginx.conf`
- `requirements.txt`

## Current positives

- web/bot use `python:3.11-slim`.
- Dockerfiles copy `requirements.txt` before `app/`, so dependency cache is mostly correct.
- apt install and apt list cleanup are in the same `RUN` layer.
- Python packages are installed with `pip install --no-cache-dir`.
- Secrets are not hardcoded in Dockerfiles.
- web has a `/health` healthcheck in compose.
- nginx blocks public `/uploads/` access.

## Required follow-up

1. Add root `.dockerignore`.
   Must exclude VCS metadata, local environment files, Python caches, virtualenvs, runtime data, backups, logs, local DB files, coverage output, and optional docs/build artifacts.

2. Split runtime and dev dependencies.
   Runtime Docker images should not install test-only packages. Move `pytest`, `pytest-asyncio`, and `httpx` to a dev requirements file.

3. Rework runtime user model.
   Current Dockerfiles create user `zhkh`, but containers still start through root and drop privileges in shell scripts using `gosu`. Preferred hardened state is `USER zhkh` in Dockerfiles, with bind-mount permissions prepared on host. If `gosu` remains, document it as a compatibility compromise and test it.

4. Remove unnecessary runtime packages.
   `curl` is used only for healthcheck. Prefer a Python stdlib healthcheck in compose, then remove `curl` from web/bot images if possible.

5. Pin nginx image version.
   Replace floating `nginx:alpine` with a version-pinned tag such as `nginx:1.27-alpine`, or use a digest-pinned image.

6. Add image metadata.
   Add OCI labels to web/bot images and add `EXPOSE 8000` to the web Dockerfile.

7. Optional compose hardening.
   Consider `security_opt: ["no-new-privileges:true"]`. Consider `read_only: true` only after writable mounts/tmpfs are explicitly handled for app data, backups, logs, and nginx runtime paths.

## Validation required

Run after implementation:

```bash
python -m compileall app init_db.py tests && python -m pytest
docker compose config
docker compose up -d --build
```

Manual smoke:

- web `/health` returns success;
- login page works;
- Telegram bot container starts without permission errors;
- backup page opens;
- receipt upload/download still works;
- `docker compose logs web bot nginx` has no startup or permission errors.

## Boundaries

- Do not combine this Docker hardening with P2-17 unless explicitly requested.
- Do not mark this complete without Docker build and smoke confirmation.
- Do not mark P1-AUDIT-1 complete only because Docker hardening is done; dependency audit and Docker smoke are still separate release blockers.
- Be careful with `USER zhkh`: it can break bind-mount writes if host directory ownership is not prepared.
