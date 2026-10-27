# trpg-server/app/rounds/skill_actions.py

"""
기술과 주문을 쓰는 행동(#805)을 받고 판정한다.

기술이 무엇인지는 룰북의 데이터다(rules.skills: 이름, 비용, 대상, 효과). 누가 아는지는 시트에 있다(시나리오의 시트에서
복사한 table_sheets.skills). 효과는 소모품과 같은 엔진으로 낸다(app/rounds/item_actions.py 의 apply_to_member).

받을 때(accept_skill)
  - 룰북에 없는 기술이면 ActionNotInRulesError(skill), 모르는 기술이면 RoundConflictError(skill_not_known).
  - 비용이 모자라면 RoundConflictError(skill_cost_short).
  - 피해가 없는 기술에 죽이려 한다(lethal)를 적었으면 ActionNotInRulesError(lethal).
  - 상대에게 쓰는 기술(#805 ②)은 인물이나 몬스터 하나를 겨눈다. 앉은 사람을 적었거나 아무도 겨누지 않았으면
    ActionTargetError(target). 겨눈 쪽이 이번 장면에 있는지는 치기와 같이 부르는 쪽(app/rounds/acceptance.py)이 본다.
  - 자신과 동료에게 쓰는 기술에 인물이나 몬스터를 적었으면 ActionTargetError(npc, monster).
  - 자신에게만 쓰는 기술에 남을 적으면 ActionTargetError(target). 받을 사람이 앉아 있지 않으면 ActionTargetError,
    죽었으면 RoundConflictError(patient_dead). 비워 둔 대상은 자기 자신으로 채운다.
  - 해로운 효과(피해, 부상, 수치를 내림)가 있는 기술을 동료에게 쓰는 것은 치기와 같다(#803, friendly_fire).
닫을 때(judge_skill). 들어온 순서로 한 번만 한다.
  - 다시 본다. 받을 사람이 없거나 해칠 수 없게 바뀌었거나 비용이 모자라면 쓰지 못한다. 그때는 비용도 내지 않는다.
    겨눈 몬스터가 죽었거나 다른 곳에 있어도 쓰지 못한다(치기와 같은 target_gone 도 적는다).
  - 비용을 먼저 낸다(쓴 사람의 수치가 준다).
  - 굴리지 않는 기술(자신에게, 판정이 없는 기술을 동료에게)은 효과들을 적힌 차례대로 낸다. 빗나가는 일이 없다.
  - 굴리는 기술(상대에게, 판정이 있는 기술을 자기 아닌 동료에게, #805 ②)은 맞히는 판정을 한다. 물건을 던지는 것과
    같다(app/rounds/item_targets.py). 피해가 있으면 그 등급의 타격으로 판정한다. 맞히면 효과가 든다.
    빗나가도 비용은 낸다.

DB 를 모른다. 시트와 맞은 쪽의 상태를 고친다. 저장하지 않는다.
"""

from app.engine.action import SkillAction
from app.engine.injury import Trigger
from app.engine.item_effects import EffectKind, first_of, is_harmful
from app.engine.resources import find_resource
from app.engine.ruleset import Ruleset, Skill, SkillCost, SkillTarget
from app.rounds import friendly_fire
from app.rounds.checks import judge_check, monster_gone
from app.rounds.effects import Judging
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, Conflict, RoundConflictError
from app.rounds.item_actions import apply_to_member, living, person
from app.rounds.item_targets import apply_after_hit, landed, mark_harm, target_of, to_check
from app.tables import resources, sheets
from app.tables import state as table_state
from app.tables.models import GameTable, TableMember, TableSheet


class Reason:
    """쓰지 못한 까닭. 결과의 reason 에 적는다."""

    # 그 기술을 모른다(받은 뒤에 시트가 바뀌었다. 새 캐릭터로 바뀐 것 같은 일)
    NOT_KNOWN = 'not_known'
    # 비용이 모자랐다. 앞 차례에 수치가 줄었다
    COST_SHORT = 'cost_short'
    # 받을 사람이 떠났거나 죽었다. 해로운 기술을 쓸 동료가 쓰러졌거나 다른 곳에 있다
    TARGET_GONE = 'target_gone'
    # 해로운 기술을 쓸 동료가 받아들이지 않게 바뀌었다(#803)
    FRIENDLY_FIRE_OFF = 'friendly_fire_off'


def find_skill(ruleset: Ruleset, key: str) -> Skill | None:
    """규칙에서 기술을 찾는다. 없으면 None."""
    return next((skill for skill in ruleset.skills if skill.key == key), None)


def knows(sheet: TableSheet, key: str) -> bool:
    """이 시트가 그 기술을 아는가."""
    return key in (sheet.skills or [])


def affordable(ruleset: Ruleset, sheet: TableSheet, cost: SkillCost | None) -> bool:
    """비용을 낼 수 있는가. 비용이 없으면 늘 된다. 그 수치의 지금 값이 비용 이상이어야 한다."""
    if cost is None:
        return True
    resource = find_resource(ruleset, cost.resource)
    return resource is not None and resources.level_of(ruleset, sheet, resource).value >= cost.amount


def harms_ally(skill: Skill, member: TableMember, target_id) -> bool:
    """해로운 기술을 자기 아닌 동료에게 쓰는가."""
    return target_id != member.user_id and is_harmful(skill.effects)


def rolls(skill: Skill, member: TableMember, action: SkillAction) -> bool:
    """
    맞히는 판정을 하는가(#805 ②). 상대에게 쓰는 기술은 늘, 판정이 있는 기술은 자기 아닌 동료에게 쓸 때 굴린다.

    받을 때 대상을 채웠다. 자신과 동료에게 쓰는 기술의 target 은 비어 있지 않다.
    """
    if skill.target == SkillTarget.FOE:
        return True
    return skill.check is not None and action.target is not None and action.target != member.user_id


def check_terms(ruleset: Ruleset, skill: Skill) -> tuple[str, str | None]:
    """
    맞히는 판정의 능력과 난이도. 기술에 적혀 있으면 그것, 없으면 룰북의 맞히는 판정(item_check)이다.

    상대에게 쓰는 기술은 둘 중 하나가 있다(규칙이 본다). 동료에게 쓰는 기술은 판정이 있을 때만 굴린다.
    """
    if skill.check is not None:
        return skill.check.ability, skill.check.difficulty
    return ruleset.item_check.ability, ruleset.item_check.difficulty


# --- 받을 때 ---


def require_skill(ruleset: Ruleset, member: TableMember, key: str) -> Skill:
    """룰북에 있고 이 캐릭터가 아는 기술. 없으면 ActionNotInRulesError(skill), 모르면 skill_not_known."""
    skill = find_skill(ruleset, key)
    if skill is None:
        raise ActionNotInRulesError('skill')
    if not knows(member.sheet, key):
        raise RoundConflictError(Conflict.SKILL_NOT_KNOWN)
    return skill


def require_target(table: GameTable, member: TableMember, skill: Skill, action: SkillAction) -> TableMember:
    """받을 사람. 자신에게만 쓰는 기술이면 자신이다. 앉아 있지 않으면 ActionTargetError, 죽었으면 patient_dead."""
    target_id = action.target or member.user_id
    if skill.target == SkillTarget.SELF and target_id != member.user_id:
        raise ActionTargetError('target')
    target = table_state.find_member(table, target_id)
    if target is None:
        raise ActionTargetError('target')
    if sheets.is_dead(target):
        raise RoundConflictError(Conflict.PATIENT_DEAD)
    return target


def require_foe(action: SkillAction) -> None:
    """
    상대에게 쓰는 기술(#805 ②)은 인물이나 몬스터 하나를 겨눈다. 겨누지 않았으면 ActionTargetError(target).

    앉은 사람(target)을 적었으면 인물과 몬스터는 비어 있다(행동의 모양이 하나만 받는다). 그것도 여기서 막힌다.
    """
    if action.npc is None and action.monster is None:
        raise ActionTargetError('target')


def require_no_foe(action: SkillAction) -> None:
    """자신과 동료에게 쓰는 기술은 인물이나 몬스터를 겨누지 않는다. 적었으면 ActionTargetError(npc, monster)."""
    if action.npc is not None:
        raise ActionTargetError('npc')
    if action.monster is not None:
        raise ActionTargetError('monster')


def accept_skill(table: GameTable, member: TableMember, ruleset: Ruleset, action: SkillAction) -> dict:
    """
    기술을 쓰는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다(자신과 동료에게 쓰는 기술은 대상을 채운다).

    상대에게 쓰는 기술은 겨눈 쪽이 이번 장면에 있는지 보지 않는다. 부르는 쪽이 장면을 들고 본다.
    """
    skill = require_skill(ruleset, member, action.skill)
    if not affordable(ruleset, member.sheet, skill.cost):
        raise RoundConflictError(Conflict.SKILL_COST_SHORT)
    if action.lethal and first_of(skill.effects, EffectKind.DAMAGE) is None:
        raise ActionNotInRulesError('lethal')
    if skill.target == SkillTarget.FOE:
        require_foe(action)
        return action.model_dump(mode='json')
    require_no_foe(action)
    target = require_target(table, member, skill, action)
    if harms_ally(skill, member, target.user_id):
        friendly_fire.require_harmable(table, member, target.user_id)
    return action.model_copy(update={'target': target.user_id}).model_dump(mode='json')


# --- 닫을 때 ---


def refused(judging: Judging, member: TableMember, skill: Skill, target: TableMember | None) -> str | None:
    """지금 쓰지 못하는 까닭. 쓸 수 있으면 None. 모름 → 받을 사람 → 해칠 수 있는가 → 비용의 차례로 본다."""
    if not knows(member.sheet, skill.key):
        return Reason.NOT_KNOWN
    if target is None:
        return Reason.TARGET_GONE
    if harms_ally(skill, member, target.user_id):
        gone = friendly_fire.ally_gone(judging, member, target.user_id)
        if gone is not None:
            off = gone['reason'] == friendly_fire.AllyGone.FRIENDLY_FIRE_OFF
            return Reason.FRIENDLY_FIRE_OFF if off else Reason.TARGET_GONE
    if not affordable(judging.ruleset, member.sheet, skill.cost):
        return Reason.COST_SHORT
    return None


def pay(judging: Judging, member: TableMember, cost: SkillCost | None) -> list[dict]:
    """비용을 낸다. 쓴 사람의 수치가 준 것의 문서를 돌려준다. 비용이 없으면 빈 목록이다."""
    if cost is None:
        return []
    shift = resources.adjust(judging.ruleset, member.sheet, cost.resource, -cost.amount)
    return [resources.shift_document(shift, member.user_id)] if shift is not None else []


def skill_document(
    skill: Skill, reason: str | None, target: dict | None, terms: tuple[str, str | None] | None = None
) -> dict:
    """
    쓴 결과의 문서(skill_use)의 머리. 무엇을, 썼는가, 못 했으면 까닭, 대상, 굴렸으면 판정의 능력과 난이도다.

    대상은 앉은 사람이면 user_id 와 캐릭터 이름, 굴린 쪽이면(#805 ②) 맞을 쪽의 문서다(item_targets.target_of).
    """
    ability, difficulty = terms if terms is not None else (None, None)
    return {
        'skill': skill.key,
        'name': skill.name,
        'used': reason is None,
        'reason': reason,
        'target': target,
        'ability': ability,
        'difficulty': difficulty,
        'cost': [],
        'cured': [],
        'injured': [],
        'resources': [],
    }


def judge_skill(judging: Judging, member: TableMember, action: SkillAction) -> dict:
    """
    기술 하나를 쓴다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다. 굴리는 기술이면 judge_rolled_skill 이다.

    HP 가 바뀌었으면 그 내용(effect)을, 낸 비용(cost), 푼 부상(cured), 입힌 부상(injured), 맞춘 수치(resources)를
    skill_use 에 적는다. 동료에게 해로운 기술이면 장난의 상한을 지킨다(#803).
    """
    skill = find_skill(judging.ruleset, action.skill)
    if rolls(skill, member, action):
        return judge_rolled_skill(judging, member, skill, action)
    target = living(table_state.find_member(judging.table, action.target or member.user_id))
    reason = refused(judging, member, skill, target)
    if reason is not None:
        return {'skill_use': skill_document(skill, reason, person(target)), 'effect': None}
    cost = pay(judging, member, skill.cost)
    prank = harms_ally(skill, member, target.user_id) and friendly_fire.is_prank_toward(judging, member, target)
    applied = apply_to_member(judging, target, skill.effects, prank, Trigger.SKILL)
    used = {
        **skill_document(skill, None, person(target)),
        'cost': cost,
        'cured': applied['cured'],
        'injured': applied['injured'],
        'resources': applied['resources'],
    }
    return {'skill_use': used, 'effect': applied['effect']}


# --- 굴리는 기술(#805 ②) ---

# 빗나갔거나 효과가 없는 기술의 효과 결과
NOTHING_APPLIED = {'cured': [], 'injured': [], 'resources': []}


def refused_rolled(
    judging: Judging, member: TableMember, skill: Skill, action: SkillAction
) -> tuple[str | None, dict | None]:
    """
    굴리는 기술을 지금 쓰지 못하는 까닭과, 겨눈 몬스터가 없으면 치기와 같은 그 문서. 쓸 수 있으면 (None, None).

    모름 → 겨눈 몬스터 → 동료(굴리지 않는 기술과 같다) → 비용의 차례로 본다.
    인물은 장면이 바뀌지 않아 보지 않는다. 쓰러졌거나 죽은 인물은 판정이 다룬다(물건과 같다).
    """
    if not knows(member.sheet, skill.key):
        return Reason.NOT_KNOWN, None
    if action.monster is not None:
        gone = monster_gone(judging, member, action.monster)
        if gone is not None:
            return Reason.TARGET_GONE, gone
    if action.target is not None:
        target = living(table_state.find_member(judging.table, action.target))
        reason = refused(judging, member, skill, target)
        return reason, None
    if not affordable(judging.ruleset, member.sheet, skill.cost):
        return Reason.COST_SHORT, None
    return None, None


def is_prank_skill(judging: Judging, member: TableMember, skill: Skill, action: SkillAction) -> bool:
    """해로운 기술을 동료에게 쓰는 장난인가(#803). 맞힌 뒤의 부상이 상한을 지킨다."""
    if action.target is None or not harms_ally(skill, member, action.target):
        return False
    target = table_state.find_member(judging.table, action.target)
    return target is not None and friendly_fire.is_prank_toward(judging, member, target)


def judge_rolled_skill(judging: Judging, member: TableMember, skill: Skill, action: SkillAction) -> dict:
    """
    맞히는 판정을 하는 기술을 쓴다(#805 ②). 물건을 던지는 것과 같다(app/rounds/throws.py).

    썼으면 판정의 결과(판정, 대상의 변화, 방어, 드롭)에 skill_use 를 더한다. skill_use 에는 판정의 능력과 난이도,
    낸 비용, 맞혔으면 푼 부상과 입힌 부상과 맞춘 수치가 있다. 빗나가도 비용은 낸다.
    못 썼으면 skill_use 만 있다. 겨눈 몬스터가 없어 못 썼으면 target_gone 도 있다.
    """
    terms = check_terms(judging.ruleset, skill)
    check = to_check(judging, skill.effects, action, *terms)
    target = target_of(judging, action)
    reason, gone = refused_rolled(judging, member, skill, action)
    if reason is not None:
        refusal = {'skill_use': skill_document(skill, reason, target, (check.ability, check.difficulty))}
        return {**refusal, 'target_gone': gone} if gone is not None else refusal
    cost = pay(judging, member, skill.cost)
    mark_harm(judging, member, skill.effects, action, check)
    prank = is_prank_skill(judging, member, skill, action)
    outcome = judge_check(judging, member, check)
    hit = landed(outcome, check)
    applied = apply_after_hit(judging, skill.effects, action, prank, Trigger.SKILL) if hit else NOTHING_APPLIED
    used = {**skill_document(skill, None, target, (check.ability, check.difficulty)), 'cost': cost, **applied}
    return {**outcome, 'skill_use': used}
