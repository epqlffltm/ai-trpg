# trpg-server/app/engine/treatment.py

"""
치료의 계산. 오래 가는 부상을 치료하는 판정과, 그 결과로 나을 시각이 어떻게 바뀌는지.

무엇을 치료할 수 있는지, 얼마나 어려운지, 실패하면 무엇이 일어나는지는 규칙의 데이터다
(app/engine/ruleset.py 의 Treatment, MishapTable, Injury.treat_difficulty, treat_minutes).

  - 성공하면 나을 시각이 treat_minutes 만큼 앞당겨진다. 이 장면이 끝나는 때에 닿으면 그 자리에서 낫는다.
  - 실패하면 치료 실패 표를 굴린다. 아무 일 없음, 좀 아픔(피해), 덧남(나을 시각이 늦춰짐), 즉사 중 하나다.
  - 시각은 게임 안의 분이다(app/calendar/).

여기의 함수는 DB 도 HTTP 도 모른다. 규칙과 숫자를 받아 계산만 한다. 주사위만 밖에서 받는다.
누구를 치료하는지, 그 사람이 정말 그 부상을 입고 있는지는 부른 쪽이 안다(app/rounds/treatments.py).
"""

from dataclasses import dataclass

from app.engine.check import HinderedCheck, find_difficulty, resolve_hindered
from app.engine.dice import Dice
from app.engine.injury import Hindrance, find_injury
from app.engine.ruleset import Injury, Mishap, MishapRow, MishapTable, Ruleset


@dataclass(frozen=True)
class MishapRoll:
    """
    치료 실패 표를 한 번 굴린 것. 눈과, 그 눈이 든 줄의 일이다.

    delay_minutes 는 덧날 때 늦춰지는 시간(분), magnitude 는 피해의 등급(규칙의 Magnitude.key)이다. 없으면 None.
    """

    roll: int
    kind: Mishap
    delay_minutes: int | None
    magnitude: str | None


def treatable(ruleset: Ruleset, key: str) -> Injury | None:
    """
    이 규칙에서 치료할 수 있는 부상이면 그 부상을 돌려준다. 아니면 None.

    규칙에 치료가 있고, 그 부상에 치료의 난이도가 적혀 있어야 한다. 규칙의 검사가 그 둘을 함께 보장한다.
    """
    if ruleset.treatment is None:
        return None
    injury = find_injury(ruleset, key)
    if injury is None or injury.treat_difficulty is None:
        return None
    return injury


def treat(
    ruleset: Ruleset, injury: Injury, abilities: dict[str, int], dice: Dice, hindrance: Hindrance, bonus: int = 0
) -> HinderedCheck:
    """
    치료 판정을 한 번 한다. 능력은 규칙의 치료 능력, 난이도는 그 부상의 치료 난이도다.

    abilities 는 치료하는 캐릭터의 시트에 적힌 점수, hindrance 는 그 캐릭터의 부상이 치료 능력에 주는 것이다.
    bonus 는 치료에 붙여 쓴 물건의 보정이다(#277). 보정(modifier)에 더한다.
    treatable 이 돌려준 부상에만 쓴다. 그래서 규칙에 치료가 있는지 다시 따지지 않는다.
    """
    difficulty = find_difficulty(ruleset, injury.treat_difficulty)
    score = abilities[ruleset.treatment.ability]
    return resolve_hindered(ruleset, score, difficulty, dice, hindrance, bonus=bonus)


def row_mishap(table: MishapTable, roll: int) -> MishapRow:
    """표에서 이 눈이 든 줄. 표는 모든 눈을 덮는다(MishapTable 의 검사)."""
    return next(row for row in table.rows if row.low <= roll <= row.high)


def roll_mishap(ruleset: Ruleset, dice: Dice) -> MishapRoll:
    """치료 실패 표를 한 번 굴린다. 규칙에 치료가 있을 때만 부른다."""
    table = ruleset.treatment.mishaps
    roll = dice.roll(table.sides)
    row = row_mishap(table, roll)
    return MishapRoll(roll=roll, kind=row.kind, delay_minutes=row.delay_minutes, magnitude=row.magnitude)


def shortened(heals_at: int, injury: Injury) -> int:
    """
    치료에 성공한 뒤의 나을 시각(분). treat_minutes 만큼 앞당긴다.

    이 장면이 끝나는 때보다 앞이 될 수도 있다. 그러면 그 자리에서 낫는다(is_healed).
    """
    return heals_at - injury.treat_minutes


def is_healed(heals_at: int, scene_end: int) -> bool:
    """나을 시각이 이 장면이 끝나는 때이거나 그 앞이면 낫는다. 이 라운드가 닫힐 때 그 자리에서 낫는다."""
    return heals_at <= scene_end


def lengthened(heals_at: int, mishap: MishapRoll) -> int:
    """덧난 뒤의 나을 시각(분). 덧남이 아니면 그대로다."""
    return heals_at + (mishap.delay_minutes or 0)
