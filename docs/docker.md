# Локальный запуск Analyst Days в Docker

Нужны запущенный Docker Desktop с Docker Compose и свободные порты 3000/8000.
Команды выполняются из корня `analyst-days-backend`. Репозитории должны находиться рядом:

```text
analyst-days/
  analyst-days-backend/
    compose.yaml
  analyst-days-frontend/
```

Оба репозитория необходимо клонировать перед сборкой. Основная версия Compose хранится в backend-репозитории.

```sh
docker compose up --build -d
docker compose ps -a
```

- Приложение: http://localhost:3000 (используйте именно localhost для корректного Origin).
- Swagger: http://localhost:8000/docs (для просмотра; мутации по умолчанию разрешены только с origin frontend).
- Health: http://localhost:8000/api/health.

`init-db` создаёт схему и демонстрационные записи, затем завершается с кодом 0 — это нормально. Повторный seed сохраняет существующий выбор. Backend стартует после успешной инициализации, frontend — после healthcheck backend. Браузер обращается к `/api`, Next.js проксирует запросы внутри Docker на `http://backend:8000`. Этот адрес задаётся при сборке.

SQLite хранится в именованном томе `analyst-days_backend-data`; локальная БД в backend/data не используется. Обычная остановка и пересоздание контейнеров не удаляют том:

```sh
docker compose down
docker compose up -d
```

Не добавляйте `-v` к `down`, если нужно сохранить данные. Доступ к личной программе также требует исходную cookie браузера.

Логи и пересборка после изменения кода:

```sh
docker compose logs --tail=100 backend frontend init-db
docker compose up --build -d
```

Порты опубликованы только на 127.0.0.1. Конфигурация предназначена для локального HTTP, не для публичного размещения. Основная конфигурация Compose хранится в backend-репозитории; общий Git-репозиторий не создавался.

## Результат попытки запуска 20 ноября 2026

`docker compose config --quiet` прошёл. Docker Desktop 29.2.0 доступен, порты свободны. Сборка и отдельный повторный `docker pull python:3.12-slim` остановились на `TLS handshake timeout` к registry-1.docker.io. Базовых образов Python/Node в локальном кэше нет. На хосте registry отвечает, но Docker daemon не завершает TLS-соединение. Нужна проверка сети/VPN/proxy Docker Desktop, затем повтор `docker compose up --build -d`.

Контейнеры приложения не запущены; основной сценарий именно в Docker пока не проверен. Результаты прежней проверки вне Docker не заменяют эту проверку.

## Успешный запуск — 21 ноября 2026

После перезапуска Docker Desktop загрузка образов восстановилась. Исправлена конфигурация: backend-образ собирается только сервисом backend; init-db использует этот образ с pull_policy: never, без конкурирующей сборки под тем же именем.

`docker compose up --build -d` завершился успешно. Инициализация завершилась с кодом 0: 2 дня, 3 зала, 20 докладов. Оба сервиса прошли healthcheck.

Против контейнеров выполнен `REAL_API=1 npm run test:e2e -- tests/integration.spec.ts`: 1 passed. Проверены подробности доклада, выбор, конфликты, удаление, reload, cookie через proxy, идемпотентность, доклады встык и изоляция новой сессии.

Дополнительный браузерный сценарий подтвердил сохранение выбора после `docker compose up -d --no-deps --force-recreate backend` с тем же volume. Тестовый выбор после проверки удалён. Кратковременные ECONNREFUSED в логах frontend возникли во время намеренного пересоздания backend.

После пользовательской проверки контейнеры остановлены командой `docker compose down`; том с БД сохранён.
