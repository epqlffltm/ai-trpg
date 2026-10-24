# trpg-server/app/rounds/judging.py

"""
닫히는 라운드의 판정. 닫기 시작할 때 한 번만 한다(app/rounds/service.py 의 begin_closing).

서술이 실패해 다시 맡겨도 주사위를 다시 굴리지 않는다. 다시 굴리면 서술을 실패시켜 결과를 바꿀 수 있다.
  1. 행동들을 판정한다(roll_checks). 맞붙은 몬스터나 싸우는 NPC 가 있으면 차례(app/rounds/initiative.py)대로 행동과
     몬스터의 공격(app/rounds/monster_attacks.py), NPC 의 공격(app/rounds/npc_attacks.py)을 판정하고,
     없으면 들어온 순서로 판정한다.
     판정이면 app/rounds/checks.py, 치료면 app/rounds/treatments.py,
     지목이면 app/rounds/naming.py(주사위를 굴리지 않는다), 물건을 쓰거나 건네면 app/rounds/item_actions.py,
     던지면 app/rounds/throws.py(#277, 물건에 적힌 판정으로 치기),
     맵에서 가거나 찾으면 app/rounds/map_actions.py, 쉬면 app/rounds/rests.py(시간만 늘리고 회복은 4 에서),
     사고팔거나 돈을 건네면 app/rounds/trades.py, 엄폐하면 app/rounds/covers.py(굴림이 없다).
     엄폐한 사람의 커버는 판정을 시작하기 전에 정한다. 차례를 기다리지 않고 그 라운드 동안 든다.
  2. 쓰러진 캐릭터는 죽음의 굴림을 굴린다(roll_death_saves, app/engine/death.py).
     이번 라운드에 쓰러진 캐릭터는 굴리지 않는다. 동료가 일으킬 틈이 한 라운드는 있다.
     이번 라운드에 회복을 받아 일어난 캐릭터도 굴리지 않는다. 행동의 결과를 먼저 끝내고 나서 굴린다.
  3. 때가 된 부상을 끝낸다(expire_injuries). 오래 가는 것이 나으면 후유증 표를 굴린다.
  4. 쉰 사람이 회복하고, 고비를 넘긴 사람이 되살아나기를 굴리고, 저절로 회복한다(app/rounds/rests.py).
     이번 라운드에 누가 다쳤는지(roll_checks 가 돌려준다)를 보고 정한다. 다친 사람의 휴식은 깨진다.
DB 를 모른다. 이미 읽어 온 테이블과 이번 장면을 고친다. 저장과 이벤트는 부른 쪽이 한다.
"""

import uuid
from dataclasses import asdict

from app.assets.scenarios.snapshot import person_entries, read_snapshot
from app.engine import action as actions
from app.engine import death
from app.engine.action import (
    AnyAction,
    BuyAction,
    CoverAction,
    DoorAction,
    GiveAction,
    LootAction,
    MoveAction,
    NameAction,
    PayAction,
    PutDownAction,
    RestAction,
    SearchAction,
    SellAction,
    StealAction,
    TakeAction,
    ThrowAction,
    TreatAction,
    UseAction,
    WaitAction,
)
from app.engine.dice import Dice
from app.rounds import initiative, npc_attacks
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember, Scene
from app.rounds.checks import judge_check
from app.rounds.covers import covers_of, judge_cover
from app.rounds.door_actions import judge_door
from app.rounds.effects import Judging
from app.rounds.initiative import Turn
from app.rounds.item_actions import judge_give, judge_use
from app.rounds.loots import judge_loot
from app.rounds.map_actions import judge_move, judge_search
from app.rounds.models import Declaration, Round
from app.rounds.monster_attacks import can_act, take_monster_turn
from app.rounds.monster_scene import SceneMonster
from app.rounds.naming import judge_naming
from app.rounds.place_item_actions import judge_put_down, judge_take, search_items
from app.rounds.rests import judge_rest
from app.rounds.state import find_declaration, rules_of
from app.rounds.steals import judge_steal
from app.rounds.throws import judge_throw
from app.rounds.trades import judge_buy, judge_pay, judge_sell
from app.rounds.treatments import judge_treatment
from app.rounds.waits import judge_wait
from app.tables import items, sheets
from app.tables.models import GameTable, TableMember


def judge(judging: Judging, member: TableMember, action: AnyAction) -> dict:
    """
    한 사람의 행동을 판정하고 그 결과를 정한다.
    행동의 종류에 따라 판정(judge_check), 치료(judge_treatment), 지목(judge_naming),
    물건 쓰기(judge_use), 건네기(judge_give), 가기(judge_move), 찾기(search_place), 줍기(judge_take),
    내려놓기(judge_put_down), 훔치기(judge_steal), 빼앗기(judge_loot), 쉬기(judge_rest), 기다리기(judge_wait),
    사기(judge_buy), 팔기(judge_sell), 돈 건네기(judge_pay), 엄폐하기(judge_cover),
    문 다루기(judge_door: 잠그기, 열기, 따기, 부수기, #281), 던지기(judge_throw, #277)다.
    """
    if isinstance(action, TreatAction):
        return judge_treatment(judging, member, action)
    if isinstance(action, NameAction):
        return judge_naming(judging, action)
    if isinstance(action, UseAction):
        return judge_use(judging, member, action)
    if isinstance(action, GiveAction):
        return judge_give(judging, member, action)
    if isinstance(action, ThrowAction):
        return judge_throw(judging, member, action)
    if isinstance(action, MoveAction):
        return judge_move(judging, member, action)
    if isinstance(action, SearchAction):
        return search_place(judging, member)
    if isinstance(action, TakeAction):
        return judge_take(judging, member, action)
    if isinstance(action, PutDownAction):
        return judge_put_down(judging, member, action)
    if isinstance(action, StealAction):
        return judge_steal(judging, member, action)
    if isinstance(action, LootAction):
        return judge_loot(judging, member, action)
    if isinstance(action, RestAction):
        return judge_rest(judging, action)
    if isinstance(action, WaitAction):
        return judge_wait(action)
    if isinstance(action, BuyAction):
        return judge_buy(judging, member, action)
    if isinstance(action, SellAction):
        return judge_sell(judging, member, action)
    if isinstance(action, PayAction):
        return judge_pay(judging, member, action)
    if isinstance(action, CoverAction):
        return judge_cover(judging, member)
    if isinstance(action, DoorAction):
        return judge_door(judging, member, action)
    return judge_check(judging, member, action)


def search_place(judging: Judging, member: TableMember) -> dict:
    """
    지금 장소를 찾는다. 숨긴 길을 먼저(app/rounds/map_actions.py), 숨긴 물건을 그다음에 굴린다
    (app/rounds/place_item_actions.py). 찾은 것만 결과에 적는다.
    """
    outcome = judge_search(judging, member)
    outcome['search']['items'] = search_items(judging, member)
    return outcome


def lost_turn(member: TableMember) -> str | None:
    """
    차례가 왔을 때 이 캐릭터가 행동하지 못하는 까닭. 행동할 수 있으면 None.

    선언을 낸 뒤 앞 차례에 쓰러지거나 죽을 수 있다(몬스터의 공격, 앞사람의 치료가 실패한 즉사).
    쓰러진 캐릭터는 선언을 내지 못하는 것과 같은 까닭으로 행동하지 못한다.
    """
    if sheets.is_dead(member):
        return 'dead'
    if sheets.is_downed_alive(member):
        return 'downed'
    return None


def take_member_turn(judging: Judging, member: TableMember, declaration: Declaration) -> None:
    """
    앉은 사람 한 명의 차례. 행동을 판정하고 그 결과를 선언에 적는다.

    차례가 오기 전에 쓰러지거나 죽었으면 판정하지 않고 그 까닭만 적는다(turn_lost). 판정도 결과도 없다.
    """
    lost = lost_turn(member)
    if lost is not None:
        declaration.outcome = {'turn_lost': lost}
        return
    declaration.outcome = judge(judging, member, actions.read_action(declaration.action))


def rolling_members(table: GameTable, round_: Round) -> list[tuple[TableMember, Declaration]]:
    """
    이번 라운드에 행동을 판정할 사람과 그 선언. 앉은 순서다.

    지금 앉아 있고, 선언에 행동을 붙였고, 시트가 있는 사람만이다.
    진행 중인 테이블에서는 모두에게 시트가 있다(app/tables/sheets.py). 없는 사람이 있어도 라운드는 닫혀야 해서 건너뛴다.
    """
    return [
        (member, declaration)
        for member in table.members
        if (declaration := find_declaration(round_, member.user_id)) is not None
        and declaration.action is not None
        and member.sheet is not None
    ]


def build_judging(
    table: GameTable,
    round_: Round,
    dice: Dice,
    scene: Scene,
    downed: frozenset[uuid.UUID] = frozenset(),
    rolling: list[tuple[TableMember, Declaration]] | None = None,
) -> Judging:
    """
    이번 라운드의 판정에 함께 쓰는 것들을 모은다.

    판의 복사본(규칙, 인물 항목, 물건, 맵)을 통째로 읽는다. 싸지 않아서 판정할 것이 있을 때만 부른다.
    downed 는 판정을 시작하기 전에 쓰러져 있던 사람들이다(몬스터와 NPC 가 칠 수 있다).
    rolling 은 행동을 판정할 사람과 그 선언이다. 엄폐한 사람의 커버를 여기서 정한다(app/rounds/covers.py).
    """
    snapshot = read_snapshot(table.content)
    return Judging(
        table=table,
        ruleset=snapshot.rulebook.rules,
        dice=dice,
        cast=scene.cast,
        round_number=round_.number,
        moment=round_injuries.moment_of(table, round_.number),
        npcs=scene.npcs,
        people=person_entries(snapshot),
        items=items.catalog(snapshot),
        snapshot=snapshot,
        monsters=scene.monsters,
        downed_at_start=downed,
        covers=covers_of(snapshot, rolling or []),
    )


def build_turns(
    judging: Judging,
    rolling: list[tuple[TableMember, Declaration]],
    acting: list[SceneMonster],
    fighting: list[CastMember],
) -> list[Turn]:
    """
    행동할 사람들과 공격할 마리들과 싸우는 인물들의 차례를 정한다(app/rounds/initiative.py).

    앉은 사람, 그다음 몬스터, 그다음 인물로 넘긴다.
    """
    ruleset, snapshot = judging.ruleset, judging.snapshot
    ambushed = initiative.ambushed_places(snapshot, judging.monsters, judging.round_number)
    turns = [initiative.member_turn(ruleset, member, ambushed) for member, _ in rolling]
    turns += [initiative.monster_turn(ruleset, snapshot, monster, judging.round_number) for monster in acting]
    turns += [initiative.npc_turn(ruleset, person) for person in fighting]
    return initiative.order_turns(turns, ruleset.die, judging.dice)


def take_turn(judging: Judging, turn: Turn, declarations: dict[uuid.UUID, Declaration]) -> dict:
    """
    차례 하나를 판정한다. 라운드의 turns 에 적을 문서를 돌려준다.

    앉은 사람의 결과는 그 사람의 선언에, 몬스터와 인물의 결과는 차례의 문서(outcome)에 적는다.
    """
    document = initiative.turn_document(turn)
    if turn.kind == initiative.TurnKind.PC:
        take_member_turn(judging, turn.member, declarations[turn.member.user_id])
    elif turn.kind == initiative.TurnKind.NPC:
        document['outcome'] = npc_attacks.take_npc_turn(judging, turn.npc)
    else:
        document['outcome'] = take_monster_turn(judging, turn.monster)
    return document


def take_turns(judging: Judging, turns: list[Turn], declarations: dict[uuid.UUID, Declaration]) -> list[dict]:
    """차례대로 판정한다. 앞 차례의 결과를 다 끝낸 뒤 다음 차례로 간다. 라운드의 turns 에 적을 문서들을 돌려준다."""
    return [take_turn(judging, turn, declarations) for turn in turns]


def roll_checks(table: GameTable, round_: Round, dice: Dice, scene: Scene) -> set[uuid.UUID]:
    """
    닫히는 라운드의 행동과 몬스터의 공격을 판정하고, 결과에 따라 HP 를 바꾸고, 결과를 적는다.

    장면에 맞붙은 몬스터(공격이 있고 쓰러지지 않은 마리, app/rounds/monster_attacks.py 의 can_act)나
    싸우는 인물(적대이고 싸움이 붙었고 공격이 있는 인물, app/rounds/npc_attacks.py 의 can_act)이 있으면
    차례를 정해 그 순서로 굴린다(app/rounds/initiative.py). 차례와 몬스터, 인물의 결과는 라운드의 turns 에 적는다.
    없으면 들어온(앉은) 순서로 굴리고 turns 는 비어 있다. 둘 다 없는 판은 이 칸이 생기기 전과 같다.
    싸우는 인물은 판정을 시작하기 전에 고른다. 이번 라운드에 싸움이 붙은 인물은 다음 라운드부터 친다.

    한 사람의 판정과 그 결과(피해, 회복, 부상, 치료)를 끝낸 뒤에 다음 차례로 넘어간다.
    앞사람이 쓰러뜨린 것을 뒷사람이 일으킬 수 있다. NPC 도 그렇다. 앞사람이 죽인 NPC 는 뒷사람이 바꾸지 못한다.
    같은 부상을 여럿이 치료하면 앞사람부터 차례로 적용한다. 앞사람이 다 낫게 했으면 뒷사람은 치료할 것이 없다.
    차례가 오기 전에 쓰러지거나 죽은 캐릭터는 행동하지 못한다(lost_turn). 앞 차례에 쓰러진 마리도 그렇다.
    scene 은 이번 장면의 NPC 와 몬스터들이다(app/rounds/cast.py, app/rounds/monster_scene.py).
    NPC 와 몬스터의 상태는 그 안에 들어 있고, 여기서 고친다. 앞사람이 죽인 몬스터는 뒷사람이 치지 못한다.
    지목은 장면에 나오지 않은 인물도 짚을 수 있어서 상태 전부(scene.npcs)를 함께 넘긴다.

    판정을 시작하기 전에 쓰러져 있던 사람들을 한 번 뜬다. 몬스터와 NPC 는 그들도 칠 수 있다(#369,
    app/rounds/downed_strikes.py). 이번 라운드에 앞 차례에서 쓰러진 사람은 이번 라운드에는 맞지 않는다.

    장면의 마리 중 아직 만나지 않은 것에는 이번 라운드를 만난 첫 라운드로 적는다(mark_engaged).
    기습은 그 라운드에만 쓴다.

    이번 라운드에 피해를 입은 앉은 사람들(user_id)을 돌려준다. 쉬는 사람의 휴식이 깨졌는지 이것으로 본다.
    """
    initiative.mark_engaged(scene.monsters, round_.number)
    rolling = rolling_members(table, round_)
    acting = [monster for monster in scene.monsters if can_act(monster)]
    fighting = [person for person in scene.cast if npc_attacks.can_act(person)]
    if not rolling and not acting and not fighting:
        return set()

    downed = frozenset(member.user_id for member in find_dying(table))
    judging = build_judging(table, round_, dice, scene, downed, rolling)
    if not acting and not fighting:
        for member, declaration in rolling:
            take_member_turn(judging, member, declaration)
        return judging.hurt
    turns = build_turns(judging, rolling, acting, fighting)
    declarations = {member.user_id: declaration for member, declaration in rolling}
    round_.turns = take_turns(judging, turns, declarations)
    return judging.hurt


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
    짧은 것은 라운드로, 오래 가는 것은 이 장면이 끝나는 게임 안의 시각으로 본다(moment_of).

    오래 가는 것이 나으면 후유증 표를 굴린다. 그 순서는 앉은 사람, 그다음 NPC 다(app/rounds/injuries.py).
    끝날 부상이 하나도 없으면 규칙을 읽지 않는다. 판에 굳은 복사본을 통째로 읽는 일이라 싸지 않다.
    """
    moment = round_injuries.moment_of(table, round_number)
    if not round_injuries.any_due(table.members, scene, moment):
        return []
    return round_injuries.expire_all(table.members, scene, rules_of(table), dice, table.id, moment)
