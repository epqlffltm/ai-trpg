# trpg-server/app/rounds/chapters.py

"""
라운드가 닫힐 때 장을 넘기는 것(#481, docs/architecture/chapters.md). 테이블의 지금 장은 app/tables/chapters.py 가 본다.

  - 라운드가 닫힐 때 퀘스트와 판의 사건을 본 뒤에 본다(app/rounds/service.py 의 begin_closing).
    이번 라운드에 이룬 퀘스트와 일어난 사건으로 넘어올 수 있다. 기한은 그 뒤에 본다.
  - 다음 장의 조건(when, match)을 지금의 상태로 맞춘다. 모양은 퀘스트의 조건과 같다(quest_goals.all_met).
    맞으면 그 장으로 넘어간다. 한 번에 한 장만 간다. 그 다음 장의 조건도 맞아도 다음 라운드에 간다. 뒤로 가지 않는다.
  - 넘어간 것은 이벤트(chapter_changed)로 남긴다. 행한 사람은 없다. 그 라운드의 서술이 받는다.

DB 를 모른다(이벤트를 적는 record 말고). 테이블의 지금 장만 고친다. 저장은 부른 쪽이 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import ChapterSnapshot, read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.rounds.quest_goals import all_met
from app.tables import chapters
from app.tables.models import GameTable, TableMonster, TableNpc


def chapter_ref(chapter: ChapterSnapshot | None) -> dict | None:
    """이벤트에 적는 장의 모양. id 와 이름이다."""
    return None if chapter is None else {'id': chapter.id, 'name': chapter.name}


def settle(table: GameTable, round_number: int, monsters: list[TableMonster], npcs: list[TableNpc]) -> dict | None:
    """
    다음 장의 조건이 맞으면 그 장으로 넘어간다. 넘어간 것을 이벤트에 적을 모양으로 돌려준다. 안 넘어가면 None.

    monsters 와 npcs 는 테이블의 상태 전부다(장면 밖도). 장이 없는 판이면 판을 읽지 않는다.
    """
    if table.chapter_id is None:
        return None
    snapshot = read_snapshot(table.content)
    following = chapters.following(table, snapshot)
    if following is None or not all_met(tuple(following.when), following.match, table, monsters, npcs):
        return None
    previous = chapters.current(table, snapshot)
    chapters.enter(table, following, round_number)
    return {
        'round': round_number,
        'from': chapter_ref(previous),
        'to': chapter_ref(following),
        'number': snapshot.chapters.index(following) + 1,
    }


def record(session: AsyncSession, table: GameTable, change: dict | None, group: uuid.UUID) -> None:
    """장이 넘어갔으면 이벤트를 적는다. 닫힘의 묶음(group)에 넣는다."""
    if change is not None:
        recorder.record(session, table, EventType.CHAPTER_CHANGED, payload=change, group=group)
