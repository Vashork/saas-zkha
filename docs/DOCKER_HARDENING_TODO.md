# Docker hardening TODO

Branch: `audit/main-hardening-followup`

Status: implementation completed through GitHub connector; tests/config validated locally; Docker build/smoke validation still pending because the pinned nginx image cannot be pulled from Docker CDN in the local environment.

Reviewed files:

- `.dockerignore`
- `docker/Dockerfile.web`
- `docker/Dockerfile.bot`
- `docker-compose.yml`
- `docker/start-web.sh`
- `docker/start-bot.sh`
- `docker/nginx.conf`
- `requirements.txt`
- `requirements-dev.txt`
- `tests/test_docker_runtime.py`

## Implemented hardening

1. Root `.dockerignore` added.
   - Excludes VCS metadata, local environment files, Python caches, virtualenvs, runtime data, backups, logs, local DB files, coverage output, build artifacts, and large local docs artifacts.

2. Runtime and dev dependencies split.
   - `requirements.txt` now contains runtime dependencies only.
   - `requirements-dev.txt` includes `-r requirements.txt` plus `pytest`, `pytest-asyncio`, and `httpx`.

3. Runtime user model hardened.
   - `docker/Dockerfile.web` and `docker/Dockerfile.bot` now set `USER zhkh`.
   - `gosu` was removed from runtime images.
   - Startup scripts no longer perform root-to-user privilege dropping.
   - Compose build args expose `APP_UID` / `APP_GID` so host bind-mount ownership can be aligned with the container user.

4. Unnecessary runtime packages removed.
   - `curl` was removed from web/bot images.
   - Compose healthcheck now uses Python stdlib `urllib.request` against `/health`.

5. Nginx image version pinned.
   - `nginx:alpine` replaced with `nginx:1.27-alpine`.

6. Image metadata added.
   - OCI labels added to web/bot images.
   - `EXPOSE 8000` added to `docker/Dockerfile.web`.

7. Compose hardening added.
   - `security_opt: ["no-new-privileges:true"]` added for web, bot, and nginx.
   - `read_only: true` intentionally not enabled yet because app data, backups, logs, uploads, nginx runtime paths, and tmpfs needs must be handled explicitly first.

8. Docker runtime regression tests updated.
   - `tests/test_docker_runtime.py` now asserts the hardened non-root model: `USER zhkh`, no `gosu`, no `curl`, pinned nginx, Python stdlib healthcheck, and `no-new-privileges:true`.

## Local validation confirmed

Confirmed by user on Windows cmd.exe, 2026-06-29:

```text
python -m pip install -r requirements-dev.txt                  # ok
python -m compileall app init_db.py tests && python -m pytest  # 284 passed, 8 skipped, 5 warnings in 60.22s
docker compose config                                          # ok
```

`docker compose config` confirms:

- `nginx:1.27-alpine`;
- Python stdlib healthcheck with `urllib.request`;
- `APP_UID` / `APP_GID` build args;
- `security_opt: no-new-privileges:true` for web, bot, and nginx.

## Validation still required before fully closing

Docker image pull/build and full smoke are still pending.

Current local blockers:

- `docker pull nginx:1.27-alpine` fails with `failed to copy ... production.cloudfront.docker.com ... EOF`.
- `docker compose up -d --build` fails for the same pinned nginx image pull reason.
- `docker compose ps` still shows an older running `zhkh-nginx` based on `nginx:alpine`, so the current running stack cannot be used as final proof for the new hardening state.
- Bot logs show `Cannot connect to host api.telegram.org:443` / DNS failures. This is an external network/Telegram reachability issue, not a bind-mount permission or non-root startup error.

Run when Docker CDN / registry access is working:

```bat
set APP_UID=1000
set APP_GID=1000
docker pull nginx:1.27-alpine
docker compose up -d --build
```

Manual smoke still required on newly built containers:

- web `/health` returns success;
- login page works;
- Telegram bot container starts without permission errors and can reach `api.telegram.org:443`, or Telegram reachability is explicitly documented as an environment/network blocker;
- backup page opens;
- receipt upload/download still works;
- `docker compose logs web bot nginx` has no startup or permission errors.

## Host bind-mount note

The images now run directly as `zhkh` instead of starting as root. Before Docker smoke on Linux hosts, ensure writable host directories exist and are writable by the UID/GID passed into compose:

```bash
mkdir -p data/uploads backups logs/nginx
chown -R "$(id -u):$(id -g)" data backups logs
```

On Docker Desktop for Windows, Linux-style `chown` usually is not needed for bind mounts, but `APP_UID` / `APP_GID` still need values for the image build args. Use `1000` / `1000` unless the deployment host uses a different service UID/GID.

If the deployment host intentionally uses a different service UID/GID, pass those values through `APP_UID` and `APP_GID` and prepare directory ownership accordingly.

## Boundaries

- Docker hardening implementation is separate from P2-17.
- Do not mark this item fully complete until Docker build and smoke confirmation are available.
- Do not mark P1-AUDIT-1 complete only because Docker hardening implementation is done; dependency audit and Docker smoke are still separate release blockers.
- Be careful with `USER zhkh`: it can break bind-mount writes if host directory ownership is not prepared.
