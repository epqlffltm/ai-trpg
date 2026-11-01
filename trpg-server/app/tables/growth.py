# trpg-server/app/tables/growth.py

"""
캐릭터의 성장(#286). 경험치를 모아 레벨이 오른다. 규칙은 판의 룰북의 레벨표(Ruleset.progression)다.

  - 캐릭터는 레벨 1, 경험치 0 에서 시작한다. 레벨은 모은 경험치와 레벨표로 정한다(level_of). 따로 적지 않는다.
  - 경험치를 주는 것은 엔진뿐이다. 퀘스트의 보상(각자 다), 쓰러뜨린 몬스터와 판의 사건(#286 ②, 시나리오의
    xp_split 대로 각자 다 또는 받는 사람 수로 나눔, share_of)이다. 방장도 AI 도 주지 못한다.
  - 경험치가 레벨표의 다음 줄에 닿으면 그 레벨이 된다. 한 번에 여러 레벨을 오를 수 있다.
    오른 레벨마다 최대 HP 에 그 줄의 양을 더하고(지금 HP 도 그만큼, 쓰러져 있으면 최대만), 능력치 점수를 쌓는다.
    최대 HP 는 시트의 상한(SHEET_MAX_HP)을 넘지 않는다. 경험치도 상한(PROGRESSION_MAX_XP)까지만 모은다.
  - 마지막 레벨에 닿은 뒤에도 경험치는 모인다(상한까지). 레벨은 그대로다.
  - 쌓인 능력치 점수를 능력치에 놓는 것은 플레이어가 고른다(raise_abilities, #286 ③). 한 점이 능력치 1 이다.
    규칙의 상한(score_max)을 넘지 못한다. 최대 HP 에 닿는 능력치(Ruleset.hp_ability)를 올려 보정이 오르면
    최대 HP 도 그만큼 오른다(지금 HP 도, 쓰러져 있으면 최대만).
    수치의 최대는 능력치로 그때그때 구하므로 따로 고치지 않는다.
  - 성장이 없는 규칙(progression 이 None)이면 아무것도 하지 않는다.

DB 를 모른다. 시트의 칸만 고친다. 저장은 부르는 쪽이 한다.
"""

from app.assets.models import XpSplit
from app.engine.creation import hp_bonus
from app.engine.ruleset import PROGRESSION_MAX_XP, Progression, Ruleset
from app.engine.sheet import SHEET_MAX_HP
from app.tables.errors import Conflict, TableConflictError, TableOptionError
from app.tables.models import TableMember, TableSheet


def level_of(xp: int, progression: Progression | None) -> int:
    """그 경험치의 레벨. 1 부터다. 성장이 없는 규칙이면 늘 1 이다."""
    if progression is None:
        return 1
    return 1 + sum(1 for level in progression.levels if level.xp <= xp)


def next_level_xp(xp: int, progression: Progression | None) -> int | None:
    """다음 레벨이 되는 누적 경험치. 마지막 레벨이거나 성장이 없는 규칙이면 None."""
    if progression is None:
        return None
    return next((level.xp for level in progression.levels if level.xp > xp), None)


def is_downed(sheet: TableSheet) -> bool:
    """쓰러져 있는가. 쓰러진 캐릭터는 최대 HP 만 오르고 지금 HP 는 그대로다(일어나는 것은 회복의 일이다)."""
    return sheet.hp == 0


def raise_max_hp(sheet: TableSheet, amount: int) -> int:
    """최대 HP 를 그만큼 올린다(상한까지). 쓰러져 있지 않으면 지금 HP 도 같이 올린다. 실제로 올린 양을 돌려준다."""
    raised = min(sheet.max_hp + amount, SHEET_MAX_HP) - sheet.max_hp
    if not is_downed(sheet):
        sheet.hp += raised
    sheet.max_hp += raised
    return raised


def gain(sheet: TableSheet, amount: int, progression: Progression | None) -> dict | None:
    """
    시트에 경험치를 준다. 레벨이 오르면 오른 레벨마다 최대 HP 와 능력치 점수를 받는다.
    이벤트에 적을 모양을 돌려준다. 성장이 없는 규칙이거나 줄 경험치가 없으면 아무것도 하지 않고 None.

    count 는 받은 경험치(상한에 닿으면 덜 받는다, capped), total 은 그 뒤의 경험치다.
    level 은 그 뒤의 레벨, previous_level 은 그 앞의 레벨이다. 같으면 오르지 않았다.
    max_hp 는 그 뒤의 최대 HP, points 는 그 뒤의 쌓인 능력치 점수다.
    """
    if progression is None or amount <= 0:
        return None
    previous_level = level_of(sheet.xp, progression)
    count = min(amount, PROGRESSION_MAX_XP - sheet.xp)
    sheet.xp += count
    level = level_of(sheet.xp, progression)
    reached = progression.levels[previous_level - 1 : level - 1]
    raise_max_hp(sheet, sum(step.max_hp for step in reached))
    sheet.points += sum(step.points for step in reached)
    return {
        'count': count,
        'total': sheet.xp,
        'capped': count < amount,
        'previous_level': previous_level,
        'level': level,
        'max_hp': sheet.max_hp,
        'points': sheet.points,
    }


def leveled(gained: dict | None) -> bool:
    """그 경험치로 레벨이 올랐는가."""
    return gained is not None and gained['level'] > gained['previous_level']


def share_of(amount: int, receivers: int, split: XpSplit) -> int:
    """
    한 사람이 받는 몫. 각자 다(each)면 그대로, 나눔(share)이면 받는 사람 수로 나눈 몫이다(나머지는 버린다).

    받는 사람이 없으면 0 이다.
    """
    if receivers == 0:
        return 0
    return amount if split == XpSplit.EACH else amount // receivers


def grant(members: list[TableMember], amount: int, split: XpSplit, progression: Progression | None) -> list[dict]:
    """
    그 사람들의 지금 캐릭터에게 경험치를 나눠 준다(몬스터, 사건, #286 ②). 앉은 순서로, 받은 사람마다
    누구(user_id, character_name)와 받은 것(xp, gain 의 모양)을 돌려준다. 퀘스트의 보상(rewards)과 같은 모양이다.

    몫이 0 이거나(나누어 떨어지지 않게 작다) 성장이 없는 규칙이면 아무도 받지 않는다(빈 목록).
    """
    each = share_of(amount, len(members), split)
    given = [(member, gain(member.sheet, each, progression)) for member in members]
    return [
        {'user_id': str(member.user_id), 'character_name': member.character_name, 'xp': gained}
        for member, gained in given
        if gained is not None
    ]


def require_raisable(ruleset: Ruleset, sheet: TableSheet, raises: dict[str, int]) -> None:
    """
    쌓인 점수로 그만큼 올릴 수 있는지 본다(#286 ③).

    규칙에 없는 능력치면 TableOptionError(raises), 점수가 모자라면 TableConflictError(not_enough_points),
    상한(score_max)을 넘으면 TableConflictError(ability_at_max).
    """
    known = {ability.key for ability in ruleset.abilities}
    if any(key not in known for key in raises):
        raise TableOptionError('raises')
    if sum(raises.values()) > sheet.points:
        raise TableConflictError(Conflict.NOT_ENOUGH_POINTS)
    if any(sheet.abilities[key] + amount > ruleset.score_max for key, amount in raises.items()):
        raise TableConflictError(Conflict.ABILITY_AT_MAX)


def raise_abilities(ruleset: Ruleset, sheet: TableSheet, raises: dict[str, int]) -> list[dict]:
    """
    쌓인 능력치 점수를 능력치에 놓는다(#286 ③). 능력치마다 앞뒤의 점수를 규칙의 차례로 돌려준다.

    못 놓으면 아무것도 바꾸지 않고 오류다(require_raisable). 최대 HP 에 닿는 능력치의 보정이 오르면 최대 HP 도 오른다.
    """
    require_raisable(ruleset, sheet, raises)
    before = dict(sheet.abilities)
    # JSONB 칸은 새 묶음을 넣어야 바뀐 것으로 적힌다
    sheet.abilities = {key: score + raises.get(key, 0) for key, score in before.items()}
    sheet.points -= sum(raises.values())
    raise_max_hp(sheet, hp_bonus(ruleset, sheet.abilities) - hp_bonus(ruleset, before))
    return [
        {'ability': ability.key, 'name': ability.name, 'from': before[ability.key], 'to': sheet.abilities[ability.key]}
        for ability in ruleset.abilities
        if ability.key in raises
    ]
