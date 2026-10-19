# game-server/app/rounds/acceptance.py

"""
선언을 받는다. 선언에 붙은 행동을 테이블과 견주어 보고, 저장할 모양으로 바꿔 라운드에 적는다.

DB 를 모른다. 이미 읽어 온 테이블, 자리, 라운드, 이번 장면의 인물을 받는다.
저장은 부른 쪽(app/rounds/service.py)이 한다.

행동은 열이다(app/engine/action.py).
  - 판정(CheckAction). 이번 장면에 나온 NPC 를 겨눌 수 있다(app/rounds/cast.py). 노려 칠 수도 있다.
    자기가 선 장소의 몬스터 한 마리를 칠 수도 있다(app/rounds/monster_scene.py).
  - 치료(TreatAction). 능력과 난이도는 규칙이 정한다. 대상이 그 부상을 입고 있어야 한다.
  - 지목(NameAction). 인물의 진짜 이름을 짚는다. 맞는지는 여기서 보지 않는다(app/rounds/judging.py).
  - 쓰기(UseAction), 건네기(GiveAction). 판의 물건을 지금 가지고 있어야 한다.
    닫힐 때 차례가 오면 다시 본다(app/rounds/item_actions.py). 그사이에 건넸거나 빼앗겼을 수 있다.
  - 가기(MoveAction), 찾기(SearchAction). 맵에 서 있어야 한다. 가기는 아는 길로 이어진 곳으로만
    (app/rounds/map_actions.py).
  - 쉬기(RestAction). 규칙에 쉬기가 있어야 한다. 쉴 수 없는 곳은 없다(app/rounds/rests.py).
  - 줍기(TakeAction). 맵에 서 있고, 그 장소에 보이게 남은 물건이어야 한다(app/rounds/place_item_actions.py).
  - 내려놓기(PutDownAction). 맵에 서 있고, 판의 물건을 그만큼 가지고 있어야 한다.
누구를 겨눌 수 있는지는 선언을 받을 때와 닫기 시작할 때 같다. 장면은 라운드가 열린 뒤로 바뀌지 않는다.
비워 둔 칸(난이도, 회복과 치료의 대상)은 여기서 채워 저장한다. 읽는 쪽이 "비어 있으면"을 다시 따지지 않는다.
"""

import uuid

from app.assets.models import ITEM_STACK_MAX, ItemKind
from app.assets.scenarios.snapshot import read_snapshot
from app.engine import action as actions
from app.engine.action import (
    AnyAction,
    CheckAction,
    GiveAction,
    MoveAction,
    NameAction,
    PutDownAction,
    RestAction,
    SearchAction,
    TakeAction,
    TreatAction,
    UseAction,
)
from app.engine.ruleset import Ruleset
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember, Scene, find_cast_member, is_named
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, Conflict, RoundConflictError
from app.rounds.map_actions import accept_move, accept_search, standing_place
from app.rounds.models import Declaration, Round
from app.rounds.monster_scene import SceneMonster, find_scene_monster, stands_with
from app.rounds.place_item_actions import accept_take
from app.rounds.rests import accept_rest
from app.rounds.state import find_declaration, is_down, rules_of
from app.tables import items, npcs, sheets
from app.tables import monsters as table_monsters
from app.tables import state as table_state
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableMember


def aim(action: CheckAction, actor_id: uuid.UUID) -> CheckAction:
    """
    회복의 대상을 비워 뒀으면 행동한 사람 자신으로 채운 행동을 돌려준다. 받은 행동은 고치지 않는다.

    저장하는 행동에는 회복이 있으면 늘 대상이 적혀 있게 한다. 읽는 쪽이 "비어 있으면 자기"를 다시 따지지 않는다.
    NPC 를 회복시키는 행동은 대상이 NPC 다. 채우지 않는다.
    """
    if action.recover is None or action.target is not None or action.npc is not None:
        return action
    return action.model_copy(update={'target': actor_id})


def aim_treatment(action: TreatAction, actor_id: uuid.UUID) -> TreatAction:
    """치료받는 쪽을 비워 뒀으면 치료하는 사람 자신으로 채운 행동을 돌려준다. 받은 행동은 고치지 않는다."""
    if action.target is not None or action.npc is not None:
        return action
    return action.model_copy(update={'target': actor_id})


def require_npc_target(cast: list[CastMember], npc_id: uuid.UUID, aim: str | None) -> None:
    """
    겨눈 NPC 가 이번 장면의 살아 있는(쓰러졌어도 된다) 인물인지 본다. 노려 쳤으면 그 부상을 아직 입지 않았는지도 본다.

    장면에 나오지 않았으면 ActionTargetError, 이미 죽었거나 노린 부상을 이미 입었으면 RoundConflictError.
    """
    member = find_cast_member(cast, npc_id)
    if member is None:
        raise ActionTargetError('npc')
    if npcs.is_dead(member.npc):
        raise RoundConflictError(Conflict.NPC_DEAD)
    if aim is not None and round_injuries.wears(member.npc.injuries, aim):
        raise RoundConflictError(Conflict.ALREADY_INJURED)


def require_monster_target(monsters: list[SceneMonster], member: TableMember, monster_id: uuid.UUID) -> None:
    """
    겨눈 몬스터가 이번 장면에서 행동하는 캐릭터와 같은 장소에 있는 죽지 않은(쓰러졌어도 된다) 마리인지 본다.

    장면에 없거나 다른 장소에 있으면 ActionTargetError, 이미 죽었으면 RoundConflictError.
    장면에 없는 것과 다른 장소에 있는 것을 가르지 않는다. 가르면 아무도 없는 장소의 몬스터가 있다는 것이 드러난다.
    """
    monster = find_scene_monster(monsters, monster_id)
    if monster is None or not stands_with(member, monster):
        raise ActionTargetError('monster')
    if table_monsters.is_dead(monster.state):
        raise RoundConflictError(Conflict.MONSTER_DEAD)


def require_able(table: GameTable, member: TableMember) -> Ruleset:
    """
    선언하는 사람이 행동을 붙일 수 있는지 본다. 이 테이블의 규칙을 돌려준다.

    쓰러져 있거나, 행동을 막는 부상(기절 같은 것)을 입었으면 RoundConflictError. 그 사람은 글만 낼 수 있다.
    """
    if is_down(member):
        raise RoundConflictError(Conflict.CHARACTER_DOWNED)
    ruleset = rules_of(table)
    if member.sheet is not None and round_injuries.is_incapacitated(ruleset, member.sheet.injuries):
        raise RoundConflictError(Conflict.CHARACTER_INCAPACITATED)
    return ruleset


def accept_check(table: GameTable, member: TableMember, action: CheckAction, scene: Scene, ruleset: Ruleset) -> dict:
    """
    판정하는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 규칙에 없는 능력, 난이도, 양의 등급이면 ActionNotInRulesError.
      - 대상이 이 테이블에 앉은 사람이 아니면 ActionTargetError.
      - 겨눈 NPC 가 이번 장면의 인물이 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 겨눈 몬스터가 같은 장소의 마리가 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 노린 부상이 규칙에서 노릴 수 없는 것이면 ActionNotInRulesError, 대상이 이미 입었으면 RoundConflictError.
    비워 둔 난이도는 규칙의 기본 난이도로, 비워 둔 회복의 대상은 자기 자신으로 채운다.
    """
    fault = actions.find_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    if action.target is not None and table_state.find_member(table, action.target) is None:
        raise ActionTargetError('target')
    if action.npc is not None:
        require_npc_target(scene.cast, action.npc, action.aim)
    if action.monster is not None:
        require_monster_target(scene.monsters, member, action.monster)
    return aim(actions.settle(ruleset, action), member.user_id).model_dump(mode='json')


def patient_rows(table: GameTable, action: TreatAction, cast: list[CastMember]) -> list:
    """
    치료받는 쪽의 부상 목록. 대상을 채운 행동(aim_treatment)에 쓴다.

      - NPC 가 이번 장면의 인물이 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 앉은 사람이 아니면 ActionTargetError, 그 캐릭터가 이미 죽었으면 RoundConflictError.
    """
    if action.npc is not None:
        member = find_cast_member(cast, action.npc)
        if member is None:
            raise ActionTargetError('npc')
        if npcs.is_dead(member.npc):
            raise RoundConflictError(Conflict.NPC_DEAD)
        return member.npc.injuries
    patient = table_state.find_member(table, action.target)
    if patient is None:
        raise ActionTargetError('target')
    if sheets.is_dead(patient):
        raise RoundConflictError(Conflict.PATIENT_DEAD)
    return patient.sheet.injuries if patient.sheet is not None else []


def accept_treatment(
    table: GameTable, member: TableMember, action: TreatAction, cast: list[CastMember], ruleset: Ruleset
) -> dict:
    """
    치료하는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 규칙에서 치료할 수 없는 부상이면 ActionNotInRulesError(injury).
      - 대상이 앉은 사람이나 이번 장면의 인물이 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 대상이 그 부상을 입고 있지 않으면 RoundConflictError.
    비워 둔 대상은 자기 자신으로 채운다.
    """
    fault = actions.find_treat_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    aimed = aim_treatment(action, member.user_id)
    if not round_injuries.wears(patient_rows(table, aimed, cast), aimed.injury):
        raise RoundConflictError(Conflict.NOT_INJURED)
    return aimed.model_dump(mode='json')


def accept_naming(action: NameAction, cast: list[CastMember]) -> dict:
    """
    지목하는 행동을 이번 장면과 견주어 보고, 저장할 모양으로 바꾼다.

      - 겨눈 인물이 이번 장면의 인물이 아니면 ActionTargetError. 죽은 인물도 이름은 짚을 수 있다.
      - 겨눈 인물의 진짜 이름이 이미 드러났으면 RoundConflictError.
    짚은 이름이 맞는지는 보지 않는다. 받을 때 맞고 틀림을 알려 주면 라운드를 닫기 전에 정답을 캘 수 있다.
    """
    if action.npc is not None:
        member = find_cast_member(cast, action.npc)
        if member is None:
            raise ActionTargetError('npc')
        if is_named(member.npc):
            raise RoundConflictError(Conflict.ALREADY_NAMED)
    return action.model_dump(mode='json')


def find_item(table: GameTable, entry_id: uuid.UUID) -> CatalogItem:
    """판의 물건을 찾는다. 판에 없으면(인물, 장소, 없는 항목) ActionNotInRulesError(item)."""
    item = items.catalog(read_snapshot(table.content)).get(entry_id)
    if item is None:
        raise ActionNotInRulesError('item')
    return item


def require_held(member: TableMember, entry_id: uuid.UUID, count: int) -> None:
    """그 물건을 count 개 이상 가지고 있는지 본다. 아니면 RoundConflictError(item_not_held)."""
    if member.sheet is None or items.count_of(member.sheet, entry_id) < count:
        raise RoundConflictError(Conflict.ITEM_NOT_HELD)


def living_target(table: GameTable, target_id: uuid.UUID, dead_reason: Conflict) -> TableMember:
    """
    물건을 받거나 회복받을 사람. 앉아 있지 않으면 ActionTargetError(target), 캐릭터가 죽었으면 RoundConflictError.
    """
    target = table_state.find_member(table, target_id)
    # 진행 중인 테이블에서는 앉은 사람 모두에게 시트가 있다(app/tables/sheets.py)
    if target is None:
        raise ActionTargetError('target')
    if sheets.is_dead(target):
        raise RoundConflictError(dead_reason)
    return target


def accept_use(table: GameTable, member: TableMember, action: UseAction) -> dict:
    """
    물건을 쓰는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 판의 물건이 아니거나 소모품이 아니면 ActionNotInRulesError(item). 장비는 쓰지 않는다.
      - 하나도 가지고 있지 않으면 RoundConflictError(item_not_held).
      - 회복하는 소모품: 대상이 앉은 사람이 아니면 ActionTargetError, 죽었으면 RoundConflictError(patient_dead).
        비워 둔 대상은 자기 자신으로 채운다.
      - 회복하지 않는 소모품에 대상을 적었으면 ActionNotInRulesError(target). 무엇을 하려는지 알 수 없다.
    """
    item = find_item(table, action.item)
    if item.kind != ItemKind.CONSUMABLE:
        raise ActionNotInRulesError('item')
    require_held(member, action.item, 1)
    if item.heals is None:
        if action.target is not None:
            raise ActionNotInRulesError('target')
        return action.model_dump(mode='json')
    target = living_target(table, action.target or member.user_id, Conflict.PATIENT_DEAD)
    return action.model_copy(update={'target': target.user_id}).model_dump(mode='json')


def accept_give(table: GameTable, member: TableMember, action: GiveAction) -> dict:
    """
    물건을 건네는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 판의 물건이 아니면 ActionNotInRulesError(item).
      - 그만큼 가지고 있지 않으면 RoundConflictError(item_not_held).
      - 받는 사람이 자기 자신이거나 앉은 사람이 아니면 ActionTargetError(target), 죽었으면 RoundConflictError.
      - 받는 쪽이 그 물건을 더 가질 수 없으면 RoundConflictError(recipient_full).
    """
    find_item(table, action.item)
    require_held(member, action.item, action.count)
    if action.target == member.user_id:
        raise ActionTargetError('target')
    recipient = living_target(table, action.target, Conflict.RECIPIENT_DEAD)
    if items.count_of(recipient.sheet, action.item) + action.count > ITEM_STACK_MAX:
        raise RoundConflictError(Conflict.RECIPIENT_FULL)
    return action.model_dump(mode='json')


def accept_put_down(table: GameTable, member: TableMember, action: PutDownAction) -> dict:
    """
    내려놓는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 맵에 서 있지 않으면 RoundConflictError(not_on_map). 놓을 곳이 없다.
      - 판의 물건이 아니면 ActionNotInRulesError(item).
      - 그만큼 가지고 있지 않으면 RoundConflictError(item_not_held).
    """
    standing_place(member)
    find_item(table, action.item)
    require_held(member, action.item, action.count)
    return action.model_dump(mode='json')


def accept_action(
    table: GameTable,
    member: TableMember,
    action: AnyAction | None,
    scene: Scene,
) -> dict | None:
    """
    선언에 붙은 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다. 행동이 없으면 None.

    member 는 선언하는 사람이고, scene 은 이번 장면(인물과 몬스터)이다.
    쓰러져 있거나 행동을 막는 부상을 입었으면 RoundConflictError(require_able).
    나머지는 행동의 종류마다 본다(accept_check, accept_treatment, accept_naming, accept_use, accept_give,
    accept_move, accept_search, accept_rest, accept_take, accept_put_down).
    """
    if action is None:
        return None
    ruleset = require_able(table, member)
    if isinstance(action, TreatAction):
        return accept_treatment(table, member, action, scene.cast, ruleset)
    if isinstance(action, NameAction):
        return accept_naming(action, scene.cast)
    if isinstance(action, UseAction):
        return accept_use(table, member, action)
    if isinstance(action, GiveAction):
        return accept_give(table, member, action)
    if isinstance(action, MoveAction):
        return accept_move(table, member, action)
    if isinstance(action, SearchAction):
        return accept_search(member, action)
    if isinstance(action, TakeAction):
        return accept_take(table, member, action)
    if isinstance(action, PutDownAction):
        return accept_put_down(table, member, action)
    if isinstance(action, RestAction):
        return accept_rest(ruleset, action)
    return accept_check(table, member, action, scene, ruleset)


def put_declaration(round_: Round, member: TableMember, content: str, action: dict | None) -> None:
    """
    이 사람의 선언을 적는다. 이미 냈으면 글과 행동을 통째로 바꾼다.

    캐릭터 이름을 함께 적어 둔다. 이 사람이 나중에 떠나도 누구의 선언이었는지 남는다.
    """
    declaration = find_declaration(round_, member.user_id)
    if declaration is None:
        round_.declarations.append(
            Declaration(user_id=member.user_id, character_name=member.character_name, content=content, action=action)
        )
    else:
        declaration.content = content
        declaration.action = action
