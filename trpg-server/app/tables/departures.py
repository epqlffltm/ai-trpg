# trpg-server/app/tables/departures.py

"""
자리를 떠난 사람을 적어 둔다(#428). 떠난 뒤에도 자기가 함께한 데까지의 기록을 읽게 하려고 한다.

떠나는 길은 셋이다. 스스로 나가기, 방장이 내보내기(app/tables/service.py), 크레딧이 모자라 서버가 빼기
(app/rounds/credit_waits.py). 셋 모두 자리를 지우고 이벤트를 적은 뒤 여기를 부른다.
DB 를 읽지 않는다. 세션에 올리기만 하고 저장하지 않는다. 부르는 쪽이 자리를 지운 것과 함께 저장한다.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import TableEvent
from app.tables.models import DepartureKind, GameTable, TableDeparture, TableMember, TableStatus


def remembers(table: GameTable) -> bool:
    """이 테이블에서 떠나는 사람을 적어 두는가. 시작한 테이블(진행 중, 끝남)만이다. 모집 중에는 아직 이야기가 없다."""
    return table.status != TableStatus.RECRUITING


def to_departure(table: GameTable, member: TableMember, kind: DepartureKind, left: TableEvent) -> TableDeparture:
    """떠난 사람의 줄을 만든다. 읽을 수 있는 끝은 떠났다는 이벤트(left)의 번호다."""
    return TableDeparture(
        table_id=table.id,
        user_id=member.user_id,
        character_name=member.character_name,
        kind=kind,
        last_sequence=left.sequence,
    )


def record_departure(
    session: AsyncSession, table: GameTable, member: TableMember, kind: DepartureKind, left: TableEvent
) -> None:
    """시작한 테이블이면 떠난 사람을 세션에 올린다. 모집 중이면 아무것도 하지 않는다."""
    if remembers(table):
        session.add(to_departure(table, member, kind, left))
