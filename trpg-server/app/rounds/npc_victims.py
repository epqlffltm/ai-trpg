# trpg-server/app/rounds/npc_victims.py

"""
몬스터가 치는 인물(NPC)(#254 NPC와 몬스터 사이). 몬스터의 차례(app/rounds/monster_attacks.py)가 쓴다.

몬스터는 같은 장소의 캐릭터만이 아니라 인물도 친다. 적대인 인물도, 적대가 아닌 인물도 친다.
누구를 칠 수 있는지, 맞으면 무엇이 바뀌는지는 엔진이 정한다. 서술(AI)이 끼지 않는다.
  - 대상(victims_of): 이번 장면의 인물 중 자리가 있고 그 마리와 같은 장소에 있는 인물이다.
    살아 있거나, 라운드를 닫기 시작할 때부터 쓰러져 있던 인물이다(캐릭터와 같다, app/rounds/downed_strikes.py).
    이번 라운드에 쓰러진 인물은 다음 라운드부터 대상이다. 일행이 일으키거나 치료할 틈이다.
    그 마리와 한편인 인물은 치지 않는다(is_allied). NPC 시트의 allied_monsters 에 그 몬스터를 적은 인물이다.
    자리가 없는 인물은 장소를 몰라서 치지 않는다.
  - 서 있는 인물을 맞히면 피해를 준다. 피해, 성질과 저항, 장비의 방어, 부상 표는 일행이 인물을 칠 때와 같다
    (app/rounds/checks.py 의 change_cast_member). 몬스터의 공격은 제압이다(lethal 이 아니다). HP 가 0 이 되면 쓰러진다.
  - 쓰러진 인물을 맞히면 마무리한다(finishing). 죽이려는 타격으로 피해를 주어 죽는다.
    인물에게는 죽음의 굴림이 없다. 세이브로 막으면 맞지 않은 것과 같다.
  - 공격의 효과(부상, 수치의 맞추기, #805 ③-b)는 판정에 맞혔으면 든다. 덫의 효과와 같은 길이다
    (app/rounds/item_targets.py 의 apply_to_struck). 그 타격으로 죽었으면 들지 않는다.
  - 몬스터가 처음 쓰러뜨린 인물은 드롭을 굴린다. 덫에 쓰러진 인물과 같다(app/rounds/drops.py 의 npc_drop_at).
    받는 사람은 그 인물이 선 장소의 한 명이다. 마무리해 죽였을 때는 이미 쓰러진 적이 있어 굴리지 않는다.

DB 를 모른다. 인물의 상태를 고친다. 저장하지는 않는다.
"""

from app.assets.scenarios.snapshot import AttackSnapshot
from app.engine.action import ActionKind, CheckAction, Consequence, Recipient
from app.engine.health import ChangeKind
from app.engine.injury import Trigger
from app.engine.ruleset import ResourceHolder
from app.rounds import blows, resisting
from app.rounds.blows import Blow
from app.rounds.cast import CastMember
from app.rounds.checks import change_cast_member
from app.rounds.effects import Judging
from app.rounds.item_targets import Struck, apply_to_struck
from app.rounds.monster_scene import SceneMonster
from app.rounds.state import required
from app.tables import npcs
from app.tables.models import NpcStatus


def is_allied(person: CastMember, monster: SceneMonster) -> bool:
    """이 인물이 그 마리와 한편인가. 인물의 시트에 그 몬스터를 적었다. 시트가 없는 인물은 누구와도 한편이 아니다."""
    return person.definition is not None and monster.definition.id in person.definition.allied_monsters


def can_be_struck(judging: Judging, person: CastMember) -> bool:
    """
    이 인물이 몬스터의 대상이 될 수 있는가. 장소와 편은 보지 않는다(부르는 쪽이 본다).

    살아 있거나, 라운드를 닫기 시작할 때부터 쓰러져 있었다.
    """
    if person.npc.status == NpcStatus.ALIVE:
        return True
    return person.npc.status == NpcStatus.DOWNED and person.entry_id in judging.npcs_downed_at_start


def victims_of(judging: Judging, monster: SceneMonster) -> list[CastMember]:
    """이 마리가 칠 수 있는 인물들. 같은 장소에 있고, 칠 수 있고, 한편이 아닌 인물이다. 장면의 인물 순서다."""
    place_id = monster.state.place_id
    return [
        person
        for person in judging.cast
        if person.npc.place_id is not None
        and person.npc.place_id == place_id
        and can_be_struck(judging, person)
        and not is_allied(person, monster)
    ]


def is_finishing(person: CastMember) -> bool:
    """쓰러진 인물을 치는가. 그러면 맞혔을 때 마무리한다(죽인다)."""
    return person.npc.status == NpcStatus.DOWNED


def strike_check(attack: AttackSnapshot, person: CastMember) -> CheckAction:
    """
    몬스터의 타격을 인물에게 겨눈 판정의 모양. HP 를 바꾸는 함수가 대상과 lethal 을 읽는다.

    서 있는 인물에게는 제압(쓰러뜨린다), 쓰러진 인물에게는 죽이려는 타격(마무리한다)이다.
    """
    return CheckAction(
        kind=ActionKind.CHECK,
        ability=attack.ability,
        harm=attack.harm,
        npc=person.entry_id,
        lethal=is_finishing(person),
    )


def harm_of(attack: AttackSnapshot) -> Consequence:
    """공격의 피해. 맞은 인물이 받는다. 피해 등급이 있는 공격에만 부른다."""
    return Consequence(kind=ChangeKind.DAMAGE, magnitude=required(attack.harm, 'harm'), recipient=Recipient.TARGET)


def plan_npc_blow(judging: Judging, weapon: blows.Weapon | None, person: CastMember) -> Blow:
    """몬스터의 타격 하나에 장비가 드는 것을 정한다. 인물이 착용한 것으로 방어를 세고 부위를 굴린다."""
    return blows.plan_blow(judging, weapon, blows.npc_protection(judging, person), None)


def wound(judging: Judging, attack: AttackSnapshot, person: CastMember, blow: Blow, nature: str | None) -> dict | None:
    """
    맞힌 타격의 피해를 인물에게 준다. 바뀐 것(npc_effect 의 모양)을 돌려준다. 피해 등급이 없는 공격이면 None.

    맞은 부위의 방어가 깎는 양(blow.cut)만큼 덜 입는다. 성질(nature)은 그 인물의 저항을 따른다.
    """
    if attack.harm is None:
        return None
    return change_cast_member(judging, strike_check(attack, person), harm_of(attack), blow.cut, nature)


def struck_npc(judging: Judging, person: CastMember) -> Struck:
    """공격의 효과를 받을 쪽으로서의 인물. 인물의 상태와 수치, 지금 막는 성질이다."""
    return Struck(person.npc, ResourceHolder.NPCS, None, lambda: resisting.of_cast(judging, person))


def effects_on(judging: Judging, attack: AttackSnapshot, person: CastMember, hit: bool) -> dict:
    """
    공격의 효과(#805 ③-b)를 맞은 인물에게 낸다. 입힌 것(injured)과 맞춘 수치(resources)다.

    효과가 없는 공격이면 빈 문서다(차례의 모양이 바뀌지 않는다). 빗나갔거나 그 타격으로 죽었으면 내지 않는다.
    """
    if not attack.effects:
        return {}
    if not hit or npcs.is_dead(person.npc):
        return {'injured': [], 'resources': []}
    applied = apply_to_struck(judging, struck_npc(judging, person), attack.effects, trigger=Trigger.ATTACK)
    return {'injured': applied['injured'], 'resources': applied['resources']}


def target_document(person: CastMember) -> dict:
    """차례의 outcome 에 적을 맞은 인물. 항목의 id 와 장면의 이름이다. 쓰러진 인물을 쳤으면 finishing 이 참이다."""
    return {
        'target_entry_id': str(person.entry_id),
        'target_name': person.name,
        'finishing': is_finishing(person),
    }
