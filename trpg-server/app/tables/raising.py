# trpg-server/app/tables/raising.py

"""
쌓인 능력치 점수를 능력치에 놓는다(#286 ③). 레벨이 올라 받은 점수를 플레이어가 고른 능력치에 쓴다.
라운드의 행동이 아니고 AI 를 부르지 않는다. 계산은 app/tables/growth.py 의 raise_abilities 다.

  - 자기 캐릭터만 바꾼다. 방장도 남의 능력치를 정하지 못한다. 모델도 바꾸지 못한다.
  - 진행 중이고, 라운드가 선언을 받는 중일 때만 바꾼다. 닫는 중(판정하는 동안)에는 능력치가 바뀌지 않는다.
  - 죽은 캐릭터는 바꾸지 못한다. 쓰러진 캐릭터는 바꿀 수 있다(몸을 움직이는 일이 아니다).
  - 바꾼 것은 이벤트(abilities_raised)로 남긴다. 시트는 앉은 사람 모두가 본다.

HTTP 를 모른다. 테이블을 잠그고 한다. 같은 사람의 두 요청이 같은 점수를 동시에 쓰지 못한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.rounds import service as rounds
from app.rounds import state as round_state
from app.rounds.errors import Conflict as RoundConflict
from app.rounds.errors import RoundConflictError
from app.tables import growth, sheets
from app.tables.content import snapshot_of
from app.tables.models import GameTable, TableMember, TableSheet
from app.tables.service import save


def require_living(member: TableMember) -> TableSheet:
    """능력치를 바꿀 수 있는 캐릭터의 시트. 죽었으면 RoundConflictError(character_dead)."""
    if sheets.is_dead(member):
        raise RoundConflictError(RoundConflict.CHARACTER_DEAD)
    return member.current_sheet


async def lock_raiser(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[GameTable, TableMember, TableSheet]:
    """
    테이블을 잠그고, 라운드가 선언을 받는 중인지, 자기 캐릭터가 살아 있는지 본다.

    앉지 않았으면 TableNotFoundError, 진행 중이 아니거나 라운드가 닫는 중이면 RoundConflictError.
    """
    table, member, round_ = await rounds.lock_current_round(session, user_id, table_id)
    round_state.require_open(round_)
    return table, member, require_living(member)


def describe_raise(member: TableMember, sheet: TableSheet, raised: list[dict]) -> dict:
    """놓은 것을 이벤트에 적을 모양. 누가, 어느 능력치를 몇에서 몇으로, 남은 점수와 그 뒤의 최대 HP."""
    return {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'raises': raised,
        'points': sheet.points,
        'max_hp': sheet.max_hp,
    }


async def raise_abilities(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, raises: dict[str, int]
) -> GameTable:
    """
    자기 캐릭터의 쌓인 점수를 그 능력치들에 놓는다. raises 는 능력치의 이름표에서 놓을 점수로 간다.

    규칙에 없는 능력치면 TableOptionError(raises), 점수가 모자라면 TableConflictError(not_enough_points),
    상한을 넘으면 TableConflictError(ability_at_max).
    """
    table, member, sheet = await lock_raiser(session, user_id, table_id)
    ruleset = snapshot_of(table).rulebook.rules
    raised = growth.raise_abilities(ruleset, sheet, raises)
    payload = describe_raise(member, sheet, raised)
    recorder.record(session, table, EventType.ABILITIES_RAISED, actor_id=user_id, payload=payload)
    return await save(session, table)
