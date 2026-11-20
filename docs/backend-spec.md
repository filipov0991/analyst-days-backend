# ТЗ бэкенда — Analyst Days: моя программа

## Задание
Прочитать docs/context-v0.md. Реализовать самостоятельный локальный сервис в analyst-days-backend. Не менять frontend-репозиторий. Довести реализацию до запуска, тестов и документов, не останавливаться на плане.

## Стек и структура
Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, SQLite, pytest. Закрепить совместимые стабильные зависимости и способ их воспроизводимой установки.
Рекомендуемая структура: app/main.py, app/config.py, app/db.py, app/models.py, app/schemas.py, app/api/, app/services/, app/seed.py, tests/, docs/.
Отделить HTTP-обработчики, работу с сессией, расчёт конфликтов и доступ к данным. Избегать лишних абстракций.

## Модель данных
| Таблица | Поля |
|---|---|
| conference_days | id PK, label, date UNIQUE, sort_order |
| rooms | id PK, name UNIQUE, sort_order |
| speakers | id PK, name, bio |
| talks | id PK, day_id FK, room_id FK, speaker_id FK, title, description, topic, starts_at, ends_at |
| anonymous_sessions | id PK, token_hash UNIQUE, created_at, expires_at |
| selected_talks | session_id FK, talk_id FK, created_at; составной PK(session_id, talk_id) |

Поля обязательны; bio может быть пустой строкой. Индексировать внешние ключи и starts_at. Включить PRAGMA foreign_keys для каждого соединения. Добавить CHECK ends_at > starts_at. При удалении сессии или доклада удалять связанные selected_talks каскадно.
SQLite не хранит timezone как отдельный тип: сохранять нормализованные UTC-значения, на границе приложения восстанавливать UTC и сериализовать RFC3339 с Z; протестировать round-trip. День доклада должен совпадать с conference_days.date после преобразования в Europe/Moscow.
Создание схемы для MVP допустимо через отдельную команду init-db. Обычный старт не должен сбрасывать данные. Настроить транзакции, busy_timeout и безопасное разрешение гонки повторного добавления через уникальное ограничение.

## Seed
Одна команда создаёт схему при необходимости и заполняет 2 дня, 3 зала, 20 докладов с вымышленными спикерами. Даты — из контекста. Детерминированные ID и идемпотентная вставка. Повторный запуск не очищает таблицы, не перезаписывает пользовательский выбор и не создаёт дубликаты. Не размещать два перекрывающихся доклада в одном зале; конфликты seed показывать между разными залами.

## Анонимная сессия и безопасность
Генерировать токен secrets.token_urlsafe(32), в БД хранить только SHA-256. Не логировать токены, Cookie и содержимое персональных программ. По токену выбирать только текущую сессию. Недействительная/просроченная cookie создаёт новую сессию. Проверять срок на каждом персональном запросе.
Сессионный токен не принимать из тела или URL. Все запросы к выбору ограничиваются текущей сессией. Не открывать CORS для всех origin с credentials. Для same-origin proxy CORS не требуется. Проверка Origin определена контрактом ниже.
500 не раскрывает traceback клиенту; диагностика остаётся на сервере без секретов. Ошибки валидации FastAPI привести к общему формату.

## Расчёт конфликтов
Для максимум 20 выбранных докладов достаточно сравнения каждой пары O(n²). Использовать строгое неравенство границ, сравнивать UTC datetime, не строки без нормализации. Расчёт выполнять при чтении программы и после добавления; конфликты отдельно в БД не хранить.

## Общий контракт API v1

Этот раздел одинаков в двух ТЗ. Имена полей, nullable-поля и формы ответов менять только согласованно.
Все пути начинаются с `/api`. JSON — UTF-8; ID — положительные целые числа. Время — RFC 3339 с обязательным смещением; backend возвращает UTC (`Z`), frontend отображает Europe/Moscow. Для валидации использовать явные response-модели.

### Типы
```typescript
type Day = { id: number; label: string; date: string; sort_order: number };
type Room = { id: number; name: string; sort_order: number };
type Speaker = { id: number; name: string; bio: string };
type Talk = {
  id: number;
  day_id: number;
  title: string;
  description: string;
  topic: string;
  starts_at: string;
  ends_at: string;
  room: Room;
  speaker: Speaker;
};
type Conference = {
  name: string;
  timezone: "Europe/Moscow";
  is_demo: boolean;
  demo_notice: string;
  days: Day[];
  rooms: Room[];
};
type Conflict = { talk_id: number; conflicting_talk_ids: number[] };
type Program = {
  talks: Talk[];
  conflicts: Conflict[];
  selected_count: number;
  conflicting_talk_count: number;
};
type ApiError = {
  error: {
    code: string;
    message: string;
    details: { field: string; message: string }[];
  };
};
```
Все перечисленные поля обязательны, null не используется. Необязательная биография — пустая строка. Пустые коллекции — `[]`.
`Talk` одинаков в списке, подробностях и личной программе; для 20 докладов отдельная сокращённая схема не требуется.

### Методы и ответы
| Метод | Параметры / тело | Успех | Ошибки |
|---|---|---|---|
| GET /api/health | Нет | 200 `{ "status": "ok", "database": "ok" }` | 503 HEALTH_UNAVAILABLE |
| GET /api/conference | Нет | 200 Conference | 500 INTERNAL_ERROR |
| GET /api/talks | Query: необязательные day_id и room_id, целые > 0 | 200 `{ "items": Talk[], "total": number }` | 422 VALIDATION_ERROR |
| GET /api/talks/{talk_id} | Целое > 0 | 200 Talk | 404 TALK_NOT_FOUND, 422 VALIDATION_ERROR |
| GET /api/me/program | Нет | 200 Program | 500 INTERNAL_ERROR |
| PUT /api/me/program/talks/{talk_id} | Целое > 0, без тела | 200 Program после добавления | 404 TALK_NOT_FOUND, 422 VALIDATION_ERROR, 403 ORIGIN_NOT_ALLOWED |
| DELETE /api/me/program/talks/{talk_id} | Целое > 0, без тела | 204, без тела | 422 VALIDATION_ERROR, 403 ORIGIN_NOT_ALLOWED |

Все внутренние ошибки имеют единый формат ApiError. `details` обычно пустой; при 422 содержит безопасные сведения о неверных полях без исходных секретных значений.
Пример 404:
```json
{"error":{"code":"TALK_NOT_FOUND","message":"Доклад не найден","details":[]}}
```
GET /talks для неизвестного положительного day_id или room_id возвращает пустую коллекцию, не 404. `total` — число элементов после фильтрации; пагинации нет.
DELETE возвращает 204 даже если доклада или выбора уже нет. PUT идемпотентен и возвращает актуальную программу при повторе.

### Порядок и конфликты
`days` и `rooms` сортируются по sort_order, затем id. Доклады — starts_at, room.sort_order, id.
`conflicts` содержит только выбранные доклады с конфликтами. Связь симметрична: для A/B присутствуют записи A→B и B→A. ID внутри списка уникальны и отсортированы. Сами записи сортируются по talk_id.
`selected_count = talks.length`; `conflicting_talk_count` — число уникальных докладов, участвующих хотя бы в одном конфликте, а не число пар.
Пустая программа:
```json
{"talks":[],"conflicts":[],"selected_count":0,"conflicting_talk_count":0}
```

### Сессия и транспорт
GET /me/program, PUT и DELETE создают анонимную сессию, если действующей нет. Инициализацию frontend выполняет одним GET /me/program до разрешения кнопок изменения, чтобы не создавать несколько сессий конкурентными первыми запросами.
Backend устанавливает cookie `ad_session`: HttpOnly, SameSite=Lax, Path=/, Max-Age=2592000; Secure по окружению, без Domain. Истечение в БД — фиксированные 30 дней с создания. Не продлевать срок неявно.
Клиент не читает токен и не передаёт session_id. Запросы same-origin `/api/*`, credentials: `same-origin`, cache: `no-store`. Next.js proxy должен передавать Cookie и Set-Cookie.
Все ответы /me/*: Cache-Control: no-store. Origin для PUT/DELETE обязателен и должен совпадать с ALLOWED_ORIGINS, иначе 403. Swagger и curl для мутаций должны отправлять разрешённый Origin явно; это описать в README.

## Запуск и конфигурация
.env.example:
```dotenv
DATABASE_URL=sqlite:///./data/app.db
APP_ENV=development
COOKIE_SECURE=false
ALLOWED_ORIGINS=http://localhost:3000
```
Описать создание venv, установку, init/seed, запуск uvicorn app.main:app --reload --port 8000, тесты. Конкретные команды должны соответствовать реализации. Для production отключить reload. /docs и /openapi.json доступны непосредственно на backend.
Добавить Dockerfile, .dockerignore, .gitignore; не коммитить .env, data/, .venv/, кэш и секреты. Для будущего контейнера описать DATABASE_URL=sqlite:////data/app.db и постоянный том /data. Docker не обязателен для локального запуска. Health проверяет SELECT 1; при недоступной БД возвращает 503 в общем формате.

## Проверки
pytest с отдельной временной БД и отдельными cookie-клиентами:
- Получение программы и фильтры; неизвестный фильтр даёт пустой список.
- Детали существующего/несуществующего доклада, ошибки 422 в согласованном формате.
- Добавление, повторное добавление, удаление, повторное удаление.
- Разные сессии изолированы; чужой выбор нельзя получить подменой параметров.
- Отсутствующая, неверная и просроченная cookie.
- Частичное/полное/вложенное пересечение, несколько конфликтов, доклады встык и разные дни.
- Симметрия конфликтов, счётчики, исчезновение конфликта после удаления.
- Повторный seed сохраняет выбор и не создаёт дубликаты.
- Сохранение после пересоздания приложения с тем же файлом БД.
- Проверка Origin и атрибутов cookie; сериализация времени с часовым поясом.
Проверить реальный /docs и соответствие OpenAPI контракту.

## Материалы и завершение
Подготовить ERD и Sequence в Mermaid, описание API, README, отчёт тестов, context-v1 с фактическими изменениями, реальные промпты, сценарий видео и чек-лист сдачи согласно контексту. Не придумывать успешные результаты.
В финальном отчёте: реализованное, команды запуска, фактические результаты тестов, ограничения и что требуется для размещения. Не публиковать сервис на этом этапе.
