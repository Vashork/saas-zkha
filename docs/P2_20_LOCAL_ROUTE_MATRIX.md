# P2-20 local route matrix handoff

Connector accepted `tests/test_role_matrix.py` but blocked the larger route-level matrix test file.

Committed:

- `tests/test_role_matrix.py`
- commit `02826b53a5a46d7058703eeac6c47e4577b01f46`
- covers default role action matrix and disjoint action sets.

Local AI follow-up:

1. Add a route-level matrix test file.
2. Use an in-memory SQLite database and patch `auth.async_session_factory`.
3. Create users for admin, operator, viewer, legacy user and empty-page-access viewer.
4. Cover page visibility with `auth._require_page`.
5. Cover a business mutation route such as `contractors.add_contractor`: admin/operator allowed, viewer/legacy denied.
6. Cover a system route such as `auth.create_user`: only admin allowed.
7. Cover a sensitive helper such as `backups._require_action_user` with `BACKUPS_MANAGE`: only admin allowed.
8. Then run:

```cmd
git pull --ff-only && python -m pytest tests/test_role_matrix.py -v && python -m pytest -q
```

Do not include env contents, tokens, passwords, or full Compose config output in evidence.
