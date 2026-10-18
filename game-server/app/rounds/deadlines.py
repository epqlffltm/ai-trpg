# game-server/app/rounds/deadlines.py

"""
라운드가 닫힐 때 기한을 넘긴 퀘스트를 실패로 바꾼다(app/rounds/service.py 의 begin_closing).

기한을 판정하는 것은 서버뿐이다. 방장도 AI 도 이 판정을 하지 않는다.
그 전에 엔진이 조건을 보고 성공으로(app/rounds/quest_goals.py), 방장이 실패로 끝낼 수 있다.
  - 넘긴 것: 진행 중이고, 기한이 이 라운드가 열린 시각이나 그 앞에 끝났다(app/tables/quests.py 의 is_overdue).
    기한이 장면 안에서 끝나면 다음 라운드 하나 동안은 그대로다. 그 라운드에 조건을 채우면 성공이다.
  - 이미 끝난 것(같은 라운드에 조건을 채워 성공한 것)은 진행 중이 아니므로 건드리지 않는다.
  - 실패에는 보상이 없다. 사람이 한 일이 아니므로 누가 했는지는 비우고 까닭(deadline)을 적는다.

DB 를 모른다. 잠근 테이블의 퀘스트 행을 고치고 이벤트에 적을 모양을 돌려준다. 이벤트를 적는 것은 record_failures 다.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.tables import quests
from app.tables.models import GameTable, QuestStatus, TableQuest
from app.tables.quest_changes import describe
from app.tables.quests import CatalogQuest

# 서버가 퀘스트를 바꾼 까닭. 이벤트의 reason 에 적는다
DEADLINE = 'deadline'


def fail(row: TableQuest, quest: CatalogQuest) -> dict:
    """기한을 넘긴 퀘스트 하나를 실패로 바꾼다. 이벤트에 적을 모양을 돌려준다."""
    previous = row.status
    row.status = QuestStatus.FAILED
    row.changed_at = func.now()
    return describe(quest, previous, QuestStatus.FAILED, [], row.due_at, reason=DEADLINE)


def expire_quests(table: GameTable) -> list[dict]:
    """
    기한을 넘긴 퀘스트를 모두 실패로 바꾼다. 판의 순서로, 이벤트에 적을 모양들을 돌려준다.

    지금 시계는 이 라운드가 열린 시각이다. 시간은 다음 라운드가 열릴 때 흐른다(app/rounds/opener.py).
    넘긴 것이 하나도 없으면 판을 읽지 않는다. 판에 굳은 복사본을 통째로 읽는 일이라 싸지 않다.
    """
    overdue = quests.overdue_quests(table, table.clock.minutes)
    if not overdue:
        return []
    catalog = quests.catalog(read_snapshot(table.content))
    return [fail(row, catalog[row.entry_id]) for row in quests.in_catalog_order(overdue, catalog)]


def record_failures(session: AsyncSession, table: GameTable, failures: list[dict], group: uuid.UUID) -> None:
    """기한을 넘겨 실패한 퀘스트마다 이벤트를 적는다. 닫힘의 묶음(group)에 넣는다."""
    for payload in failures:
        recorder.record(session, table, EventType.QUEST_CHANGED, payload=payload, group=group)
