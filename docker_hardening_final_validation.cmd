@echo off
setlocal

REM ============================================================
REM Docker hardening final validation v3
REM Repo: Vashork/saas-zkha
REM Branch: audit/main-hardening-followup
REM
REM Fix in v3:
REM   - Removed delayed expansion because it breaks "!" in cmd.exe.
REM   - Rewrote gosu/curl absence checks without shell "!".
REM   - Keeps safe "docker compose config -q" only.
REM ============================================================

echo.
echo [1/16] Switch to target branch and fast-forward from origin/audit/main-hardening-followup
git switch audit/main-hardening-followup
if errorlevel 1 goto :error

git fetch origin audit/main-hardening-followup
if errorlevel 1 goto :error

git merge --ff-only FETCH_HEAD
if errorlevel 1 goto :error

echo.
echo [2/16] Install dev dependencies
python -m pip install -r requirements-dev.txt
if errorlevel 1 goto :error

echo.
echo [3/16] Compile Python files
python -m compileall app init_db.py tests
if errorlevel 1 goto :error

echo.
echo [4/16] Run full pytest
python -m pytest
if errorlevel 1 goto :error

echo.
echo [5/16] Run targeted Docker runtime tests
python -m pytest tests/test_docker_runtime.py -v
if errorlevel 1 goto :error

echo.
echo [6/16] Safe Compose validation, no resolved secrets printed
docker compose config -q
if errorlevel 1 goto :error

echo.
echo [7/16] Pull pinned base images
docker pull python:3.11-slim
if errorlevel 1 goto :error
docker pull nginx:1.27-alpine
if errorlevel 1 goto :error

echo.
echo [8/16] Build web and bot without cache
docker compose build --no-cache web bot
if errorlevel 1 goto :error

echo.
echo [9/16] Start stack
docker compose up -d --build
if errorlevel 1 goto :error

echo.
echo [10/16] Show container status
docker compose ps
if errorlevel 1 goto :error

echo.
echo [11/16] Check /health through nginx
curl -f http://localhost/health
if errorlevel 1 goto :error

echo.
echo [12/16] Check web and bot runtime users
docker compose exec -T web id
if errorlevel 1 goto :error
docker compose exec -T bot id
if errorlevel 1 goto :error

echo.
echo [13/16] Assert web and bot are uid/gid 1000
docker compose exec -T web sh -lc "test $(id -u) = 1000 && test $(id -g) = 1000"
if errorlevel 1 goto :error
docker compose exec -T bot sh -lc "test $(id -u) = 1000 && test $(id -g) = 1000"
if errorlevel 1 goto :error

echo.
echo [14/16] Assert gosu and curl are absent in runtime containers
docker compose exec -T web sh -lc "if command -v gosu >/dev/null 2>&1; then echo ERROR: gosu found in web; exit 1; fi; if command -v curl >/dev/null 2>&1; then echo ERROR: curl found in web; exit 1; fi; echo web: gosu/curl absent"
if errorlevel 1 goto :error
docker compose exec -T bot sh -lc "if command -v gosu >/dev/null 2>&1; then echo ERROR: gosu found in bot; exit 1; fi; if command -v curl >/dev/null 2>&1; then echo ERROR: curl found in bot; exit 1; fi; echo bot: gosu/curl absent"
if errorlevel 1 goto :error

echo.
echo [15/16] Check writable bind-mount paths for non-root runtime user
docker compose exec -T web sh -lc "touch /app/data/.write-test && rm /app/data/.write-test"
if errorlevel 1 goto :error
docker compose exec -T web sh -lc "touch /app/backups/.write-test && rm /app/backups/.write-test"
if errorlevel 1 goto :error
docker compose exec -T bot sh -lc "touch /var/log/zhkh-bot/.write-test && rm /var/log/zhkh-bot/.write-test"
if errorlevel 1 goto :error

echo.
echo [16/16] Logs and image evidence
docker compose logs --tail=120 web
if errorlevel 1 goto :error
docker compose logs --tail=120 nginx
if errorlevel 1 goto :error
docker compose logs --tail=120 bot
if errorlevel 1 goto :error
docker compose images
if errorlevel 1 goto :error

echo.
echo ============================================================
echo SUCCESS: Docker hardening final validation completed.
echo Expected evidence:
echo - pytest green
echo - tests/test_docker_runtime.py green
echo - docker compose config -q has no output/errors
echo - web healthy, nginx up on nginx:1.27-alpine, bot up
echo - /health returns status/database/scheduler ok
echo - web and bot run as uid=1000(zhkh) gid=1000(zhkh)
echo - gosu and curl are absent from web/bot containers
echo - write tests pass without Permission denied
echo - logs have no startup or permission errors
echo ============================================================
echo.

REM Uncomment this if you want automatic cleanup after successful smoke:
REM docker compose down

exit /b 0

:error
echo.
echo ============================================================
echo FAILED: command above returned an error.
echo Stack is left running for inspection.
echo Useful commands:
echo   git branch -vv
echo   docker compose ps
echo   docker compose logs --tail=120 web
echo   docker compose logs --tail=120 nginx
echo   docker compose logs --tail=120 bot
echo ============================================================
exit /b 1
