# game-server/app/rounds/checks.py

"""
판정하는 행동의 결과를 정한다. 판정을 한 번 하고, 그 결과로 HP 와 NPC 의 상태와 부상이 바뀐다.

판정은 닫기 시작할 때 한 번만 한다(app/rounds/judging.py). 결과를 선언에 적어 두고, 그 뒤로는 읽기만 한다.
HP 도 그때 한 번만 바뀐다. 판정의 결과에 따라 피해를 입거나 회복한다(app/engine/health.py).
행동이 NPC 를 겨눴으면 그 NPC 가 피해를 입거나 회복한다(app/tables/npcs.py 의 change_npc).
행동이 몬스터를 겨눴으면 그 마리가 피해를 입는다(app/tables/monsters.py 의 change_monster). 몬스터는 부상을 입지 않는다.
겨눈 마리가 판정할 때 이미 죽었거나 다른 곳에 있으면 굴리지 않고 그 까닭을 적는다(target_gone).
살아 있던 마리를 처음 쓰러뜨리면 엔진이 드롭을 굴려 그 장소의 한 명에게 준다(app/rounds/drops.py).
큰 타격이나 쓰러짐이면 부상 표를 굴린다. 노려 친 타격은 그 부상이 확정으로 생긴다.
DB 를 모른다. 시트와 NPC 의 상태를 고친다. 저장하지는 않는다.
"""

from dataclasses import asdict

from app.engine import action as actions
from app.engine import health
from app.engine.action import CheckAction, Consequence, Recipient
from app.engine.check import Check
from app.engine.health import Change, ChangeKind
from app.rounds import drops, wakes
from app.rounds import injuries as round_injuries
from app.rounds.cast import find_cast_member
from app.rounds.effects import (
    Judging,
    injury_after,
    mark_fight,
    mark_hurt,
    mark_npc_fight,
    member_effect,
    monster_effect,
    npc_effect,
)
from app.rounds.monster_scene import Gone, find_scene_monster, gone_reason
from app.tables import monsters as table_monsters
from app.tables import npcs, sheets
from app.tables import state as table_state
from app.tables.models import GameTable, TableMember, TableNpc


def find_affected(
    table: GameTable, actor: TableMember, action: CheckAction, recipient: Recipient
) -> TableMember | None:
    """
    HP 가 바뀔 사람을 찾는다. 실패의 대가는 행동한 사람이 입고, 회복은 행동의 대상이 받는다.

    대상이 그사이에 테이블을 떠났으면 None.
    """
    return actor if recipient == Recipient.ACTOR else table_state.find_member(table, action.target)


def change_member(judging: Judging, actor: TableMember, action: CheckAction, found: Consequence) -> dict | None:
    """
    앉은 사람의 HP 를 바꾸고, 바뀐 내용을 문서로 돌려준다. 바뀔 HP 가 없으면 None.

    시트의 hp 를 고친다. 저장하지는 않는다. 양을 정하는 주사위를 여기서 굴린다.
    큰 타격이나 쓰러짐이면 부상 표도 굴린다(injury_roll). 양의 주사위 다음에 굴린다.
    돌려준 문서는 선언의 outcome 안에 적힌다.
    """
    affected = find_affected(judging.table, actor, action, found.recipient)
    return change_sheet(judging, affected, found.kind, found.magnitude)


def change_sheet(judging: Judging, affected: TableMember | None, kind: ChangeKind, magnitude_key: str) -> dict | None:
    """
    앉은 사람 하나의 HP 를 그 등급만큼 바꾸고, 바뀐 내용을 문서로 돌려준다. 바뀔 HP 가 없으면 None.

    판정의 결과와 소모품의 회복(app/rounds/item_actions.py)이 함께 쓴다.
    """
    # 대상이 떠났거나 시트가 없으면 바뀔 HP 가 없다. 양을 정하는 주사위도 굴리지 않는다.
    # 죽은 캐릭터도 그렇다. 회복으로 되살리지 못한다
    if affected is None or affected.sheet is None or sheets.is_dead(affected):
        return None

    sheet = affected.sheet
    magnitude = health.find_magnitude(judging.ruleset, magnitude_key)
    change = health.change_hp(kind, magnitude, sheet.hp, sheet.max_hp, judging.dice)
    sheet.hp = change.after
    if kind == ChangeKind.DAMAGE:
        mark_hurt(judging, affected)
    # 일어났으면 죽음의 굴림에서 센 것은 처음으로 돌아간다. 다시 쓰러지면 처음부터 센다
    if not change.downed:
        sheets.clear_death_saves(sheet)
    # 캐릭터는 피해로 바로 죽지 않는다(죽음의 굴림으로 죽는다)
    injury_roll = injury_after(judging, change, sheet.max_hp, False, sheet.injuries)
    return member_effect(affected, magnitude_key, change, injury_roll)


def npc_injury(judging: Judging, action: CheckAction, change: Change, npc: TableNpc) -> dict | None:
    """
    HP 가 바뀐 NPC 가 입는 부상. 노려 친 타격이면 그 부상이 확정으로 생기고 표를 굴리지 않는다.
    아니면 큰 타격이나 쓰러짐에 표를 굴린다. 죽었으면 어느 쪽도 없다. 회복이면 아무것도 없다.
    """
    if npcs.is_dead(npc):
        return None
    if action.aim is not None and change.kind == ChangeKind.DAMAGE:
        return round_injuries.take_aimed(judging.ruleset, action.aim, npc.injuries, judging.table.id, judging.moment)
    return injury_after(judging, change, npc.max_hp, False, npc.injuries)


def change_cast_member(judging: Judging, action: CheckAction, found: Consequence) -> dict | None:
    """
    겨눈 NPC 의 HP 와 생사를 바꾸고, 바뀐 내용을 문서로 돌려준다. 바뀔 것이 없으면 None.

    상태를 고치는 것은 change_npc 다. 저장하지는 않는다.
    큰 타격이나 쓰러짐이면 부상 표도 굴린다. 죽었으면 굴리지 않는다.
    같은 라운드에 앞사람이 그 NPC 를 죽였으면 아무 일도 없다. 양을 정하는 주사위도 굴리지 않는다.
    """
    member = find_cast_member(judging.cast, action.npc)
    # 선언을 받을 때 장면의 인물인지 봤다. 장면은 바뀌지 않으므로 없을 수 없지만, 없으면 아무 일도 없는 것으로 둔다
    if member is None or npcs.is_dead(member.npc):
        return None

    npc = member.npc
    status_before = npc.status
    magnitude = health.find_magnitude(judging.ruleset, found.magnitude)
    change = npcs.change_npc(npc, found.kind, magnitude, action.lethal, judging.dice)
    injury_roll = npc_injury(judging, action, change, npc)
    return npc_effect(member, found.magnitude, change, action.lethal, status_before, injury_roll)


def change_scene_monster(judging: Judging, action: CheckAction, found: Consequence) -> dict | None:
    """
    겨눈 몬스터 한 마리의 HP 와 생사를 바꾸고, 바뀐 내용을 문서로 돌려준다. 바뀔 것이 없으면 None.

    상태를 고치는 것은 change_monster 다. 저장하지는 않는다. 쓰러질지 부서질지는 그 몬스터의 타입이 정한다.
    판정하기 전에 칠 수 있는지 봤다(target_gone). 그래도 없거나 죽었으면 아무 일도 없는 것으로 둔다.
    """
    monster = find_scene_monster(judging.monsters, action.monster)
    if monster is None or table_monsters.is_dead(monster.state):
        return None

    status_before = monster.state.status
    magnitude = health.find_magnitude(judging.ruleset, found.magnitude)
    traits = table_monsters.traits_of(monster.definition.kind)
    change = table_monsters.change_monster(monster.state, traits, magnitude, action.lethal, judging.dice)
    return monster_effect(monster, found.magnitude, change, action.lethal, status_before)


def target_gone(judging: Judging, member: TableMember, action: CheckAction) -> dict | None:
    """
    겨눈 몬스터를 지금 칠 수 없으면 그 까닭을 문서로. 칠 수 있거나 몬스터를 겨누지 않았으면 None.

    받을 때는 칠 수 있었어도 차례가 오기 전에 앞사람이 죽였을 수 있다. 그때는 판정을 굴리지 않는다.
    굴리면 실패의 대가를 치를 수 있는데, 칠 상대가 없는 행동이었다.
    """
    if action.monster is None:
        return None
    monster = find_scene_monster(judging.monsters, action.monster)
    if monster is None:
        return {'monster_id': str(action.monster), 'name': None, 'reason': Gone.ELSEWHERE}
    reason = gone_reason(member, monster)
    if reason is None:
        return None
    return {'monster_id': str(monster.state.id), 'name': monster.name, 'reason': reason}


def monster_outcome(judging: Judging, action: CheckAction, found: Consequence) -> dict:
    """
    몬스터를 친 판정의 결과 칸들. 마리의 변화(monster_effect)와, 처음 쓰러뜨려 무엇이 나왔으면 그 드롭(drop)이다.

    drop 은 나온 것이 있을 때만 적는다. 드롭이 없는 판정의 결과는 이 칸이 생기기 전과 같다.
    """
    effect = change_scene_monster(judging, action, found)
    outcome = {'effect': None, 'npc_effect': None, 'monster_effect': effect}
    drop = drops.drop_after(judging, effect)
    if drop is not None:
        outcome['drop'] = drop
    return outcome


def npc_outcome(judging: Judging, actor: TableMember, action: CheckAction, found: Consequence) -> dict:
    """
    NPC 를 겨눈 판정의 결과 칸들. NPC 의 변화(npc_effect)와, 처음 쓰러뜨려 무엇이 나왔으면 그 드롭(drop),
    쓰러진 동안 빼앗겼던 인물을 일으켰으면 깨어날 때의 반응(wake)이다.

    drop 과 wake 는 있을 때만 적는다. 받는 곳은 친 사람이 선 장소다(app/rounds/drops.py, app/rounds/wakes.py).
    """
    effect = change_cast_member(judging, action, found)
    outcome = {'effect': None, 'npc_effect': effect}
    drop = drops.npc_drop_after(judging, actor, effect)
    if drop is not None:
        outcome['drop'] = drop
    wake = wakes.wake_after(judging, effect)
    if wake is not None:
        outcome['wake'] = wake
    return outcome


def apply_consequence(judging: Judging, actor: TableMember, action: CheckAction, check: Check) -> dict:
    """
    판정의 결과에 따라 HP 를 바꾸고, 바뀐 내용을 선언의 outcome 에 넣을 칸들로 돌려준다.

    effect 는 앉은 사람의 변화, npc_effect 는 NPC 의 변화, monster_effect 는 몬스터의 변화다.
    몬스터나 NPC 를 처음 쓰러뜨려 무엇이 나왔으면 drop 도 있다(app/rounds/drops.py).
    한 판정에서 하나만 일어난다. 없으면 effect 와 npc_effect 가 None 이다.
    monster_effect 는 몬스터를 겨눈 판정에만 적는다. 몬스터가 없는 판정의 결과는 이 칸이 생기기 전과 같다.
    대가는 늘 행동한 사람이 입는다. 대상의 일(타격, 회복)은 행동이 겨눈 NPC 나 몬스터가, 아니면 앉은 사람이 받는다.
    """
    found = actions.consequence(action, check)
    if found is None:
        return {'effect': None, 'npc_effect': None}
    if found.recipient == Recipient.TARGET and action.monster is not None:
        return monster_outcome(judging, action, found)
    if found.recipient == Recipient.TARGET and action.npc is not None:
        return npc_outcome(judging, actor, action, found)
    return {'effect': change_member(judging, actor, action, found), 'npc_effect': None}


def mark_npc_attack(judging: Judging, member: TableMember, action: CheckAction) -> None:
    """
    NPC 를 타격(harm)으로 겨눴으면 그 NPC 와 싸운 것으로 적는다. 맞든 빗나가든 싸움이다. 몬스터와 같다.

    회복이나 타격 없는 판정(설득 같은)은 싸움이 아니다. 이미 죽은 NPC 는 적지 않는다.
    """
    if action.npc is None or action.harm is None:
        return
    person = find_cast_member(judging.cast, action.npc)
    if person is not None and not npcs.is_dead(person.npc):
        mark_npc_fight(judging, person.npc, member)


def judge_check(judging: Judging, member: TableMember, action: CheckAction) -> dict:
    """
    한 사람의 판정하는 행동을 판정하고 그 결과를 정한다. 선언의 outcome 에 적을 문서를 돌려준다.

    그 캐릭터가 입은 부상이 이 행동의 능력에 주는 것(보정 깎기, 불리함)을 판정에 적용한다(hindrance).
    겨눈 몬스터를 지금 칠 수 없으면 굴리지 않고 그 까닭만 적는다(target_gone).
    """
    gone = target_gone(judging, member, action)
    if gone is not None:
        return {'target_gone': gone}
    if action.monster is not None:
        mark_fight(judging, find_scene_monster(judging.monsters, action.monster).state, member)
    mark_npc_attack(judging, member, action)
    sheet = member.sheet
    hindrance = round_injuries.hindrance_for(judging.ruleset, sheet.injuries, action.ability)
    hindered = actions.attempt_hindered(judging.ruleset, action, sheet.abilities, judging.dice, hindrance)
    return {
        **asdict(hindered.check),
        'hindrance': round_injuries.hindrance_document(hindered),
        'called_shot': round_injuries.called_shot_document(judging.ruleset, action.aim),
        **apply_consequence(judging, member, action, hindered.check),
    }
