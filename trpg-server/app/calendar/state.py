# trpg-server/app/calendar/state.py

"""
테이블의 시계를 만들고 흘린다. 잠근 테이블의 객체만 고친다. 저장도, 이벤트도, DB 읽기도 하지 않는다.

  - 테이블을 만들 때 판의 시작 시각으로 시계를 단다(app/tables/service.py).
  - 새 라운드가 열릴 때 흐를 시간만큼 흘린다(app/rounds/opener.py). 첫 라운드는 흘리지 않는다. 시작 시각에 열린다.
  - 흐를 시간은 판의 기본이다. 라운드가 닫힐 때 엔진이 늘릴 수 있다(길을 가기, 쉬기, 기다리기).
    늘린 값은 한 번 쓰고 지운다. 사람(방장)이 정하는 길은 없다(#367).

파일을 따로 둔 이유: 라운드를 여는 쪽(opener)이 부른다. opener 는 어느 서비스도 불러오지 않는다.
이 파일도 서비스를 불러오지 않는다.
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
    """다음 라운드가 열릴 때 흐를 시간(분). 엔진이 늘렸으면 그 값, 아니면 판의 기본."""
    if table.clock.next_step_minutes is not None:
        return table.clock.next_step_minutes
    return default_step(table)


def set_next_step(table: GameTable, minutes: int | None) -> None:
    """다음 라운드가 열릴 때 흐를 시간을 정한다. None 이면 판의 기본으로 되돌린다."""
    table.clock.next_step_minutes = minutes


def stretch_next_step(table: GameTable, minutes: int) -> bool:
    """
    다음 라운드가 열릴 때 적어도 minutes 분은 흐르게 한다. 이미 그보다 길면 그대로 둔다. 늘렸으면 True.

    맵에서 시간이 걸리는 길로 갔을 때(app/rounds/map_actions.py), 쉴 때(app/rounds/rests.py),
    모두 기다렸을 때(app/rounds/waits.py) 엔진이 부른다. 여럿이면 가장 긴 것을 따른다. 늘린 값은 한 번 쓰고 지워진다.
    """
    if next_step(table) >= minutes:
        return False
    set_next_step(table, minutes)
    return True


def pass_round(table: GameTable) -> int:
    """새 라운드가 열릴 때 시간을 흘린다. 흐른 분을 돌려준다. 엔진이 늘린 값은 한 번 쓰고 지운다."""
    passed = next_step(table)
    table.clock.minutes += passed
    table.clock.next_step_minutes = None
    return passed


def describe(table: GameTable) -> dict:
    """지금 시각을 이벤트에 적을 모양. 며칠째, 몇 시, 몇 분, 하루의 어느 때."""
    return clock.as_document(table.clock.minutes)


def scene_end(table: GameTable) -> int:
    """
    이번 라운드의 장면이 끝나는 시각(분). 다음 라운드가 열릴 시각이다. 지금 시각에 다음 걸음을 더한다.

    라운드가 닫힐 때 오래 가는 부상이 낫는지 이 시각으로 본다(app/rounds/injuries.py).
    """
    return table.clock.minutes + next_step(table)
