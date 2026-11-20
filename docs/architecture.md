# Архитектура MVP

HTTP и зависимости — `app/api`; конфигурация и сборка приложения — `config.py`, `main.py`; ORM и соединения — `models.py`, `db.py`; сессии, выбор и конфликты — отдельные сервисы. Каталог не имеет публичных методов записи.

```mermaid
erDiagram
    conference_days ||--o{ talks : contains
    rooms ||--o{ talks : hosts
    speakers ||--o{ talks : presents
    anonymous_sessions ||--o{ selected_talks : owns
    talks ||--o{ selected_talks : selected
    conference_days {
        int id PK
        string label
        date date UK
        int sort_order
    }
    rooms {
        int id PK
        string name UK
        int sort_order
    }
    speakers {
        int id PK
        string name
        string bio
    }
    talks {
        int id PK
        int day_id FK
        int room_id FK
        int speaker_id FK
        string title
        string description
        string topic
        datetime starts_at
        datetime ends_at
    }
    anonymous_sessions {
        int id PK
        string token_hash UK
        datetime created_at
        datetime expires_at
    }
    selected_talks {
        int session_id PK,FK
        int talk_id PK,FK
        datetime created_at
    }
```

Все поля NOT NULL. Составной PK исключает дубликаты выбора, удаление сессии/доклада каскадирует выбор. Индексы покрывают FK (session_id — левый префикс PK) и starts_at. CHECK запрещает неположительную длительность. SQLite хранит naive UTC, TypeDecorator восстанавливает aware UTC; ORM-записи проверяют соответствие дня Москве. Seed валидирует день при формировании данных.

```mermaid
sequenceDiagram
    participant B as Браузер
    participant P as Next.js proxy
    participant A as FastAPI
    participant D as SQLite
    B->>P: GET /api/me/program
    P->>A: Cookie при наличии
    A->>D: Проверить hash и expires_at
    opt Нет действующей сессии
        A->>D: Создать сессию с hash, срок 30 дней
    end
    A-->>P: Program + Set-Cookie при создании + no-store
    P-->>B: Program + cookie
    B->>P: PUT /api/me/program/talks/1 + Origin
    P->>A: Cookie + Origin, без тела
    A->>A: Проверить Origin
    A->>D: Проверить сессию и наличие доклада
    A->>D: INSERT ON CONFLICT DO NOTHING, COMMIT
    A->>D: Прочитать текущий выбор
    A->>A: Сравнить пары интервалов O(n²)
    A-->>P: Program с конфликтами + no-store
    P-->>B: 200 Program
```

Транзакции запускаются явно. Read-транзакции проверки завершаются перед записью для предотвращения гонки повышения SQLite-блокировки. Вставка выбора атомарна и защищена уникальным ограничением; busy_timeout — 5000 мс. Read программы получает единый снимок списка. Приложение не создаёт схему на старте.

Технические справочники: [SQLAlchemy SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html), [FastAPI error handlers](https://fastapi.tiangolo.com/tutorial/handling-errors/).
