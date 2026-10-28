# trpg-server/app/rounds/acceptance.py

"""
선언을 받는다. 선언에 붙은 행동을 테이블과 견주어 보고, 저장할 모양으로 바꿔 라운드에 적는다.

DB 를 모른다. 이미 읽어 온 테이블, 자리, 라운드, 이번 장면의 인물을 받는다.
저장은 부른 쪽(app/rounds/service.py)이 한다.

행동은 열일곱이다(app/engine/action.py).
  - 판정(CheckAction). 이번 장면에 나온 NPC 를 겨눌 수 있다(app/rounds/cast.py). 노려 칠 수도 있다.
    자기가 선 장소의 몬스터 한 마리를 칠 수도 있다(app/rounds/monster_scene.py).
    같은 장소의 앉은 사람을 칠 수도 있다(#803). 테이블과 맞는 쪽이 받아들여야 한다(app/rounds/friendly_fire.py).
  - 치료(TreatAction). 능력과 난이도는 규칙이 정한다. 대상이 그 부상을 입고 있어야 한다.
  - 지목(NameAction). 인물의 진짜 이름을 짚는다. 맞는지는 여기서 보지 않는다(app/rounds/judging.py).
  - 쓰기(UseAction), 건네기(GiveAction). 판의 물건을 지금 가지고 있어야 한다.
    닫힐 때 차례가 오면 다시 본다(app/rounds/item_actions.py). 그사이에 건넸거나 빼앗겼을 수 있다.
  - 가기(MoveAction), 찾기(SearchAction). 맵에 서 있어야 한다. 가기는 아는 길로 이어진 곳으로만
    (app/rounds/map_actions.py).
  - 쉬기(RestAction). 규칙에 쉬기가 있어야 한다. 쉴 수 없는 곳은 없다(app/rounds/rests.py).
  - 기다리기(WaitAction). 규칙과 장소를 보지 않는다. 몬스터가 있어도 받는다(app/rounds/waits.py).
  - 줍기(TakeAction). 맵에 서 있고, 그 장소에 보이게 남은 물건이어야 한다(app/rounds/place_item_actions.py).
  - 내려놓기(PutDownAction). 맵에 서 있고, 판의 물건을 그만큼 가지고 있어야 한다.
  - 훔치기(StealAction). 규칙에 훔치기가 있고, 자기가 선 장소의 죽지 않은 마리나 이번 장면의 죽지 않은 인물이
    그 물건을 지금 지녀야 한다(app/rounds/steals.py).
  - 빼앗기(LootAction). 자기가 선 장소의 마리나 이번 장면의 인물이 쓰러졌거나 죽어 있고, 그 물건을 지금 지녀야 한다
    (app/rounds/loots.py). 판정이 없어 규칙을 보지 않는다.
  - 사기(BuyAction), 팔기(SellAction), 돈 건네기(PayAction). 화폐가 있는 판이어야 한다. 사고팔기는 이번 장면의
    거래하는 상인과, 값이 있는 물건과, 그만큼의 돈(재고, 소지품)이 있어야 한다(app/rounds/trades.py).
  - 엄폐하기(CoverAction). 세이브 방식의 규칙이고, 맵에 서 있고, 그 장소에 커버가 있어야 한다(app/rounds/covers.py).
  - 던지기(ThrowAction, #277). 던지는 판정이 있는 판의 소모품을 가지고 있고, 맞을 쪽이 치기와 같이 닿아야 한다
    (app/rounds/throws.py).
누구를 겨눌 수 있는지는 선언을 받을 때와 닫기 시작할 때 같다. 장면은 라운드가 열린 뒤로 바뀌지 않는다.
비워 둔 칸(난이도, 회복과 치료의 대상)은 여기서 채워 저장한다. 읽는 쪽이 "비어 있으면"을 다시 따지지 않는다.
"""

import uuid

from app.assets.models import ITEM_STACK_MAX, ItemKind
from app.assets.scenarios.snapshot import read_snapshot
from app.engine import action as actions
from app.engine.action import (
    AnyAction,
    BuyAction,
    CheckAction,
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
    SkillAction,
    StealAction,
    TakeAction,
    ThrowAction,
    TreatAction,
    UseAction,
    WaitAction,
)
from app.engine.item_aids import AidAct
from app.engine.item_effects import EffectKind, first_of
from app.engine.ruleset import Ruleset
from app.rounds import friendly_fire
from app.rounds import injuries as round_injuries
from app.rounds.aids import require_aid
from app.rounds.cast import CastMember, Scene, find_cast_member, find_reachable, is_named
from app.rounds.covers import accept_cover
from app.rounds.door_actions import accept_door
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, Conflict, RoundConflictError
from app.rounds.map_actions import accept_move, accept_search, standing_place
from app.rounds.models import Declaration, Round
from app.rounds.monster_scene import SceneMonster, find_scene_monster, stands_with
from app.rounds.place_item_actions import accept_take
from app.rounds.rests import accept_rest
from app.rounds.skill_actions import accept_skill
from app.rounds.state import find_declaration, is_down, rules_of
from app.rounds.steals import require_steal
from app.rounds.trades import accept_buy, accept_pay, accept_sell
from app.rounds.victims import find_monster_carried, find_npc_carried
from app.rounds.waits import accept_wait
from app.tables import items, npcs, sheets
from app.tables import monsters as table_monsters
from app.tables import state as table_state
from app.tables.items import CatalogItem
from app.tables.models import GameTable, NpcStatus, TableMember


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


def require_npc_target(cast: list[CastMember], member: TableMember, npc_id: uuid.UUID, aim: str | None) -> None:
    """
    겨눈 NPC 가 이번 장면의 살아 있는(쓰러졌어도 된다) 인물인지 본다. 노려 쳤으면 그 부상을 아직 입지 않았는지도 본다.

    장면에 나오지 않았거나 자리가 있는 인물이 행동하는 캐릭터와 다른 장소에 있으면 ActionTargetError(#282).
    둘을 가르지 않는다. 몬스터와 같다. 이미 죽었거나 노린 부상을 이미 입었으면 RoundConflictError.
    라운드가 열려 있는 동안 캐릭터와 인물의 자리는 바뀌지 않는다. 그래서 판정할 때 다시 보지 않는다.
    """
    person = find_reachable(cast, member, npc_id)
    if person is None:
        raise ActionTargetError('npc')
    if npcs.is_dead(person.npc):
        raise RoundConflictError(Conflict.NPC_DEAD)
    if aim is not None and round_injuries.wears(person.npc.injuries, aim):
        raise RoundConflictError(Conflict.ALREADY_INJURED)


def require_monster_target(
    monsters: list[SceneMonster],
    member: TableMember,
    monster_id: uuid.UUID,
    aim: str | None = None,
    ruleset: Ruleset | None = None,
) -> None:
    """
    겨눈 몬스터가 이번 장면에서 행동하는 캐릭터와 같은 장소에 있는 죽지 않은(쓰러졌어도 된다) 마리인지 본다.

    장면에 없거나 다른 장소에 있으면 ActionTargetError, 이미 죽었으면 RoundConflictError.
    장면에 없는 것과 다른 장소에 있는 것을 가르지 않는다. 가르면 아무도 없는 장소의 몬스터가 있다는 것이 드러난다.
    노려 쳤으면(#799) 그 부상을 아직 입지 않았는지(already_injured), 그 성질에 면역이 아닌지(target_immune)도 본다.
    """
    monster = find_scene_monster(monsters, monster_id)
    if monster is None or not stands_with(member, monster):
        raise ActionTargetError('monster')
    if table_monsters.is_dead(monster.state):
        raise RoundConflictError(Conflict.MONSTER_DEAD)
    if aim is not None:
        require_aimable_monster(monster, aim, ruleset)


def require_aimable_monster(monster: SceneMonster, aim: str, ruleset: Ruleset) -> None:
    """노려 칠 부상을 그 마리가 이미 입었으면 already_injured, 그 성질에 면역이면 target_immune(#799)."""
    if round_injuries.wears(monster.state.injuries, aim):
        raise RoundConflictError(Conflict.ALREADY_INJURED)
    if round_injuries.immune_to(ruleset, aim, table_monsters.immunities(ruleset, monster.definition)):
        raise RoundConflictError(Conflict.TARGET_IMMUNE)


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


def require_weapon(table: GameTable, member: TableMember, entry_id: uuid.UUID) -> None:
    """
    타격에 쓰겠다는 무기를 본다(#276). 공격 보정이 있는 판의 물건이 아니면 ActionNotInRulesError(weapon),
    착용하고 있지 않으면 RoundConflictError(weapon_not_worn).
    """
    item = items.catalog(read_snapshot(table.content)).get(entry_id)
    if item is None or item.attack is None:
        raise ActionNotInRulesError('weapon')
    if member.sheet is None or all(row.entry_id != entry_id for row in member.sheet.worn):
        raise RoundConflictError(Conflict.WEAPON_NOT_WORN)


def accept_check(table: GameTable, member: TableMember, action: CheckAction, scene: Scene, ruleset: Ruleset) -> dict:
    """
    판정하는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 규칙에 없는 능력, 난이도, 양의 등급이면 ActionNotInRulesError.
      - 대상이 이 테이블에 앉은 사람이 아니면 ActionTargetError.
      - 겨눈 NPC 가 이번 장면의 인물이 아니거나 다른 장소에 있으면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 겨눈 몬스터가 같은 장소의 마리가 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 노린 부상이 규칙에서 노릴 수 없는 것이면 ActionNotInRulesError, 대상이 이미 입었으면 RoundConflictError.
      - 노린 부위가 규칙에서 노릴 수 없는 것이면 ActionNotInRulesError(strike, #276).
      - 무기가 공격 보정이 없는 물건이면 ActionNotInRulesError, 착용하고 있지 않으면 RoundConflictError(#276).
      - 앉은 사람을 치면(#803) require_ally_target.
    비워 둔 난이도는 규칙의 기본 난이도로, 비워 둔 회복의 대상은 자기 자신으로 채운다.
    """
    fault = actions.find_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    if action.target is not None and action.harm is not None:
        require_ally_target(table, member, action, ruleset)
    elif action.target is not None and table_state.find_member(table, action.target) is None:
        raise ActionTargetError('target')
    if action.npc is not None:
        require_npc_target(scene.cast, member, action.npc, action.aim)
    if action.monster is not None:
        require_monster_target(scene.monsters, member, action.monster, action.aim, ruleset)
    if action.weapon is not None:
        require_weapon(table, member, action.weapon)
    return aim(actions.settle(ruleset, action), member.user_id).model_dump(mode='json')


def require_ally_target(table: GameTable, member: TableMember, action: CheckAction, ruleset: Ruleset) -> None:
    """
    앉은 사람을 치는 판정(#803). 해칠 수 있는지(friendly_fire.require_harmable), 노린 부상을 아직 입지 않았는지 본다.

    장난만이면 짧은 부상만 노린다(friendly_fire_prank). 이미 입었으면 RoundConflictError(already_injured).
    """
    target, level = friendly_fire.require_harmable(table, member, action.target)
    friendly_fire.require_prank_aim(ruleset, level, action.aim)
    if action.aim is not None and round_injuries.wears(target.sheet.injuries, action.aim):
        raise RoundConflictError(Conflict.ALREADY_INJURED)


def patient_rows(table: GameTable, member: TableMember, action: TreatAction, cast: list[CastMember]) -> list:
    """
    치료받는 쪽의 부상 목록. 대상을 채운 행동(aim_treatment)에 쓴다. member 는 치료하는 사람이다.

      - NPC 가 이번 장면의 인물이 아니거나 다른 장소에 있으면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 앉은 사람이 아니면 ActionTargetError, 그 캐릭터가 이미 죽었으면 RoundConflictError.
    """
    if action.npc is not None:
        person = find_reachable(cast, member, action.npc)
        if person is None:
            raise ActionTargetError('npc')
        if npcs.is_dead(person.npc):
            raise RoundConflictError(Conflict.NPC_DEAD)
        return person.npc.injuries
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
      - 대상이 앉은 사람이나 이번 장면의 인물이 아니면(다른 장소의 인물이면) ActionTargetError,
        이미 죽었으면 RoundConflictError.
      - 대상이 그 부상을 입고 있지 않으면 RoundConflictError.
      - 붙여 쓰는 물건(#277, #802)이 판의 물건이 아니거나 치료를 거들지 않으면 ActionNotInRulesError(item),
        하나도 가지고 있지 않으면 RoundConflictError(item_not_held).
    비워 둔 대상은 자기 자신으로 채운다.
    """
    fault = actions.find_treat_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    if action.item is not None:
        require_aid(table, member, action.item, AidAct.TREAT)
    aimed = aim_treatment(action, member.user_id)
    if not round_injuries.wears(patient_rows(table, member, aimed, cast), aimed.injury):
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


def accept_use(table: GameTable, member: TableMember, action: UseAction, scene: Scene) -> dict:
    """
    물건을 쓰는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 판의 물건이 아니거나 소모품이 아니면 ActionNotInRulesError(item). 장비는 쓰지 않는다.
      - 하나도 가지고 있지 않으면 RoundConflictError(item_not_held).
      - 누구에게도 들지 않는(효과가 없는) 소모품에 대상을 적었으면 ActionNotInRulesError(target, npc, monster).
        무엇을 하려는지 알 수 없다.
      - 인물이나 몬스터에게 쓰기(#800): accept_use_on.
      - 효과가 있는 소모품을 앉은 사람에게: 대상이 앉은 사람이 아니면 ActionTargetError, 죽었으면
        RoundConflictError(patient_dead). 비워 둔 대상은 자기 자신으로 채운다. 해로운 효과(피해, 부상)가 있으면
        치기와 같이 해칠 수 있어야 한다(#803, friendly_fire.require_harmable). 자기 자신에게는 늘 된다.
    """
    item = find_item(table, action.item)
    if item.kind != ItemKind.CONSUMABLE:
        raise ActionNotInRulesError('item')
    require_held(member, action.item, 1)
    if not items.takes_target(item):
        named = next((field for field in ('target', 'npc', 'monster') if getattr(action, field) is not None), None)
        if named is not None:
            raise ActionNotInRulesError(named)
        return action.model_dump(mode='json')
    if action.npc is not None or action.monster is not None:
        return accept_use_on(table, member, action, item, scene)
    target = living_target(table, action.target or member.user_id, Conflict.PATIENT_DEAD)
    if items.is_harmful(item) and target.user_id != member.user_id:
        friendly_fire.require_harmable(table, member, target.user_id)
    return action.model_copy(update={'target': target.user_id}).model_dump(mode='json')


def accept_use_on(table: GameTable, member: TableMember, action: UseAction, item: CatalogItem, scene: Scene) -> dict:
    """
    물건을 인물이나 몬스터에게 쓰는 행동(#800). 겨누는 조건은 치기와 같다.

      - 규칙에 맞히는 판정(rules.item_check)이 없으면 ActionNotInRulesError(npc 나 monster).
      - 인물이 이번 장면의 인물이 아니거나 다른 장소에 있으면 ActionTargetError(npc), 몬스터가 같은 장소의 마리가
        아니면 ActionTargetError(monster), 이미 죽었으면 RoundConflictError.
      - 피해가 없는 물건에 죽이려 한다(lethal)를 적었으면 ActionNotInRulesError(lethal).
    """
    field = 'npc' if action.npc is not None else 'monster'
    if rules_of(table).item_check is None:
        raise ActionNotInRulesError(field)
    if action.lethal and first_of(item.effects, EffectKind.DAMAGE) is None:
        raise ActionNotInRulesError('lethal')
    if action.npc is not None:
        require_npc_target(scene.cast, member, action.npc, None)
    else:
        require_monster_target(scene.monsters, member, action.monster)
    return action.model_dump(mode='json')


def accept_throw(table: GameTable, member: TableMember, action: ThrowAction, scene: Scene) -> dict:
    """
    물건을 던지는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다(#277). 어떤 물건이든 던진다(#801).

      - 판의 물건이 아니거나, 던지는 판정이 물건에도 룰북(rules.item_check)에도 없으면 ActionNotInRulesError(item).
      - 하나도 가지고 있지 않으면 RoundConflictError(item_not_held).
      - 피해의 효과가 없는 물건에 죽이려 한다(lethal)를 적었으면 ActionNotInRulesError(lethal).
      - 맞을 쪽은 치기와 같다. 인물이 이번 장면의 인물이 아니거나 다른 장소에 있으면 ActionTargetError(npc),
        몬스터가 같은 장소의 마리가 아니면 ActionTargetError(monster), 이미 죽었으면 RoundConflictError.
      - 앉은 사람에게 던지면(#803): 자기 자신이거나 같은 장소의 사람이 아니면 ActionTargetError(target),
        죽었으면 RoundConflictError(ally_dead). 해로운 물건이면 치기와 같이 해칠 수 있어야 한다.
    능력과 난이도는 받지 않는다. 물건에 적혀 있어 저장할 것이 없다.
    """
    item = find_item(table, action.item)
    if item.throw is None and rules_of(table).item_check is None:
        raise ActionNotInRulesError('item')
    require_held(member, action.item, 1)
    if action.lethal and first_of(item.effects, EffectKind.DAMAGE) is None:
        raise ActionNotInRulesError('lethal')
    if action.npc is not None:
        require_npc_target(scene.cast, member, action.npc, None)
    if action.monster is not None:
        require_monster_target(scene.monsters, member, action.monster)
    if action.target is not None:
        require_throw_target(table, member, action.target, item)
    return action.model_dump(mode='json')


def accept_skill_on(table: GameTable, member: TableMember, ruleset: Ruleset, action: SkillAction, scene: Scene) -> dict:
    """
    기술을 쓰는 행동(#805, app/rounds/skill_actions.py 의 accept_skill). 상대에게 쓰는 기술이면(#805 ②) 겨눈 쪽을
    치기와 같이 본다. 인물이 이번 장면의 인물이 아니거나 다른 장소에 있으면 ActionTargetError(npc), 몬스터가 같은
    장소의 마리가 아니면 ActionTargetError(monster), 이미 죽었으면 RoundConflictError.
    """
    accepted = accept_skill(table, member, ruleset, action)
    if action.npc is not None:
        require_npc_target(scene.cast, member, action.npc, None)
    if action.monster is not None:
        require_monster_target(scene.monsters, member, action.monster)
    return accepted


def require_throw_target(table: GameTable, member: TableMember, target_id: uuid.UUID, item: CatalogItem) -> None:
    """
    앉은 사람에게 던지기(#803). 자기 자신은 아니다(그것은 쓰기다). 같은 장소의 살아 있는 사람이어야 한다.

    해로운 물건이면 해칠 수 있어야 한다(friendly_fire.require_harmable). 이로운 물건(물약)은 쓰러진 동료에게도 던진다.
    """
    if target_id == member.user_id:
        raise ActionTargetError('target')
    if items.is_harmful(item):
        friendly_fire.require_harmable(table, member, target_id)
        return
    target = living_target(table, target_id, Conflict.ALLY_DEAD)
    if not friendly_fire.stands_together(member, target):
        raise ActionTargetError('target')


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


def require_carried_by_victim(scene: Scene, action: StealAction | LootAction) -> None:
    """훔칠 대상(몬스터나 NPC)이 그 물건을 지금 지녔는지 본다. 아니면 ActionTargetError(carried)."""
    if action.monster is not None:
        line = find_monster_carried(find_scene_monster(scene.monsters, action.monster), action.item)
    else:
        line = find_npc_carried(find_cast_member(scene.cast, action.npc), action.item)
    if line is None:
        raise ActionTargetError('carried')


def accept_steal(ruleset: Ruleset, member: TableMember, scene: Scene, action: StealAction) -> dict:
    """
    훔치는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 규칙에 훔치기가 없으면 ActionNotInRulesError(kind).
      - 몬스터가 자기가 선 장소에 없거나 이미 죽었으면 칠 때와 같다(require_monster_target). 쓰러진 마리는 된다.
      - NPC 가 이번 장면의 인물이 아니거나 다른 장소에 있거나 이미 죽었으면 겨눌 때와 같다(require_npc_target).
        쓰러진 인물은 된다.
      - 그 대상이 그 물건을 지금 지니지 않았으면 ActionTargetError(carried).
    """
    require_steal(ruleset)
    if action.monster is not None:
        require_monster_target(scene.monsters, member, action.monster)
    else:
        require_npc_target(scene.cast, member, action.npc, None)
    require_carried_by_victim(scene, action)
    return action.model_dump(mode='json')


def require_downed_victim(scene: Scene, member: TableMember, action: LootAction) -> None:
    """
    빼앗을 대상이 쓰러졌거나 죽어 있는지 본다. 몬스터와 자리가 있는 인물은 자기가 선 장소에 있어야 한다.

    장면에 없거나 다른 장소에 있으면 ActionTargetError(monster, npc), 살아 있으면 RoundConflictError(target_not_down).
    """
    if action.monster is not None:
        monster = find_scene_monster(scene.monsters, action.monster)
        if monster is None or not stands_with(member, monster):
            raise ActionTargetError('monster')
        status = monster.state.status
    else:
        person = find_reachable(scene.cast, member, action.npc)
        if person is None:
            raise ActionTargetError('npc')
        status = person.npc.status
    if status == NpcStatus.ALIVE:
        raise RoundConflictError(Conflict.TARGET_NOT_DOWN)


def accept_loot(member: TableMember, scene: Scene, action: LootAction) -> dict:
    """
    빼앗는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 대상이 쓰러졌거나 죽어 있어야 한다(require_downed_victim). 살아 있는 대상에게서는 훔친다.
      - 그 대상이 그 물건을 지금 지니지 않았으면 ActionTargetError(carried).
    """
    require_downed_victim(scene, member, action)
    require_carried_by_victim(scene, action)
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
    accept_move, accept_search, accept_rest, accept_take, accept_put_down, accept_steal, accept_loot,
    accept_buy, accept_sell, accept_pay, accept_cover, 문을 다루는 accept_door, 던지는 accept_throw,
    기술을 쓰는 accept_skill, #805).
    """
    if action is None:
        return None
    ruleset = require_able(table, member)
    if isinstance(action, TreatAction):
        return accept_treatment(table, member, action, scene.cast, ruleset)
    if isinstance(action, NameAction):
        return accept_naming(action, scene.cast)
    if isinstance(action, UseAction):
        return accept_use(table, member, action, scene)
    if isinstance(action, SkillAction):
        return accept_skill_on(table, member, ruleset, action, scene)
    if isinstance(action, GiveAction):
        return accept_give(table, member, action)
    if isinstance(action, ThrowAction):
        return accept_throw(table, member, action, scene)
    if isinstance(action, MoveAction):
        return accept_move(table, member, action)
    if isinstance(action, SearchAction):
        return accept_search(member, action)
    if isinstance(action, TakeAction):
        return accept_take(table, member, action)
    if isinstance(action, PutDownAction):
        return accept_put_down(table, member, action)
    if isinstance(action, StealAction):
        return accept_steal(ruleset, member, scene, action)
    if isinstance(action, LootAction):
        return accept_loot(member, scene, action)
    if isinstance(action, RestAction):
        return accept_rest(ruleset, action)
    if isinstance(action, WaitAction):
        return accept_wait(action)
    if isinstance(action, BuyAction):
        return accept_buy(table, member, scene, action)
    if isinstance(action, SellAction):
        return accept_sell(table, member, scene, action)
    if isinstance(action, PayAction):
        return accept_pay(table, member, action)
    if isinstance(action, CoverAction):
        return accept_cover(table, member, ruleset, action)
    if isinstance(action, DoorAction):
        return accept_door(table, member, action)
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
