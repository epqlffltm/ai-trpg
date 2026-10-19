# trpg-server/app/tables/seating.py

"""
자리. 앉기, 테이블 끝내기, 방장이 떠났을 때 다음 방장 정하기.

DB 를 모른다. 이미 읽어 온 테이블을 고친다. 저장은 부른 쪽이 한다.
초대 코드로 들어오든 로비에서 들어오든 앉는 규칙은 같다(take_seat).
방장이 나가면 남은 사람 중 가장 먼저 들어온 사람이 방장이 된다. 마지막 사람이 나가면 테이블이 끝난다.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType, TableEvent
from app.tables.errors import Conflict, TableConflictError
from app.tables.models import GameTable, TableMember, TableStatus
from app.tables.state import find_member, require_recruiting


def take_seat(table: GameTable, user_id: uuid.UUID) -> None:
    """
    테이블에 앉는다. 모집 중이 아니거나, 이미 앉아 있거나, 자리가 없으면 TableConflictError.

    테이블을 잠근 뒤에 부른다. 초대 코드로 들어오든 로비에서 들어오든 앉는 규칙은 같다.
    """
    require_recruiting(table)
    if find_member(table, user_id) is not None:
        raise TableConflictError(Conflict.ALREADY_SEATED)
    if len(table.members) >= table.capacity:
        raise TableConflictError(Conflict.TABLE_FULL)
    table.members.append(TableMember(user_id=user_id))


def end(table: GameTable) -> None:
    """테이블을 끝낸다."""
    table.status = TableStatus.ENDED
    table.ended_at = func.now()


def hand_over(table: GameTable) -> EventType | None:
    """
    방장이 떠난 테이블의 다음 방장을 정한다. 남은 사람 중 가장 먼저 들어온 사람이다.

    남은 사람이 없으면 테이블을 끝낸다.
    무슨 일이 일어났는지를 이벤트의 종류로 돌려준다. 이미 끝난 테이블에서 마지막 사람이 나갔으면 아무 일도 없다(None).
    """
    if table.members:
        table.host_id = table.members[0].user_id
        return EventType.HOST_CHANGED
    if table.status != TableStatus.ENDED:
        end(table)
        return EventType.TABLE_ENDED
    return None


def record_hand_over(session: AsyncSession, table: GameTable, outcome: EventType | None, left: TableEvent) -> None:
    """
    방장이 나간 뒤에 일어난 일(hand_over 가 돌려준 것)을 이벤트로 적는다. 원인은 방장이 나간 이벤트다.

    사람이 한 일이 아니므로 actor_id 가 없다.
    """
    if outcome == EventType.HOST_CHANGED:
        recorder.record(session, table, outcome, payload={'user_id': str(table.host_id)}, cause=left)
    elif outcome == EventType.TABLE_ENDED:
        recorder.record(session, table, outcome, cause=left)
