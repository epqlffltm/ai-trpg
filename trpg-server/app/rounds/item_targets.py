# trpg-server/app/rounds/item_targets.py

"""
물건을 인물(NPC)이나 몬스터에게 쓰는 것(#800). 독 바른 단검을 찌르고, 기절 가루를 뿌리고, 쓰러진 인물에게 물약을 먹인다.

맞히는 판정을 늘 거친다. 능력과 난이도는 룰북의 것이다(rules.item_check). 이로운 물건이어도 굴린다.
잘못 먹이거나 엉뚱한 곳에 바를 수 있다. 맞히면 효과가 들고, 빗나가면 아무 일도 없다. 굴렸으면 물건은 하나 없어진다.
  - 피해(damage)가 있는 물건은 그 등급의 타격으로 판정한다(app/rounds/checks.py 의 judge_check 를 그대로 부른다).
    방어, 세이브, 부상 표, 드롭이 치기와 같다. 세이브로 막으면 다른 효과도 들지 않는다.
  - 회복(heal)이 있는 물건을 인물에게 쓰면 그 등급의 회복으로 판정한다. 몬스터에게는 회복이 없다(효과가 없다).
  - 그 밖(풀기, 부상만)은 대상 없이 굴린다. 맞히면 그 대상에게 효과를 낸다.
  피해나 부상이 있으면 싸움이다. 맞든 빗나가든 그 대상과 싸운 것으로 적는다.
  HP 를 바꾼 다음에 풀기와 부상을 적힌 차례대로 낸다. 대상이 그 타격으로 죽었으면 내지 않는다.
  몬스터는 그 성질에 면역인 부상을 입지 않는다(#799).
가지고 있지 않으면(not_held), 겨눈 몬스터가 죽었거나 다른 곳에 있으면(target_gone) 굴리지 않고 물건도 그대로다.

DB 를 모른다. 시트의 소지품과 맞은 쪽의 상태를 고친다. 저장하지 않는다.
"""

from app.engine.action import ActionKind, CheckAction, UseAction
from app.engine.item_effects import EffectKind, first_of, is_harmful
from app.rounds.cast import CastMember, find_cast_member
from app.rounds.checks import judge_check, monster_gone
from app.rounds.effects import Judging, mark_fight, mark_npc_fight
from app.rounds.item_actions import Reason, cure, injure, use_document
from app.rounds.monster_scene import SceneMonster, find_scene_monster
from app.tables import items, npcs
from app.tables import monsters as table_monsters
from app.tables.items import CatalogItem
from app.tables.models import TableInjury, TableMember


def to_check(judging: Judging, item: CatalogItem, action: UseAction) -> CheckAction:
    """
    맞히는 판정. 룰북의 능력과 난이도에, 물건이 HP 를 바꾸면 그 등급의 타격이나 회복을 겨눈다.

    받을 때 룰북에 맞히는 판정이 있는지 봤다(app/rounds/acceptance.py). 판에 굳은 룰북이라 바뀌지 않는다.
    """
    rule = judging.ruleset.item_check
    damage = first_of(item.effects, EffectKind.DAMAGE)
    heal = first_of(item.effects, EffectKind.HEAL)
    base = {'kind': ActionKind.CHECK, 'ability': rule.ability, 'difficulty': rule.difficulty}
    if damage is not None:
        return CheckAction(**base, harm=damage.magnitude, npc=action.npc, monster=action.monster, lethal=action.lethal)
    if heal is not None and action.npc is not None:
        return CheckAction(**base, recover=heal.magnitude, npc=action.npc)
    return CheckAction(**base)


def target_of(judging: Judging, action: UseAction) -> dict:
    """쓴 쪽을 결과에 적을 모양. 몬스터면 그 마리의 id 와 이름, 인물이면 항목의 id 와 장면의 호칭이다."""
    if action.monster is not None:
        monster = find_scene_monster(judging.monsters, action.monster)
        return {'monster_id': str(action.monster), 'name': monster.name if monster else None}
    person = find_cast_member(judging.cast, action.npc)
    return {'entry_id': str(action.npc), 'name': person.name if person else None}


def mark_harm(judging: Judging, member: TableMember, item: CatalogItem, action: UseAction, check: CheckAction) -> None:
    """
    해로운 물건이면 그 대상과 싸운 것으로 적는다. 타격으로 판정하면 judge_check 가 적으므로 여기서는 적지 않는다.
    """
    if not is_harmful(item.effects) or check.harm is not None:
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
    return outcome.get('npc_effect') is not None or outcome.get('monster_effect') is not None


def struck_rows(judging: Judging, action: UseAction) -> tuple[list[TableInjury], frozenset] | None:
    """
    풀기와 부상을 낼 대상의 부상 목록과 그 면역. 대상이 죽었거나 없으면 None.

    몬스터면 그 마리의 면역(타입과 시트, #799)을, 인물이면 면역이 없다.
    """
    if action.monster is not None:
        monster: SceneMonster | None = find_scene_monster(judging.monsters, action.monster)
        if monster is None or table_monsters.is_dead(monster.state):
            return None
        return monster.state.injuries, table_monsters.immunities(monster.definition)
    person: CastMember | None = find_cast_member(judging.cast, action.npc)
    if person is None or npcs.is_dead(person.npc):
        return None
    return person.npc.injuries, frozenset()


def apply_after_hit(judging: Judging, item: CatalogItem, action: UseAction) -> dict:
    """맞힌 대상에게 풀기와 부상을 적힌 차례대로 낸다. 푼 것(cured)과 입힌 것(injured)이다."""
    found = struck_rows(judging, action)
    if found is None:
        return {'cured': [], 'injured': []}
    rows, immune = found
    cured: list[dict] = []
    injured: list[dict] = []
    for one in item.effects:
        if one.kind == EffectKind.CURE:
            cured.extend(cure(judging, rows, one.injuries))
        elif one.kind == EffectKind.INJURE:
            injured.append(injure(judging, rows, one.injury, immune))
    return {'cured': cured, 'injured': injured}


def judge_use_on(judging: Judging, member: TableMember, action: UseAction) -> dict:
    """
    물건 하나를 인물이나 몬스터에게 쓴다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    굴렸으면 판정의 결과(판정, 대상의 변화, 방어, 드롭)에 item_use 를 더한다. item_use 에는 판정의 능력과 난이도,
    푼 부상(cured)과 입힌 부상(injured)이 있다. 못 썼으면 item_use 만 있다. 겨눈 몬스터가 없으면 target_gone 도 있다.
    """
    item = judging.items[action.item]
    check = to_check(judging, item, action)
    target = target_of(judging, action)
    terms = {'ability': check.ability, 'difficulty': check.difficulty}
    if items.count_of(member.sheet, action.item) < 1:
        return {'item_use': {**use_document(item, member, Reason.NOT_HELD, target), **terms}}
    gone = monster_gone(judging, member, action.monster) if action.monster is not None else None
    if gone is not None:
        return {'item_use': {**use_document(item, member, Reason.TARGET_GONE, target), **terms}, 'target_gone': gone}
    mark_harm(judging, member, item, action, check)
    items.remove_items(member.sheet, action.item, 1)
    outcome = judge_check(judging, member, check)
    applied = apply_after_hit(judging, item, action) if landed(outcome, check) else {'cured': [], 'injured': []}
    used = {**use_document(item, member, None, target), **terms, **applied}
    return {**outcome, 'item_use': used}
