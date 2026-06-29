"""Action-level permission helper regression tests."""

from pathlib import Path
from types import SimpleNamespace

from app.web import permissions

ROOT = Path(__file__).resolve().parents[1]


def _user(role: str):
    return SimpleNamespace(role=role)


def test_admin_has_all_business_and_system_action_permissions():
    admin = _user("admin")

    assert permissions.has_action_permission(admin, permissions.PAYMENTS_CREATE)
    assert permissions.has_action_permission(admin, permissions.PAYMENTS_UPDATE)
    assert permissions.has_action_permission(admin, permissions.PAYMENTS_DELETE)
    assert permissions.has_action_permission(admin, permissions.CONTRACTORS_CREATE)
    assert permissions.has_action_permission(admin, permissions.CONTRACTORS_UPDATE)
    assert permissions.has_action_permission(admin, permissions.CONTRACTORS_DELETE)
    assert permissions.has_action_permission(admin, permissions.USERS_MANAGE)
    assert permissions.has_action_permission(admin, permissions.TELEGRAM_MANAGE)
    assert permissions.has_action_permission(admin, permissions.BACKUPS_RESTORE)


def test_operator_is_modeled_but_has_no_mutations_until_p2_17():
    operator = _user("operator")

    assert not permissions.has_action_permission(operator, permissions.PAYMENTS_CREATE)
    assert not permissions.has_action_permission(operator, permissions.PAYMENTS_UPDATE)
    assert not permissions.has_action_permission(operator, permissions.PAYMENTS_DELETE)
    assert not permissions.has_action_permission(operator, permissions.CONTRACTORS_CREATE)
    assert not permissions.has_action_permission(operator, permissions.CONTRACTORS_UPDATE)
    assert not permissions.has_action_permission(operator, permissions.CONTRACTORS_DELETE)
    assert not permissions.has_action_permission(operator, permissions.USERS_MANAGE)
    assert not permissions.has_action_permission(operator, permissions.TELEGRAM_MANAGE)
    assert not permissions.has_action_permission(operator, permissions.BACKUPS_RESTORE)


def test_viewer_and_legacy_user_have_no_action_permissions():
    for role in ("viewer", "user", "unexpected"):
        user = _user(role)
        assert not permissions.has_action_permission(user, permissions.PAYMENTS_CREATE)
        assert not permissions.has_action_permission(user, permissions.CONTRACTORS_CREATE)
        assert not permissions.has_action_permission(user, permissions.USERS_MANAGE)


def test_role_normalization_maps_legacy_user_to_viewer():
    assert permissions.normalize_role("user") == "viewer"
    assert permissions.normalize_role("viewer") == "viewer"
    assert permissions.normalize_role("operator") == "operator"
    assert permissions.normalize_role("admin") == "admin"
    assert permissions.normalize_role("bad-role") == "viewer"


def test_contractors_route_uses_named_action_permissions():
    source = (ROOT / "app" / "web" / "routes" / "contractors.py").read_text(encoding="utf-8")

    assert "has_action_permission" in source
    assert "_require_action_user" in source
    assert "CONTRACTORS_CREATE" in source
    assert "CONTRACTORS_UPDATE" in source
    assert "CONTRACTORS_DELETE" in source
    assert "CONTRACTORS_TOGGLE" in source
    assert 'current_user.role != "admin"' not in source


def test_payments_route_uses_named_action_permissions():
    source = (ROOT / "app" / "web" / "routes" / "payments.py").read_text(encoding="utf-8")

    assert "has_action_permission" in source
    assert "_require_action_user" in source
    assert "PAYMENTS_CREATE" in source
    assert "PAYMENTS_UPDATE" in source
    assert "PAYMENTS_DELETE" in source
    assert "PAYMENT_TRANSACTIONS_CREATE" in source
    assert "PAYMENT_TRANSACTIONS_UPDATE" in source
    assert "PAYMENT_TRANSACTIONS_DELETE" in source
    assert "PAYMENTS_RECEIPTS_CLEANUP" in source
    assert 'current_user.role != "admin"' not in source


def test_sensitive_admin_routes_use_named_action_permissions():
    auth_source = (ROOT / "app" / "web" / "routes" / "auth.py").read_text(encoding="utf-8")
    settings_source = (ROOT / "app" / "web" / "routes" / "system_settings.py").read_text(encoding="utf-8")
    telegram_source = (ROOT / "app" / "web" / "routes" / "telegram.py").read_text(encoding="utf-8")
    backups_source = (ROOT / "app" / "web" / "routes" / "backups.py").read_text(encoding="utf-8")

    assert "USERS_MANAGE" in auth_source
    assert "SYSTEM_SETTINGS_MANAGE" in auth_source
    assert "SYSTEM_SETTINGS_MANAGE" in settings_source
    assert "TELEGRAM_MANAGE" in telegram_source
    assert "BACKUPS_MANAGE" in backups_source
    assert "BACKUPS_RESTORE" in backups_source
    assert 'current_user.role != "admin"' not in settings_source
    assert 'current_user.role != "admin"' not in telegram_source
    assert 'current_user.role != "admin"' not in backups_source
