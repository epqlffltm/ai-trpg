# trpg-server/app/calendar/responses.py

"""
테이블의 시계를 응답의 모양(ClockOut)으로 바꾼다.

시계의 길(GET /tables/{id}/clock, app/calendar/router.py)과 테이블 하나의 응답(TableDetail, app/tables/router.py)이
함께 쓴다. 두 곳의 값이 갈라지지 않게 한 곳에 둔다(#428).
시계는 테이블과 함께 읽힌다(app/calendar/models.py 의 selectin). 그래서 DB 를 다시 읽지 않는다.
"""

from app.calendar import clock, state
from app.calendar.schemas import ClockOut
from app.tables.models import GameTable


def to_clock(table: GameTable) -> ClockOut:
    """테이블의 시계를 응답으로 바꾼다."""
    now = clock.read_time(table.clock.minutes)
    return ClockOut(
        day=now.day,
        hour=now.hour,
        minute=now.minute,
        time_of_day=now.time_of_day,
        next_step_minutes=state.next_step(table),
        default_step_minutes=state.default_step(table),
        step_changed=table.clock.next_step_minutes is not None,
    )
