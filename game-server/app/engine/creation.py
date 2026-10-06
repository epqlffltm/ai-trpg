# game-server/app/engine/creation.py

"""
플레이어가 능력치를 정한 캐릭터의 시트를 만드는 계산.

프리젠과 기본 시트는 제작자가 숫자를 다 적어 둔 것이다. 여기는 그렇지 않은 경우를 다룬다.
플레이어가 능력치의 점수를 정하면, 최대 HP 는 플레이어가 적지 않고 규칙으로 구한다.

  최대 HP = 제작자가 정한 기준값 + 능력치의 보정. 제작자가 정한 상한을 넘지 않고, 1 아래로 내려가지 않는다.

기준값과 상한은 시나리오의 것이고(제작자가 시나리오의 위험도에 맞춰 정한다),
어느 능력치의 보정을 더하는지는 규칙의 것이다(Ruleset.hp_ability).

여기의 함수는 DB 도 HTTP 도 모른다.
"""

from app.engine.check import modifier_of
from app.engine.ruleset import Ruleset
from app.engine.sheet import Sheet


def hp_bonus(ruleset: Ruleset, abilities: dict[str, int]) -> int:
    """
    능력치에서 최대 HP 에 더해지는 값. 규칙이 정한 능력치의 보정이다. 음수일 수 있다.

    규칙이 그런 능력치를 정하지 않았으면 0 이다.
    """
    if ruleset.hp_ability is None:
        return 0
    return modifier_of(ruleset, abilities[ruleset.hp_ability])


def max_hp_for(ruleset: Ruleset, abilities: dict[str, int], base: int, cap: int) -> int:
    """
    플레이어가 정한 능력치로 최대 HP 를 구한다.

    base 는 제작자가 정한 기준값, cap 은 제작자가 정한 상한이다. 결과는 1 이상 cap 이하다.
    """
    return max(1, min(cap, base + hp_bonus(ruleset, abilities)))


def build_sheet(ruleset: Ruleset, abilities: dict[str, int], base: int, cap: int) -> Sheet:
    """
    플레이어가 정한 능력치로 시트를 만든다. 최대 HP 를 구해 채운다.

    규칙에 맞는지 본 능력치에만 쓴다(app/engine/sheet.py 의 abilities_fit).
    """
    return Sheet(abilities=abilities, max_hp=max_hp_for(ruleset, abilities, base, cap))
