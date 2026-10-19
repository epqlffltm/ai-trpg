# game-server/app/tables/monster_items.py

"""
몬스터 한 마리가 지닌 물건(#456). 판의 몬스터에 적은 장비와 소지품을 마리마다 따로 센다.

DB 를 모른다. 이미 읽어 온 마리(TableMonster)와 판의 몬스터(MonsterSnapshot)를 받아 개수를 읽고 고친다.
저장은 부르는 쪽이 한다.

  - 줄의 번호(slot)는 장비 다음 소지품의 차례다. 판은 바뀌지 않으므로 번호도 밀리지 않는다.
  - 처음에는 판의 개수 그대로다. 행이 없다. 개수가 바뀐 줄만 행(TableMonsterItem)을 만든다.
    그래서 이 표가 생기기 전에 시작한 테이블의 마리도 채우지 않고 판의 개수로 읽힌다.
  - 0 이 된 줄은 지니지 않은 것이다. 행은 남긴다.
"""

import uuid
from dataclasses import dataclass

from app.assets.scenarios.snapshot import MonsterItemSnapshot, MonsterSnapshot
from app.tables.models import TableMonster, TableMonsterItem


@dataclass(frozen=True)
class Carried:
    """마리가 지금 지닌 물건 한 줄. 줄의 번호, 물건, 지금 개수, 장비인지, 떨어질 확률(%)."""

    slot: int
    entry_id: uuid.UUID
    count: int
    equipped: bool
    chance: int


def lines_of(definition: MonsterSnapshot) -> list[tuple[MonsterItemSnapshot, bool]]:
    """판의 몬스터가 지닌 줄들과 장비인지. 장비 다음 소지품의 차례가 줄의 번호다."""
    return [(line, True) for line in definition.equipment] + [(line, False) for line in definition.inventory]


def find_row(monster: TableMonster, slot: int) -> TableMonsterItem | None:
    """그 줄의 바뀐 개수. 바뀐 적이 없으면 None."""
    return next((row for row in monster.items if row.slot == slot), None)


def count_at(monster: TableMonster, slot: int, line: MonsterItemSnapshot) -> int:
    """그 줄을 지금 몇 개 지녔는가. 바뀐 적이 없으면 판의 개수다."""
    row = find_row(monster, slot)
    return line.count if row is None else row.count


def carried(monster: TableMonster, definition: MonsterSnapshot) -> list[Carried]:
    """마리가 지금 지닌 것. 줄의 차례다. 0 이 된 줄은 뺀다."""
    held = [
        Carried(slot, line.entry_id, count_at(monster, slot, line), equipped, line.chance)
        for slot, (line, equipped) in enumerate(lines_of(definition))
    ]
    return [one for one in held if one.count > 0]


def set_count(monster: TableMonster, slot: int, count: int) -> None:
    """그 줄의 개수를 고친다. 처음 바뀌는 줄이면 행을 만든다."""
    row = find_row(monster, slot)
    if row is None:
        monster.items.append(TableMonsterItem(monster_id=monster.id, slot=slot, count=count))
        return
    row.count = count
