# trpg-server/app/rounds/door_actions.py

"""
길의 문을 다루는 행동(#281). 잠그기(lock), 열기(unlock), 따기(pick), 부수기(force), 고치기(repair),
바꾸기(replace).

선언을 받을 때 보고(accept_door), 라운드가 닫힐 때 차례가 오면 정한다(judge_door).
문은 지금 서 있는 장소에 닿은 아는 길의 것이다. 길의 방향은 보지 않는다(어느 끝에서든 다룬다). 지나가지는 않는다.

  - 잠그기, 열기: 자물쇠는 그 열쇠를 지닌 사람이, 빗장은 빗장 쪽에 선 사람이 한다. 부서진 문은 잠그지 못한다.
    장치(device)는 그 길에 하나만 있으면 비워도 된다. 자물쇠와 빗장이 다 있으면 적어야 한다.
  - 따기: 판에 적힌 따는 판정으로 잠긴 자물쇠를 연다. 판이 도구를 요구하면 따기를 거드는 물건을 붙이고 지녀야 한다.
    빗장은 따지 못한다.
  - 부수기: 판에 적힌 부수는 판정으로 문을 부순다. 자물쇠와 빗장이 다 열리고, 고치기 전까지 다시 잠그지 못한다.
  - 고치기: 판에 적힌 고치는 판정으로 부서진 문을 고친다. 판이 도구를 요구하면 따기와 같다. 고친 문은 열린 채다.
  - 따기, 부수기, 고치기에는 그 행동을 거드는 물건(#802)을 붙일 수 있다. 굴리면 그 보정을 더하고, 굴린 뒤 그 물건의
    방식대로 없어진다(app/rounds/aids.py). 굴리지 않았으면 그대로다.
  - 바꾸기: 지닌 자물쇠 물건으로 판에 자물쇠가 있던 문의 자물쇠를 바꿔 단다. 굴리지 않는다.
    부서진 문은 고친 뒤에, 잠긴 자물쇠는 연 뒤에 바꾼다. 단 자물쇠는 열린 채이고 자물쇠 물건은 하나 없어진다.
    그 뒤로 그 문의 열쇠와 따는 판정은 자물쇠 물건의 것이다(지금의 자물쇠, app/tables/route_locks.py 의 current_lock).
    자물쇠 물건 하나는 한 테이블에서 한 번만 단다.
  - 받을 때는 문이 있는지(그 장치, 따는 판정, 부수는 판정, 고치는 판정, 판의 자물쇠)만 본다.
    바꾸기는 자물쇠 물건인지와 지녔는지도 본다.
    열쇠, 서 있는 쪽, 문의 지금 상태는 차례가 오면 본다.
    앞 차례에 누가 열쇠를 건넸거나 문을 열었을 수 있다. 할 수 없으면 굴리지 않고 까닭(reason)을 적는다.
  - 판정은 부상의 영향을 받는다. 실패하면 아무 일도 없다. 굴림은 공개다(check_rolled).

DB 를 모른다. 테이블의 문의 상태를 고친다(app/tables/route_locks.py). 저장하지 않는다.
"""

import uuid

from app.assets.scenarios.snapshot import (
    ItemLockSnapshot,
    LockSnapshot,
    RouteSnapshot,
    Snapshot,
    door_devices,
    item_rule_of,
    read_snapshot,
)
from app.engine.action import (
    DoorAction,
    DoorDevice,
    ForceAction,
    LockAction,
    PickAction,
    RepairAction,
    ReplaceAction,
    UnlockAction,
)
from app.engine.item_aids import AidAct
from app.rounds.aids import (
    AidUse,
    TakenAid,
    aid_bonus,
    aid_document,
    has_tool,
    require_aid,
    require_tool,
    take_aid,
    wear_aid,
)
from app.rounds.effects import Judging
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, Conflict, RoundConflictError
from app.rounds.map_actions import holds_key, roll_terms, standing_place, terms_document
from app.tables import items, places, route_locks
from app.tables.models import GameTable, TableMember

# 거들기가 있는 문 다루기와 그 거드는 행동(#802)
AID_ACTS = {PickAction: AidAct.PICK, ForceAction: AidAct.FORCE, RepairAction: AidAct.REPAIR}


class DoorReason:
    """문을 다루지 못한 까닭. 결과의 door.reason 에 적는다."""

    # 그 자물쇠의 열쇠가 없었다
    NO_KEY = 'no_key'
    # 빗장의 반대쪽에 서 있었다
    WRONG_SIDE = 'wrong_side'
    # 문이 부서져 잠그지 못했다
    BROKEN = 'broken'
    # 이미 그렇게 되어 있었다(잠긴 것을 잠그기, 열린 것을 열기·따기·부수기, 부서지지 않은 것을 고치기)
    ALREADY = 'already'
    # 따거나 고치는 데 있어야 하는 도구(그 행동을 거드는 물건)를 붙이지 않았거나 더 지니지 않았다
    NO_TOOL = 'no_tool'
    # 따기, 부수기, 고치기의 판정에 실패했다
    FAILED = 'failed'
    # 앞 차례에 바꿔 단 자물쇠가 따지 못하는 것이었다
    NO_PICK = 'no_pick'
    # 자물쇠가 잠겨 있어 바꾸지 못했다. 연 뒤에 바꾼다
    LOCKED = 'locked'
    # 바꿔 달 자물쇠 물건을 더 지니지 않았다(앞 차례에 건넸거나 내려놓았다)
    NO_ITEM = 'no_item'
    # 그 자물쇠 물건을 이 테이블에서 이미 달았다
    USED = 'used'


def joining_route(table: GameTable, here: uuid.UUID, there: uuid.UUID) -> RouteSnapshot | None:
    """지금 장소와 그 장소를 잇는 아는 길. 방향은 보지 않는다. 없으면 None."""
    snapshot = read_snapshot(table.content)
    known = places.known_map(snapshot, places.knowledge(table))
    return places.route_joining(known, here, there)


def resolve_device(route: RouteSnapshot, device: DoorDevice | None) -> DoorDevice:
    """
    잠그기와 열기가 다룰 장치. 적었으면 그 길에 있어야 하고, 비웠으면 그 길에 하나만 있어야 한다.

    아니면 ActionTargetError(device). 문이 없는 길도 같다.
    """
    present = door_devices(route)
    if device is not None and device in present:
        return device
    if device is None and len(present) == 1:
        return present[0]
    raise ActionTargetError('device')


def require_opening(route: RouteSnapshot, lock: LockSnapshot | ItemLockSnapshot | None, action: DoorAction) -> None:
    """
    따기, 부수기, 고치기, 바꾸기가 할 수 있는 문인지 본다. 판에 그 판정이 없으면 RoundConflictError.

    따기는 지금의 자물쇠(lock, 바꿔 달았으면 자물쇠 물건의 것)를 본다. 바꾸기는 판에 자물쇠가 있던 문이어야 한다.
    """
    if isinstance(action, PickAction) and (lock is None or lock.pick is None):
        raise RoundConflictError(Conflict.NOT_PICKABLE)
    if isinstance(action, ReplaceAction) and route.lock is None:
        raise RoundConflictError(Conflict.NOT_REPLACEABLE)
    if isinstance(action, ForceAction) and route.force is None:
        raise RoundConflictError(Conflict.NOT_FORCEABLE)
    if isinstance(action, RepairAction) and route.repair is None:
        raise RoundConflictError(Conflict.NOT_REPAIRABLE)


def require_lock_item(snapshot: Snapshot, member: TableMember, action: ReplaceAction) -> None:
    """
    바꿔 달 물건이 자물쇠 물건이고 지녔는지 본다.

    판에 자물쇠를 적은 물건이 아니면 ActionNotInRulesError(item),
    하나도 지니지 않았으면 RoundConflictError(item_not_held).
    """
    if item_rule_of(snapshot, action.item).lock is None:
        raise ActionNotInRulesError('item')
    if items.count_of(member.sheet, action.item) < 1:
        raise RoundConflictError(Conflict.ITEM_NOT_HELD)


def accept_door(table: GameTable, member: TableMember, action: DoorAction) -> dict:
    """
    문을 다루는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 맵에 서 있지 않으면 RoundConflictError(not_on_map).
      - 지금 장소와 아는 길로 이어진 장소가 아니면 ActionTargetError(place). 가기와 같다.
      - 잠그기, 열기: 장치가 그 길에 없거나, 둘 다 있는데 비웠으면 ActionTargetError(device).
        비운 장치는 그 길의 하나로 채운다.
      - 따기: 판에 따는 판정이 없으면 RoundConflictError(not_pickable). 부수기: 부수는 판정이 없으면 not_forceable.
        고치기: 고치는 판정이 없으면 not_repairable. 따기는 바꿔 단 자물쇠면 그 자물쇠의 따는 판정을 본다.
      - 바꾸기: 판에 자물쇠가 없던 문이면 RoundConflictError(not_replaceable). 자물쇠 물건이 아니면
        ActionNotInRulesError(item), 지니지 않았으면 RoundConflictError(item_not_held).
      - 따기, 부수기, 고치기에 붙인 물건(#802)이 그 행동을 거들지 않으면 ActionNotInRulesError(item),
        지니지 않았으면 RoundConflictError(item_not_held).
        도구가 있어야 하는데 붙이지 않았으면 ActionNotInRulesError(item).
    """
    here = standing_place(member)
    route = joining_route(table, here, action.place)
    if route is None:
        raise ActionTargetError('place')
    if isinstance(action, LockAction | UnlockAction):
        action = action.model_copy(update={'device': resolve_device(route, action.device)})
    snapshot = read_snapshot(table.content)
    lock = route_locks.current_lock(table, snapshot, route)
    require_opening(route, lock, action)
    if isinstance(action, ReplaceAction):
        require_lock_item(snapshot, member, action)
    act = AID_ACTS.get(type(action))
    if act is not None:
        require_door_aid(table, member, opening_check(route, lock, action), action, act)
    # 붙이지 않은 물건은 적지 않는다. 거들기가 생기기 전과 같은 모양이다
    return action.model_dump(mode='json', exclude_none=True)


def opening_check(route: RouteSnapshot, lock: LockSnapshot | ItemLockSnapshot | None, action: DoorAction):
    """따기, 부수기, 고치기가 굴릴 판정. 따기는 지금의 자물쇠의 것이다. require_opening 이 있는지 봤다."""
    if isinstance(action, PickAction):
        return lock.pick
    if isinstance(action, RepairAction):
        return route.repair
    return route.force


def require_door_aid(table: GameTable, member: TableMember, check, action: DoorAction, act: AidAct) -> None:
    """붙인 물건과 도구를 본다(#802). 붙였으면 그 행동을 거드는지와 지녔는지, 도구가 있어야 하면 붙였는지."""
    if action.item is not None:
        require_aid(table, member, action.item, act)
    require_tool(getattr(check, 'needs_tool', False), action.item)


# --- 차례가 왔을 때 ---


def set_bar(judging: Judging, member: TableMember, route: RouteSnapshot, barred: bool) -> str | None:
    """
    빗장을 걸거나(barred 참) 푼다. 못 했으면 그 까닭.

    빗장 쪽에 서 있어야 한다. 이미 그렇게 되어 있으면 already, 부서진 문에는 걸지 못한다(broken).
    """
    table = judging.table
    if member.sheet.place_id != route.bar.side:
        return DoorReason.WRONG_SIDE
    if barred and route_locks.is_broken(table, route):
        return DoorReason.BROKEN
    if route_locks.is_barred(table, route) == barred:
        return DoorReason.ALREADY
    if barred:
        route_locks.bar(table, route)
    else:
        route_locks.unbar(table, route)
    return None


def set_lock(judging: Judging, member: TableMember, route: RouteSnapshot, locked: bool) -> str | None:
    """
    자물쇠를 잠그거나(locked 참) 연다. 못 했으면 그 까닭.

    지금의 자물쇠의 열쇠를 지녀야 한다(바꿔 달았으면 새 열쇠). 이미 그렇게 되어 있으면 already,
    부서진 문은 잠그지 못한다(broken).
    """
    table = judging.table
    if locked and route_locks.is_broken(table, route):
        return DoorReason.BROKEN
    if route_locks.is_locked(table, route) == locked:
        return DoorReason.ALREADY
    if not holds_key(member, route_locks.current_lock(table, judging.snapshot, route)):
        return DoorReason.NO_KEY
    if locked:
        route_locks.lock(table, route)
    else:
        route_locks.unlock(table, route)
    return None


def set_door(judging: Judging, member: TableMember, route: RouteSnapshot, device: DoorDevice, shut: bool) -> str | None:
    """장치대로 문을 잠그거나(shut 참) 연다. 못 했으면 그 까닭."""
    if device == DoorDevice.BAR:
        return set_bar(judging, member, route, shut)
    return set_lock(judging, member, route, shut)


# 문 다루기의 결과. (못 한 까닭, 판정의 문서, 붙여 쓴 물건을 어떻게 했나). 굴리지 않았으면 뒤의 둘이 None
Handled = tuple[str | None, dict | None, AidUse | None]


def roll_opening(judging: Judging, member: TableMember, check, taken: TakenAid | None) -> tuple[bool, dict, AidUse]:
    """
    따기, 부수기, 고치기의 판정을 굴린다(#802). (성공했는가, 판정의 문서, 붙여 쓴 물건을 어떻게 했나)를 돌려준다.

    붙여 쓴 물건이 있으면 그 보정을 더하고, 굴린 뒤 그 물건의 방식대로 한다.
    """
    rolled = roll_terms(judging, member, check, bonus=aid_bonus(taken))
    use = wear_aid(member, taken, rolled.check.success)
    return rolled.check.success, terms_document(judging, check, rolled), use


def pick_lock(judging: Judging, member: TableMember, route: RouteSnapshot, taken: TakenAid | None) -> Handled:
    """
    자물쇠를 딴다. 잠겨 있지 않거나 도구가 없으면 굴리지 않는다.

    지금의 자물쇠의 따는 판정으로 굴린다. 받은 뒤 앞 차례에 따지 못하는 자물쇠로 바뀌었으면 no_pick 이다.
    도구가 있어야 하는데 붙인 물건을 더 지니지 않았으면(바꿔 단 자물쇠가 도구를 요구하면 붙이지 않았으면) no_tool 이다.
    성공하면 자물쇠가 열린다.
    """
    pick = route_locks.current_lock(judging.table, judging.snapshot, route).pick
    if not route_locks.is_locked(judging.table, route):
        return DoorReason.ALREADY, None, None
    if pick is None:
        return DoorReason.NO_PICK, None, None
    if pick.needs_tool and not has_tool(taken):
        return DoorReason.NO_TOOL, None, None
    success, check, use = roll_opening(judging, member, pick, taken)
    if success:
        route_locks.unlock(judging.table, route)
    return (None if success else DoorReason.FAILED), check, use


def force_door(judging: Judging, member: TableMember, route: RouteSnapshot, taken: TakenAid | None) -> Handled:
    """
    문을 부순다. 잠기지도 걸리지도 않았으면 굴리지 않는다.

    성공하면 자물쇠와 빗장이 부서져 열린다.
    """
    table = judging.table
    if not (route_locks.is_locked(table, route) or route_locks.is_barred(table, route)):
        return DoorReason.ALREADY, None, None
    success, check, use = roll_opening(judging, member, route.force, taken)
    if success:
        route_locks.break_open(table, route)
    return (None if success else DoorReason.FAILED), check, use


def repair_door(judging: Judging, member: TableMember, route: RouteSnapshot, taken: TakenAid | None) -> Handled:
    """
    부서진 문을 고친다. 부서지지 않았거나 도구가 없으면 굴리지 않는다.

    성공하면 문이 고쳐진다. 열린 채다(자물쇠도 빗장도 풀린 그대로).
    """
    repair = route.repair
    if not route_locks.is_broken(judging.table, route):
        return DoorReason.ALREADY, None, None
    if repair.needs_tool and not has_tool(taken):
        return DoorReason.NO_TOOL, None, None
    success, check, use = roll_opening(judging, member, repair, taken)
    if success:
        route_locks.repair(judging.table, route)
    return (None if success else DoorReason.FAILED), check, use


def replace_lock(judging: Judging, member: TableMember, route: RouteSnapshot, item: uuid.UUID) -> str | None:
    """
    문의 자물쇠를 자물쇠 물건으로 바꿔 단다. 못 했으면 그 까닭.

    부서진 문(broken)은 고친 뒤에, 잠긴 자물쇠(locked)는 연 뒤에 바꾼다. 자물쇠 물건을 더 지니지 않았으면 no_item,
    이 테이블에서 이미 단 자물쇠 물건이면 used 다. 바꾸면 열린 채이고 자물쇠 물건이 하나 없어진다.
    """
    table = judging.table
    if route_locks.is_broken(table, route):
        return DoorReason.BROKEN
    if route_locks.is_locked(table, route):
        return DoorReason.LOCKED
    if items.count_of(member.sheet, item) < 1:
        return DoorReason.NO_ITEM
    if route_locks.is_fitted(table, item):
        return DoorReason.USED
    items.remove_items(member.sheet, item, 1)
    route_locks.fit_lock(table, route, item)
    return None


def handle_door(
    judging: Judging, member: TableMember, route: RouteSnapshot, action: DoorAction, taken: TakenAid | None
) -> Handled:
    """
    행동의 종류대로 문을 다룬다. 잠그기, 열기, 바꾸기는 굴리지 않는다.

    taken 은 따기, 부수기, 고치기에 붙여 쓴 물건이다(#802).
    """
    if isinstance(action, LockAction | UnlockAction):
        return set_door(judging, member, route, action.device, isinstance(action, LockAction)), None, None
    if isinstance(action, ReplaceAction):
        return replace_lock(judging, member, route, action.item), None, None
    if isinstance(action, PickAction):
        return pick_lock(judging, member, route, taken)
    if isinstance(action, RepairAction):
        return repair_door(judging, member, route, taken)
    return force_door(judging, member, route, taken)


def judge_door(judging: Judging, member: TableMember, action: DoorAction) -> dict:
    """
    문을 다룬다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    받은 뒤로 서 있는 곳은 바뀌지 않는다(한 사람의 행동은 하나다). 그래서 받을 때 본 길이 있다.
    문서는 누가(user_id, character_name), 무엇을(act, device), 어느 길의(from, to), 했는가(done)와 까닭, 판정이다.
    따기, 부수기, 고치기에 물건을 붙였으면 그 물건(aid, app/rounds/aids.py 의 aid_document)도 적는다(#802).
    """
    here = member.sheet.place_id
    route = joining_route(judging.table, here, action.place)
    act = AID_ACTS.get(type(action))
    taken = take_aid(judging, member, action.item, act) if act is not None else None
    reason, check, use = handle_door(judging, member, route, action, taken)
    door = {
        **places.describe_move(judging.snapshot, member, here, action.place),
        'act': action.kind,
        'device': getattr(action, 'device', None),
        'done': reason is None,
        'reason': reason,
        'check': check,
    }
    # 붙여 쓴 물건(#802)은 붙였을 때만 적는다. 거들기가 생기기 전과 같은 모양이다
    if taken is not None:
        door['aid'] = aid_document(member, taken, use)
    return {'door': door}
