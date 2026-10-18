# game-server/app/tables/quest_changes.py

"""
방장이 퀘스트의 상태를 바꾼다. 드러내고(진행 중), 실패로 끝낸다.

AI GM 은 퀘스트를 바꾸지 못한다. 서술에서 "왕녀를 구했다"고 해도 퀘스트는 그대로다.
성공은 사람도 정하지 않는다. 판의 조건을 라운드가 닫힐 때 엔진이 보고 정한다(app/rounds/quest_goals.py, #367).
방장은 PC 라서 자기 일행에게 유리하게 결과를 정하면 안 된다. 드러내기와 실패는 대체가 들어오기 전까지 방장이 한다.

  - 진행 중인 테이블에서만 한다. 퀘스트는 시작할 때 만든다.
  - 판의 퀘스트(로어북의 사건 항목)만 다룬다.
  - 성공으로 바꾸려 하면 거절한다(quest_success_by_engine).
  - 드러내면(진행 중) 판의 기한으로 끝나는 시각을 적는다. 이 라운드가 열린 시각부터 센다.
  - 바꾼 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다. 숨김에서 나온 것만 적으므로 숨긴 것은 새지 않는다.

HTTP 를 모른다. 테이블을 잠그고 한다. 두 요청이 같은 퀘스트를 동시에 바꿔도 하나씩 차례로 한다.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.calendar import clock
from app.events import recorder
from app.events.models import EventType
from app.tables import quests
from app.tables.item_grants import require_playing
from app.tables.models import GameTable, QuestStatus
from app.tables.quests import CatalogQuest
from app.tables.service import lock_seated, save
from app.tables.state import require_host


def due_at_document(minutes: int | None) -> dict | None:
    """기한이 끝나는 시각을 이벤트에 적을 모양(며칠째 몇 시). 기한이 없으면 None."""
    return None if minutes is None else clock.as_document(minutes)


def describe(
    quest: CatalogQuest,
    previous: str,
    status: QuestStatus,
    rewards: list[dict],
    due_at: int | None,
    reason: str | None = None,
) -> dict:
    """
    바꾼 것을 이벤트에 적을 모양. 무엇이, 무엇에서 무엇으로, 누가 무엇을 받았는가, 기한은 언제 끝나는가.

    reason 은 사람이 아니라 서버가 바꾼 까닭이다(기한을 넘김, app/rounds/deadlines.py). 사람이 바꿨으면 None.
    """
    return {
        'entry_id': str(quest.entry_id),
        'name': quest.name,
        'previous': previous,
        'status': status,
        'rewards': rewards,
        'due_at': due_at_document(due_at),
        'reason': reason,
    }


def apply_change(
    session: AsyncSession, table: GameTable, entry_id: uuid.UUID, status: QuestStatus, actor_id: uuid.UUID
) -> None:
    """
    잠근 테이블의 퀘스트 하나를 드러내거나 실패로 바꾸고 이벤트를 적는다. 저장하지 않는다.

    방장이 바꿀 때(change_quest)와 방장이 장부 초안을 받아들일 때(app/drafts/decisions.py)가 같이 쓴다.
    성공으로는 바꾸지 못한다(quest_success_by_engine). 성공과 보상은 엔진이 준다(app/rounds/quest_goals.py).
    이 테이블의 퀘스트가 아니면 TableOptionError, 바꿀 수 없는 상태면 TableConflictError.
    """
    snapshot = read_snapshot(table.content)
    row, quest = quests.require_quest(table, quests.catalog(snapshot), entry_id)
    previous = row.status
    quests.require_changeable(QuestStatus(previous), status)
    row.status = status
    row.changed_at = func.now()
    if status == QuestStatus.ACTIVE:
        quests.reveal(row, quest, table.clock.minutes)
    payload = describe(quest, previous, status, [], row.due_at)
    recorder.record(session, table, EventType.QUEST_CHANGED, actor_id=actor_id, payload=payload)


async def change_quest(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, entry_id: uuid.UUID, status: QuestStatus
) -> GameTable:
    """
    방장이 퀘스트를 드러내거나 실패로 바꾼다. 성공은 엔진만 정한다.

    방장이 아니면 NotHostError, 진행 중이 아니면 TableConflictError, 이 테이블의 퀘스트가 아니면 TableOptionError,
    바꿀 수 없는 상태면 TableConflictError(quest_finished, quest_already_active, quest_success_by_engine).
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_playing(table)
    apply_change(session, table, entry_id, status, host_id)
    return await save(session, table)
