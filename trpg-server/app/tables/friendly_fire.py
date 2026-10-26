# trpg-server/app/tables/friendly_fire.py

"""
앉은 사람끼리 해칠 수 있는 정도를 정한다(#803). 순수한 계산이다.

  - 자기 자신에게 하는 것(자폭 포함)은 늘 된다(다 됨).
  - 다른 사람에게는 테이블의 설정(방장)과 맞는 쪽의 설정(본인이 받아들이는 정도) 중 낮은 것이 든다.
    방장이 다 됨으로 해도 본인이 받아들이기 전에는 해치지 못한다. 본인이 다 받아들여도 테이블이 끄면 못 한다.

받을 때(app/rounds/acceptance.py)와 라운드를 닫을 때(app/rounds/friendly_fire.py) 같은 함수로 본다.
그사이에 설정이 바뀌었으면 닫을 때의 것이 든다.

DB 도 HTTP 도 모른다.
"""

import uuid

from app.tables.models import FriendlyFire, GameTable, TableMember

# 낮은 것부터. 둘 중 낮은 것을 고를 때 쓴다
ORDER = (FriendlyFire.OFF, FriendlyFire.PRANK, FriendlyFire.FULL)


def lower(first: FriendlyFire, second: FriendlyFire) -> FriendlyFire:
    """둘 중 낮은 정도."""
    return min(first, second, key=ORDER.index)


def level_toward(table: GameTable, actor_id: uuid.UUID, target: TableMember) -> FriendlyFire:
    """actor_id 가 target 을 해칠 수 있는 정도. 자기 자신이면 늘 다 됨이다."""
    if target.user_id == actor_id:
        return FriendlyFire.FULL
    return lower(FriendlyFire(table.friendly_fire), FriendlyFire(target.friendly_fire))


def is_prank(level: FriendlyFire) -> bool:
    """장난만인가. HP 를 1 아래로 내리지 못하고 짧은 부상만 입힌다."""
    return level == FriendlyFire.PRANK
