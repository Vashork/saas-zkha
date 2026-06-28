# LOCAL AI TODO

Файл ведётся как актуальный рабочий хвост задач для локального ИИ.
Выполненные пункты удаляются из раздела актуальных задач или переносятся в `Выполнено`.
Если задача из `docs/RELEASE_ROADMAP.md` не получилась за текущую итерацию, нужно кратко записать сюда причину и следующий шаг.

## Актуальные задачи

### 1. Timezone в настройках

Связано с `docs/RELEASE_ROADMAP.md`: P2 timezone + tests.

Нужно:
- добавить в UI настроек поле timezone;
- сохранять значение в `settings.notification_timezone`;
- использовать сохранённое значение для времени на странице бекапов;
- проверить, нужен ли этот timezone в scheduler/notifications, и применить там, где это действительно используется;
- добавить route/template tests для сохранения и отображения timezone.

Важно: страница бекапов уже умеет читать `notification_timezone`, но в UI/settings ещё нет полноценного сохранения этого значения.

### 2. Select и блок бекапов

Связано с `docs/RELEASE_ROADMAP.md`: P2 local UI cleanup.

Создан файл `app/web/static/css/local-ui-tweaks.css`.
Нужно выбрать один вариант:
- подключить его в `app/web/templates/base.html`, если правки ещё нужны;
- или удалить файл, если эти правки уже неактуальны.

Файл содержит:
- правый отступ для выпадающих списков;
- увеличенный отступ в блоке настройки бекапов;
- увеличенный line-height для карточек `Локально` и `Mounted share`.

Если стрелка select всё ещё близко к краю после padding-right, заменить нативную стрелку на кастомную CSS-стрелку.

## Заблокировано / не получилось

- Дата: 2026-06-29
- Задача: P1 — прогнать полный test run и зафиксировать результат перед merge/release.
- Что пробовали: пользователь выполнил `python -m pytest` на Windows/Python 3.13 после установки зависимостей. Прогон дошёл до выполнения тестов: 254 collected, 236 passed, 11 failed, 7 skipped.
- Что не получилось: release-gate пока не зелёный. Падения были в Alembic subprocess на Windows, UTF-8 чтении source-файлов, low-level fcntl lock assertion на Windows, parser `06.26`, receipt ownership source assertion и UI asset assertions.
- Следующий шаг: после внесённых follow-up fixes выполнить `git pull --ff-only origin audit/main-hardening-followup`, затем `python -m pip install -r requirements.txt` и повторить `python -m pytest`. Если зелёный — обновить `docs/RELEASE_ROADMAP.md` и отметить P1 release-gate как `[x]`; если останутся failures — приложить новый вывод.

## Выполнено

- Создан `docs/LOCAL_AI_TODO.md`.
- Создан `docs/LOCALAL.md`.
- Создан `app/web/static/css/local-ui-tweaks.css`.
- На странице analytics порядок меню и отступы select уже поправлены.
- Все страницы с верхним меню приведены к порядку: Дашборд → Платежи → Подрядчики → Аналитика → История → Бекапы → Настройки.
