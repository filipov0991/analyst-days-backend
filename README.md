# Analyst Days — backend

Локальный MVP «Analyst Days: моя программа»: каталог докладов, анонимная личная программа, сохранение в SQLite и серверная проверка пересечений. Python 3.12, FastAPI, SQLAlchemy 2, Pydantic.

**Демонстрационная программа. Не является официальным расписанием Analyst Days.** В seed — 20 вымышленных докладов, два дня и три зала. Условные даты заданы только в `app/seed.py`; интерфейс должен показывать «День 1» / «День 2» и время Europe/Moscow.

## Установка и запуск

Выполняйте команды из корня backend-репозитория. Нужен Python 3.12.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m app.db init-db
python -m app.seed
uvicorn app.main:app --reload --port 8000 --no-access-log
```

`requirements.txt` фиксирует все установленные зависимости, включая тестовые. `init-db` создаёт отсутствующие таблицы; `seed` сам вызывает инициализацию и вставляет отсутствующие демонстрационные записи. Повторный seed не обновляет существующие записи и не удаляет выбор. Обычный запуск ничего не создаёт и не сбрасывает. База по умолчанию — `data/app.db`, каталог создаёт команда инициализации.

- API: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- Swagger: [http://localhost:8000/docs](http://localhost:8000/docs)
- OpenAPI: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

Frontend находится в отдельном соседнем репозитории `analyst-days-frontend`; его публичная ссылка пока не предоставлена. Он должен проксировать `/api/*` на backend, передавать `Cookie`, `Set-Cookie`, `Origin`, сохранять `Cache-Control: no-store`. До включения кнопок выбора нужен один GET `/api/me/program`. Этот репозиторий frontend не изменяет; интеграция с ним отдельно не проверена.

## Конфигурация

Настройки загружаются из `.env` и переменных окружения (окружение имеет приоритет):

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| DATABASE_URL | sqlite:///./data/app.db | SQLite, относительный путь от рабочего каталога |
| APP_ENV | development | В production требуется Secure cookie |
| COOKIE_SECURE | false | `true` для HTTPS |
| ALLOWED_ORIGINS | http://localhost:3000 | Точные origin через запятую, без завершающего `/` |

CORS не включён: предусмотрен same-origin proxy. PUT/DELETE требуют разрешённый `Origin`; отсутствие заголовка также даёт 403. Для Swagger «Try it out» на backend добавьте `http://localhost:8000` в `ALLOWED_ORIGINS` и перезапустите сервис. Браузер управляет заголовком Origin самостоятельно; одно заполнение поля `origin` в Swagger не может обойти ограничения браузера. Если используется адрес `127.0.0.1`, его origin нужно разрешить отдельно. curl должен отправлять заголовок явно.

Cookie `ad_session`: HttpOnly, SameSite=Lax, Path=/, Max-Age=2592000, без Domain; Secure зависит от окружения. Срок в БД фиксирован — 30 дней без продления. В БД хранится только SHA-256 токена. Истёкшая/некорректная cookie заменяется новой при персональном запросе; старый выбор не переносится. Конфликты не запрещают сохранение.

## Проверка

```sh
source .venv/bin/activate
python -m pytest -q
python -m pip check
```

Тесты используют отдельные временные SQLite-файлы, не рабочую БД. [Отчёт проверок](docs/test-report.md).

С запущенным сервером можно выполнить автоматическую HTTP-проверку: `python scripts/smoke.py`. Она использует новую сессию и удаляет свой выбор после проверки.

HTTP-сценарий вручную (cookie-файл вне Git):

```sh
COOKIE_JAR=$(mktemp)
curl -fsS http://localhost:8000/api/health
curl -fsS 'http://localhost:8000/api/talks?day_id=1&room_id=1'
curl -fsS -c "$COOKIE_JAR" http://localhost:8000/api/me/program
curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X PUT \
  -H 'Origin: http://localhost:3000' http://localhost:8000/api/me/program/talks/1
curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X PUT \
  -H 'Origin: http://localhost:3000' http://localhost:8000/api/me/program/talks/2
curl -fsS -b "$COOKIE_JAR" http://localhost:8000/api/me/program
curl -fsS -b "$COOKIE_JAR" -X DELETE \
  -H 'Origin: http://localhost:3000' http://localhost:8000/api/me/program/talks/2
rm "$COOKIE_JAR"
```

После добавления 1 и 2 ожидаются `selected_count=2`, `conflicting_talk_count=2`, симметричный конфликт. DELETE — 204 без тела. Выбор остаётся после перезапуска с тем же файлом БД и той же cookie. Не публикуйте cookie-файлы или их содержимое.

## Docker — подготовка к следующему этапу

Контейнер не развёрнут; локальный Docker build в этой работе не проверялся. Для будущего запуска предусмотрен непривилегированный пользователь и постоянный том `/data`:

```sh
docker build -t analyst-days-backend .
docker volume create analyst-days-data
docker run --rm -v analyst-days-data:/data analyst-days-backend python -m app.seed
docker run --rm -p 127.0.0.1:8000:8000 -v analyst-days-data:/data \
  -e DATABASE_URL=sqlite:////data/app.db \
  -e ALLOWED_ORIGINS=http://localhost:3000 analyst-days-backend
```

Для размещения потребуются HTTPS/proxy, `APP_ENV=production`, `COOKIE_SECURE=true`, точный внешний `ALLOWED_ORIGINS`, постоянное хранилище и резервное копирование. В production запускать без `--reload`. Не включать логирование Cookie, токенов или содержимого личных программ. Access log в примерах отключён, чтобы не сохранять произвольные query-параметры.

## Документация и ограничения

- [Исходный контекст v0](docs/context-v0.md), [ТЗ и API-контракт v1](docs/backend-spec.md)
- [Фактический контекст v1](docs/context-v1.md), [API и примеры](docs/api.md)
- [ERD и sequence](docs/architecture.md), [Отчёт проверок](docs/test-report.md)
- [Промпты](docs/prompts.md), [Сценарий видео](docs/video-script.md), [Чек-лист сдачи](docs/checklist.md)

MVP не содержит регистрации, редактирования каталога, миграций схемы, импорта официальной программы или периодической очистки истёкших сессий. SQLite рассчитана на небольшой локальный демонстрационный сервис. Health проверяет только `SELECT 1`, а не заполненность схемы. Frontend, мобильный сценарий, Docker и публичное размещение требуют отдельных проверок. Детали и результаты — в отчёте.
