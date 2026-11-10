# trpg-server/app/rounds/chapters.py

"""
라운드가 닫힐 때 장을 넘기는 것(#481, docs/architecture/chapters.md). 테이블의 지금 장은 app/tables/chapters.py 가 본다.

  - 라운드가 닫힐 때 퀘스트와 판의 사건을 본 뒤에 본다(app/rounds/service.py 의 begin_closing).
    이번 라운드에 이룬 퀘스트와 일어난 사건으로 넘어올 수 있다. 기한은 그 뒤에 본다.
  - 다음에 갈 수 있는 장들(지금 장을 앞의 장으로 둔 장, #289 갈림길)의 조건(when, match)을 목록의 차례로 지금의 상태로
    맞춘다. 모양은 퀘스트의 조건과 같다(quest_goals.all_met). 처음 맞는 장으로 넘어간다(함께 맞으면 목록의 앞쪽).
    한 번에 한 장만 간다. 그 다음 장의 조건도 맞아도 다음 라운드에 간다. 뒤로 가지 않는다.
    고르지 않은 가지의 장은 그 테이블에서 다시 고를 수 없다(지금 장 다음만 보므로). 그 장이 여는 것은 닫힌 채다.
  - 넘어간 것은 이벤트(chapter_changed)로 남긴다. 행한 사람은 없다. 그 라운드의 서술이 받는다.
  - 넘어간 장이 여는 퀘스트(#481 ②-b) 가운데 진행 중으로 시작하는 것은 그때 드러난다(기한도 그때부터 센다).
    숨긴 채로 시작하는 것은 그 뒤로 제 드러나는 조건을 기다린다. 이루는 조건은 다음 라운드가 닫힐 때 본다.

DB 를 모른다(이벤트를 적는 record 말고). 테이블의 지금 장만 고친다. 저장은 부른 쪽이 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import ChapterSnapshot, Snapshot, read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.rounds import quest_goals
from app.rounds.quest_goals import all_met
from app.tables import chapters, quests
from app.tables.models import GameTable, QuestStatus, TableMonster, TableNpc

# 장이 열려 드러난 퀘스트의 까닭(quest_changed 의 reason)
CHAPTER_OPENED = 'chapter_opened'


def chapter_ref(chapter: ChapterSnapshot | None) -> dict | None:
    """이벤트에 적는 장의 모양. id 와 이름이다."""
    return None if chapter is None else {'id': chapter.id, 'name': chapter.name}


def open_quests(table: GameTable, snapshot: Snapshot, chapter: ChapterSnapshot) -> list[dict]:
    """
    그 장이 여는 퀘스트 가운데 진행 중으로 시작하는 것을 드러낸다. 판의 순서로, 이벤트에 적을 모양들을 돌려준다.

    시작할 때 숨겨 둔 것이다(app/tables/chapters.py 의 hold_back_quests). 이미 끝났거나 드러난 것은 그대로다.
    """
    catalog = quests.catalog(snapshot)
    opened = set(chapter.opens.quests)
    rows = [row for row in table.quests if row.entry_id in opened and row.status == QuestStatus.HIDDEN]
    held = [row for row in rows if catalog[row.entry_id].start == QuestStatus.ACTIVE]
    ordered = quests.in_catalog_order(held, catalog)
    return [quest_goals.show(table, row, catalog[row.entry_id], CHAPTER_OPENED) for row in ordered]


def next_chapter(
    table: GameTable, snapshot: Snapshot, monsters: list[TableMonster], npcs: list[TableNpc]
) -> ChapterSnapshot | None:
    """다음에 갈 수 있는 장 가운데 넘어오는 조건이 맞는 첫 장. 목록의 차례로 본다. 없으면 None."""
    return next(
        (
            chapter
            for chapter in chapters.candidates(table, snapshot)
            if all_met(tuple(chapter.when), chapter.match, table, monsters, npcs)
        ),
        None,
    )


def settle(
    table: GameTable, round_number: int, monsters: list[TableMonster], npcs: list[TableNpc]
) -> tuple[dict | None, list[dict]]:
    """
    다음에 갈 수 있는 장 가운데 조건이 맞는 첫 장으로 넘어간다. 넘어간 것과, 그 장이 열어 드러난 퀘스트들을
    이벤트에 적을 모양으로 돌려준다. 안 넘어가면 (None, []).

    number 는 몇째로 들어선 장인가(지나온 장의 수)다. 갈림길이 없으면 판의 장의 차례와 같다.

    monsters 와 npcs 는 테이블의 상태 전부다(장면 밖도). 장이 없는 판이면 판을 읽지 않는다.
    """
    if table.chapter_id is None:
        return None, []
    snapshot = read_snapshot(table.content)
    following = next_chapter(table, snapshot, monsters, npcs)
    if following is None:
        return None, []
    previous = chapters.current(table, snapshot)
    chapters.enter(table, following, round_number)
    change = {
        'round': round_number,
        'from': chapter_ref(previous),
        'to': chapter_ref(following),
        'number': chapters.number_of(table),
    }
    return change, open_quests(table, snapshot, following)


def record(session: AsyncSession, table: GameTable, settled: tuple[dict | None, list[dict]], group: uuid.UUID) -> None:
    """장이 넘어갔으면 이벤트를 적고, 그 장이 드러낸 퀘스트마다 quest_changed 를 잇는다. 닫힘의 묶음(group)에 넣는다."""
    change, revealed = settled
    if change is not None:
        recorder.record(session, table, EventType.CHAPTER_CHANGED, payload=change, group=group)
    quest_goals.record_changes(session, table, revealed, group)
