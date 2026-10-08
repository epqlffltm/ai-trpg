# game-server/app/engine/death.py

"""
죽음의 굴림. 쓰러진 캐릭터가 죽는지, 고비를 넘기는지를 주사위가 정한다.

굴리는 법은 규칙에서 온다(Ruleset.death_save). 눈이 목표값 이상이면 성공이고, 성공과 실패를 따로 센다.
실패가 정해진 수만큼 모이면 죽고, 성공이 정해진 수만큼 모이면 고비를 넘긴다.

지금까지 센 것(성공 몇 번, 실패 몇 번)은 밖에서 받는다. 여기서는 한 번 굴리고, 그 뒤의 수를 돌려준다.
센 것을 어디에 적어 두는지, 언제 굴리는지는 부르는 쪽의 일이다.

주사위는 밖에서 받는다(app/engine/dice.py). 여기의 함수는 DB 도 HTTP 도 모른다.
"""

import enum
from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.ruleset import DeathSave, Ruleset


class Fate(enum.StrEnum):
    """쓰러진 캐릭터의 갈림길."""

    # 죽어 가는 중. 라운드가 닫힐 때마다 굴린다
    DYING = 'dying'
    # 고비를 넘겼다. 더 굴리지 않는다. 쓰러진 채로 있다
    STABLE = 'stable'
    # 죽었다. 되돌릴 수 없다
    DEAD = 'dead'


@dataclass(frozen=True)
class DeathSaveRoll:
    """죽음의 굴림 한 번의 결과. 과정을 모두 담는다."""

    # 주사위의 눈과 넘어야 하는 값
    roll: int
    target: int
    success: bool
    # 이번 굴림까지 센 성공과 실패의 수
    successes: int
    failures: int
    # 이번 굴림 뒤의 갈림길
    fate: Fate


def fate_of(death_save: DeathSave, successes: int, failures: int) -> Fate:
    """
    센 성공과 실패로 갈림길을 정한다.

    실패를 먼저 본다. 둘이 함께 찰 수는 없지만(한 번에 하나씩 오른다), 찼다면 죽은 것으로 본다.
    """
    if failures >= death_save.failures:
        return Fate.DEAD
    if successes >= death_save.successes:
        return Fate.STABLE
    return Fate.DYING


def is_rolling(death_save: DeathSave, successes: int, failures: int) -> bool:
    """이 캐릭터가 아직 굴려야 하는가. 죽어 가는 중일 때만 굴린다."""
    return fate_of(death_save, successes, failures) == Fate.DYING


def roll_death_save(ruleset: Ruleset, successes: int, failures: int, dice: Dice) -> DeathSaveRoll | None:
    """
    죽음의 굴림을 한 번 굴린다. successes 와 failures 는 지금까지 센 것이다.

    규칙에 죽음의 굴림이 없거나, 이미 갈림길이 정해졌으면(고비를 넘겼거나 죽었으면) 굴리지 않고 None.
    그때는 주사위를 건드리지 않는다.
    능력치의 보정을 더하지 않는다. 눈이 그대로 결과다.
    """
    death_save = ruleset.death_save
    if death_save is None or not is_rolling(death_save, successes, failures):
        return None
    roll = dice.roll(ruleset.die)
    success = roll >= death_save.target
    successes += 1 if success else 0
    failures += 0 if success else 1
    return DeathSaveRoll(
        roll=roll,
        target=death_save.target,
        success=success,
        successes=successes,
        failures=failures,
        fate=fate_of(death_save, successes, failures),
    )
