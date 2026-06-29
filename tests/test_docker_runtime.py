"""Docker runtime hardening regression tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_dockerfile_runs_as_non_root_user_and_uses_start_script():
    dockerfile = (ROOT / "docker" / "Dockerfile.web").read_text(encoding="utf-8")

    assert "ARG APP_UID=1000" in dockerfile
    assert "ARG APP_GID=1000" in dockerfile
    assert "useradd" in dockerfile
    assert "mkdir -p /app/data/uploads /app/backups /var/log/zhkh-bot" in dockerfile
    assert "COPY docker/start-web.sh /usr/local/bin/start-web" in dockerfile
    assert "sed -i 's/\\r$//' /usr/local/bin/start-web" in dockerfile
    assert "USER zhkh" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "org.opencontainers.image.title" in dockerfile
    assert "gosu" not in dockerfile
    assert "curl" not in dockerfile
    assert 'CMD ["/usr/local/bin/start-web"]' in dockerfile

    start_script = (ROOT / "docker" / "start-web.sh").read_text(encoding="utf-8")
    assert "chown" not in start_script
    assert "gosu" not in start_script
    assert "exec python -m uvicorn app.web.main:app" in start_script


def test_gitattributes_forces_lf_for_container_runtime_files():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "*.sh text eol=lf" in attrs
    assert "docker/* text eol=lf" in attrs


def test_bot_dockerfile_runs_as_non_root_user():
    dockerfile = (ROOT / "docker" / "Dockerfile.bot").read_text(encoding="utf-8")

    assert "ARG APP_UID=1000" in dockerfile
    assert "ARG APP_GID=1000" in dockerfile
    assert "useradd" in dockerfile
    assert "mkdir -p /app/data/uploads /var/log/zhkh-bot" in dockerfile
    assert "COPY docker/start-bot.sh /usr/local/bin/start-bot" in dockerfile
    assert "sed -i 's/\\r$//' /usr/local/bin/start-bot" in dockerfile
    assert "USER zhkh" in dockerfile
    assert "org.opencontainers.image.title" in dockerfile
    assert "gosu" not in dockerfile
    assert "curl" not in dockerfile
    assert 'CMD ["/usr/local/bin/start-bot"]' in dockerfile

    start_script = (ROOT / "docker" / "start-bot.sh").read_text(encoding="utf-8")
    assert "chown" not in start_script
    assert "gosu" not in start_script
    assert "exec python -m app.bot.main" in start_script


def test_compose_uses_pinned_nginx_python_healthcheck_and_no_new_privileges():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "nginx:1.27-alpine" in compose
    assert "nginx:alpine" not in compose
    assert "urllib.request" in compose
    assert "curl" not in compose
    assert compose.count("no-new-privileges:true") == 3
    assert "APP_UID: ${APP_UID:-1000}" in compose
    assert "APP_GID: ${APP_GID:-1000}" in compose


def test_readme_documents_non_root_bind_mount_permissions():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "запускают приложение не от root" in readme
    assert "Entrypoint контейнера" in readme
    assert "sudo chown -R 1000:1000 data backups logs" in readme
    assert "APP_UID" in readme
    assert "APP_GID" in readme
