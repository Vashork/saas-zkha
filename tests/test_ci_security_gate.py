"""CI/security gate regression tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-audit.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_dependency_audit_workflow_exists():
    assert WORKFLOW.is_file()


def test_dependency_audit_workflow_runs_pip_audit_against_runtime_requirements():
    workflow = _workflow_text()

    assert "python -m pip install pip-audit" in workflow
    assert "python -m pip_audit -r requirements.txt" in workflow
    assert "requirements.txt" in workflow
    assert "requirements-dev.txt" in workflow


def test_dependency_audit_workflow_is_low_privilege_and_not_secret_dependent():
    workflow = _workflow_text()

    assert "contents: read" in workflow
    assert "TELEGRAM_BOT_TOKEN" not in workflow
    assert "docker compose config" not in workflow
    assert "env:" not in workflow
