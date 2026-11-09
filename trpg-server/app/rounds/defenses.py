# trpg-server/app/rounds/defenses.py

"""
맞서는 굴림의 양쪽을 만든다(#254). 몬스터의 차례(app/rounds/monster_attacks.py), NPC 의 차례
(app/rounds/npc_attacks.py), 캐릭터의 타격(app/rounds/checks.py 의 judge_check)이 쓴다.
계산은 엔진이 한다(app/engine/check.py 의 resolve_opposed).

판의 규칙에 막는 규칙(Ruleset.defense)이 있으면 공격은 맞서는 굴림이다. 없으면(그 전에 굳힌 판) 고정 난이도다.
  - 공격하는 쪽: 공격의 능력치의 점수. 무기의 공격 보정과, 공격의 난이도의 보정(기본 난이도가 0, difficulty_shift)을
    더한다. 입은 부상의 영향을 받는다.
  - 받는 쪽: 공격에 적은 막는 능력치(AttackSnapshot.defense), 없으면 규칙의 것의 점수. 맞은 부위의 방어가 목표값을
    올리는 규칙(ac)이면 그 양을 받는 쪽에 더한다. 받는 쪽도 입은 부상의 영향을 받는다.
  - 공격의 합이 받는 쪽의 합보다 높아야 맞는다. 같으면 막는다.
  - 캐릭터의 타격(치기, 던지기, 물건과 기술의 피해): 행동의 능력치와 난이도로 공격한다. 노려 치기의 대가(목표값을
    올리는 양)는 공격에서 빼고, 불리함이면 공격이 불리하다. 받는 쪽은 규칙의 막는 능력치로 굴린다(행동에는 막는
    능력치가 없다). 방어 태세의 동료를 치면 공격이 불리하다.

DB 를 모른다. 상태를 고치지 않는다.
"""

from collections.abc import Mapping, Sequence

from app.assets.scenarios.snapshot import AttackSnapshot
from app.engine import action as actions
from app.engine import check as checks
from app.engine.action import CheckAction
from app.engine.check import HinderedCheck, Side
from app.engine.ruleset import Ruleset
from app.rounds import injuries as round_injuries
from app.rounds.blows import Blow
from app.rounds.cast import CastMember
from app.tables.models import TableMember


def defending_ability(ruleset: Ruleset, attack: AttackSnapshot) -> str | None:
    """이 공격을 받는 쪽이 굴리는 능력치. 공격에 적은 것, 없으면 규칙의 것이다. 규칙에 막는 규칙이 없으면 None."""
    if ruleset.defense is None:
        return None
    return attack.defense or ruleset.defense.ability


def attacker_side(
    ruleset: Ruleset,
    abilities: Mapping[str, int],
    injuries: Sequence,
    attack: AttackSnapshot,
    blow: Blow,
    guarded: bool = False,
) -> Side:
    """
    공격하는 쪽. 공격의 능력치의 점수에 무기의 보정과 난이도의 보정을 더한다. 입은 부상의 영향을 받는다.

    받는 쪽이 방어 태세면(guarded, #254, app/rounds/guards.py) 불리하다.
    """
    difficulty = checks.find_difficulty(ruleset, attack.difficulty)
    shift = checks.difficulty_shift(ruleset, difficulty)
    hindrance = round_injuries.hindrance_for(ruleset, injuries, attack.ability)
    return Side(score=abilities[attack.ability], adjust=blow.bonus + shift, hindrance=hindrance, disadvantage=guarded)


def defender_side(
    ruleset: Ruleset, abilities: Mapping[str, int], injuries: Sequence, ability: str, blow: Blow | None
) -> Side:
    """
    받는 쪽. 막는 능력치의 점수에, 맞은 부위의 방어가 올리는 양(ac)을 더한다. 입은 부상의 영향을 받는다.

    타격이 아니면(blow 가 None, 피해 없는 효과로 맞히기) 부위가 없어 더하지 않는다.
    """
    hindrance = round_injuries.hindrance_for(ruleset, injuries, ability)
    raise_by = blow.raise_by if blow is not None else 0
    return Side(score=abilities[ability], adjust=raise_by, hindrance=hindrance)


def member_defense(ruleset: Ruleset, member: TableMember, attack: AttackSnapshot, blow: Blow) -> Side | None:
    """앉은 사람이 이 공격을 막는 쪽. 고정 난이도의 판이면 None."""
    ability = defending_ability(ruleset, attack)
    if ability is None:
        return None
    sheet = member.sheet
    return defender_side(ruleset, sheet.abilities, sheet.injuries, ability, blow)


def npc_defense(ruleset: Ruleset, person: CastMember, attack: AttackSnapshot, blow: Blow) -> Side | None:
    """인물이 이 공격을 막는 쪽. 고정 난이도의 판이면 None."""
    ability = defending_ability(ruleset, attack)
    if ability is None:
        return None
    return defender_side(ruleset, person.npc.abilities, person.npc.injuries, ability, blow)


def strike_side(
    ruleset: Ruleset,
    abilities: Mapping[str, int],
    injuries: Sequence,
    action: CheckAction,
    blow: Blow | None,
    guarded: bool = False,
) -> Side:
    """
    캐릭터의 판정에서 공격하는 쪽. 행동의 능력치의 점수에 무기의 보정과 난이도의 보정을 더한다.
    타격이 아니면(blow 가 None, 피해 없는 효과로 맞히기) 무기의 보정이 없다.

    노려 치기(app/engine/action.py 의 called_shot_terms)는 목표값을 올리는 만큼 빼거나, 불리하게 한다.
    받는 쪽이 방어 태세면(guarded) 불리하다. 입은 부상의 영향을 받는다.
    """
    difficulty = checks.find_difficulty(ruleset, action.difficulty)
    aim_raise, aim_disadvantage = actions.called_shot_terms(ruleset, action)
    shift = checks.difficulty_shift(ruleset, difficulty) - aim_raise
    hindrance = round_injuries.hindrance_for(ruleset, injuries, action.ability)
    return Side(
        score=abilities[action.ability],
        adjust=(blow.bonus if blow is not None else 0) + shift,
        hindrance=hindrance,
        disadvantage=aim_disadvantage or guarded,
    )


def struck_ability(ruleset: Ruleset) -> str | None:
    """캐릭터의 타격을 받는 쪽이 굴리는 능력치. 규칙의 것이다. 규칙에 막는 규칙이 없으면 None(고정 난이도)."""
    return ruleset.defense.ability if ruleset.defense is not None else None


def defense_document(ability: str, rolled: HinderedCheck) -> dict:
    """
    차례의 outcome 에 적을 받는 쪽의 굴림. 능력치, 눈, 보정, 합, 목표값, 막았는지, 굴린 합들, 부상의 영향이다.

    over 의 목표값은 공격의 합이다(그 이상이면 막는다).
    """
    check = rolled.check
    return {
        'ability': ability,
        'roll': check.roll,
        'modifier': check.modifier,
        'total': check.total,
        'target': check.target,
        'success': check.success,
        'style': check.style,
        'faces': list(check.faces),
        'rolls': list(rolled.rolls),
        'hindrance': round_injuries.hindrance_document(rolled),
    }
