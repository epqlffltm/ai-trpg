# trpg-server/app/rounds/skill_actions.py

"""
기술과 주문을 쓰는 행동(#805)을 받고 판정한다.

기술이 무엇인지는 룰북의 데이터다(rules.skills: 이름, 비용, 대상, 효과). 누가 아는지는 시트에 있다(시나리오의 시트에서
복사한 table_sheets.skills). 효과는 소모품과 같은 엔진으로 낸다(app/rounds/item_actions.py 의 apply_to_member).

받을 때(accept_skill)
  - 룰북에 없는 기술이면 ActionNotInRulesError(skill), 모르는 기술이면 RoundConflictError(skill_not_known).
  - 비용이 모자라면 RoundConflictError(skill_cost_short).
  - 자신에게만 쓰는 기술에 남을 적으면 ActionTargetError(target). 받을 사람이 앉아 있지 않으면 ActionTargetError,
    죽었으면 RoundConflictError(patient_dead). 비워 둔 대상은 자기 자신으로 채운다.
  - 해로운 효과(피해, 부상, 수치를 내림)가 있는 기술을 동료에게 쓰는 것은 치기와 같다(#803, friendly_fire).
닫을 때(judge_skill). 들어온 순서로 한 번만 한다. 굴리지 않는다.
  - 다시 본다. 받을 사람이 없거나 해칠 수 없게 바뀌었거나 비용이 모자라면 쓰지 못한다. 그때는 비용도 내지 않는다.
  - 비용을 먼저 내고(쓴 사람의 수치가 준다), 그다음 효과들을 적힌 차례대로 낸다. 빗나가는 일이 없다.

DB 를 모른다. 시트를 고친다. 저장하지 않는다.
"""

from app.engine.action import SkillAction
from app.engine.injury import Trigger
from app.engine.item_effects import is_harmful
from app.engine.resources import find_resource
from app.engine.ruleset import Ruleset, Skill, SkillCost, SkillTarget
from app.rounds import friendly_fire
from app.rounds.effects import Judging
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, Conflict, RoundConflictError
from app.rounds.item_actions import apply_to_member, living, person
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


def accept_skill(table: GameTable, member: TableMember, ruleset: Ruleset, action: SkillAction) -> dict:
    """기술을 쓰는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다(대상을 채운다)."""
    skill = require_skill(ruleset, member, action.skill)
    if not affordable(ruleset, member.sheet, skill.cost):
        raise RoundConflictError(Conflict.SKILL_COST_SHORT)
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


def skill_document(skill: Skill, reason: str | None, target: TableMember | None) -> dict:
    """쓴 결과의 문서(skill_use)의 머리. 무엇을, 썼는가, 못 했으면 까닭, 대상이다."""
    return {
        'skill': skill.key,
        'name': skill.name,
        'used': reason is None,
        'reason': reason,
        'target': person(target),
        'cost': [],
        'cured': [],
        'injured': [],
        'resources': [],
    }


def judge_skill(judging: Judging, member: TableMember, action: SkillAction) -> dict:
    """
    기술 하나를 쓴다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    HP 가 바뀌었으면 그 내용(effect)을, 낸 비용(cost), 푼 부상(cured), 입힌 부상(injured), 맞춘 수치(resources)를
    skill_use 에 적는다. 동료에게 해로운 기술이면 장난의 상한을 지킨다(#803).
    """
    skill = find_skill(judging.ruleset, action.skill)
    target = living(table_state.find_member(judging.table, action.target or member.user_id))
    reason = refused(judging, member, skill, target)
    if reason is not None:
        return {'skill_use': skill_document(skill, reason, target), 'effect': None}
    cost = pay(judging, member, skill.cost)
    prank = harms_ally(skill, member, target.user_id) and friendly_fire.is_prank_toward(judging, member, target)
    applied = apply_to_member(judging, target, skill.effects, prank, Trigger.SKILL)
    used = {
        **skill_document(skill, None, target),
        'cost': cost,
        'cured': applied['cured'],
        'injured': applied['injured'],
        'resources': applied['resources'],
    }
    return {'skill_use': used, 'effect': applied['effect']}
