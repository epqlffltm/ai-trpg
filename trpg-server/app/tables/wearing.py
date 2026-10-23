# trpg-server/app/tables/wearing.py

"""
캐릭터가 장비를 착용하고 벗는다(#276). 지도나 소지품처럼 화면에서 바로 바꾼다.
라운드의 행동이 아니고 AI 를 부르지 않는다.

  - 자기 캐릭터만 바꾼다. 방장도 남의 장비를 바꾸지 못한다.
  - 진행 중이고, 라운드가 선언을 받는 중일 때만 바꾼다. 닫는 중(판정하는 동안)에는 장비가 바뀌지 않는다.
  - 살아 있고 쓰러지지 않은 캐릭터만 바꾼다. 의식이 없는 캐릭터는 갑옷을 벗지 못한다.
  - 가진 물건만, 그 물건이 들어갈 수 있는 칸에, 차지하는 칸의 수만큼 끼운다(app/tables/equipment.py).
  - 바꾼 것은 이벤트(equipment_changed)로 남긴다. 착용은 모두에게 보인다(소지품과 같다).

HTTP 를 모른다. 테이블을 잠그고 한다. 같은 사람의 두 요청이 같은 칸을 동시에 바꿔도 하나씩 차례로 한다.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.engine.ruleset import Ruleset
from app.events import recorder
from app.events.models import EventType
from app.rounds import service as rounds
from app.rounds import state as round_state
from app.rounds.errors import Conflict as RoundConflict
from app.rounds.errors import RoundConflictError
from app.tables import equipment, items, sheets
from app.tables.errors import Conflict, TableConflictError
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableMember, TableSheet, TableWorn
from app.tables.service import save


def require_able(member: TableMember) -> TableSheet:
    """
    장비를 바꿀 수 있는 캐릭터의 시트. 죽었으면 RoundConflictError(character_dead),
    쓰러져 있으면 RoundConflictError(character_downed).
    """
    if sheets.is_dead(member):
        raise RoundConflictError(RoundConflict.CHARACTER_DEAD)
    if round_state.is_down(member):
        raise RoundConflictError(RoundConflict.CHARACTER_DOWNED)
    return member.sheet


async def lock_wearer(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[GameTable, TableMember, TableSheet]:
    """
    테이블을 잠그고, 라운드가 선언을 받는 중인지, 자기 캐릭터가 장비를 바꿀 수 있는지 본다.

    앉지 않았으면 TableNotFoundError, 진행 중이 아니거나 라운드가 닫는 중이면 RoundConflictError.
    """
    table, member, round_ = await rounds.lock_current_round(session, user_id, table_id)
    round_state.require_open(round_)
    return table, member, require_able(member)


def worn_document(row: TableWorn, catalog: dict[uuid.UUID, CatalogItem]) -> dict:
    """착용 하나를 이벤트에 적을 모양. 무엇을 어느 칸에."""
    return {'entry_id': str(row.entry_id), 'name': catalog[row.entry_id].name, 'slots': list(row.slots)}


def describe_change(
    member: TableMember, change: str, row: TableWorn, removed: Sequence[TableWorn], catalog: dict
) -> dict:
    """바꾼 것을 이벤트에 적을 모양. 누가, 끼웠는지(wear) 벗었는지(take_off), 무엇을, 함께 빠진 것."""
    return {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'change': change,
        **worn_document(row, catalog),
        'removed': [worn_document(one, catalog) for one in removed],
    }


def require_wearable(ruleset: Ruleset, item: CatalogItem, slots: Sequence[str]) -> None:
    """그 물건을 그 칸들에 끼울 수 있는지 본다. 아니면 TableOptionError(entry_id, slots)."""
    equipment.require_fits(ruleset, item.slots, item.slot_count, slots)


async def wear_item(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, entry_id: uuid.UUID, slots: Sequence[str]
) -> GameTable:
    """
    자기 캐릭터가 가진 물건 하나를 그 칸들에 끼운다. 찬 칸의 것은 벗겨진다.

    판에 없는 물건이거나 착용하지 않는 물건이면 TableOptionError(entry_id), 칸이 맞지 않으면 TableOptionError(slots),
    가지고 있지 않으면 TableConflictError(not_enough_items).
    """
    table, member, sheet = await lock_wearer(session, user_id, table_id)
    snapshot = read_snapshot(table.content)
    catalog = items.catalog(snapshot)
    item = items.require_in_catalog(catalog, entry_id)
    require_wearable(snapshot.rulebook.rules, item, slots)
    held = items.count_of(sheet, entry_id)
    if held < 1:
        raise TableConflictError(Conflict.NOT_ENOUGH_ITEMS)
    removed = equipment.wear(table.id, sheet, entry_id, slots, held)
    worn = sheet.worn[-1]
    payload = describe_change(member, 'wear', worn, removed, catalog)
    recorder.record(session, table, EventType.EQUIPMENT_CHANGED, actor_id=user_id, payload=payload)
    return await save(session, table)


async def take_off_slot(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, slot: str) -> GameTable:
    """
    자기 캐릭터의 그 칸을 비운다. 그 칸을 차지한 착용이 통째로 빠진다(두 손 검이면 두 칸 다).

    비어 있는 칸이면 아무것도 바꾸지 않고 이벤트도 남기지 않는다. 같은 요청을 두 번 보내도 결과가 같다.
    """
    table, member, sheet = await lock_wearer(session, user_id, table_id)
    row = equipment.take_off(sheet, slot)
    if row is not None:
        catalog = items.catalog(read_snapshot(table.content))
        payload = describe_change(member, 'take_off', row, [], catalog)
        recorder.record(session, table, EventType.EQUIPMENT_CHANGED, actor_id=user_id, payload=payload)
    return await save(session, table)
