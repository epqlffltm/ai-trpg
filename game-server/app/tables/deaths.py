# game-server/app/tables/deaths.py

"""
쓰러진 캐릭터를 플레이어가 스스로 보낸다.

캐릭터가 죽는 길은 둘이다.
  - 규칙이 정한다. 쓰러진 채로 라운드가 닫힐 때마다 죽음의 굴림을 굴리고, 실패가 다 모이면 죽는다
    (app/rounds/service.py 의 roll_death_saves).
  - 플레이어가 정한다(여기). 쓰러진 캐릭터를 그 전에 스스로 보낼 수 있다.
    동료의 회복이나 주사위를 기다리지 않고 새 캐릭터로 넘어가려는 때다.

멀쩡한 캐릭터는 보낼 수 없다. 마음에 안 드는 캐릭터를 버리고 새로 만드는 길이 되면 안 된다.
죽음은 되돌릴 수 없다. 죽었다고 적는 함수만 있고 되살리는 함수는 없다.

HTTP 를 모른다. 테이블을 잠그고 하고, 무슨 일이 있었는지를 이벤트로 적는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.tables import sheets
from app.tables.models import DeathCause, GameTable, TableMember, TableStatus
from app.tables.service import Conflict, TableConflictError, lock_seated, save


def require_playing(table: GameTable) -> None:
    """테이블이 진행 중인지 확인한다. 아니면 TableConflictError."""
    if table.status != TableStatus.PLAYING:
        raise TableConflictError(Conflict.NOT_PLAYING)


def require_downed_alive(member: TableMember) -> None:
    """
    이 사람의 캐릭터가 쓰러져 있고 아직 살아 있는지 확인한다. 아니면 TableConflictError.

    이미 죽었으면 죽었다고, 쓰러져 있지 않으면 쓰러져 있지 않다고 알린다.
    """
    if sheets.is_dead(member):
        raise TableConflictError(Conflict.CHARACTER_DEAD)
    if not sheets.is_downed_alive(member):
        raise TableConflictError(Conflict.CHARACTER_NOT_DOWNED)


async def give_up_character(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> GameTable:
    """
    쓰러진 자기 캐릭터를 보낸다. 캐릭터가 죽는다.

    앉지 않았으면 TableNotFoundError.
    진행 중이 아니거나, 캐릭터가 쓰러져 있지 않거나, 이미 죽었으면 TableConflictError.

    테이블을 잠그고 한다. 라운드가 닫히면서 굴리는 죽음의 굴림과 엇갈리지 않는다.
    라운드가 닫는 중이어도 된다. 그 라운드의 굴림은 이미 끝나 있다.
    """
    table, member = await lock_seated(session, user_id, table_id)
    require_playing(table)
    require_downed_alive(member)

    sheets.mark_dead(member.sheet)
    payload = {
        'user_id': str(user_id),
        'character_name': member.character_name,
        'cause': DeathCause.GAVE_UP,
    }
    recorder.record(session, table, EventType.CHARACTER_DIED, actor_id=user_id, payload=payload)
    return await save(session, table)
