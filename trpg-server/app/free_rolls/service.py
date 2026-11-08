# trpg-server/app/free_rolls/service.py

"""
자유 굴림(#404). 앉은 사람이 주사위를 굴려 모두에게 보인다. 게임의 상태와 무관하다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

  - 앉은 사람만 굴린다. 끝난 테이블에서는 굴리지 못한다.
  - 굴림은 서버의 주사위로 한다. 화면이 보낸 눈을 받지 않는다.
  - 한 사람이 한 테이블에서 굴리는 수를 센다(limiting.limits.free_roll). 넘으면 TooManyAttempts. 잠그기 전에 센다.
  - 이벤트(dice_rolled)로 남긴다. 판정도 피해도 아니다. 서술하는 AI 에게 주지 않는다(서술의 입력은 선언과 판정이다).
  - 이벤트의 번호를 정하려고 테이블의 행을 잠그고 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import dice_notation
from app.engine.dice import Dice
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.free_rolls.schemas import FreeRollCreate
from app.limits.setup import Limiting
from app.tables import service as tables
from app.tables import state as table_state
from app.tables.models import GameTable, TableMember


def payload_of(member: TableMember, rolled: dice_notation.Rolled) -> dict:
    """이벤트에 적을 내용. 누가, 무엇을 굴려, 어떤 눈이 나왔는가."""
    return {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'dice': rolled.notation.text,
        'faces': list(rolled.faces),
        'bonus': rolled.notation.bonus,
        'total': rolled.total,
    }


def record_roll(
    session: AsyncSession, table: GameTable, member: TableMember, rolled: dice_notation.Rolled
) -> TableEvent:
    """굴린 것을 이벤트로 적는다. 저장하지는 않는다."""
    return recorder.record(
        session, table, EventType.DICE_ROLLED, actor_id=member.user_id, payload=payload_of(member, rolled)
    )


async def roll_dice(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: FreeRollCreate, dice: Dice, limiting: Limiting
) -> TableEvent:
    """
    자유 굴림을 한다. 적은 이벤트를 돌려준다.

    앉지 않았으면 TableNotFoundError, 끝난 테이블이면 TableConflictError.
    굴리는 수를 넘으면 TooManyAttempts. 주사위 설명은 받을 때 읽어 봤다(FreeRollCreate).
    """
    await limiting.limiter.count_attempt(limiting.limits.free_roll, f'{table_id}:{user_id}')
    table, member = await tables.lock_seated(session, user_id, table_id)
    table_state.require_not_ended(table)
    rolled = dice_notation.roll(dice_notation.parse(data.dice), dice)
    event = record_roll(session, table, member, rolled)
    await tables.commit(session, table)
    return event
