# trpg-server/app/tables/chapters.py

"""
테이블의 지금 장(#481, docs/architecture/chapters.md)과 갈림길(#289).
판의 장(Snapshot.chapters)과 테이블의 칸(chapter_id, chapter_round, chapter_path)을 본다.

  - 장이 있는 판은 첫 장에서 시작한다(start). 장이 없는 판은 지금 장이 없다.
  - 장마다 어느 장 다음에 올 수 있는지(after)가 있다. 비우면 목록에서 바로 앞의 장 다음이다(predecessors).
    after 는 목록에서 앞의 장만 가리키므로 장은 늘 앞으로만 간다.
  - 지나온 장(passed)은 첫 장부터 지금 장까지 들어선 장들이다. 고르지 않은 가지의 장은 들지 않는다.
    이 칸(chapter_path)이 생기기 전에 시작한 테이블은 판의 첫 장부터 지금 장까지로 본다(그때는 장이 한 줄이었다).
  - 다음에 갈 수 있는 장(candidates)은 지금 장을 앞의 장으로 둔 장들이다. 목록의 차례로 본다.
    넘기는 것은 엔진이다(app/rounds/chapters.py). 모델과 방장은 넘기지 못한다.
  - 지금 장이 어느 장 이상인지(at_least)는 그 장을 지나왔는가다. 조건 chapter_at_least 가 쓴다
    (app/rounds/quest_goals.py). 판을 읽지 않고 테이블의 판 문서에서 장만 꺼낸다.
  - 열림(#481 ②-b): 지나오지 않은 장이 여는 장소와 퀘스트는 닫혀 있다(locked_ids). 뒤의 장과, 고르지 않은 가지의 장이다.
    어느 장에도 적지 않은 것과 지나온 장이 연 것은 열려 있다. 장은 앞으로만 가므로 한 번 열린 것은 닫히지 않는다.
    닫힌 장소는 지도에 없고 갈 수 없고 찾을 수 없다(app/tables/places.py). 닫힌 퀘스트는 드러나지도 이루지도 않는다
    (app/rounds/quest_goals.py). 서술의 로어 검색에도 들지 않는다(app/lore/retrieval.py).

DB 를 모른다. 테이블의 칸만 고친다.
"""

import uuid

from app.assets.scenarios.snapshot import ChapterSnapshot, Snapshot
from app.tables.models import GameTable, QuestStatus


def start(table: GameTable, snapshot: Snapshot) -> None:
    """장이 있는 판이면 첫 장에서 시작한다. 장이 없으면 아무것도 하지 않는다."""
    if snapshot.chapters:
        table.chapter_id = snapshot.chapters[0].id
        table.chapter_round = None
        table.chapter_path = [snapshot.chapters[0].id]


def documents(table: GameTable) -> list[dict]:
    """테이블의 판 문서에 있는 장들. 장의 차례다. 장이 없는 판이면 빈 목록이다."""
    return list(table.content.get('chapters') or [])


def order(table: GameTable) -> list[str]:
    """판의 장의 id 들. 장의 차례다. 장이 없는 판이면 빈 목록이다."""
    return [chapter['id'] for chapter in documents(table)]


def predecessors(ids: list[str], position: int, after: list[str]) -> list[str]:
    """목록의 그 자리의 장이 어느 장 다음에 올 수 있는가. after 를 비웠으면 바로 앞의 장이다. 첫 장은 없다."""
    if after:
        return list(after)
    return [ids[position - 1]] if position > 0 else []


def passed(table: GameTable) -> list[str]:
    """
    지나온 장들. 첫 장부터 지금 장까지 들어선 차례다. 지금 장이 없으면 빈 목록이다.

    지나온 장을 적기 전에 시작한 테이블은 판의 첫 장부터 지금 장까지다(그때는 장이 한 줄이었다).
    """
    if table.chapter_path:
        return list(table.chapter_path)
    ids = order(table)
    if table.chapter_id not in ids:
        return []
    return ids[: ids.index(table.chapter_id) + 1]


def number_of(table: GameTable) -> int:
    """지금 장이 몇째로 들어선 장인가(1 부터). 지나온 장의 수다. 지금 장이 없으면 0."""
    return len(passed(table))


def longest(snapshot: Snapshot) -> int:
    """
    첫 장에서 가장 많은 장을 지나는 길의 장의 수. 갈림길이 없으면 장의 수와 같다.

    after 는 앞의 장만 가리키므로 목록의 차례로 한 번 훑으면 된다. 첫 장에서 닿지 않는 장은 세지 않는다.
    """
    ids = [chapter.id for chapter in snapshot.chapters]
    depth: dict[str, int] = {}
    for position, chapter in enumerate(snapshot.chapters):
        before = [depth[one] for one in predecessors(ids, position, chapter.after) if one in depth]
        if position == 0:
            depth[chapter.id] = 1
        elif before:
            depth[chapter.id] = max(before) + 1
    return max(depth.values(), default=0)


def at_least(table: GameTable, chapter_id: str) -> bool:
    """그 장을 지나왔는가(지금 장이 그 장이거나 그 뒤인가). 고르지 않은 가지의 장이면 아니다."""
    return chapter_id in passed(table)


def current(table: GameTable, snapshot: Snapshot) -> ChapterSnapshot | None:
    """지금 장. 지금 장이 없으면 None."""
    return next((chapter for chapter in snapshot.chapters if chapter.id == table.chapter_id), None)


def candidates(table: GameTable, snapshot: Snapshot) -> list[ChapterSnapshot]:
    """
    지금 장 다음에 갈 수 있는 장들. 지금 장을 앞의 장으로 둔 장이고, 목록의 차례다.

    지금 장이 없거나 갈 장이 없으면(마지막 장, 갈림길의 끝) 빈 목록이다.
    """
    if table.chapter_id is None:
        return []
    ids = [chapter.id for chapter in snapshot.chapters]
    return [
        chapter
        for position, chapter in enumerate(snapshot.chapters)
        if table.chapter_id in predecessors(ids, position, chapter.after)
    ]


def enter(table: GameTable, chapter: ChapterSnapshot, round_number: int) -> None:
    """그 장으로 넘어간다. 넘어온 라운드를 적고 지나온 장에 더한다."""
    table.chapter_path = [*passed(table), chapter.id]
    table.chapter_id = chapter.id
    table.chapter_round = round_number


# --- 열림(#481 ②-b) ---


def locked_ids(table: GameTable) -> frozenset[uuid.UUID]:
    """
    아직 열리지 않은 장소와 퀘스트(사건 항목)들. 지나오지 않은 장이 여는 것이다(뒤의 장, 고르지 않은 가지의 장).

    지금 장이 없으면(장이 없는 판, 장이 생기기 전에 시작한 테이블) 아무것도 막지 않는다.
    판을 읽지 않고 테이블의 판 문서에서 장의 여는 것만 꺼낸다. 길을 볼 때마다 판 전체를 읽지 않게 한다.
    """
    done = set(passed(table))
    if not done:
        return frozenset()
    opens = [chapter.get('opens') or {} for chapter in documents(table) if chapter['id'] not in done]
    ids = [one for opened in opens for one in [*opened.get('places', []), *opened.get('quests', [])]]
    return frozenset(uuid.UUID(one) for one in ids)


def hold_back_quests(table: GameTable) -> None:
    """
    시작할 때, 뒤의 장이 여는 퀘스트가 진행 중으로 시작하면 숨긴 채로 둔다. 기한도 아직 세지 않는다.

    그 장이 열릴 때 드러난다(app/rounds/chapters.py 의 open_quests). 고르지 않은 가지의 것은 끝내 숨은 채다.
    """
    locked = locked_ids(table)
    for row in table.quests:
        if row.entry_id in locked and row.status == QuestStatus.ACTIVE:
            row.status = QuestStatus.HIDDEN
            row.due_at = None
