# trpg-server/app/rounds/door_actions.py

"""
길의 문을 다루는 행동(#281). 잠그기(lock), 열기(unlock), 따기(pick), 부수기(force), 고치기(repair).

선언을 받을 때 보고(accept_door), 라운드가 닫힐 때 차례가 오면 정한다(judge_door).
문은 지금 서 있는 장소에 닿은 아는 길의 것이다. 길의 방향은 보지 않는다(어느 끝에서든 다룬다). 지나가지는 않는다.

  - 잠그기, 열기: 자물쇠는 그 열쇠를 지닌 사람이, 빗장은 빗장 쪽에 선 사람이 한다. 부서진 문은 잠그지 못한다.
    장치(device)는 그 길에 하나만 있으면 비워도 된다. 자물쇠와 빗장이 다 있으면 적어야 한다.
  - 따기: 판에 적힌 따는 판정으로 잠긴 자물쇠를 연다. 판에 도구를 적었으면 그것을 지녀야 한다. 빗장은 따지 못한다.
  - 부수기: 판에 적힌 부수는 판정으로 문을 부순다. 자물쇠와 빗장이 다 열리고, 고치기 전까지 다시 잠그지 못한다.
  - 고치기: 판에 적힌 고치는 판정으로 부서진 문을 고친다. 판에 도구를 적었으면 그것을 지녀야 한다. 고친 문은 열린 채다.
  - 받을 때는 문이 있는지(그 장치, 따는 판정, 부수는 판정, 고치는 판정)만 본다.
    열쇠, 서 있는 쪽, 문의 지금 상태는 차례가 오면 본다.
    앞 차례에 누가 열쇠를 건넸거나 문을 열었을 수 있다. 할 수 없으면 굴리지 않고 까닭(reason)을 적는다.
  - 판정은 부상의 영향을 받는다. 실패하면 아무 일도 없다. 굴림은 공개다(check_rolled).

DB 를 모른다. 테이블의 문의 상태를 고친다(app/tables/route_locks.py). 저장하지 않는다.
"""

import uuid

from app.assets.scenarios.snapshot import RouteSnapshot, door_devices, read_snapshot
from app.engine.action import DoorAction, DoorDevice, ForceAction, LockAction, PickAction, RepairAction, UnlockAction
from app.rounds.effects import Judging
from app.rounds.errors import ActionTargetError, Conflict, RoundConflictError
from app.rounds.map_actions import holds_key, roll_terms, standing_place, terms_document
from app.tables import items, places, route_locks
from app.tables.models import GameTable, TableMember


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
    # 따거나 고치는 데 있어야 하는 도구가 없었다
    NO_TOOL = 'no_tool'
    # 따기, 부수기, 고치기의 판정에 실패했다
    FAILED = 'failed'


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


def require_opening(route: RouteSnapshot, action: DoorAction) -> None:
    """따기, 부수기, 고치기가 할 수 있는 문인지 본다. 판에 그 판정이 없으면 RoundConflictError."""
    if isinstance(action, PickAction) and (route.lock is None or route.lock.pick is None):
        raise RoundConflictError(Conflict.NOT_PICKABLE)
    if isinstance(action, ForceAction) and route.force is None:
        raise RoundConflictError(Conflict.NOT_FORCEABLE)
    if isinstance(action, RepairAction) and route.repair is None:
        raise RoundConflictError(Conflict.NOT_REPAIRABLE)


def accept_door(table: GameTable, member: TableMember, action: DoorAction) -> dict:
    """
    문을 다루는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 맵에 서 있지 않으면 RoundConflictError(not_on_map).
      - 지금 장소와 아는 길로 이어진 장소가 아니면 ActionTargetError(place). 가기와 같다.
      - 잠그기, 열기: 장치가 그 길에 없거나, 둘 다 있는데 비웠으면 ActionTargetError(device).
        비운 장치는 그 길의 하나로 채운다.
      - 따기: 판에 따는 판정이 없으면 RoundConflictError(not_pickable). 부수기: 부수는 판정이 없으면 not_forceable.
        고치기: 고치는 판정이 없으면 not_repairable.
    """
    here = standing_place(member)
    route = joining_route(table, here, action.place)
    if route is None:
        raise ActionTargetError('place')
    if isinstance(action, LockAction | UnlockAction):
        action = action.model_copy(update={'device': resolve_device(route, action.device)})
    require_opening(route, action)
    return action.model_dump(mode='json')


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

    그 열쇠를 지녀야 한다. 이미 그렇게 되어 있으면 already, 부서진 문은 잠그지 못한다(broken).
    """
    table = judging.table
    if locked and route_locks.is_broken(table, route):
        return DoorReason.BROKEN
    if route_locks.is_locked(table, route) == locked:
        return DoorReason.ALREADY
    if not holds_key(member, route.lock):
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


def pick_lock(judging: Judging, member: TableMember, route: RouteSnapshot) -> tuple[str | None, dict | None]:
    """
    자물쇠를 딴다. (못 한 까닭, 판정의 문서)를 돌려준다. 잠겨 있지 않거나 도구가 없으면 굴리지 않는다.

    성공하면 자물쇠가 열린다.
    """
    pick = route.lock.pick
    if not route_locks.is_locked(judging.table, route):
        return DoorReason.ALREADY, None
    if pick.tool is not None and items.count_of(member.sheet, pick.tool) < 1:
        return DoorReason.NO_TOOL, None
    rolled = roll_terms(judging, member, pick)
    if rolled.check.success:
        route_locks.unlock(judging.table, route)
    return (None if rolled.check.success else DoorReason.FAILED), terms_document(judging, pick, rolled)


def force_door(judging: Judging, member: TableMember, route: RouteSnapshot) -> tuple[str | None, dict | None]:
    """
    문을 부순다. (못 한 까닭, 판정의 문서)를 돌려준다. 잠기지도 걸리지도 않았으면 굴리지 않는다.

    성공하면 자물쇠와 빗장이 부서져 열린다.
    """
    table = judging.table
    if not (route_locks.is_locked(table, route) or route_locks.is_barred(table, route)):
        return DoorReason.ALREADY, None
    rolled = roll_terms(judging, member, route.force)
    if rolled.check.success:
        route_locks.break_open(table, route)
    return (None if rolled.check.success else DoorReason.FAILED), terms_document(judging, route.force, rolled)


def repair_door(judging: Judging, member: TableMember, route: RouteSnapshot) -> tuple[str | None, dict | None]:
    """
    부서진 문을 고친다. (못 한 까닭, 판정의 문서)를 돌려준다. 부서지지 않았거나 도구가 없으면 굴리지 않는다.

    성공하면 문이 고쳐진다. 열린 채다(자물쇠도 빗장도 풀린 그대로).
    """
    repair = route.repair
    if not route_locks.is_broken(judging.table, route):
        return DoorReason.ALREADY, None
    if repair.tool is not None and items.count_of(member.sheet, repair.tool) < 1:
        return DoorReason.NO_TOOL, None
    rolled = roll_terms(judging, member, repair)
    if rolled.check.success:
        route_locks.repair(judging.table, route)
    return (None if rolled.check.success else DoorReason.FAILED), terms_document(judging, repair, rolled)


def handle_door(judging: Judging, member: TableMember, route: RouteSnapshot, action: DoorAction) -> tuple:
    """행동의 종류대로 문을 다룬다. (못 한 까닭, 판정의 문서)를 돌려준다. 잠그기와 열기는 굴리지 않는다."""
    if isinstance(action, LockAction | UnlockAction):
        return set_door(judging, member, route, action.device, isinstance(action, LockAction)), None
    if isinstance(action, PickAction):
        return pick_lock(judging, member, route)
    if isinstance(action, RepairAction):
        return repair_door(judging, member, route)
    return force_door(judging, member, route)


def judge_door(judging: Judging, member: TableMember, action: DoorAction) -> dict:
    """
    문을 다룬다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    받은 뒤로 서 있는 곳은 바뀌지 않는다(한 사람의 행동은 하나다). 그래서 받을 때 본 길이 있다.
    문서는 누가(user_id, character_name), 무엇을(act, device), 어느 길의(from, to), 했는가(done)와 까닭, 판정이다.
    """
    here = member.sheet.place_id
    route = joining_route(judging.table, here, action.place)
    reason, check = handle_door(judging, member, route, action)
    return {
        'door': {
            **places.describe_move(judging.snapshot, member, here, action.place),
            'act': action.kind,
            'device': getattr(action, 'device', None),
            'done': reason is None,
            'reason': reason,
            'check': check,
        }
    }
