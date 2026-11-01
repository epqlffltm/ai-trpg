# trpg-server/app/tables/chapters.py

"""
테이블의 지금 장(#481, docs/architecture/chapters.md).
판의 장(Snapshot.chapters)과 테이블의 칸(chapter_id, chapter_round)을 본다.

  - 장이 있는 판은 첫 장에서 시작한다(start). 장이 없는 판은 지금 장이 없다.
  - 장은 앞으로만, 한 번에 한 장씩 간다(enter). 넘기는 것은 엔진이다(app/rounds/chapters.py).
    모델과 방장은 넘기지 못한다.
  - 지금 장이 어느 장 이상인지(at_least)는 조건 chapter_at_least 가 쓴다(app/rounds/quest_goals.py).
    판을 읽지 않고 테이블의 판 문서에서 장의 차례만 꺼낸다. 조건 하나를 맞출 때마다 판 전체를 읽지 않게 한다.
  - 열림(#481 ②-b): 지금 장 뒤의 장이 여는 장소와 퀘스트는 아직 닫혀 있다(locked_ids). 어느 장에도 적지 않은 것과
    지금 장까지 연 것은 열려 있다. 장은 앞으로만 가므로 한 번 열린 것은 닫히지 않는다.
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


def order(table: GameTable) -> list[str]:
    """판의 장의 id 들. 장의 차례다. 장이 없는 판이면 빈 목록이다."""
    return [chapter['id'] for chapter in table.content.get('chapters') or []]


def index_of(table: GameTable) -> int | None:
    """지금 장이 몇째인가(0 부터). 지금 장이 없으면 None."""
    chapters = order(table)
    return chapters.index(table.chapter_id) if table.chapter_id in chapters else None


def at_least(table: GameTable, chapter_id: str) -> bool:
    """지금 장이 그 장이거나 그 뒤인가. 지금 장이 없거나 판에 없는 장이면 아니다."""
    chapters = order(table)
    current = index_of(table)
    return current is not None and chapter_id in chapters and current >= chapters.index(chapter_id)


def current(table: GameTable, snapshot: Snapshot) -> ChapterSnapshot | None:
    """지금 장. 지금 장이 없으면 None."""
    return next((chapter for chapter in snapshot.chapters if chapter.id == table.chapter_id), None)


def following(table: GameTable, snapshot: Snapshot) -> ChapterSnapshot | None:
    """지금 장 다음의 장. 지금 장이 없거나 마지막 장이면 None."""
    position = index_of(table)
    if position is None or position + 1 >= len(snapshot.chapters):
        return None
    return snapshot.chapters[position + 1]


def enter(table: GameTable, chapter: ChapterSnapshot, round_number: int) -> None:
    """그 장으로 넘어간다. 넘어온 라운드를 적는다."""
    table.chapter_id = chapter.id
    table.chapter_round = round_number


# --- 열림(#481 ②-b) ---


def locked_ids(table: GameTable) -> frozenset[uuid.UUID]:
    """
    아직 열리지 않은 장소와 퀘스트(사건 항목)들. 지금 장 뒤의 장이 여는 것이다.

    지금 장이 없으면(장이 없는 판, 장이 생기기 전에 시작한 테이블) 아무것도 막지 않는다.
    판을 읽지 않고 테이블의 판 문서에서 장의 여는 것만 꺼낸다. 길을 볼 때마다 판 전체를 읽지 않게 한다.
    """
    position = index_of(table)
    if position is None:
        return frozenset()
    later = (table.content.get('chapters') or [])[position + 1 :]
    opens = [chapter.get('opens') or {} for chapter in later]
    ids = [one for opened in opens for one in [*opened.get('places', []), *opened.get('quests', [])]]
    return frozenset(uuid.UUID(one) for one in ids)


def hold_back_quests(table: GameTable) -> None:
    """
    시작할 때, 뒤의 장이 여는 퀘스트가 진행 중으로 시작하면 숨긴 채로 둔다. 기한도 아직 세지 않는다.

    그 장이 열릴 때 드러난다(app/rounds/chapters.py 의 open_quests).
    """
    locked = locked_ids(table)
    for row in table.quests:
        if row.entry_id in locked and row.status == QuestStatus.ACTIVE:
            row.status = QuestStatus.HIDDEN
            row.due_at = None
