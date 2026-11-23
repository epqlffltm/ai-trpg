# trpg-server/app/rounds/pauses.py

"""
아무도 선언하지 않은 라운드를 마감에 닫지 않고 멈춘다(#1341).

마감이 지나면 서버의 시계가 라운드를 닫는다(app/rounds/service.py 의 close_on_time). 안 낸 사람은 아무것도 하지 않은
것으로 넘어간다. 그런데 앉은 사람이 모두 나가기를 누르지 않고 화면을 떠나면 서버는 그것을 모른다. 그러면
"마감 → 서술 → 다음 라운드 → 마감"이 아무도 없는 채로 되풀이되고, 라운드마다 앉은 사람의 크레딧이 빠졌다.
  - 멈추는 것(is_idle): 마감이 지났는데 기다리는 사람이 있고, 앉은 사람 누구도 선언을 내지 않았다.
    한 사람이라도 냈으면 지금처럼 닫는다. 자리를 비운 사람 때문에 낸 사람이 기다리지 않게 한다.
    기다릴 사람이 없으면(모두 쓰러짐) 멈추지 않는다. 마감이 닫아 죽음의 굴림 같은 것을 이어 간다.
  - 멈추기(pause): 마감을 지우고 멈춘 시각을 적는다. 시계는 마감이 있는 라운드만 찾으므로 다시 고르지 않는다.
    서술하지 않으므로 서술 값을 받지 않는다. 이 라운드에 걸어 둔 값은 그대로 걸려 있다.
    이어 가면 그 값으로 서술하고, 나가기로 떠나면 돌려준다(app/billing/charges.py 의 release_departed).
  - 이어 가기(resume): 멈춘 라운드에 누가 선언을 내면 그때부터 테이블의 지금 시간 제한만큼 새 마감을 건다.
    방장이 그사이 시간 제한을 없앴으면 마감 없이 이어 간다. 방장은 멈춘 라운드도 그대로 닫을 수 있다.
  - 둘 다 이벤트로 남긴다(round_paused, round_resumed). 돌아온 사람이 왜 멈췄는지 본다.
접속 여부(스트림)로 가르지 않는다. 접속을 따로 세야 하고, 화면을 열어 둔 채 자리를 비운 사람은 가르지 못한다.

DB 를 모른다. 잠근 테이블의 라운드를 고치고 이벤트를 적는다. 저장은 부른 쪽이 한다.
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.rounds.models import Round
from app.rounds.opener import deadline_for
from app.rounds.state import find_declaration, waiting_for
from app.tables.models import GameTable

# 멈춘 까닭. 이벤트(round_paused)의 reason 에 적는다
NO_DECLARATIONS = 'no_declarations'


def is_idle(table: GameTable, round_: Round) -> bool:
    """마감에 닫지 않고 멈출 라운드인가. 기다리는 사람이 있는데 앉은 사람 누구도 선언을 내지 않았다."""
    if not waiting_for(table, round_):
        return False
    return all(find_declaration(round_, member.user_id) is None for member in table.members)


def pause(session: AsyncSession, table: GameTable, round_: Round, now: datetime) -> None:
    """라운드를 멈춘다. 마감을 지우고 멈춘 시각을 적고 이벤트를 남긴다."""
    round_.deadline_at = None
    round_.paused_at = now
    recorder.record(session, table, EventType.ROUND_PAUSED, payload={'round': round_.number, 'reason': NO_DECLARATIONS})


def is_paused(round_: Round) -> bool:
    """멈춘 라운드인가."""
    return round_.paused_at is not None


def resume(session: AsyncSession, table: GameTable, round_: Round, actor_id: uuid.UUID, now: datetime) -> None:
    """멈춘 라운드를 이어 간다. 지금부터 테이블의 시간 제한만큼 새 마감을 걸고, 이어 가게 한 사람을 이벤트에 남긴다."""
    deadline = deadline_for(table, now)
    round_.paused_at = None
    round_.deadline_at = deadline
    recorder.record(
        session,
        table,
        EventType.ROUND_RESUMED,
        actor_id=actor_id,
        payload={'round': round_.number, 'deadline_at': deadline.isoformat() if deadline is not None else None},
    )
