"""Role matrix regression tests."""

from types import SimpleNamespace

from app.web import permissions


def _user(role: str):
    return SimpleNamespace(role=role)


def test_role_action_matrix_defaults():
    matrix = {
        "admin": (True, True),
        "operator": (True, False),
        "viewer": (False, False),
        "user": (False, False),
        "unexpected": (False, False),
    }

    for role, (business_expected, system_expected) in matrix.items():
        user = _user(role)
        for permission in permissions.BUSINESS_ACTION_PERMISSIONS:
            assert permissions.has_action_permission(user, permission) is business_expected
        for permission in permissions.SYSTEM_ACTION_PERMISSIONS:
            assert permissions.has_action_permission(user, permission) is system_expected


def test_role_page_action_sets_are_disjoint_and_complete():
    assert permissions.BUSINESS_ACTION_PERMISSIONS.isdisjoint(permissions.SYSTEM_ACTION_PERMISSIONS)
    assert permissions.VIEW_ACTION_PERMISSIONS.isdisjoint(permissions.BUSINESS_ACTION_PERMISSIONS)
    assert permissions.VIEW_ACTION_PERMISSIONS.isdisjoint(permissions.SYSTEM_ACTION_PERMISSIONS)
    assert permissions.ALL_ACTION_PERMISSIONS == (
        permissions.VIEW_ACTION_PERMISSIONS
        | permissions.BUSINESS_ACTION_PERMISSIONS
        | permissions.SYSTEM_ACTION_PERMISSIONS
    )


def test_operator_never_gets_sensitive_actions_by_default():
    operator = _user("operator")

    for permission in (
        permissions.USERS_MANAGE,
        permissions.SYSTEM_SETTINGS_MANAGE,
        permissions.TELEGRAM_MANAGE,
        permissions.BACKUPS_MANAGE,
        permissions.BACKUPS_RESTORE,
        permissions.SECURITY_AUDIT_VIEW,
    ):
        assert not permissions.has_action_permission(operator, permission)


def test_legacy_and_unknown_roles_normalize_to_viewer_policy():
    for role in ("user", "unexpected", ""):
        assert permissions.normalize_role(role) == "viewer"
        assert permissions.permissions_for_role(role) == permissions.permissions_for_role("viewer")
