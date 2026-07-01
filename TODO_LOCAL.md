# Backlog

Do not close these items without real implementation and tests.

## Email code verification

Not implemented yet. Add a real email provider, challenge table with hashed code and expiry, request and confirm routes, attempt limits, and tests for expiry and replay.

## Durable rate limiting

Not implemented yet. Use persistent limits by IP, user, and storefront. Respect trusted proxy boundaries.

## Notifications

Not implemented yet. Add a clean notification adapter for new request and status change events.

## Audit log

Not implemented yet. Add audit events for auth, user actions, storefront changes, lot changes, request status changes, settings changes, and upload failures.
