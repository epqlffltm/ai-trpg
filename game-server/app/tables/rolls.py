# game-server/app/tables/rolls.py

"""
능력치의 점수를 주사위로 굴리고, 방장이 "한 번 더"를 준다.

주사위로 정하는 방식(rolled)은 두 걸음이다.
  1. 굴린다(여기). 서버가 굴려서 점수들을 테이블에 적어 둔다. 화면이 굴린 값을 받지 않는다.
  2. 놓는다(app/tables/service.py 의 set_character). 플레이어가 그 점수들을 원하는 능력치에 놓아 보낸다.

캐릭터 하나에 한 번 굴린다. 좋은 눈이 나올 때까지 굴릴 수 있으면 주사위의 뜻이 없다.
캐릭터가 죽어 새 캐릭터를 들일 때는 새로 굴린다. 지난 캐릭터의 점수를 물려받지 않는다.
같은 캐릭터를 위해 다시 굴리는 길은 하나다. 시나리오의 제작자가 허락했고, 방장이 그 사람에게 "한 번 더"를 줬을 때다.
제작자가 허락하지 않았으면 방장도 주지 못한다.

굴린 것은 사람이 나가도 남는다(app/tables/models.py 의 TableRoll). 나갔다 들어와서 새로 굴리지 못한다.

HTTP 를 모른다. 테이블을 잠그고 하고, 무슨 일이 있었는지를 이벤트로 적는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import read_snapshot
from app.engine.dice import Dice
from app.engine.score_roll import RolledScore, roll_scores
from app.events import recorder
from app.events.models import EventType
from app.tables import sheets
from app.tables.models import GameTable, TableMember, TableRoll
from app.tables.service import (
    Conflict,
    MemberNotFoundError,
    TableConflictError,
    find_member,
    lock_seated,
    require_choosing,
    require_host,
    save,
)


def require_rolled_mode(table: GameTable) -> None:
    """이 테이블이 주사위로 정하는 방식을 허용하는지 확인한다. 아니면 TableConflictError."""
    if CharacterMode.ROLLED not in table.character_modes:
        raise TableConflictError(Conflict.CHARACTER_MODE_NOT_ALLOWED)


def write_roll(table: GameTable, member: TableMember, rolled: list[RolledScore]) -> TableRoll:
    """
    굴린 것을 테이블에 적는다. 처음이면 행을 만들고, 다시 굴린 것이면 있던 행의 값을 바꾼다.

    이 사람의 몇 번째 캐릭터를 위해 굴렸는지를 함께 적는다. 지금 정하고 있는 캐릭터의 번호다.
    받아 둔 "한 번 더"가 있었으면 쓴 것이다. 꺼 둔다. 지난 캐릭터 때 받아 두고 쓰지 않은 것도 여기서 꺼진다.
    """
    dice = [list(score.dice) for score in rolled]
    scores = [score.score for score in rolled]
    number = sheets.next_number(member)
    roll = sheets.find_roll(table, member.user_id)
    if roll is None:
        roll = TableRoll(user_id=member.user_id, dice=dice, scores=scores, times_rolled=1, character_number=number)
        table.rolls.append(roll)
        return roll
    roll.dice = dice
    roll.scores = scores
    roll.times_rolled += 1
    roll.character_number = number
    roll.reroll_granted = False
    return roll


def drop_rolled_character(member: TableMember) -> None:
    """
    옛 점수로 만든 캐릭터를 지운다. 다시 굴렸을 때 부른다.

    그 캐릭터의 능력치는 지난 굴림의 점수다. 새 점수와 맞지 않는 것을 자리에 남겨 두지 않는다.
    다른 방식으로 만든 캐릭터는 굴림과 상관없으니 그대로 둔다.

    시트를 받은 캐릭터는 건드리지 않는다. 진행 중에 굴리는 사람의 자리에는 죽은 캐릭터가 적혀 있다.
    그 캐릭터는 이미 정해진 것이고, 지금 굴리는 것은 다음 캐릭터를 위한 것이다.
    """
    if member.sheet is None and member.character_mode == CharacterMode.ROLLED:
        sheets.clear_character(member)


async def roll_abilities(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, dice: Dice) -> GameTable:
    """
    자기 능력치의 점수를 주사위로 굴린다. 굴린 점수는 테이블에 적히고 모두에게 보인다.

    앉지 않았으면 TableNotFoundError.
    캐릭터를 정할 수 있는 때가 아니거나(모집 중이 아니고, 진행 중인데 캐릭터가 살아 있다),
    이 테이블이 그 방식을 허용하지 않거나, 이 캐릭터를 위해 이미 굴렸으면 TableConflictError.

    진행 중에는 캐릭터가 죽은 사람이 새 캐릭터를 위해 굴린다. 지난 캐릭터를 위해 굴린 것은 굴린 것으로 치지 않는다.
    테이블을 잠그고 한다. 같은 사람의 요청 둘이 동시에 와도 한 번만 굴린다.
    """
    table, member = await lock_seated(session, user_id, table_id)
    require_choosing(table, member)
    require_rolled_mode(table)
    if not sheets.may_roll(sheets.find_roll(table, user_id), member):
        raise TableConflictError(Conflict.ALREADY_ROLLED)

    # 그 방식을 허용한 판의 규칙에는 굴리는 법이 반드시 있다(게시 조건). 없으면 굴릴 수 없는 테이블이다
    rolled = roll_scores(read_snapshot(table.content).rulebook.rules, dice)
    if rolled is None:
        raise TableConflictError(Conflict.CHARACTER_MODE_NOT_ALLOWED)

    roll = write_roll(table, member, rolled)
    drop_rolled_character(member)
    payload = {
        'dice': roll.dice,
        'scores': roll.scores,
        'times_rolled': roll.times_rolled,
        'character_number': roll.character_number,
    }
    recorder.record(session, table, EventType.ABILITIES_ROLLED, actor_id=user_id, payload=payload)
    return await save(session, table)


async def grant_reroll(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, user_id: uuid.UUID) -> GameTable:
    """
    방장이 한 사람에게 "한 번 더 굴리기"를 준다. 받은 사람은 한 번 다시 굴릴 수 있다.

    방장이 아니면 NotHostError, 그 사람이 앉아 있지 않으면 MemberNotFoundError.
    그 사람이 캐릭터를 정할 수 있는 때가 아니거나, 그 방식을 허용하지 않는 테이블이거나,
    제작자가 다시 굴리기를 허락하지 않았거나, 그 사람이 지금 정하는 캐릭터를 위해 아직 굴리지 않았거나,
    이미 줬는데 아직 쓰지 않았으면 TableConflictError.

    방장이 자기 자신에게 줄 수도 있다. 누가 누구에게 줬는지는 이벤트로 모두에게 보인다.
    진행 중에는 캐릭터가 죽어 새 캐릭터를 굴린 사람에게 준다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    member = find_member(table, user_id)
    if member is None:
        raise MemberNotFoundError
    require_choosing(table, member)
    require_rolled_mode(table)
    if not read_snapshot(table.content).reroll_allowed:
        raise TableConflictError(Conflict.REROLL_NOT_ALLOWED)

    roll = sheets.find_fresh_roll(table, member)
    if roll is None:
        raise TableConflictError(Conflict.NOT_ROLLED)
    if roll.reroll_granted:
        raise TableConflictError(Conflict.REROLL_ALREADY_GRANTED)

    roll.reroll_granted = True
    recorder.record(session, table, EventType.REROLL_GRANTED, actor_id=host_id, payload={'user_id': str(user_id)})
    return await save(session, table)
