# trpg-server/app/campaigns/seating.py

"""
다음 편의 테이블에 넘긴 캐릭터로 앉고, 시작할 때 그 캐릭터의 시트를 준다
(docs/architecture/campaigns.md 의 "다음 편", "옮기는 것").

  - 앉을 때: 그 사람이 그 플레이에서 가장 나중에 넘긴 것이 있으면 그 캐릭터로 앉는다(campaign_seats).
    이름과 설명을 자리에 적는다. 방식은 custom 으로 적되 판의 캐릭터 방식과 상관없이 앉는다.
    넘긴 것이 없는 사람(죽었거나 새로 온 사람)은 보통처럼 판의 방식대로 캐릭터를 정한다.
  - 넘긴 캐릭터로 앉은 사람은 캐릭터를 바꾸지 못한다(409 character_carried).
  - 시작할 때: 넘긴 능력치, 최대 HP(지금 HP 는 가득), 경험치, 놓지 않은 점수, 기술, 저항, 돈을 그대로 준다.
    소지품은 이 편의 판에 같은 물건 항목이 있는 것만 옮긴다. 착용은 풀어서 옮긴다(입지 않은 채로 시작한다).
    판의 시작 소지품과 시작 돈은 받지 않는다. 넘긴 것이 그 캐릭터의 것이다.

같은 룰북이라 숫자를 다시 계산하지 않는다(게시할 때 막는다). 레벨은 경험치와 레벨표로 정해진다.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import ItemStackSnapshot, Snapshot, item_entries
from app.campaigns import repository
from app.campaigns.carrying import Carry, CarryItem
from app.campaigns.models import CampaignCarry, CampaignRun, CampaignSeat
from app.engine.sheet import CharacterSheet
from app.tables import items, sheets
from app.tables.errors import Conflict, TableConflictError
from app.tables.models import GameTable, TableMember


def sit_as(member: TableMember, carry: Carry) -> None:
    """
    자리에 넘긴 캐릭터를 적는다. 프리젠과 직접 정한 능력치는 비운다(숫자는 시작할 때 넘긴 것에서 준다).

    방식은 이름과 설명만 쓰기(custom)로 적는다. 캐릭터가 있는 자리에는 방식이 있어야 한다(DB 의 CHECK).
    판의 방식과 상관없이 앉고, 시작할 때 기본 시트가 아니라 넘긴 것을 받는다(campaign_seats 가 그 표시다).
    """
    member.character_name = carry.character_name
    member.character_description = carry.character_description
    member.character_mode = CharacterMode.CUSTOM
    member.pregen_index = None
    member.abilities = None


async def seat_carried(session: AsyncSession, run: CampaignRun, table: GameTable, member: TableMember) -> bool:
    """
    그 사람이 넘긴 것이 있으면 그 캐릭터로 앉힌다. 앉혔으면 True. 넘긴 것이 없으면 아무것도 하지 않는다.

    테이블을 잠근 뒤에 부른다. 저장은 부른 쪽이 한다.
    """
    carry = await repository.last_carry(session, run.id, member.user_id)
    if carry is None:
        return False
    repository.add(session, CampaignSeat(table_id=table.id, user_id=member.user_id, carry_id=carry.id))
    sit_as(member, Carry.model_validate(carry.carry))
    return True


async def is_carried(session: AsyncSession, table_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """그 자리가 넘긴 캐릭터로 앉은 자리인가."""
    return await session.get(CampaignSeat, (table_id, user_id)) is not None


async def require_not_carried(session: AsyncSession, table_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """넘긴 캐릭터로 앉은 자리면 TableConflictError(character_carried). 캐릭터를 정하기 전에 부른다."""
    if await is_carried(session, table_id, user_id):
        raise TableConflictError(Conflict.CHARACTER_CARRIED)


async def carried_for(session: AsyncSession, table: GameTable) -> dict[uuid.UUID, Carry]:
    """그 테이블에서 넘긴 캐릭터로 앉은 사람마다의 넘길 것. 캠페인의 테이블이 아니면 비어 있다."""
    query = (
        select(CampaignSeat.user_id, CampaignCarry.carry)
        .join(CampaignCarry, CampaignCarry.id == CampaignSeat.carry_id)
        .where(CampaignSeat.table_id == table.id)
    )
    return {user_id: Carry.model_validate(carry) for user_id, carry in (await session.execute(query)).all()}


def kept_items(carried: list[CarryItem], snapshot: Snapshot) -> list[ItemStackSnapshot]:
    """넘긴 소지품 가운데 이 편의 판에 같은 물건 항목이 있는 것."""
    known = {entry.id for entry in item_entries(snapshot)}
    return [ItemStackSnapshot(entry_id=item.entry_id, count=item.count) for item in carried if item.entry_id in known]


def give_carried(table: GameTable, snapshot: Snapshot, member: TableMember, carry: Carry) -> None:
    """넘긴 캐릭터의 시트를 준다. 지금 HP 는 가득이다. 판에 없는 물건은 옮기지 않는다."""
    source = CharacterSheet(
        abilities=carry.abilities, max_hp=carry.max_hp, skills=carry.skills, resistances=carry.resistances
    )
    sheet = sheets.give_sheet(member, source)
    sheet.xp = carry.xp
    sheet.points = carry.points
    sheet.money = carry.money
    items.give_starting_items(table.id, sheet, kept_items(carry.items, snapshot))


def hand_out_carried(table: GameTable, snapshot: Snapshot, carried: dict[uuid.UUID, Carry]) -> None:
    """넘긴 캐릭터로 앉은 사람마다 시트를 준다. 나머지 사람의 시트는 sheets.hand_out 이 준다."""
    for member in table.members:
        if member.user_id in carried:
            give_carried(table, snapshot, member, carried[member.user_id])
