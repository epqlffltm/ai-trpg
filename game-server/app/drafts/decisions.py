# game-server/app/drafts/decisions.py

"""
방장이 장부 초안의 줄을 받아들이거나 버린다. 받아들여야 장부(소지품, 퀘스트)가 바뀐다.

받아들일 때 지금의 장부로 다시 본다. 초안을 쓴 뒤에 바뀌었을 수 있다.
  - 물건: 그 사람이 아직 앉아 있고(404), 지금 캐릭터가 살아 있고(409 character_dead),
    초안을 쓸 때의 그 캐릭터여야 한다(409 draft_stale. 죽고 새 캐릭터가 들어왔으면 새 캐릭터에게 주지 않는다).
    한 가지를 99 개까지 갖는다. 넘는 만큼은 받지 않는다(퀘스트의 보상과 같다). 이미 99 개면 409 too_many_items.
    방장이 손으로 주는 것과 같은 이벤트(items_gained)가 모두에게 간다.
  - 퀘스트: 방장이 손으로 바꿀 때와 같은 길이다(app/tables/quest_changes.py 의 apply_change). 같은 규칙,
    같은 이벤트(quest_changed). 실패만 받는다. 그사이 끝났으면 그 충돌(quest_finished)이다.
    드러내기를 엔진의 몫으로 옮기기 전에 쓴 드러내기 초안은 받지 않는다(quest_reveal_by_engine).
버리는 것은 줄의 처지만 바꾼다. 장부는 그대로다. 끝난 테이블에서도 버릴 수 있다(정리).

이미 결정했거나 만료된 줄은 다시 결정하지 못한다(409 draft_decided).
테이블을 잠그고 한다. 같은 줄을 동시에 두 번 받아들여도 한 번만 바뀐다.
다음 초안이 줄을 만료시키는 일과도 겹치지 않는다.

HTTP 를 모른다.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import ITEM_STACK_MAX
from app.assets.scenarios.snapshot import read_snapshot
from app.drafts import repository
from app.drafts.models import DraftKind, DraftStatus, LedgerDraft
from app.events import recorder
from app.events.models import EventType
from app.tables import item_grants, items, quest_changes
from app.tables.errors import Conflict, TableConflictError
from app.tables.item_grants import require_playing
from app.tables.models import GameTable, QuestStatus
from app.tables.service import lock_seated, save
from app.tables.state import require_host


class DraftNotFoundError(Exception):
    """그 테이블에 그런 줄이 없다."""


async def lock_draft(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, draft_id: uuid.UUID
) -> tuple[GameTable, LedgerDraft]:
    """
    테이블을 잠그고 방장인지, 기다리는 줄인지 확인한다. 테이블과 줄을 돌려준다.

    앉지 않았으면 TableNotFoundError, 방장이 아니면 NotHostError, 줄이 없으면 DraftNotFoundError,
    이미 결정했거나 만료됐으면 TableConflictError(draft_decided).
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    draft = await repository.find_draft(session, table.id, draft_id)
    if draft is None:
        raise DraftNotFoundError
    if draft.status != DraftStatus.PENDING:
        raise TableConflictError(Conflict.DRAFT_DECIDED)
    return table, draft


def decide(draft: LedgerDraft, status: DraftStatus) -> None:
    """줄의 처지를 옮기고 결정한 때를 적는다."""
    draft.status = status
    draft.decided_at = func.now()


def apply_found_item(session: AsyncSession, table: GameTable, payload: dict, host_id: uuid.UUID) -> None:
    """물건 줄을 장부에 옮긴다. 그 사람의 지금 캐릭터가 초안의 캐릭터여야 한다. 99 개를 넘는 만큼은 받지 않는다."""
    member, sheet = item_grants.living_sheet(table, uuid.UUID(payload['user_id']))
    if member.character_name != payload['character_name']:
        raise TableConflictError(Conflict.DRAFT_STALE)
    entry_id = uuid.UUID(payload['entry_id'])
    if items.count_of(sheet, entry_id) >= ITEM_STACK_MAX:
        raise TableConflictError(Conflict.TOO_MANY_ITEMS)
    item = items.require_in_catalog(items.catalog(read_snapshot(table.content)), entry_id)
    given = items.add_up_to(table.id, sheet, entry_id, payload['count'])
    event = item_grants.describe(member, item, given, items.count_of(sheet, entry_id))
    recorder.record(session, table, EventType.ITEMS_GAINED, actor_id=host_id, payload=event)


def apply_draft(session: AsyncSession, table: GameTable, draft: LedgerDraft, host_id: uuid.UUID) -> None:
    """줄 하나를 장부에 옮긴다. 줄의 종류로 길을 고른다."""
    if draft.kind == DraftKind.FOUND_ITEM:
        apply_found_item(session, table, draft.payload, host_id)
        return
    status = QuestStatus(draft.payload['status'])
    quest_changes.apply_change(session, table, uuid.UUID(draft.payload['entry_id']), status, host_id)


async def accept_draft(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, draft_id: uuid.UUID
) -> GameTable:
    """방장이 줄 하나를 받아들인다. 장부를 바꾸고 줄을 받아들인 것으로 적는다. 진행 중에만 된다."""
    table, draft = await lock_draft(session, host_id, table_id, draft_id)
    require_playing(table)
    apply_draft(session, table, draft, host_id)
    decide(draft, DraftStatus.ACCEPTED)
    return await save(session, table)


async def reject_draft(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, draft_id: uuid.UUID) -> None:
    """방장이 줄 하나를 버린다. 장부는 그대로다."""
    _, draft = await lock_draft(session, host_id, table_id, draft_id)
    decide(draft, DraftStatus.REJECTED)
    await session.commit()
