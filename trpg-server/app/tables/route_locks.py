# trpg-server/app/tables/route_locks.py

"""
테이블의 길의 문(#281, table_route_locks)을 만들고 읽고 바꾸는 작은 함수들. 문은 자물쇠와 빗장이다.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 문의 행을 만들거나 고친다. 저장은 부르는 쪽이 한다.

  - 만들기: 테이블을 시작할 때 판에 자물쇠나 빗장을 적은 길마다 하나씩 만든다. 처음 상태는 판의 것이다.
  - 읽기: 길 하나의 자물쇠가 잠겼는가, 빗장이 걸렸는가, 문이 부서졌는가. 문이 없는 길과,
    문이 생기기 전에 시작한 테이블의 길은 잠기지도 걸리지도 부서지지도 않았다.
  - 바꾸기: 잠그기와 열기, 걸기와 풀기, 부수기. 열쇠를 지녔는지, 어느 쪽에 섰는지, 이미 그런지는 부르는 쪽이 본다
    (app/rounds/map_actions.py, app/rounds/door_actions.py). 부서진 문은 열린 채다(DB 의 CHECK 도 막는다).
"""

import uuid

from app.assets.scenarios.snapshot import RouteSnapshot, Snapshot
from app.tables.models import GameTable, TableRouteLock
from app.tables.places import key_of


def has_door(route: RouteSnapshot) -> bool:
    """이 길에 문(자물쇠나 빗장)이 있는가."""
    return route.lock is not None or route.bar is not None


def new_door(table_id: uuid.UUID, route: RouteSnapshot) -> TableRouteLock:
    """길 하나의 문의 처음 상태. 자물쇠와 빗장의 처음 상태는 판의 것이고, 없으면 잠기지도 걸리지도 않았다."""
    return TableRouteLock(
        table_id=table_id,
        from_place=route.from_place,
        to_place=route.to_place,
        locked=route.lock is not None and route.lock.locked,
        barred=route.bar is not None and route.bar.barred,
        broken=False,
    )


def make_route_locks(table_id: uuid.UUID, snapshot: Snapshot) -> list[TableRouteLock]:
    """판에 문을 적은 길마다 지금 상태를 만든다. 판의 길 순서다. 문이 없는 판이면 빈 목록이다."""
    return [new_door(table_id, route) for route in snapshot.routes if has_door(route)]


def find_lock(table: GameTable, route: RouteSnapshot) -> TableRouteLock | None:
    """그 길의 문. 문이 없는 길이거나 문이 생기기 전에 시작한 테이블이면 None."""
    return next((row for row in table.route_locks if (row.from_place, row.to_place) == key_of(route)), None)


def is_locked(table: GameTable, route: RouteSnapshot) -> bool:
    """그 길의 자물쇠가 지금 잠겨 있는가."""
    row = find_lock(table, route)
    return row is not None and row.locked


def is_barred(table: GameTable, route: RouteSnapshot) -> bool:
    """그 길의 빗장이 지금 걸려 있는가."""
    row = find_lock(table, route)
    return row is not None and row.barred


def is_broken(table: GameTable, route: RouteSnapshot) -> bool:
    """그 길의 문이 부서졌는가."""
    row = find_lock(table, route)
    return row is not None and row.broken


def unlock(table: GameTable, route: RouteSnapshot) -> None:
    """그 길의 자물쇠를 연다. 문이 있는 길에만 부른다."""
    find_lock(table, route).locked = False


def lock(table: GameTable, route: RouteSnapshot) -> None:
    """그 길의 자물쇠를 잠근다. 부서지지 않은 문에만 부른다."""
    find_lock(table, route).locked = True


def unbar(table: GameTable, route: RouteSnapshot) -> None:
    """그 길의 빗장을 푼다. 문이 있는 길에만 부른다."""
    find_lock(table, route).barred = False


def bar(table: GameTable, route: RouteSnapshot) -> None:
    """그 길의 빗장을 건다. 부서지지 않은 문에만 부른다."""
    find_lock(table, route).barred = True


def break_open(table: GameTable, route: RouteSnapshot) -> None:
    """그 길의 문을 부순다. 자물쇠도 빗장도 열린 채 다시 잠그거나 걸지 못한다."""
    row = find_lock(table, route)
    row.locked = False
    row.barred = False
    row.broken = True
