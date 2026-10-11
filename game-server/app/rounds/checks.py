# game-server/app/rounds/checks.py

"""
판정하는 행동의 결과를 정한다. 판정을 한 번 하고, 그 결과로 HP 와 NPC 의 상태와 부상이 바뀐다.

판정은 닫기 시작할 때 한 번만 한다(app/rounds/judging.py). 결과를 선언에 적어 두고, 그 뒤로는 읽기만 한다.
HP 도 그때 한 번만 바뀐다. 판정의 결과에 따라 피해를 입거나 회복한다(app/engine/health.py).
행동이 NPC 를 겨눴으면 그 NPC 가 피해를 입거나 회복한다(app/tables/npcs.py 의 change_npc).
큰 타격이나 쓰러짐이면 부상 표를 굴린다. 노려 친 타격은 그 부상이 확정으로 생긴다.
DB 를 모른다. 시트와 NPC 의 상태를 고친다. 저장하지는 않는다.
"""

from dataclasses import asdict

from app.engine import action as actions
from app.engine import health
from app.engine.action import CheckAction, Consequence, Recipient
from app.engine.check import Check
from app.engine.health import Change, ChangeKind
from app.rounds import injuries as round_injuries
from app.rounds.cast import find_cast_member
from app.rounds.effects import Judging, injury_after, member_effect, npc_effect
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
    # 대상이 떠났거나 시트가 없으면 바뀔 HP 가 없다. 양을 정하는 주사위도 굴리지 않는다.
    # 죽은 캐릭터도 그렇다. 회복으로 되살리지 못한다
    if affected is None or affected.sheet is None or sheets.is_dead(affected):
        return None

    sheet = affected.sheet
    magnitude = health.find_magnitude(judging.ruleset, found.magnitude)
    change = health.change_hp(found.kind, magnitude, sheet.hp, sheet.max_hp, judging.dice)
    sheet.hp = change.after
    # 일어났으면 죽음의 굴림에서 센 것은 처음으로 돌아간다. 다시 쓰러지면 처음부터 센다
    if not change.downed:
        sheets.clear_death_saves(sheet)
    # 캐릭터는 피해로 바로 죽지 않는다(죽음의 굴림으로 죽는다)
    injury_roll = injury_after(judging, change, sheet.max_hp, False, sheet.injuries)
    return member_effect(affected, found.magnitude, change, injury_roll)


def npc_injury(judging: Judging, action: CheckAction, change: Change, npc: TableNpc) -> dict | None:
    """
    HP 가 바뀐 NPC 가 입는 부상. 노려 친 타격이면 그 부상이 확정으로 생기고 표를 굴리지 않는다.
    아니면 큰 타격이나 쓰러짐에 표를 굴린다. 죽었으면 어느 쪽도 없다. 회복이면 아무것도 없다.
    """
    if npcs.is_dead(npc):
        return None
    if action.aim is not None and change.kind == ChangeKind.DAMAGE:
        return round_injuries.take_aimed(
            judging.ruleset, action.aim, npc.injuries, judging.table.id, judging.round_number
        )
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


def apply_consequence(judging: Judging, actor: TableMember, action: CheckAction, check: Check) -> dict:
    """
    판정의 결과에 따라 HP 를 바꾸고, 바뀐 내용을 선언의 outcome 에 넣을 칸들로 돌려준다.

    effect 는 앉은 사람의 변화, npc_effect 는 NPC 의 변화다. 한 판정에서 둘 중 하나만 일어난다. 없으면 둘 다 None.
    대가는 늘 행동한 사람이 입는다. 대상의 일(타격, 회복)은 행동이 NPC 를 겨눴으면 NPC 가, 아니면 앉은 사람이 받는다.
    """
    found = actions.consequence(action, check)
    if found is None:
        return {'effect': None, 'npc_effect': None}
    if found.recipient == Recipient.TARGET and action.npc is not None:
        return {'effect': None, 'npc_effect': change_cast_member(judging, action, found)}
    return {'effect': change_member(judging, actor, action, found), 'npc_effect': None}


def judge_check(judging: Judging, member: TableMember, action: CheckAction) -> dict:
    """
    한 사람의 판정하는 행동을 판정하고 그 결과를 정한다. 선언의 outcome 에 적을 문서를 돌려준다.

    그 캐릭터가 입은 부상이 이 행동의 능력에 주는 것(보정 깎기, 불리함)을 판정에 적용한다(hindrance).
    """
    sheet = member.sheet
    hindrance = round_injuries.hindrance_for(judging.ruleset, sheet.injuries, action.ability)
    hindered = actions.attempt_hindered(judging.ruleset, action, sheet.abilities, judging.dice, hindrance)
    return {
        **asdict(hindered.check),
        'hindrance': round_injuries.hindrance_document(hindered),
        'called_shot': round_injuries.called_shot_document(judging.ruleset, action.aim),
        **apply_consequence(judging, member, action, hindered.check),
    }
