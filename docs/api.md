# API v1: использование

Нормативный источник: [backend-spec.md](backend-spec.md). Контракт не изменён. Схема доступна по `/openapi.json`, интерактивное описание — `/docs`.

| Метод | Путь | Результат |
| --- | --- | --- |
| GET | /api/health | `{ "status": "ok", "database": "ok" }`, 503 при недоступной БД |
| GET | /api/conference | Название, demo notice, timezone, упорядоченные дни и залы |
| GET | /api/talks?day_id=1&room_id=1 | `{ "items": [...], "total": 4 }` |
| GET | /api/talks/1 | Полный Talk; 404 для неизвестного ID |
| GET | /api/me/program | Program, создаёт cookie при отсутствии действующей сессии |
| PUT | /api/me/program/talks/1 | Program после идемпотентного добавления |
| DELETE | /api/me/program/talks/1 | 204 без тела, включая повторное удаление |

ID положительные целые. Неизвестный положительный фильтр возвращает пустой список. Доклады сортируются по starts_at, room.sort_order, id; время — UTC с `Z`. На клиенте его нужно переводить в Europe/Moscow. Все поля типов обязательны, `null` не используется. Биография может быть пустой строкой.

Пустая программа:

```json
{"talks":[],"conflicts":[],"selected_count":0,"conflicting_talk_count":0}
```

После выбора seed-докладов 1 и 2 массив conflicts:

```json
[
  {"talk_id":1,"conflicting_talk_ids":[2]},
  {"talk_id":2,"conflicting_talk_ids":[1]}
]
```

Оба счётчика равны 2. Для 1 и 5 конфликт отсутствует: интервалы примыкают. Для 1 и 11 конфликта нет: разные дни. Связи рассчитываются только среди выбранных, симметричны и отсортированы. Время сравнивается как UTC datetime строгими неравенствами.

Пример ошибки:

```json
{"error":{"code":"TALK_NOT_FOUND","message":"Доклад не найден","details":[]}}
```

422 имеет код `VALIDATION_ERROR`, details с полем и безопасным сообщением; 403 — `ORIGIN_NOT_ALLOWED`; 500 — `INTERNAL_ERROR`. Исходные значения и traceback не попадают в ответ.

PUT/DELETE отправляются без тела с разрешённым `Origin`. Сессия определяется только cookie, никогда URL, телом или session_id. Все ответы `/api/me/*`, включая ошибки, имеют `Cache-Control: no-store`. Примеры curl и настройка Swagger находятся в [README](../README.md).
