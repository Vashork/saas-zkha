# LOCAL AI TODO

Файл ведётся как актуальный рабочий хвост задач для локального ИИ.
Выполненные пункты удаляются из раздела актуальных задач или переносятся в `Выполнено`.
Если задача из `docs/RELEASE_ROADMAP.md` не получилась за текущую итерацию, нужно кратко записать сюда причину и следующий шаг.

## Актуальные задачи

### 1. Timezone в настройках

Связано с `docs/RELEASE_ROADMAP.md`: P2 timezone + tests.

Нужно:

* добавить в UI настроек поле timezone;
* сохранять значение в `settings.notification_timezone`;
* использовать сохранённое значение для времени на странице бекапов;
* проверить, нужен ли этот timezone в scheduler/notifications, и применить там, где это действительно используется;
* добавить route/template tests для сохранения и отображения timezone.

Важно: страница бекапов уже умеет читать `notification_timezone`, но в UI/settings ещё нет полноценного сохранения этого значения.

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
