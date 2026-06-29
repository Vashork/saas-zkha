# LOCAL AI TODO

Файл ведётся как актуальный рабочий хвост задач для локального ИИ.
Выполненные пункты удаляются из раздела актуальных задач или переносятся в `Выполнено`.
Если задача из `docs/RELEASE_ROADMAP.md` не получилась за текущую итерацию, нужно кратко записать сюда причину и следующий шаг.

## Актуальные задачи

* P1-AUDIT-1: завершить production dependency validation после dependency bump: `pip-audit -r requirements.txt`, `docker compose config`; при доступном Docker — `docker compose up -d --build`, `/health`, login smoke, Telegram bot startup logs.
* P2-16: добавить action-level permissions вместо page-only permissions; не расширять operator CRUD без явных permission checks и тестов.

## Заблокировано / не получилось

* Дата: 2026-06-29
  * Задача: P1-AUDIT-1 — полный dependency/Docker validation после обновления `requirements.txt`.
  * Что пробовали: перечитали актуальную ветку через GitHub connector; обновили прямые pins для FastAPI/Starlette/aiogram/aiohttp/Jinja2/python-multipart/python-dotenv/pytest/pytest-asyncio; добавили compatibility adapter для legacy `TemplateResponse(name, context)` на Starlette 1.x; пользователь локально подтвердил full pytest: `276 passed, 8 skipped, 4 warnings in 64.53s`.
  * Что не получилось: в текущей sandbox-среде нельзя достоверно прогнать `pip-audit`, `docker compose config` и Docker smoke; pytest уже подтверждён локально пользователем.
  * Следующий шаг: в среде с доступом к PyPI/Docker выполнить `pip-audit -r requirements.txt`, `docker compose config` и Docker smoke; P1-AUDIT-1 отмечать `[x]` только после чистого `pip-audit` либо после документированного обоснования остаточных CVE.

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
* P2-15 role foundation закрыт 2026-06-29: добавлены `admin/operator/viewer`, legacy `user -> viewer`, UI выбора ролей и permission regression tests; full pytest — `276 passed, 8 skipped, 4 warnings in 64.53s`.
