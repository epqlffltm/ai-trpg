# game-server/app/calendar/state.py

"""
테이블의 시계를 만들고 흘린다. 잠근 테이블의 객체만 고친다. 저장도, 이벤트도, DB 읽기도 하지 않는다.

  - 테이블을 만들 때 판의 시작 시각으로 시계를 단다(app/tables/service.py).
  - 새 라운드가 열릴 때 흐를 시간만큼 흘린다(app/rounds/opener.py). 첫 라운드는 흘리지 않는다. 시작 시각에 열린다.
  - 흐를 시간은 방장이 정한 값이 있으면 그것, 없으면 판의 기본이다. 흘린 뒤에는 방장이 정한 값을 지운다.

파일을 따로 둔 이유: 라운드를 여는 쪽(opener)이 부른다. opener 는 어느 서비스도 불러오지 않는다.
이 파일도 서비스를 불러오지 않는다(app/calendar/service.py 는 테이블 서비스를 불러온다).
"""

from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.calendar import clock
from app.calendar.models import TableClock
from app.tables.models import GameTable


def start_clock(table: GameTable, snapshot: Snapshot) -> None:
    """만드는 테이블에 판의 시작 시각을 가리키는 시계를 단다."""
    minutes = clock.start_minutes(snapshot.clock.start_day, snapshot.clock.start_hour)
    table.clock = TableClock(minutes=minutes)


def default_step(table: GameTable) -> int:
    """이 테이블의 판이 정한 라운드 하나에 흐르는 기본 시간(분)."""
    return read_snapshot(table.content).clock.round_minutes


def next_step(table: GameTable) -> int:
    """다음 라운드가 열릴 때 흐를 시간(분). 방장이 정했으면 그 값, 아니면 판의 기본."""
    if table.clock.next_step_minutes is not None:
        return table.clock.next_step_minutes
    return default_step(table)


def set_next_step(table: GameTable, minutes: int | None) -> None:
    """다음 라운드가 열릴 때 흐를 시간을 정한다. None 이면 판의 기본으로 되돌린다."""
    table.clock.next_step_minutes = minutes


def pass_round(table: GameTable) -> int:
    """새 라운드가 열릴 때 시간을 흘린다. 흐른 분을 돌려준다. 방장이 정한 값은 한 번 쓰고 지운다."""
    passed = next_step(table)
    table.clock.minutes += passed
    table.clock.next_step_minutes = None
    return passed


def describe(table: GameTable) -> dict:
    """지금 시각을 이벤트에 적을 모양. 며칠째, 몇 시, 몇 분, 하루의 어느 때."""
    now = clock.read_time(table.clock.minutes)
    return {'day': now.day, 'hour': now.hour, 'minute': now.minute, 'time_of_day': now.time_of_day}
