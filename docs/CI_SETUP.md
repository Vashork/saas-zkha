# CI setup

The branch uses GitHub Actions workflow `.github/workflows/ci.yml`.

## What CI checks

On pull requests and pushes to `main` or `audit/ui-backup-delete-button`, CI runs:

1. Python 3.12 setup.
2. Dependency installation from `requirements.txt`.
3. Runtime directory preparation for `data/uploads`, `logs` and `backups`.
4. Syntax check with `python -m compileall app tests`.
5. Minimal FastAPI app import check.
6. Unit tests with `python -m pytest tests/ -v`.

## Local equivalent

Run this from the repository root:

```bash
python -m pip install -r requirements.txt
python -m compileall app tests
python -m pytest tests/ -v
```

If environment-dependent imports fail locally, export the same variables used in CI:

```bash
export SECRET_KEY=ci-secret-key
export ADMIN_PASSWORD=ci-admin-password
export USER_PASSWORD=ci-user-password
export DATABASE_URL=sqlite+aiosqlite:///./data/zhkh-ci.db
export UPLOAD_DIR=./data/uploads
export LOG_DIR=./logs
export GENERATION_ENABLED=false
export TELEGRAM_BOT_TOKEN=
export TELEGRAM_ADMIN_ID=
```

On Windows `cmd`:

```cmd
set SECRET_KEY=ci-secret-key
set ADMIN_PASSWORD=ci-admin-password
set USER_PASSWORD=ci-user-password
set DATABASE_URL=sqlite+aiosqlite:///./data/zhkh-ci.db
set UPLOAD_DIR=./data/uploads
set LOG_DIR=./logs
set GENERATION_ENABLED=false
set TELEGRAM_BOT_TOKEN=
set TELEGRAM_ADMIN_ID=
```

## Interpreting failures

- `compileall` failure: syntax/import-level issue that should be fixed before QA.
- `Import web app` failure: FastAPI app cannot start; check env variables, imports and route wiring.
- `pytest` failure: inspect the failing test first, then reproduce with `python -m pytest <test_file> -v`.

## Production note

CI uses safe placeholder secrets only for tests. Do not reuse these values in production.
