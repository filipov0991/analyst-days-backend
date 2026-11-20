"""All illustrative conference dates and scheduling fixtures live here."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.sqlite import insert

from app.config import Settings
from app.db import build_engine, init_db, session_factory
from app.models import ConferenceDay, Room, Speaker, Talk

DEMO_DATES = (date(2030, 1, 1), date(2030, 1, 2))
MOSCOW = ZoneInfo("Europe/Moscow")
# Each day: full (1/2), partial (1/4), nested (1/3), adjacent (1/5), break.
SLOTS = (
    (1, "10:00", "11:00"), (2, "10:00", "11:00"),
    (3, "10:15", "10:45"), (3, "10:45", "11:30"),
    (1, "11:00", "11:45"), (2, "11:15", "12:00"),
    (1, "13:00", "14:00"), (2, "13:00", "13:45"),
    (3, "13:30", "14:15"), (1, "14:00", "14:45"),
)
TITLES = (
    ("Как выявлять скрытые требования", "Требования"),
    ("API-контракт как язык команды", "API"),
    ("Короткое интервью: важные вопросы", "Анализ"),
    ("Данные и границы ответственности", "Данные"),
    ("Моделирование бизнес-процессов", "Анализ"),
    ("Архитектурные решения без догадок", "Архитектура"),
    ("Проверяемые нефункциональные требования", "Требования"),
    ("Версионирование API на практике", "API"),
    ("ИИ-помощник и проверка гипотез", "ИИ"),
    ("Качество данных начинается с вопросов", "Данные"),
    ("Карта заинтересованных сторон", "Анализ"),
    ("Событийные интеграции для аналитика", "Архитектура"),
    ("Критерии приёмки без двусмысленности", "Требования"),
    ("Модель данных от сценария к схеме", "Данные"),
    ("Ошибки API как часть контракта", "API"),
    ("Проверка ответов языковых моделей", "ИИ"),
    ("Как договориться о границах системы", "Архитектура"),
    ("Метрики полезности требований", "Требования"),
    ("Эксперименты с поиском по знаниям", "ИИ"),
    ("От наблюдения к продуктовой гипотезе", "Анализ"),
)


def seed(engine):
    init_db(engine)
    with session_factory(engine).begin() as db:
        for id_, day in enumerate(DEMO_DATES, 1):
            db.execute(insert(ConferenceDay).values(id=id_, label=f"День {id_}", date=day, sort_order=id_)
                       .on_conflict_do_nothing(index_elements=["id"]))
        for id_ in range(1, 4):
            db.execute(insert(Room).values(id=id_, name=f"Зал {id_}", sort_order=id_)
                       .on_conflict_do_nothing(index_elements=["id"]))
        for id_, (title, topic) in enumerate(TITLES, 1):
            day_index = (id_ - 1) // len(SLOTS)
            room_id, start, end = SLOTS[(id_ - 1) % len(SLOTS)]
            starts_at = datetime.combine(DEMO_DATES[day_index], datetime.strptime(start, "%H:%M").time(), MOSCOW)
            ends_at = datetime.combine(DEMO_DATES[day_index], datetime.strptime(end, "%H:%M").time(), MOSCOW)
            assert starts_at.astimezone(MOSCOW).date() == DEMO_DATES[day_index]
            db.execute(insert(Speaker).values(id=id_, name=f"Демо-спикер {id_:02d}",
                       bio="Вымышленный участник демонстрационной программы.")
                       .on_conflict_do_nothing(index_elements=["id"]))
            db.execute(insert(Talk).values(id=id_, day_id=day_index + 1, room_id=room_id, speaker_id=id_,
                       title=title, topic=topic,
                       description=f"{title}. Разберём учебный пример, обсудим подходы и типичные ошибки. Все примеры и участники вымышлены.",
                       starts_at=starts_at, ends_at=ends_at).on_conflict_do_nothing(index_elements=["id"]))


if __name__ == "__main__":
    engine = build_engine(Settings().database_url)
    seed(engine)
    engine.dispose()
    print("Demo seed ready: 2 days, 3 rooms, 20 talks.")
