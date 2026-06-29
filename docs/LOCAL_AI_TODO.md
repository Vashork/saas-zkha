# LOCAL AI TODO

Файл ведётся как актуальный рабочий хвост задач для локального ИИ.
Выполненные пункты удаляются из раздела актуальных задач или переносятся в `Выполнено`.
Если задача из `docs/RELEASE_ROADMAP.md` не получилась за текущую итерацию, нужно кратко записать сюда причину и следующий шаг.

## Актуальные задачи

* P1-AUDIT-1: выполнить полный локальный validation после dependency bump: `python -m compileall app init_db.py tests`, `python -m pytest`, `pip-audit -r requirements.txt`, `docker compose config`; при доступном Docker — `docker compose up -d --build`, `/health`, login smoke, Telegram bot startup logs.
* P2-15: проверить role foundation после изменений: `python -m pytest tests/test_permissions.py tests/test_theme_scope.py tests/test_telegram_gui.py`; затем полный `python -m pytest`. Если зелёный — можно отметить P2-15 закрытым и переходить к P2-16 action-level permissions.

## Заблокировано / не получилось

* Дата: 2026-06-29
  * Задача: P1-AUDIT-1 — полный локальный dependency/test/Docker validation после обновления `requirements.txt`.
  * Что пробовали: перечитали актуальную ветку через GitHub connector; обновили прямые pins для FastAPI/Starlette/aiogram/aiohttp/Jinja2/python-multipart/python-dotenv/pytest/pytest-asyncio; добавили compatibility adapter для legacy `TemplateResponse(name, context)` на Starlette 1.x; попытались получить локальный checkout через `git clone --branch audit/main-hardening-followup --single-branch https://github.com/Vashork/saas-zkha.git /mnt/data/saas-zkha`.
  * Что не получилось: текущая sandbox-среда не смогла выполнить локальный checkout из-за DNS/network error `Could not resolve host: github.com`; без локального checkout и PyPI/Docker-доступа здесь нельзя достоверно прогнать `compileall`, `pytest`, `pip-audit`, `docker compose config` и Docker smoke.
  * Следующий шаг: в среде с доступом к GitHub/PyPI/Docker выполнить команды из актуальных задач; P1-AUDIT-1 отмечать `[x]` в roadmap только после зелёного test run и чистого `pip-audit` либо после документированного обоснования остаточных CVE.
* Дата: 2026-06-29
  * Задача: P2-15 — role foundation для `admin/operator/viewer`.
  * Что пробовали: добавили роли на существующем `users.role`, нормализацию legacy `user -> viewer`, выбор ролей в settings UI и tests в `tests/test_permissions.py`.
  * Что не получилось: текущая sandbox-среда всё ещё не может достоверно прогнать локальный pytest из-за отсутствия checkout/test runtime.
  * Следующий шаг: локально выполнить targeted tests из актуальных задач; если зелёные — отметить P2-15 `[x]` и начинать P2-16 action-level permissions.

## Выполнено

* Создан `docs/LOCAL_AI_TODO.md`.
* Создан `docs/LOCALAL.md`.
* Создан `app/web/static/css/local-ui-tweaks.css`.
* На странице analytics порядок меню и отступы select уже поправлены.
* Все страницы с верхним меню приведены к порядку: Дашборд → Платежи → Подрядчики → Аналитика → История → Бекапы → Настройки.
* P1 full test run закрыт 2026-06-29: `python -m pytest` на Windows/Python 3.13 — 259 collected, 251 passed, 8 skipped, 5 warnings, 0 failed, 69.76s.
* `app/web/static/css/local-ui-tweaks.css` подключён в `base.html`; добавлен asset wiring test.
* Timezone в настройках закрыт: добавлено admin-only UI-поле, сохранение `settings.notification_timezone`, IANA validation, применение в scheduler/notifications/auto-backup и route/template tests.
* Docker non-root runtime закрыт: web/bot images запускаются под пользователем `zhkh`, `docker/start-web.sh` подключён в web image, README описывает права для bind-mount директорий.
* Scope темы оформления закрыт: `settings.ui_theme` оставлен глобальной настройкой, но `/settings/theme` теперь обслуживается admin-only route из `system_settings`; обычный пользователь не может мутировать глобальную тему.
