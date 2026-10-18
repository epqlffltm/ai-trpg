# game-server/app/rounds/opener.py

"""
라운드를 연다. 장면을 서술한 것과 라운드가 열린 것을 이벤트로 적는다.

라운드가 열리는 때는 둘이다. 테이블을 시작할 때(app/tables/service.py)와 앞 라운드가 닫혔을 때(app/rounds/service.py).
두 곳이 같은 일을 하므로 여기에 한 번만 적는다.

라운드를 열 때 테이블의 시간 제한으로 마감을 정한다(deadline_for). 열린 이벤트에도 마감을 싣는다.
화면은 그것으로 남은 시간을 보여 주고, 서버는 마감이 지난 라운드를 닫는다(app/rounds/clock.py).

라운드를 열 때 테이블의 서술 모델을 그 라운드의 것으로 굳힌다. 그 모델의 값을 걸고 그 모델로 서술한다.
그 라운드의 서술 값을 걸어야 한다고 적는다(app/billing/charges.py). 같은 트랜잭션이다.
결제 서버는 여기서 부르지 않는다. 저장한 뒤에 청구 정리가 건다(app/billing/settler.py).

라운드를 열 때 게임 안의 시간을 흘린다(app/calendar/state.py). 첫 라운드는 판의 시작 시각에 열린다.
열린 이벤트에 그때의 시각과 흐른 시간을 싣는다. 시간을 흘리는 것은 엔진이다. 서술(AI)은 시각을 바꾸지 못한다.

파일을 따로 둔 이유: 라운드 서비스는 테이블 서비스를 불러온다.
테이블 서비스가 라운드 서비스를 불러오면 서로를 불러오게 된다. 이 파일은 어느 서비스도 불러오지 않는다.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import charges
from app.calendar import state as calendar
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.rounds import repository
from app.rounds.models import Round
from app.tables.models import GameTable


def now_utc() -> datetime:
    """
    라운드를 연 시각(UTC). 앱의 시계다.

    마감과 청구의 처음 부를 시각이 이것을 함께 쓴다. 테스트가 바꿔 끼워 앱과 DB 의 시계가 어긋난 환경을 만든다.
    """
    return datetime.now(UTC)


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
    서술 모델은 테이블의 지금 것이다. 아직 서술하지 않은 동안에만 방장이 바꿀 수 있다(app/tables/narration_models.py).
    서술 값의 청구를 함께 적는다(charges.charge_round).
    첫 라운드가 아니면 게임 안의 시간을 흘린다(calendar.pass_round). 방장이 정한 걸음이 있으면 그것으로.

    앞 라운드가 있으면 닫은 것을 먼저 DB 에 보낸 뒤에 부른다(유일 색인 uq_table_rounds_open).
    """
    passed = calendar.pass_round(table) if number > 1 else 0
    opened = now_utc()
    deadline = deadline_for(table, opened)
    round_ = Round(
        table_id=table.id,
        number=number,
        scene=scene,
        deadline_at=deadline,
        narration_model=table.narration_model,
    )
    repository.add_round(session, round_)
    charges.charge_round(session, table, round_, opened)
    narration = recorder.record(session, table, EventType.GM_NARRATION, payload={'text': scene}, cause=cause)
    opened = {
        'number': number,
        'deadline_at': deadline.isoformat() if deadline is not None else None,
        'narration_model': round_.narration_model,
        'clock': calendar.describe(table),
        'passed_minutes': passed,
    }
    recorder.record(session, table, EventType.ROUND_OPENED, payload=opened, cause=narration)
    return round_
