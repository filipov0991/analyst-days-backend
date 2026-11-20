from itertools import combinations

from app.models import Talk
from app.schemas import Conflict


def find_conflicts(talks: list[Talk]) -> list[Conflict]:
    links: dict[int, set[int]] = {}
    for a, b in combinations(talks, 2):
        if a.id != b.id and a.starts_at < b.ends_at and b.starts_at < a.ends_at:
            links.setdefault(a.id, set()).add(b.id)
            links.setdefault(b.id, set()).add(a.id)
    return [Conflict(talk_id=id_, conflicting_talk_ids=sorted(ids)) for id_, ids in sorted(links.items())]
