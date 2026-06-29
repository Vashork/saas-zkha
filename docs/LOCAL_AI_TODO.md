# LOCAL AI TODO

Файл ведётся как актуальный рабочий хвост задач для локального ИИ.
Выполненные пункты удаляются из раздела актуальных задач или переносятся в `Выполнено`.
Если задача из `docs/RELEASE_ROADMAP.md` не получилась за текущую итерацию, нужно кратко записать сюда причину и следующий шаг.

## Актуальные задачи

Пока нет актуальных задач из текущего P2-хвоста, начатых в этом файле.

## Заблокировано / не получилось

Пока нет актуальных заблокированных задач.

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
