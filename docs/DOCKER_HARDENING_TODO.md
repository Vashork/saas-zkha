# Docker hardening TODO

Branch: `audit/main-hardening-followup`

Status: completed locally.

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
- `README.md`

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
   - README bind-mount guidance is guarded against the old root-entrypoint / `gosu` wording.

9. Docker runtime documentation aligned.
   - `README.md` now documents the direct `USER zhkh` runtime model.
   - It no longer describes startup scripts as fixing ownership with root privileges or dropping privileges through `gosu`.

## Local validation confirmed

Confirmed by user on Windows cmd.exe, 2026-06-29:

```text
python -m pip install -r requirements-dev.txt                  # ok
python -m compileall app init_db.py tests && python -m pytest  # 284 passed, 8 skipped, 5 warnings in 59.09s
docker compose config                                          # ok
docker pull python:3.11-slim                                   # ok
docker pull nginx:1.27-alpine                                  # ok
docker compose build --no-cache web bot                        # ok
docker compose up -d --build                                   # ok
docker compose ps                                              # web healthy, nginx up on nginx:1.27-alpine, bot up
curl -f http://localhost/health                                # {"status":"ok","database":"ok","scheduler":"running"}
docker compose exec -T web id                                  # uid=1000(zhkh) gid=1000(zhkh)
docker compose exec -T bot id                                  # uid=1000(zhkh) gid=1000(zhkh)
docker compose logs --tail=120 web                             # no startup or permission errors
docker compose logs --tail=120 nginx                           # startup ok
docker compose logs --tail=120 bot                             # bot polling started
```

`docker compose config` confirms:

- `nginx:1.27-alpine`;
- Python stdlib healthcheck with `urllib.request`;
- `APP_UID` / `APP_GID` build args;
- `security_opt: no-new-privileges:true` for web, bot, and nginx.

## Docker smoke result

Docker hardening smoke is complete for the changed runtime model based on the user-confirmed local evidence above:

- web and bot containers run as non-root `zhkh` (`uid=1000`, `gid=1000`);
- web healthcheck succeeds through nginx and internally;
- nginx starts with the pinned `nginx:1.27-alpine` image;
- web logs show clean startup, migrations, scheduler start, and repeated successful `/health` responses;
- bot logs show successful polling startup;
- no `gosu`, `chown`, bind-mount permission, or startup failures were observed in the smoke logs.

## Post-review correction

During connector review on 2026-06-29, README still contained stale wording for the old root entrypoint / `gosu` model. This was corrected after the smoke evidence above:

- `README.md` now describes direct `USER zhkh` startup and host-prepared bind-mount ownership.
- `tests/test_docker_runtime.py` now prevents the old `gosu` / root-entrypoint wording from returning.

This review did not independently rerun Docker or pytest after that documentation/test guard correction; rerun `python -m pytest tests/test_docker_runtime.py` or the full validation command before merging if fresh post-commit evidence is required.

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
- Docker hardening completion does not by itself close non-Docker release validation items; use the current roadmap and validation docs for those statuses.
- Be careful with `USER zhkh`: it can break bind-mount writes if host directory ownership is not prepared.
