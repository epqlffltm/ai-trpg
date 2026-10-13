# game-server/app/rounds/judging.py

"""
닫히는 라운드의 판정. 닫기 시작할 때 한 번만 한다(app/rounds/service.py 의 begin_closing).

서술이 실패해 다시 맡겨도 주사위를 다시 굴리지 않는다. 다시 굴리면 서술을 실패시켜 결과를 바꿀 수 있다.
  1. 행동들을 들어온 순서로 판정한다(roll_checks). 판정이면 app/rounds/checks.py, 치료면 app/rounds/treatments.py,
     지목이면 app/rounds/naming.py(주사위를 굴리지 않는다), 물건을 쓰거나 건네면 app/rounds/item_actions.py.
  2. 쓰러진 캐릭터는 죽음의 굴림을 굴린다(roll_death_saves, app/engine/death.py).
     이번 라운드에 쓰러진 캐릭터는 굴리지 않는다. 동료가 일으킬 틈이 한 라운드는 있다.
     이번 라운드에 회복을 받아 일어난 캐릭터도 굴리지 않는다. 행동의 결과를 먼저 끝내고 나서 굴린다.
  3. 때가 된 부상을 끝낸다(expire_injuries). 오래 가는 것이 나으면 후유증 표를 굴린다.
DB 를 모른다. 이미 읽어 온 테이블과 이번 장면을 고친다. 저장과 이벤트는 부른 쪽이 한다.
"""

from dataclasses import asdict

from app.assets.scenarios.snapshot import person_entries, read_snapshot
from app.engine import action as actions
from app.engine import death
from app.engine.action import CheckAction, GiveAction, NameAction, TreatAction, UseAction
from app.engine.dice import Dice
from app.rounds import injuries as round_injuries
from app.rounds.cast import Scene
from app.rounds.checks import judge_check
from app.rounds.effects import Judging
from app.rounds.item_actions import judge_give, judge_use
from app.rounds.models import Round
from app.rounds.naming import judge_naming
from app.rounds.state import find_declaration, rules_of
from app.rounds.treatments import judge_treatment
from app.tables import items, sheets
from app.tables.models import GameTable, TableMember


def judge(
    judging: Judging, member: TableMember, action: CheckAction | TreatAction | NameAction | UseAction | GiveAction
) -> dict:
    """
    한 사람의 행동을 판정하고 그 결과를 정한다.
    행동의 종류에 따라 판정(judge_check), 치료(judge_treatment), 지목(judge_naming),
    물건 쓰기(judge_use), 건네기(judge_give)다.
    """
    if isinstance(action, TreatAction):
        return judge_treatment(judging, member, action)
    if isinstance(action, NameAction):
        return judge_naming(judging, action)
    if isinstance(action, UseAction):
        return judge_use(judging, member, action)
    if isinstance(action, GiveAction):
        return judge_give(judging, member, action)
    return judge_check(judging, member, action)


def roll_checks(table: GameTable, round_: Round, dice: Dice, scene: Scene) -> None:
    """
    닫히는 라운드의 행동을 판정하고, 결과에 따라 HP 를 바꾸고, 결과를 선언에 적는다. 들어온 순서로 굴린다.

    한 사람의 판정과 그 결과(피해, 회복, 부상, 치료)를 끝낸 뒤에 다음 사람으로 넘어간다.
    앞사람이 쓰러뜨린 것을 뒷사람이 일으킬 수 있다. NPC 도 그렇다. 앞사람이 죽인 NPC 는 뒷사람이 바꾸지 못한다.
    같은 부상을 여럿이 치료하면 앞사람부터 차례로 적용한다. 앞사람이 다 낫게 했으면 뒷사람은 치료할 것이 없다.
    앞사람의 치료가 실패해 즉사한 캐릭터는 자기 차례에 행동하지 못한다. 판정도 결과도 없다.
    scene 은 이번 장면의 NPC 들이다(app/rounds/cast.py). NPC 의 상태는 그 안에 들어 있고, 여기서 고친다.
    지목은 장면에 나오지 않은 인물도 짚을 수 있어서 상태 전부(scene.npcs)를 함께 넘긴다.

    지금 앉아 있고, 선언에 행동을 붙였고, 시트가 있는 사람만 굴린다.
    진행 중인 테이블에서는 모두에게 시트가 있다(app/tables/sheets.py). 없는 사람이 있어도 라운드는 닫혀야 해서 건너뛴다.

    판의 복사본(규칙과 인물 항목)은 굴릴 사람이 있을 때만 한 번 읽는다. 통째로 읽는 일이라 싸지 않다.
    """
    rolling = [
        (member, declaration)
        for member in table.members
        if (declaration := find_declaration(round_, member.user_id)) is not None
        and declaration.action is not None
        and member.sheet is not None
    ]
    if not rolling:
        return

    snapshot = read_snapshot(table.content)
    judging = Judging(
        table=table,
        ruleset=snapshot.rulebook.rules,
        dice=dice,
        cast=scene.cast,
        round_number=round_.number,
        npcs=scene.npcs,
        people=person_entries(snapshot),
        items=items.catalog(snapshot),
    )
    for member, declaration in rolling:
        # 앞사람의 치료가 실패해 즉사했으면 그 캐릭터는 행동하지 못한다. 쓰러진 것과 다르다
        if sheets.is_dead(member):
            continue
        declaration.outcome = judge(judging, member, actions.read_action(declaration.action))


def find_dying(table: GameTable) -> list[TableMember]:
    """앉은 사람 중에서 캐릭터가 쓰러져 있고 아직 죽지 않은 사람들. 들어온 순서다."""
    return [member for member in table.members if sheets.is_downed_alive(member)]


def roll_death_saves(table: GameTable, dying: list[TableMember], dice: Dice) -> list[dict]:
    """
    죽음의 굴림을 굴리고, 센 것을 시트에 적고, 굴린 것들을 문서의 목록으로 돌려준다. 들어온 순서로 굴린다.

    dying 은 이 라운드의 행동을 판정하기 전에 쓰러져 있던 사람들이다. 그중 지금도 쓰러져 있는 사람만 굴린다.
    그사이에 회복을 받아 일어난 사람은 굴리지 않는다.
    고비를 넘긴 사람과, 죽음의 굴림이 없는 규칙의 테이블은 굴릴 것이 없다(app/engine/death.py).
    실패가 다 모이면 그 자리에서 죽은 것으로 적는다.

    돌려준 목록은 라운드에 적힌다. 서술자와 이벤트는 그것을 읽는다. 다시 굴리지 않는다.
    규칙은 굴릴 사람이 있을 때만 읽는다.
    """
    still_down = [member for member in dying if sheets.is_downed_alive(member)]
    if not still_down:
        return []

    ruleset = rules_of(table)
    rolled = []
    for member in still_down:
        sheet = member.sheet
        save = death.roll_death_save(ruleset, sheet.death_successes, sheet.death_failures, dice)
        if save is None:
            continue
        sheet.death_successes = save.successes
        sheet.death_failures = save.failures
        if save.fate == death.Fate.DEAD:
            sheets.mark_dead(sheet)
        rolled.append({'user_id': str(member.user_id), 'character_name': member.character_name, **asdict(save)})
    return rolled


def expire_injuries(table: GameTable, scene: Scene, round_number: int, dice: Dice) -> list[round_injuries.Ended]:
    """
    이 라운드가 닫힐 때 풀리거나 나을 부상을 끝낸다. 끝난 것들을 돌려준다.

    오래 가는 것이 나으면 후유증 표를 굴린다. 그 순서는 앉은 사람, 그다음 NPC 다(app/rounds/injuries.py).
    끝날 부상이 하나도 없으면 규칙을 읽지 않는다. 판에 굳은 복사본을 통째로 읽는 일이라 싸지 않다.
    """
    if not round_injuries.any_due(table.members, scene, round_number):
        return []
    return round_injuries.expire_all(table.members, scene, rules_of(table), dice, table.id, round_number)
