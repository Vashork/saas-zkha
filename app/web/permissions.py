"""Action-level permission helpers for web routes.

This layer intentionally does not replace page permissions. Page permissions still
control navigation/read visibility, while action permissions control mutations and
sensitive system operations.
"""

from __future__ import annotations

from typing import Iterable

# Role values persisted in users.role.
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"
ROLE_LEGACY_USER = "user"

# Page/read actions. Existing page_permissions still remain the source of truth
# for route visibility during the transition.
DASHBOARD_VIEW = "dashboard.view"
PAYMENTS_VIEW = "payments.view"
HISTORY_VIEW = "history.view"
CONTRACTORS_VIEW = "contractors.view"
ANALYTICS_VIEW = "analytics.view"
SETTINGS_VIEW = "settings.view"

# Business mutations.
PAYMENTS_CREATE = "payments.create"
PAYMENTS_UPDATE = "payments.update"
PAYMENTS_DELETE = "payments.delete"
PAYMENTS_RECEIPTS_DOWNLOAD = "payments.receipts.download"
PAYMENTS_RECEIPTS_UPLOAD = "payments.receipts.upload"
PAYMENTS_RECEIPTS_CLEANUP = "payments.receipts.cleanup"
PAYMENT_TRANSACTIONS_CREATE = "payments.transactions.create"
PAYMENT_TRANSACTIONS_UPDATE = "payments.transactions.update"
PAYMENT_TRANSACTIONS_DELETE = "payments.transactions.delete"

CONTRACTORS_CREATE = "contractors.create"
CONTRACTORS_UPDATE = "contractors.update"
CONTRACTORS_DELETE = "contractors.delete"
CONTRACTORS_TOGGLE = "contractors.toggle"

# Sensitive system operations.
USERS_MANAGE = "users.manage"
SYSTEM_SETTINGS_MANAGE = "system_settings.manage"
TELEGRAM_MANAGE = "telegram.manage"
BACKUPS_MANAGE = "backups.manage"
BACKUPS_RESTORE = "backups.restore"
SECURITY_AUDIT_VIEW = "security.audit.view"

BUSINESS_ACTION_PERMISSIONS = frozenset({
    PAYMENTS_CREATE,
    PAYMENTS_UPDATE,
    PAYMENTS_DELETE,
    PAYMENTS_RECEIPTS_DOWNLOAD,
    PAYMENTS_RECEIPTS_UPLOAD,
    PAYMENTS_RECEIPTS_CLEANUP,
    PAYMENT_TRANSACTIONS_CREATE,
    PAYMENT_TRANSACTIONS_UPDATE,
    PAYMENT_TRANSACTIONS_DELETE,
    CONTRACTORS_CREATE,
    CONTRACTORS_UPDATE,
    CONTRACTORS_DELETE,
    CONTRACTORS_TOGGLE,
})

SYSTEM_ACTION_PERMISSIONS = frozenset({
    USERS_MANAGE,
    SYSTEM_SETTINGS_MANAGE,
    TELEGRAM_MANAGE,
    BACKUPS_MANAGE,
    BACKUPS_RESTORE,
    SECURITY_AUDIT_VIEW,
})

VIEW_ACTION_PERMISSIONS = frozenset({
    DASHBOARD_VIEW,
    PAYMENTS_VIEW,
    HISTORY_VIEW,
    CONTRACTORS_VIEW,
    ANALYTICS_VIEW,
    SETTINGS_VIEW,
})

ALL_ACTION_PERMISSIONS = VIEW_ACTION_PERMISSIONS | BUSINESS_ACTION_PERMISSIONS | SYSTEM_ACTION_PERMISSIONS

# Default role policy:
# - admin keeps all permissions;
# - operator can run day-to-day business mutations through named route checks;
# - viewer/legacy user get no action permissions, page_permissions still control read visibility.
ROLE_ACTION_PERMISSIONS = {
    ROLE_ADMIN: ALL_ACTION_PERMISSIONS,
    ROLE_OPERATOR: BUSINESS_ACTION_PERMISSIONS,
    ROLE_VIEWER: frozenset(),
    ROLE_LEGACY_USER: frozenset(),
}


def normalize_role(role: str | None) -> str:
    """Normalize persisted role values without mutating the database."""
    value = (role or "").strip().lower()
    if value == ROLE_LEGACY_USER:
        return ROLE_VIEWER
    if value in {ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER}:
        return value
    return ROLE_VIEWER


def permissions_for_role(role: str | None) -> frozenset[str]:
    """Return default action permissions for a role."""
    return ROLE_ACTION_PERMISSIONS.get(role or "", ROLE_ACTION_PERMISSIONS[normalize_role(role)])


def has_action_permission(user, permission: str) -> bool:
    """Return True when the user has the named action permission."""
    if user is None or not permission:
        return False
    return permission in permissions_for_role(getattr(user, "role", None))


def missing_action_permissions(user, permissions: Iterable[str]) -> list[str]:
    """Return permissions that are not granted to this user."""
    return [permission for permission in permissions if not has_action_permission(user, permission)]


def has_all_action_permissions(user, permissions: Iterable[str]) -> bool:
    """Return True when the user has every named permission."""
    return not missing_action_permissions(user, permissions)
