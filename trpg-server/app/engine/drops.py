# trpg-server/app/engine/drops.py

"""
몬스터를 쓰러뜨렸을 때 지닌 것이 떨어지는지 굴린다(#372, #456).

줄 하나는 마리가 지닌 물건 하나와 떨어질 확률(%)이다. 줄마다 따로 굴린다.
확률이 100 이면 굴리지 않고 늘 떨어진다. 아니면 백면체를 굴려 확률 이하가 나오면 떨어진다.

무엇을 지녔는지(app/tables/monster_items.py), 누가 받는지(app/rounds/drops.py)는 모른다. 판도 DB 도 모른다.
"""

import uuid
from dataclasses import dataclass

from app.engine.dice import Dice

# 확률의 단위. 백분율이다
PERCENT = 100


@dataclass(frozen=True)
class Dropped:
    """떨어진 물건 하나. 무엇이 몇 개다."""

    entry_id: uuid.UUID
    count: int


def comes_out(chance: int, dice: Dice) -> bool:
    """확률 chance(%)로 떨어지는가. 100 이면 굴리지 않는다."""
    if chance >= PERCENT:
        return True
    return dice.roll(PERCENT) <= chance
