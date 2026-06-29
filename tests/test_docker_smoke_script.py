"""Docker smoke QA script regression tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docker_smoke_check.py"


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_docker_smoke_script_exists():
    assert SCRIPT.is_file()


def test_docker_smoke_script_uses_quiet_compose_config_only():
    script = _script_text()

    assert '"config", "-q"' in script
    assert '"config"]' not in script
    assert "full config may print secrets" in script
    assert "docker compose config" not in script.lower()


def test_docker_smoke_script_checks_core_runtime_evidence():
    script = _script_text()

    assert '"build", "--no-cache", "web", "bot"' in script
    assert '"up", "-d", "--build"' in script
    assert '"ps"' in script
    assert "/health" in script
    assert "/login" in script
    assert "/uploads/docker-smoke-missing.txt" in script
    assert '"web", "nginx", "bot"' in script


def test_docker_smoke_script_does_not_require_app_secrets():
    script = _script_text()

    assert "TELEGRAM_BOT_TOKEN" not in script
    assert "ADMIN_PASSWORD" not in script
    assert "USER_PASSWORD" not in script
    assert "SECRET_KEY" not in script
