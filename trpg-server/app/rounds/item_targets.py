# trpg-server/app/rounds/item_targets.py

"""
물건을 인물(NPC)이나 몬스터에게 쓰는 것(#800). 독 바른 단검을 찌르고, 기절 가루를 뿌리고, 쓰러진 인물에게 물약을 먹인다.

맞히는 판정을 늘 거친다. 능력과 난이도는 룰북의 것이다(rules.item_check). 이로운 물건이어도 굴린다.
잘못 먹이거나 엉뚱한 곳에 바를 수 있다. 맞히면 효과가 들고, 빗나가면 아무 일도 없다. 굴렸으면 물건은 하나 없어진다.
  - 피해(damage)가 있는 물건은 그 등급의 타격으로 판정한다(app/rounds/checks.py 의 judge_check 를 그대로 부른다).
    방어, 세이브, 부상 표, 드롭이 치기와 같다. 세이브로 막으면 다른 효과도 들지 않는다.
  던지기(#801, app/rounds/throws.py)도 같은 함수로 판정하고 효과를 낸다. 판정만 물건의 던지는 판정일 수 있다.
  - 회복(heal)이 있는 물건을 인물에게 쓰면 그 등급의 회복으로 판정한다. 몬스터에게는 회복이 없다(효과가 없다).
  - 그 밖(풀기, 부상만)은 대상 없이 굴린다. 맞히면 그 대상에게 효과를 낸다.
  피해나 부상이 있으면 싸움이다. 맞든 빗나가든 그 대상과 싸운 것으로 적는다.
  HP 를 바꾼 다음에 풀기와 부상을 적힌 차례대로 낸다. 대상이 그 타격으로 죽었으면 내지 않는다.
  몬스터는 그 성질에 면역인 부상을 입지 않는다(#799). 누구든 막는 성질(#886 ②, 저항)의 부상과 수치를 내리는
  맞추기는 받지 않는다(app/tables/resistances.py).
가지고 있지 않으면(not_held), 겨눈 몬스터가 죽었거나 다른 곳에 있으면(target_gone) 굴리지 않고 물건도 그대로다.
던지기는 앉은 사람도 맞힌다(#803). 해로운 물건이면 치기와 같이 해칠 수 있어야 하고, 장난이면 상한을 지킨다
(app/rounds/friendly_fire.py). 앉은 사람과는 싸운 것으로 적지 않는다.
맞히는 판정이 있는 기술(#805 ②, app/rounds/skill_actions.py)도 같은 함수로 판정하고 효과를 낸다. 판정과 효과는
물건이 아니라 기술에 적혀 있어 함수들은 물건 대신 효과 목록을 받는다.

DB 를 모른다. 시트의 소지품과 맞은 쪽의 상태를 고친다. 저장하지 않는다.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from app.engine.action import ActionKind, CheckAction, SkillAction, ThrowAction, UseAction, settle
from app.engine.injury import Trigger
from app.engine.item_effects import AdjustEffect, EffectKind, first_of, is_harmful, is_resisted
from app.engine.ruleset import ResourceHolder
from app.rounds import resisting
from app.rounds.cast import CastMember, find_cast_member
from app.rounds.checks import judge_check, monster_gone
from app.rounds.effects import Judging, mark_fight, mark_npc_fight
from app.rounds.item_actions import Reason, cure, injure, use_document
from app.rounds.monster_scene import SceneMonster, find_scene_monster
from app.tables import items, npcs, resources, sheets
from app.tables import monsters as table_monsters
from app.tables import state as table_state
from app.tables.models import TableMember
from app.tables.resources import Bearer

# 겨누는 행동. 물건의 쓰기와 던지기(#801)와 기술(#805 ②)이 같은 칸(npc, monster, lethal)을 가진다
Aimed = UseAction | ThrowAction | SkillAction


def to_check(judging: Judging, effects: list, action: Aimed, ability: str, difficulty: str | None) -> CheckAction:
    """
    맞히는 판정. 그 능력과 난이도(비우면 룰북의 기본)에, 효과가 HP 를 바꾸면 그 등급의 타격이나 회복을 겨눈다.

    쓰기는 룰북의 맞히는 판정(rules.item_check), 던지기는 물건의 던지는 판정이나 룰북의 것이다(#801).
    기술은 기술의 판정이나 룰북의 것이다(#805 ②).
    받을 때 있는지 봤다(app/rounds/acceptance.py). 판에 굳은 룰북이라 바뀌지 않는다.
    """
    damage = first_of(effects, EffectKind.DAMAGE)
    heal = first_of(effects, EffectKind.HEAL)
    base = {'kind': ActionKind.CHECK, 'ability': ability, 'difficulty': difficulty}
    # 앉은 사람에게 던지거나 기술을 쓰면(#803, #805 ②) 그 사람이 대상이다. 쓰기(UseAction)는 인물과 몬스터에게만 온다
    ally = ally_of(action)
    if damage is not None:
        aimed = {'npc': action.npc, 'monster': action.monster, 'target': ally, 'lethal': action.lethal}
        check = CheckAction(**base, harm=damage.magnitude, **aimed)
    elif heal is not None and action.npc is not None:
        check = CheckAction(**base, recover=heal.magnitude, npc=action.npc)
    elif heal is not None and ally is not None:
        check = CheckAction(**base, recover=heal.magnitude, target=ally)
    else:
        check = CheckAction(**base)
    return settle(judging.ruleset, check)


def target_of(judging: Judging, action: Aimed) -> dict:
    """
    쓴 쪽을 결과에 적을 모양. 몬스터면 그 마리의 id 와 이름, 인물이면 항목의 id 와 장면의 호칭,
    앉은 사람(#803, 던지기)이면 user_id 와 캐릭터의 이름이다.
    """
    ally = ally_of(action)
    if ally is not None:
        member = table_state.find_member(judging.table, ally)
        return {'user_id': str(ally), 'name': member.character_name if member else None}
    if action.monster is not None:
        monster = find_scene_monster(judging.monsters, action.monster)
        return {'monster_id': str(action.monster), 'name': monster.name if monster else None}
    person = find_cast_member(judging.cast, action.npc)
    return {'entry_id': str(action.npc), 'name': person.name if person else None}


def ally_of(action: Aimed) -> uuid.UUID | None:
    """
    맞을 앉은 사람(#803). 던지기와 기술(#805 ②)에만 있다. 없으면 None.

    기술은 자기 아닌 동료에게 쓸 때만 이 길로 온다(자기 자신에게는 굴리지 않는다).
    """
    return action.target if isinstance(action, ThrowAction | SkillAction) else None


def mark_harm(judging: Judging, member: TableMember, effects: list, action: Aimed, check: CheckAction) -> None:
    """
    해로운 효과면 그 대상과 싸운 것으로 적는다. 타격으로 판정하면 judge_check 가 적으므로 여기서는 적지 않는다.

    앉은 사람(#803)과는 싸운 것으로 적지 않는다. 싸움의 기록은 몬스터와 NPC 의 차례가 읽는다.
    """
    if not is_harmful(effects) or check.harm is not None or ally_of(action) is not None:
        return
    if action.monster is not None:
        mark_fight(judging, find_scene_monster(judging.monsters, action.monster).state, member)
        return
    person = find_cast_member(judging.cast, action.npc)
    if person is not None and not npcs.is_dead(person.npc):
        mark_npc_fight(judging, person.npc, member)


def landed(outcome: dict, check: CheckAction) -> bool:
    """맞혔는가. 타격으로 판정했으면 세이브로 막지 않았어야 한다(막으면 대상의 변화가 비어 있다)."""
    if not outcome['success']:
        return False
    if check.harm is None:
        return True
    hit = ('npc_effect', 'monster_effect', 'effect') if check.target is not None else ('npc_effect', 'monster_effect')
    return any(outcome.get(field) is not None for field in hit)


@dataclass(frozen=True)
class Struck:
    """
    맞은 쪽. 그 부상과 수치를 가진 것(앉은 사람의 시트, 몬스터의 상태, 인물의 상태)과 어느 쪽인지,
    누구의 것인지(앉은 사람이면 그 사람), 지금 막는 성질을 구하는 법이다(#886 ②).
    """

    bearer: Bearer
    holder: ResourceHolder
    owner_id: uuid.UUID | None
    blocked: Callable[[], frozenset[str]]

    @property
    def immune(self) -> frozenset[str]:
        """지금 막는 성질들. 효과마다 다시 구한다. 앞의 효과가 입힌 부상이 저항을 줄 수 있다."""
        return self.blocked()


def struck_of(judging: Judging, action: Aimed) -> Struck | None:
    """
    풀기와 부상과 맞추기를 낼 대상. 대상이 죽었거나 없으면 None.

    막는 성질은 몬스터면 그 마리의 면역(타입과 시트, #799)과 저항, 인물과 앉은 사람(#803)이면 저항이다(#886 ②).
    """
    ally = ally_of(action)
    if ally is not None:
        member = table_state.find_member(judging.table, ally)
        if member is None or member.sheet is None or sheets.is_dead(member):
            return None
        return Struck(
            member.sheet, ResourceHolder.CHARACTERS, member.user_id, lambda: resisting.of_member(judging, member)
        )
    if action.monster is not None:
        monster: SceneMonster | None = find_scene_monster(judging.monsters, action.monster)
        if monster is None or table_monsters.is_dead(monster.state):
            return None
        return Struck(monster.state, ResourceHolder.MONSTERS, None, lambda: resisting.of_monster(judging, monster))
    person: CastMember | None = find_cast_member(judging.cast, action.npc)
    if person is None or npcs.is_dead(person.npc):
        return None
    return Struck(person.npc, ResourceHolder.NPCS, None, lambda: resisting.of_cast(judging, person))


def adjust_struck(judging: Judging, struck: Struck, effect: AdjustEffect) -> list[dict]:
    """
    맞은 쪽의 수치를 맞춘다(#804). 그 쪽이 가지지 않는 수치거나 값이 같으면(이미 끝) 바뀐 것이 없다.

    맞은 쪽이 막는 성질의 내리는 맞추기면(#886 ②) 바꾸지 않고, 막아 낸 것(resisted)을 적는다.
    """
    if is_resisted(effect, struck.immune):
        shift = resources.standing(judging.ruleset, struck.bearer, effect.resource, struck.holder)
        return [] if shift is None else [resources.resisted_document(shift, struck.owner_id, effect.nature)]
    shift = resources.adjust(judging.ruleset, struck.bearer, effect.resource, effect.amount, struck.holder)
    if shift is None or shift.before == shift.after:
        return []
    return [resources.shift_document(shift, struck.owner_id)]


def apply_after_hit(
    judging: Judging, effects: list, action: Aimed, prank: bool = False, trigger: Trigger = Trigger.ITEM
) -> dict:
    """
    맞힌 대상에게 풀기와 부상과 맞추기를 적힌 차례대로 낸다. 푼 것(cured), 입힌 것(injured), 맞춘 수치(resources)다.
    맞추기(#804)는 그 쪽(앉은 사람, 인물, 몬스터)이 가지는 수치에만 든다(규칙의 resources[].holders).

    prank 면 동료의 장난이다(#803). 짧은 부상만 입힌다. trigger 는 부상이 어디서 왔나다(물건, 기술).
    """
    struck = struck_of(judging, action)
    if struck is None:
        return {'cured': [], 'injured': [], 'resources': []}
    rows = struck.bearer.injuries
    cured: list[dict] = []
    injured: list[dict] = []
    shifts: list[dict] = []
    for one in effects:
        if one.kind == EffectKind.CURE:
            cured.extend(cure(judging, rows, one.injuries, struck.immune))
        elif one.kind == EffectKind.INJURE:
            injured.append(injure(judging, rows, one.injury, struck.immune, prank, trigger))
        elif one.kind == EffectKind.ADJUST:
            shifts.extend(adjust_struck(judging, struck, one))
    return {'cured': cured, 'injured': injured, 'resources': shifts}


def judge_use_on(judging: Judging, member: TableMember, action: UseAction) -> dict:
    """
    물건 하나를 인물이나 몬스터에게 쓴다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    굴렸으면 판정의 결과(판정, 대상의 변화, 방어, 드롭)에 item_use 를 더한다. item_use 에는 판정의 능력과 난이도,
    푼 부상(cured)과 입힌 부상(injured)이 있다. 못 썼으면 item_use 만 있다. 겨눈 몬스터가 없으면 target_gone 도 있다.
    """
    item = judging.items[action.item]
    rule = judging.ruleset.item_check
    check = to_check(judging, item.effects, action, rule.ability, rule.difficulty)
    target = target_of(judging, action)
    terms = {'ability': check.ability, 'difficulty': check.difficulty}
    if items.count_of(member.sheet, action.item) < 1:
        return {'item_use': {**use_document(item, member, Reason.NOT_HELD, target), **terms}}
    gone = monster_gone(judging, member, action.monster) if action.monster is not None else None
    if gone is not None:
        return {'item_use': {**use_document(item, member, Reason.TARGET_GONE, target), **terms}, 'target_gone': gone}
    mark_harm(judging, member, item.effects, action, check)
    items.remove_items(member.sheet, action.item, 1)
    outcome = judge_check(judging, member, check)
    applied = (
        apply_after_hit(judging, item.effects, action)
        if landed(outcome, check)
        else {'cured': [], 'injured': [], 'resources': []}
    )
    used = {**use_document(item, member, None, target), **terms, **applied}
    return {**outcome, 'item_use': used}
