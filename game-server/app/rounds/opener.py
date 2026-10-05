# game-server/app/rounds/opener.py

"""
라운드를 연다. 장면을 서술한 것과 라운드가 열린 것을 이벤트로 적는다.

라운드가 열리는 때는 둘이다. 테이블을 시작할 때(app/tables/service.py)와 앞 라운드가 닫혔을 때(app/rounds/service.py).
두 곳이 같은 일을 하므로 여기에 한 번만 적는다.

파일을 따로 둔 이유: 라운드 서비스는 테이블 서비스를 불러온다.
테이블 서비스가 라운드 서비스를 불러오면 서로를 불러오게 된다. 이 파일은 어느 서비스도 불러오지 않는다.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType, TableEvent
from app.rounds import repository
from app.rounds.models import Round
from app.tables.models import GameTable


def open_round(session: AsyncSession, table: GameTable, number: int, scene: str, cause: TableEvent) -> Round:
    """
    새 라운드를 연다. 연 라운드를 돌려준다. 저장하지는 않는다.

    scene 은 이 라운드를 여는 GM 의 서술이다. cause 는 이 라운드를 열게 한 이벤트다(테이블 시작, 앞 라운드의 닫힘).
    이벤트는 "GM 이 서술했다 → 라운드가 열렸다" 순서로 둘을 적는다.

    앞 라운드가 있으면 닫은 것을 먼저 DB 에 보낸 뒤에 부른다(유일 색인 uq_table_rounds_open).
    """
    round_ = Round(table_id=table.id, number=number, scene=scene)
    repository.add_round(session, round_)
    narration = recorder.record(session, table, EventType.GM_NARRATION, payload={'text': scene}, cause=cause)
    recorder.record(session, table, EventType.ROUND_OPENED, payload={'number': number}, cause=narration)
    return round_
