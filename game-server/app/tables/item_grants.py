# game-server/app/tables/item_grants.py

"""
방장이 캐릭터에게 물건을 주거나 빼앗는다(#202).

AI GM 은 소지품을 바꾸지 못한다. 서술에서 "상자에서 물약을 찾았다"고 해도 소지품은 늘지 않는다.
그 장면을 소지품으로 옮기는 것은 방장이다. 사람 GM 이 장부를 고치는 것과 같다.

  - 진행 중인 테이블에서만 한다. 시트(캐릭터)가 있어야 소지품이 있다.
  - 앉아 있는 사람의 지금 캐릭터에게만 한다. 죽은 캐릭터에게는 주지도 빼앗지도 않는다.
  - 판에 있는 물건(로어북의 물건 항목)만 다룬다.
  - 준 것과 빼앗은 것은 이벤트로 남긴다. 앉은 사람 모두가 스트림으로 본다. 소지품은 모두에게 보인다.

HTTP 를 모른다. 테이블을 잠그고 한다. 두 요청이 같은 물건의 개수를 동시에 고쳐도 하나씩 차례로 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.events import recorder
from app.events.models import EventType
from app.tables import items, sheets
from app.tables.errors import Conflict, MemberNotFoundError, TableConflictError
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableMember, TableSheet, TableStatus
from app.tables.service import lock_seated, save
from app.tables.state import find_member, require_host


def require_playing(table: GameTable) -> None:
    """진행 중인 테이블인지 확인한다. 아니면 TableConflictError(not_playing). 시작 전에는 캐릭터의 시트가 없다."""
    if table.status != TableStatus.PLAYING:
        raise TableConflictError(Conflict.NOT_PLAYING)


def living_sheet(table: GameTable, user_id: uuid.UUID) -> tuple[TableMember, TableSheet]:
    """
    그 사람과 그 사람의 지금 캐릭터의 시트. 진행 중인 테이블에서 부른다.

    앉아 있지 않으면 MemberNotFoundError, 캐릭터가 죽었으면 TableConflictError(character_dead).
    """
    member = find_member(table, user_id)
    if member is None or member.sheet is None:
        raise MemberNotFoundError
    if sheets.is_dead(member):
        raise TableConflictError(Conflict.CHARACTER_DEAD)
    return member, member.sheet


def describe(member: TableMember, item: CatalogItem, count: int, total: int) -> dict:
    """주거나 빼앗은 것을 이벤트에 적을 모양. 누가, 무엇을, 몇 개, 그 뒤에 몇 개가 됐는가."""
    return {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'entry_id': str(item.entry_id),
        'name': item.name,
        'count': count,
        'total': total,
    }


async def lock_target(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, user_id: uuid.UUID, entry_id: uuid.UUID
) -> tuple[GameTable, TableMember, TableSheet, CatalogItem]:
    """
    테이블을 잠그고 방장인지, 진행 중인지, 대상과 물건이 맞는지 확인한다. 테이블, 대상, 대상의 시트, 물건을 돌려준다.

    방장이 아니면 NotHostError, 진행 중이 아니면 TableConflictError, 대상이 없으면 MemberNotFoundError,
    대상의 캐릭터가 죽었으면 TableConflictError, 판에 없는 물건이면 TableOptionError.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_playing(table)
    member, sheet = living_sheet(table, user_id)
    item = items.require_in_catalog(items.catalog(read_snapshot(table.content)), entry_id)
    return table, member, sheet, item


async def grant_items(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, user_id: uuid.UUID, entry_id: uuid.UUID, count: int
) -> GameTable:
    """방장이 그 사람의 지금 캐릭터에게 물건을 count 개 준다. 한 가지의 상한을 넘으면 TableConflictError."""
    table, member, sheet, item = await lock_target(session, host_id, table_id, user_id, entry_id)
    total = items.add_items(table.id, sheet, entry_id, count)
    payload = describe(member, item, count, total)
    recorder.record(session, table, EventType.ITEMS_GAINED, actor_id=host_id, payload=payload)
    return await save(session, table)


async def take_items(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, user_id: uuid.UUID, entry_id: uuid.UUID, count: int
) -> GameTable:
    """방장이 그 사람의 지금 캐릭터에게서 물건을 count 개 빼앗는다. 가진 것보다 많으면 TableConflictError."""
    table, member, sheet, item = await lock_target(session, host_id, table_id, user_id, entry_id)
    total = items.remove_items(sheet, entry_id, count)
    payload = describe(member, item, count, total)
    recorder.record(session, table, EventType.ITEMS_LOST, actor_id=host_id, payload=payload)
    return await save(session, table)
