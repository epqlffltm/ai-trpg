# game-server/app/engine/drops.py

"""
몬스터를 쓰러뜨렸을 때 무엇이 나오는지 굴린다(#372).

드롭은 줄마다 따로 굴린다. 줄 하나는 물건 하나, 개수, 나올 확률(%)이다.
확률이 100 이면 굴리지 않고 늘 나온다. 아니면 백면체를 굴려 확률 이하가 나오면 나온다.

누가 받는지, 소지품에 어떻게 담는지는 모른다(app/rounds/drops.py). 판도 DB 도 모른다.
줄의 모양만 안다(DropLine). 판의 드롭(DropSnapshot)이 그 모양이다.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.engine.dice import Dice

# 확률의 단위. 백분율이다
PERCENT = 100


class DropLine(Protocol):
    """드롭 한 줄의 모양. 물건, 개수, 나올 확률(1~100)."""

    entry_id: uuid.UUID
    count: int
    chance: int


@dataclass(frozen=True)
class Dropped:
    """나온 물건 하나. 무엇이 몇 개다."""

    entry_id: uuid.UUID
    count: int


def comes_out(chance: int, dice: Dice) -> bool:
    """확률 chance(%)로 나오는가. 100 이면 굴리지 않는다."""
    if chance >= PERCENT:
        return True
    return dice.roll(PERCENT) <= chance


def roll_drops(lines: list[DropLine], dice: Dice) -> list[Dropped]:
    """줄마다 따로 굴려 나온 물건들을 돌려준다. 줄의 순서다. 하나도 안 나왔으면 빈 목록이다."""
    return [Dropped(entry_id=line.entry_id, count=line.count) for line in lines if comes_out(line.chance, dice)]
