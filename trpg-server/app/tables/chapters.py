# trpg-server/app/tables/chapters.py

"""
테이블의 지금 장(#481, docs/architecture/chapters.md).
판의 장(Snapshot.chapters)과 테이블의 칸(chapter_id, chapter_round)을 본다.

  - 장이 있는 판은 첫 장에서 시작한다(start). 장이 없는 판은 지금 장이 없다.
  - 장은 앞으로만, 한 번에 한 장씩 간다(enter). 넘기는 것은 엔진이다(app/rounds/chapters.py).
    모델과 방장은 넘기지 못한다.
  - 지금 장이 어느 장 이상인지(at_least)는 조건 chapter_at_least 가 쓴다(app/rounds/quest_goals.py).
    판을 읽지 않고 테이블의 판 문서에서 장의 차례만 꺼낸다. 조건 하나를 맞출 때마다 판 전체를 읽지 않게 한다.

DB 를 모른다. 테이블의 칸만 고친다.
"""

from app.assets.scenarios.snapshot import ChapterSnapshot, Snapshot
from app.tables.models import GameTable


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
