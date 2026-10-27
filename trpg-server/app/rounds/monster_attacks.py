# trpg-server/app/rounds/monster_attacks.py

"""
몬스터의 차례. 한 마리가 자기 장소의 캐릭터 하나를 공격 하나로 친다.

차례가 오면 먼저 칠 수 있는지 본다. 앞 차례에 쓰러지거나 죽었으면, 입은 부상 때문에 움직이지 못하면(기절, #799),
또는 같은 장소에 칠 캐릭터가 없으면 굴리지 않고 그 까닭을 적는다(skipped).
마리가 입은 부상은 판정에 든다(보정 깎기, 불리함). 결과에 그 영향(hindrance)을 적는다. NPC 의 차례와 같다.
칠 수 있으면 대상과 공격을 서버의 주사위로 고른다. 고를 것이 하나뿐이면 굴리지 않는다.
제작자가 공격의 순서를 신경 쓸 필요가 없고, 대상을 고르는 데 AI 가 끼지 않는다.
판정은 앉은 사람의 판정과 같은 계산이다(app/engine/check.py). 몬스터의 점수와 공격의 난이도로 굴린다.
맞히면 그 공격의 양의 등급만큼 피해를 준다. 피해, 쓰러짐, 부상 표는 앉은 사람의 것과 같다(change_sheet).
장비가 든다(#276, app/rounds/blows.py). 공격에 적은 무기의 공격 보정이 판정에 더해지고, 대상의 맞은 부위의 방어가
목표값을 올리거나(ac) 피해를 깎는다(reduce). 부위는 공격을 고른 뒤, 판정보다 먼저 굴린다.

대상은 그 장소의 서 있는 캐릭터와, 라운드를 닫기 시작할 때부터 쓰러져 있던 캐릭터다(#369, app/rounds/downed_strikes.py).
이번 라운드에 쓰러진 캐릭터는 동료가 일으킬 틈이 있어야 해서 다음 라운드부터 대상이다.
쓰러진 캐릭터를 맞히면 피해 대신 죽음의 굴림 실패가 쌓인다(strike_downed). 이 함수는 어느 쪽인지 가르기만 한다.
이번 라운드에 이 마리에게서 훔치다 들킨 도둑이 있으면 대상을 고르지 않고 도둑을 친다(app/rounds/steals.py).
도둑이 칠 수 있는 대상이 아니면(쓰러졌거나 떠났다) 평소처럼 고른다. 친 대상과는 싸운 것으로 적는다(mark_fight).
공격에 효과가 있으면(#805 ③-b) 맞혔을 때 맞은 캐릭터에게 그 효과(부상, 수치의 맞추기)를 낸다. 방어와 세이브는
피해만 막는다. 효과는 판정에 맞혔으면 든다. 피해 등급이 없는 공격(효과만)은 피해도, 세이브도, 죽음의 굴림 실패도 없다.
공격에 비용이 있으면(#805 ③-a) 고른 뒤에 낸다. 모자라면 그 차례에 아무것도 하지 못한다(skipped cost_short).
아무것도 내지 않고 굴리지 않는다. 비용을 낼 수 있는 공격만 골라 주지 않는다. 빗나가도 낸다. NPC 의 차례와 같다.
DB 를 모른다. 시트를 고친다. 저장하지는 않는다.
"""

from dataclasses import asdict

from app.assets.scenarios.snapshot import AttackSnapshot
from app.engine import check as checks
from app.engine import resources as resource_rules
from app.engine.armor import Save
from app.engine.check import Check, HinderedCheck
from app.engine.dice import choose
from app.engine.health import ChangeKind
from app.engine.injury import Trigger
from app.engine.ruleset import Difficulty, ResourceHolder
from app.rounds import blows
from app.rounds import injuries as round_injuries
from app.rounds.blows import NO_BLOW, Blow, Weapon
from app.rounds.checks import change_sheet
from app.rounds.downed_strikes import can_be_struck, strike_downed
from app.rounds.effects import Judging, mark_fight
from app.rounds.item_actions import apply_to_member
from app.rounds.monster_scene import SceneMonster
from app.tables import resources, sheets
from app.tables.models import NpcStatus, TableMember
from app.tables.resources import Bearer


class Skipped:
    """몬스터가 차례에 아무것도 하지 못한 까닭. 차례의 outcome.skipped 에 적는다."""

    # 앞 차례에 쓰러졌다
    DOWNED = 'downed'
    # 앞 차례에 죽었다
    DEAD = 'dead'
    # 같은 장소에 칠 캐릭터가 없다(모두 떠났거나 죽었거나, 이번 라운드에 쓰러졌다)
    NO_TARGET = 'no_target'
    # 입은 부상 때문에 움직이지 못했다(기절 같은 것, #799). NPC 의 차례도 같은 까닭을 쓴다
    INCAPACITATED = 'incapacitated'
    # 고른 공격의 비용이 모자랐다(#805 ③-a). 무엇으로 누구를 치려 했는지도 적는다
    COST_SHORT = 'cost_short'


def can_act(monster: SceneMonster) -> bool:
    """이 마리가 이번 라운드에 차례를 받는가. 살아 있고(쓰러지지 않았고) 공격이 있어야 한다."""
    return monster.state.status == NpcStatus.ALIVE and bool(monster.definition.attacks)


def stopped_by(judging: Judging, monster: SceneMonster) -> str | None:
    """차례가 왔을 때 이 마리가 움직이지 못하는 까닭. 움직일 수 있으면 None. 행동을 막는 부상도 본다(#799)."""
    if monster.state.status == NpcStatus.DEAD:
        return Skipped.DEAD
    if monster.state.status == NpcStatus.DOWNED:
        return Skipped.DOWNED
    if round_injuries.is_incapacitated(judging.ruleset, monster.state.injuries):
        return Skipped.INCAPACITATED
    return None


def victims_of(judging: Judging, monster: SceneMonster) -> list[TableMember]:
    """
    이 마리가 칠 수 있는 캐릭터들. 앉은 순서다.

    같은 장소의 서 있는 캐릭터와, 라운드를 닫기 시작할 때부터 쓰러져 있던 캐릭터다(can_be_struck).
    """
    return [
        member
        for member in judging.table.members
        if can_be_struck(judging, member) and member.sheet.place_id == monster.state.place_id
    ]


def raised_difficulty(judging: Judging, attack: AttackSnapshot, blow: Blow) -> Difficulty:
    """공격의 난이도. 맞은 부위의 방어가 목표값을 올리면(ac) 그만큼 오른 것이다."""
    difficulty = checks.find_difficulty(judging.ruleset, attack.difficulty)
    if not blow.raise_by:
        return difficulty
    return difficulty.model_copy(update={'target': difficulty.target + blow.raise_by})


def roll_attack(judging: Judging, monster: SceneMonster, attack: AttackSnapshot, blow: Blow = NO_BLOW) -> HinderedCheck:
    """
    공격 하나의 판정. 몬스터의 그 능력치 점수와 공격의 난이도로 굴린다. 마리가 입은 부상의 영향을 받는다(#799).

    무기의 공격 보정을 보정에 더하고, 맞은 부위의 방어만큼 목표값이 오른다(blow, #276).
    능력치와 난이도는 게시할 때 판의 규칙에 있는 것인지 확인했다(app/assets/scenarios/publishing.py).
    """
    ruleset = judging.ruleset
    difficulty = raised_difficulty(judging, attack, blow)
    hindrance = round_injuries.hindrance_for(ruleset, monster.state.injuries, attack.ability)
    score = monster.state.abilities[attack.ability]
    return checks.resolve_hindered(ruleset, score, difficulty, judging.dice, hindrance, bonus=blow.bonus)


def hit_outcome(judging: Judging, attack: AttackSnapshot, victim: TableMember, rolled: Check, blow: Blow) -> dict:
    """
    판정 뒤의 일. 쓰러진 대상이면 죽음의 굴림 실패를 쌓고(downed_strike), 서 있는 대상이면 맞혔을 때 피해를 준다.

    차례의 outcome 에 적을 문서다. 몬스터와 싸우는 NPC 의 차례가 함께 쓴다.
    맞은 부위의 방어가 피해를 깎는다(reduce). 맞혔고 세이브 방식이면 대상이 세이브를 굴리고, 막으면 맞지 않은 것과 같다
    (쓰러진 대상에게도 죽음의 굴림 실패가 쌓이지 않는다). 장비가 든 것(blow)이 있으면 붙인다(#276).
    피해 등급이 없는 공격(#805 ③-b)은 세이브를 굴리지 않고 HP 도 죽음의 굴림도 건드리지 않는다.
    공격의 효과는 그 뒤에 낸다(with_effects). 세이브와 상관없이 판정에 맞혔으면 든다.
    """
    save = blows.roll_blow_save(judging, blow) if rolled.success and attack.harm is not None else None
    landed = rolled.success and not blows.is_saved(save)
    if attack.harm is None:
        outcome = attack_outcome(attack, victim, rolled, None)
    elif sheets.is_downed_alive(victim):
        struck = strike_downed(judging, victim, landed)
        outcome = {**attack_outcome(attack, victim, rolled, None), 'downed_strike': struck}
    else:
        effect = change_sheet(judging, victim, ChangeKind.DAMAGE, attack.harm, blow.cut) if landed else None
        outcome = attack_outcome(attack, victim, rolled, effect)
    return with_blow(judging, with_effects(judging, attack, victim, rolled.success, outcome), blow, save)


def with_effects(judging: Judging, attack: AttackSnapshot, victim: TableMember, hit: bool, outcome: dict) -> dict:
    """
    공격의 효과(#805 ③-b)를 맞은 캐릭터에게 내고, 입힌 부상(injured)과 맞춘 수치(resources)를 차례의 outcome 에 더한다.

    효과가 없는 공격이면 그대로다(효과가 생기기 전의 차례와 같은 모양).
    빗나갔거나 대상이 그 타격으로 죽었으면 내지 않는다.
    """
    if not attack.effects:
        return outcome
    if not hit or sheets.is_dead(victim):
        return {**outcome, 'injured': [], 'resources': []}
    applied = apply_to_member(judging, victim, attack.effects, trigger=Trigger.ATTACK)
    return {**outcome, 'injured': applied['injured'], 'resources': applied['resources']}


def with_blow(judging: Judging, outcome: dict, blow: Blow, save: Save | None = None) -> dict:
    """차례의 outcome 에 장비가 든 것(blow)을 붙인다. 무기도 방어도 세이브도 없으면 그대로다."""
    document = blows.blow_document(judging.ruleset, blow, save)
    return outcome if document is None else {**outcome, 'blow': document}


def plan_attack_blow(judging: Judging, weapon: Weapon | None, victim: TableMember) -> Blow:
    """공격 하나에 장비가 드는 것을 정한다. 대상의 착용으로 방어를 세고 부위를 굴린다. 몬스터와 NPC 는 노리지 않는다."""
    return blows.plan_blow(judging, weapon, blows.member_protection(judging, victim), None)


def affordable(judging: Judging, bearer: Bearer, attack: AttackSnapshot, holder: ResourceHolder) -> bool:
    """
    공격의 비용을 낼 수 있는가(#805 ③-a). 비용이 없으면 늘 된다. 그 수치의 지금 값이 비용 이상이어야 한다.

    그 쪽이 가지지 않는 수치는 낼 수 없다(게시할 때 막았다. 판에 굳은 규칙이라 바뀌지 않는다).
    """
    if attack.cost is None:
        return True
    resource = resource_rules.find_resource(judging.ruleset, attack.cost.resource)
    if resource is None or not resource_rules.holds(resource, holder):
        return False
    return resources.level_of(judging.ruleset, bearer, resource).value >= attack.cost.amount


def pay(judging: Judging, bearer: Bearer, attack: AttackSnapshot, holder: ResourceHolder) -> dict:
    """
    공격의 비용을 낸다. 차례의 outcome 에 더할 것을 돌려준다. 그 쪽의 수치가 준 것의 문서들(cost)이다.

    비용이 없는 공격이면 아무것도 더하지 않는다(빈 문서). 비용이 생기기 전의 차례와 같은 모양으로 남는다.
    """
    if attack.cost is None:
        return {}
    shift = resources.adjust(judging.ruleset, bearer, attack.cost.resource, -attack.cost.amount, holder)
    return {'cost': [resources.shift_document(shift, None)] if shift is not None else []}


def short_outcome(attack: AttackSnapshot, victim: TableMember) -> dict:
    """비용이 모자라 하지 못한 차례(#805 ③-a). 무엇으로 누구를 치려 했는지를 적는다. 굴린 것도 바뀐 것도 없다."""
    return {
        'skipped': Skipped.COST_SHORT,
        'attack': attack_document(attack),
        'user_id': str(victim.user_id),
        'character_name': victim.character_name,
    }


def attack_document(attack: AttackSnapshot) -> dict:
    """
    결과에 적을 공격. 무기는 장비가 든 것(blow)에, 비용은 낸 것(cost)에, 효과는 든 것(injured, resources)에 적는다.
    공격은 그 전의 모양 그대로다.
    """
    return attack.model_dump(exclude={'weapon', 'cost', 'effects'})


def attack_outcome(attack: AttackSnapshot, victim: TableMember, rolled: Check, effect: dict | None) -> dict:
    """
    몬스터가 공격한 것을 차례의 outcome 에 적을 문서로. 무엇으로 누구를 쳤고, 어떻게 굴렸고, 무엇이 바뀌었는지.

    effect 는 맞혔을 때 대상의 HP 가 바뀐 것이다(app/rounds/effects.py 의 member_effect). 빗나갔으면 None.
    """
    return {
        'attack': attack_document(attack),
        'user_id': str(victim.user_id),
        'character_name': victim.character_name,
        **asdict(rolled),
        'effect': effect,
    }


def pick_victim(judging: Judging, monster: SceneMonster, victims: list[TableMember]) -> TableMember:
    """칠 대상. 이 마리에게서 훔치다 들킨 도둑이 칠 수 있는 대상이면 그 사람, 아니면 서버의 주사위로 고른다."""
    thief = judging.provoked.get(monster.state.id)
    caught = next((victim for victim in victims if victim.user_id == thief), None)
    return caught if caught is not None else choose(victims, judging.dice)


def take_monster_turn(judging: Judging, monster: SceneMonster) -> dict:
    """
    몬스터 한 마리의 차례를 판정한다. 차례의 outcome 에 적을 문서를 돌려준다.

    움직이지 못하면 {'skipped': 까닭} 이다. 대상, 공격, 판정, 피해의 차례로 주사위를 굴린다.
    쓰러진 대상을 쳤으면 피해의 주사위가 없고 downed_strike 가 있다(hit_outcome).
    고른 공격의 비용이 모자라면 굴리지 않는다(short_outcome). 비용이 있는 공격이면 낸 비용(cost)을 적는다(#805 ③-a).
    """
    stopped = stopped_by(judging, monster)
    if stopped is not None:
        return {'skipped': stopped}
    victims = victims_of(judging, monster)
    if not victims:
        return {'skipped': Skipped.NO_TARGET}
    victim = pick_victim(judging, monster, victims)
    mark_fight(judging, monster.state, victim)
    attack = choose(monster.definition.attacks, judging.dice)
    if not affordable(judging, monster.state, attack, ResourceHolder.MONSTERS):
        return short_outcome(attack, victim)
    cost = pay(judging, monster.state, attack, ResourceHolder.MONSTERS)
    blow = plan_attack_blow(judging, blows.monster_weapon(judging, monster, attack), victim)
    rolled = roll_attack(judging, monster, attack, blow)
    outcome = hit_outcome(judging, attack, victim, rolled.check, blow)
    return {**outcome, **cost, 'hindrance': round_injuries.hindrance_document(rolled)}
