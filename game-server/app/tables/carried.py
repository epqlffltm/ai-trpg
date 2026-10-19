# game-server/app/tables/carried.py

"""
몬스터나 NPC 가 지닌 물건을 세는 규칙(#456, #457). 둘이 같은 규칙을 쓴다.

  - 판에 적은 줄(장비 다음 소지품)의 차례가 줄의 번호(slot)다. 판은 바뀌지 않으므로 번호도 밀리지 않는다.
  - 처음에는 판의 개수 그대로다. 개수가 바뀐 줄만 행(slot, count)을 만든다. 행이 없으면 판의 개수다.
    그래서 행의 표가 생기기 전에 시작한 테이블도 채우지 않고 판의 개수로 읽힌다.
  - 0 이 된 줄은 지니지 않은 것이다. 행은 남긴다. 지우면 판의 개수로 돌아간다.

여기의 함수는 행의 종류를 모른다. 행의 목록(slot 과 count 를 가진 것)과 판의 줄들만 받는다.
행을 새로 만드는 것은 몬스터(app/tables/monster_items.py)와 NPC(app/tables/npc_items.py)가 따로 한다.
DB 를 모른다.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.assets.scenarios.snapshot import CarriedItemSnapshot


class CountRow(Protocol):
    """판의 개수에서 바뀐 줄 하나. 줄의 번호와 지금 개수."""

    slot: int
    count: int


class CarriedLines(Protocol):
    """판에 적은 지닌 물건. 몬스터(MonsterSnapshot)와 NPC 시트(NpcSheetSnapshot)가 이 모양이다."""

    equipment: list[CarriedItemSnapshot]
    inventory: list[CarriedItemSnapshot]


@dataclass(frozen=True)
class Carried:
    """지금 지닌 물건 한 줄. 줄의 번호, 물건, 지금 개수, 장비인지, 떨어질 확률(%)."""

    slot: int
    entry_id: uuid.UUID
    count: int
    equipped: bool
    chance: int


def lines_of(definition: CarriedLines | None) -> list[tuple[CarriedItemSnapshot, bool]]:
    """판에 적은 줄들과 장비인지. 장비 다음 소지품의 차례가 줄의 번호다. 적은 것이 없으면(None) 빈 목록이다."""
    if definition is None:
        return []
    return [(line, True) for line in definition.equipment] + [(line, False) for line in definition.inventory]


def find_row[Row: CountRow](rows: Sequence[Row], slot: int) -> Row | None:
    """그 줄의 바뀐 개수. 바뀐 적이 없으면 None."""
    return next((row for row in rows if row.slot == slot), None)


def count_at(rows: Sequence[CountRow], slot: int, line: CarriedItemSnapshot) -> int:
    """그 줄을 지금 몇 개 지녔는가. 바뀐 적이 없으면 판의 개수다."""
    row = find_row(rows, slot)
    return line.count if row is None else row.count


def carried(rows: Sequence[CountRow], definition: CarriedLines | None) -> list[Carried]:
    """지금 지닌 것. 줄의 차례다. 0 이 된 줄은 뺀다."""
    held = [
        Carried(slot, line.entry_id, count_at(rows, slot, line), equipped, line.chance)
        for slot, (line, equipped) in enumerate(lines_of(definition))
    ]
    return [one for one in held if one.count > 0]


def find_carried(held: list[Carried], entry_id: uuid.UUID) -> Carried | None:
    """지닌 것 중 그 물건의 줄. 지니지 않았으면 None."""
    return next((one for one in held if one.entry_id == entry_id), None)
