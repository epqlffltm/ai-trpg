# game-server/app/tables/monster_items.py

"""
몬스터 한 마리가 지닌 물건(#456). 판의 몬스터에 적은 장비와 소지품을 마리마다 따로 센다.

세는 규칙은 NPC 와 같다(app/tables/carried.py). 바뀐 줄만 행(TableMonsterItem)으로 적는다.
여기는 마리의 행을 읽고 만드는 것만 한다.

DB 를 모른다. 이미 읽어 온 마리(TableMonster)와 판의 몬스터(MonsterSnapshot)를 받아 개수를 읽고 고친다.
저장은 부르는 쪽이 한다.
"""

from app.assets.scenarios.snapshot import MonsterSnapshot
from app.tables import carried as carried_items
from app.tables.carried import Carried
from app.tables.models import TableMonster, TableMonsterItem


def carried(monster: TableMonster, definition: MonsterSnapshot) -> list[Carried]:
    """마리가 지금 지닌 것. 줄의 차례다. 0 이 된 줄은 뺀다."""
    return carried_items.carried(monster.items, definition)


def set_count(monster: TableMonster, slot: int, count: int) -> None:
    """그 줄의 개수를 고친다. 처음 바뀌는 줄이면 행을 만든다."""
    row = carried_items.find_row(monster.items, slot)
    if row is None:
        monster.items.append(TableMonsterItem(monster_id=monster.id, slot=slot, count=count))
        return
    row.count = count
