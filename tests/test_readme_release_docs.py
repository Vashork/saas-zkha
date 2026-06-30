"""README release/security documentation regression tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_documents_authenticated_receipt_serving_only():
    readme = _readme()

    assert "`/uploads` не монтируется как публичная статика" in readme
    assert "`/payments/receipts/{path}`" in readme
    assert "ownership check" in readme
    assert "Чеки не доступны через `/uploads`" in readme
    assert "Статики** (`/static`, `/uploads`)" not in readme


def test_readme_documents_production_secrets_and_quiet_compose_validation():
    readme = _readme()

    assert "APP_ENV=production" in readme
    assert "SECRET_KEY=<unique-random-secret>" in readme
    assert "ADMIN_PASSWORD=<strong-admin-password>" in readme
    assert "USER_PASSWORD=<strong-user-password>" in readme
    assert "COOKIE_SECURE=true" in readme
    assert "docker compose config -q" in readme
    assert "Не прикладывайте полный вывод `docker compose config`" in readme
    assert "перевыпустите у BotFather" in readme


def test_readme_documents_telegram_allowlist_management_and_commands():
    readme = _readme()

    assert "TELEGRAM_ADMIN_ID" in readme
    assert "TELEGRAM_ALLOWED_USER_IDS" in readme
    assert "`TELEGRAM_ADMIN_ID` автоматически входит в allowlist" in readme
    assert "`/tglog [N]`" in readme
    assert "Admin-only web UI `/telegram`" in readme
    assert "DB-настройки Telegram имеют приоритет над env fallback" in readme


def test_readme_documents_angie_reverse_proxy_and_dns_tls_plan():
    readme = _readme()

    assert "│ │ angie        │" in readme
    assert "`zhkh-angie`" in readme
    assert "Angie проксирует" in readme
    assert "Docker Compose: `web`, `bot`, `angie`" in readme
    assert "logs/angie" in readme
    assert "docker compose logs --tail=120 angie" in readme
    assert "docker/angie.conf" in readme
    assert "docs/PRODUCTION_DNS_TLS_ROADMAP.md" in readme
    assert "zhkh-nginx" not in readme
    assert "logs/nginx" not in readme
    assert "docker/nginx.conf" not in readme
