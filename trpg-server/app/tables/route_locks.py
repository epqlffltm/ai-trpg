# trpg-server/app/tables/route_locks.py

"""
테이블의 길의 자물쇠(#281, table_route_locks)를 만들고 읽고 바꾸는 작은 함수들.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 자물쇠의 행을 만들거나 고친다. 저장은 부르는 쪽이 한다.

  - 만들기: 테이블을 시작할 때 판에 자물쇠를 적은 길마다 하나씩 만든다. 처음 상태는 판의 것(locked)이다.
  - 읽기: 길 하나가 지금 잠겨 있는가. 자물쇠가 없는 길과, 자물쇠가 생기기 전에 시작한 테이블의 길은 잠겨 있지 않다.
  - 바꾸기: 열기(unlock). 열쇠를 지녔는지는 부르는 쪽이 본다(app/rounds/map_actions.py). 잠그기는 다음에 더한다.
"""

import uuid

from app.assets.scenarios.snapshot import RouteSnapshot, Snapshot
from app.tables.models import GameTable, TableRouteLock
from app.tables.places import key_of


def make_route_locks(table_id: uuid.UUID, snapshot: Snapshot) -> list[TableRouteLock]:
    """판에 자물쇠를 적은 길마다 지금 상태를 만든다. 판의 길 순서다. 자물쇠가 없는 판이면 빈 목록이다."""
    return [
        TableRouteLock(
            table_id=table_id, from_place=route.from_place, to_place=route.to_place, locked=route.lock.locked
        )
        for route in snapshot.routes
        if route.lock is not None
    ]


def find_lock(table: GameTable, route: RouteSnapshot) -> TableRouteLock | None:
    """그 길의 자물쇠. 자물쇠가 없는 길이거나 자물쇠가 생기기 전에 시작한 테이블이면 None."""
    return next((row for row in table.route_locks if (row.from_place, row.to_place) == key_of(route)), None)


def is_locked(table: GameTable, route: RouteSnapshot) -> bool:
    """그 길이 지금 잠겨 있는가."""
    row = find_lock(table, route)
    return row is not None and row.locked


def unlock(table: GameTable, route: RouteSnapshot) -> None:
    """그 길의 자물쇠를 연다. 잠긴 자물쇠에만 부른다(is_locked)."""
    find_lock(table, route).locked = False
