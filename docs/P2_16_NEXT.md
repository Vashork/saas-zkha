# P2-16 NEXT

Done in this pass:
- `app/web/permissions.py`
- `tests/test_action_permissions.py`
- contractor mutation checks use named action permissions

Next local steps:
- run `python -m pytest tests/test_action_permissions.py tests/test_permissions.py`
- convert payments mutation checks to named action permissions
- keep operator mutations disabled until the next role-matrix step
- run full `python -m pytest`
