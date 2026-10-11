# game-server/app/rounds/opener.py

"""
라운드를 연다. 장면을 서술한 것과 라운드가 열린 것을 이벤트로 적는다.

라운드가 열리는 때는 둘이다. 테이블을 시작할 때(app/tables/service.py)와 앞 라운드가 닫혔을 때(app/rounds/service.py).
두 곳이 같은 일을 하므로 여기에 한 번만 적는다.

라운드를 열 때 테이블의 시간 제한으로 마감을 정한다(deadline_for). 열린 이벤트에도 마감을 싣는다.
화면은 그것으로 남은 시간을 보여 주고, 서버는 마감이 지난 라운드를 닫는다(app/rounds/clock.py).

파일을 따로 둔 이유: 라운드 서비스는 테이블 서비스를 불러온다.
테이블 서비스가 라운드 서비스를 불러오면 서로를 불러오게 된다. 이 파일은 어느 서비스도 불러오지 않는다.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType, TableEvent
from app.rounds import repository
from app.rounds.models import Round
from app.tables.models import GameTable


def deadline_for(table: GameTable, opened: datetime) -> datetime | None:
    """연 시각과 테이블의 시간 제한으로 정한 선언의 마감. 시간 제한이 없으면 None."""
    if table.round_time_limit is None:
        return None
    return opened + timedelta(seconds=table.round_time_limit)


def open_round(session: AsyncSession, table: GameTable, number: int, scene: str, cause: TableEvent) -> Round:
    """
    새 라운드를 연다. 연 라운드를 돌려준다. 저장하지는 않는다.

    scene 은 이 라운드를 여는 GM 의 서술이다. cause 는 이 라운드를 열게 한 이벤트다(테이블 시작, 앞 라운드의 닫힘).
    이벤트는 "GM 이 서술했다 → 라운드가 열렸다" 순서로 둘을 적는다.
    마감은 지금부터 테이블의 시간 제한만큼 뒤다. 서술을 기다린 시간은 세지 않는다.

    앞 라운드가 있으면 닫은 것을 먼저 DB 에 보낸 뒤에 부른다(유일 색인 uq_table_rounds_open).
    """
    deadline = deadline_for(table, datetime.now(UTC))
    round_ = Round(table_id=table.id, number=number, scene=scene, deadline_at=deadline)
    repository.add_round(session, round_)
    narration = recorder.record(session, table, EventType.GM_NARRATION, payload={'text': scene}, cause=cause)
    opened = {'number': number, 'deadline_at': deadline.isoformat() if deadline is not None else None}
    recorder.record(session, table, EventType.ROUND_OPENED, payload=opened, cause=narration)
    return round_
