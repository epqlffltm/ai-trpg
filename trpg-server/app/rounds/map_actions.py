# trpg-server/app/rounds/map_actions.py

"""
맵에서 가고(move) 찾는(search) 행동. 선언을 받을 때 보고(accept_*), 라운드가 닫힐 때 결과를 정한다(judge_*).

  - 가기: 지금 서 있는 장소에서 아는 길로 이어진 장소로 한 칸 간다. 한 라운드에 한 칸이다.
    받을 때 이어진 곳인지 보고, 차례가 오면 다시 본다. 받은 뒤로 위치가 바뀌었을 수 있다.
    그때는 가지 않고 왜 못 갔는지(reason)를 적는다.
    길의 조건(#281)은 차례가 왔을 때 본다. 받을 때는 보지 않는다. 앞 차례에 누가 문을 열었을 수 있다.
      - 자물쇠: 잠겨 있으면 그 열쇠를 지닌 사람만 간다. 가면서 연다. 연 문은 열린 채라 뒤의 일행도 지나간다.
        열쇠가 없으면 가지 못한다(locked). 열쇠는 없어지지 않는다.
      - 넘기 판정: 지날 때마다 가는 사람이 판에 적힌 능력과 난이도로 굴린다. 부상의 영향은 판정하는 행동과 같다.
        실패하면 그 자리에 남고(cross_failed), 판에 실패의 피해를 적었으면 그만큼 다친다(떨어짐, 휩쓸림).
      - 빗장(#281): 걸려 있으면 빗장 쪽에 선 사람은 풀고 지나간다. 반대쪽에서는 지나가지 못한다(barred).
      - 빗장, 자물쇠, 넘기의 차례로 본다. 열고 나서 넘기에 실패하면 문은 열린 채 그 자리에 남는다.
      - 업힌 사람은 따로 굴리지 않는다. 업은 사람이 지나가면 함께 간다.
  - 업고 가기(carry, #367): 같은 장소에 쓰러져 있는(죽지 않은) 동료 한 명을 함께 데려간다. 쓰러진 사람은 선언을 못 하니
    일행이 가면 혼자 남는다. 받을 때 보고, 차례가 오면 다시 본다. 그사이 일어났거나 죽었거나 다른 사람이 먼저 업고
    갔으면 혼자 간다. 업을 사람이 가지 못했으면 업힌 사람도 그대로다. 죽은 캐릭터는 쓰러진 곳에 남는다.
  - 찾기: 지금 서 있는 장소에 닿은, 아직 찾지 않은 숨긴 길마다 판에 적힌 판정(능력과 난이도)을 굴린다.
    그 장소의 숨긴 물건도 함께 찾는다(app/rounds/place_item_actions.py 의 search_items, app/rounds/judging.py).
    부상의 영향은 판정하는 행동과 같다. 성공한 길은 찾은 것으로 적는다(테이블의 모두가 안다).
    **찾지 못한 판정은 아무 데도 적지 않는다.** 굴린 것을 보이면 그 장소에 숨긴 길이 있다는 것이 드러난다.
    숨긴 길이 없는 곳을 찾아도, 있는데 못 찾아도 결과는 같다(찾은 길이 없다). 사람 GM 이 가림막 뒤에서 굴리는 것과 같다.
맵에 서 있지 않은 캐릭터(맵이 없는 판, 맵이 생기기 전에 시작한 테이블)는 둘 다 할 수 없다.

DB 를 모른다. 시트의 위치와 테이블의 서 본 곳, 찾은 길을 고친다(app/tables/places.py). 저장하지 않는다.
"""

import uuid
from dataclasses import asdict
from typing import Protocol

from app.assets.scenarios.snapshot import CrossSnapshot, LockSnapshot, RouteSnapshot, read_snapshot
from app.calendar import state as calendar
from app.engine.action import MoveAction, SearchAction
from app.engine.check import HinderedCheck, find_difficulty, resolve_hindered
from app.engine.health import ChangeKind
from app.rounds import injuries as round_injuries
from app.rounds.checks import change_sheet
from app.rounds.effects import Judging
from app.rounds.errors import ActionTargetError, Conflict, RoundConflictError
from app.tables import items, places, route_locks, sheets
from app.tables.models import GameTable, TableMember
from app.tables.state import find_member


class Reason:
    """가지 못한 까닭. 결과의 reason 에 적는다."""

    # 차례가 왔을 때 서 있는 곳에서 그 장소로 가는 아는 길이 없었다
    NOT_ADJACENT = 'not_adjacent'
    # 길이 잠겨 있었고 그 열쇠가 없었다(#281)
    LOCKED = 'locked'
    # 빗장이 반대쪽에 걸려 있었다(#281)
    BARRED = 'barred'
    # 길을 넘는 판정에 실패했다(#281)
    CROSS_FAILED = 'cross_failed'


class CarryReason:
    """업고 가지 못한 까닭. 결과의 carry.reason 에 적는다."""

    # 업을 사람이 가지 못했다
    NOT_MOVED = 'not_moved'
    # 차례가 오기 전에 일어났다(회복, 치료). 스스로 갈 수 있다
    STANDING = 'standing'
    # 차례가 오기 전에 죽었다. 죽은 캐릭터는 쓰러진 곳에 남는다
    DEAD = 'dead'
    # 같은 곳에 없다. 앞 차례에 누가 먼저 업고 갔거나 그 사람이 테이블을 떠났다
    ELSEWHERE = 'elsewhere'


def standing_place(member: TableMember) -> uuid.UUID:
    """캐릭터가 서 있는 장소. 맵에 서 있지 않으면 RoundConflictError(not_on_map)."""
    if member.sheet is None or member.sheet.place_id is None:
        raise RoundConflictError(Conflict.NOT_ON_MAP)
    return member.sheet.place_id


def accept_move(table: GameTable, member: TableMember, action: MoveAction) -> dict:
    """
    가는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 맵에 서 있지 않으면 RoundConflictError(not_on_map).
      - 지금 장소에서 아는 길로 이어진 장소가 아니면 ActionTargetError(place).
        모르는 곳, 숨긴 곳, 장소가 아닌 것, 이어지지 않은 곳을 가르지 않는다. 가르면 숨긴 장소가 드러난다.
    """
    here = standing_place(member)
    snapshot = read_snapshot(table.content)
    known = places.known_map(snapshot, places.knowledge(table))
    if action.place not in places.exits(known, here):
        raise ActionTargetError('place')
    if action.carry is not None and not can_carry(find_member(table, action.carry), here):
        raise ActionTargetError('carry')
    # 업지 않으면 carry 를 적지 않는다. 업고 가기가 생기기 전과 같은 모양이다
    return action.model_dump(mode='json', exclude_none=True)


def can_carry(carried: TableMember | None, here: uuid.UUID) -> bool:
    """
    그 사람을 업을 수 있는가. 앉아 있고, 쓰러져 있지만 죽지 않았고, 같은 장소에 있다.

    앉지 않은 사람, 서 있는 사람, 죽은 사람, 다른 곳의 사람을 가르지 않는다(모두 422 carry).
    자기 자신은 따로 보지 않는다. 선언하는 사람은 서 있다(쓰러진 사람은 선언을 못 한다).
    """
    return carried is not None and sheets.is_downed_alive(carried) and carried.sheet.place_id == here


def accept_search(member: TableMember, action: SearchAction) -> dict:
    """찾는 행동을 받는다. 맵에 서 있지 않으면 RoundConflictError(not_on_map). 숨긴 길이 있는지는 알려 주지 않는다."""
    standing_place(member)
    return action.model_dump(mode='json')


def holds_key(member: TableMember, lock: LockSnapshot) -> bool:
    """이 캐릭터가 그 자물쇠의 열쇠를 지녔는가."""
    return items.count_of(member.sheet, lock.key) >= 1


def open_lock(judging: Judging, member: TableMember, route: RouteSnapshot) -> tuple[bool, bool]:
    """
    길의 자물쇠를 지나간다. (지나갈 수 있는가, 열었는가)를 돌려준다.

    잠겨 있지 않으면 그냥 지나간다. 잠겨 있으면 열쇠를 지닌 사람만 열고 지나간다. 연 문은 열린 채다.
    """
    if not route_locks.is_locked(judging.table, route):
        return True, False
    if not holds_key(member, route.lock):
        return False, False
    route_locks.unlock(judging.table, route)
    return True, True


class Terms(Protocol):
    """판에 적힌 판정 하나의 능력과 난이도. 넘기, 따기, 부수기(#281)가 이 모양이다."""

    ability: str
    difficulty: str | None


def roll_terms(judging: Judging, member: TableMember, terms: Terms) -> HinderedCheck:
    """
    판에 적힌 판정을 굴린다. 그 능력과 난이도(비웠으면 규칙의 기본)로, 입은 부상의 영향을 받는다.

    길을 넘을 때, 자물쇠를 딸 때, 문을 부술 때 쓴다. 판에 굳을 때 규칙에 있는 능력과 난이도인지 봤다
    (게시의 route_cross_invalid, route_open_invalid).
    """
    ruleset = judging.ruleset
    sheet = member.sheet
    difficulty = find_difficulty(ruleset, terms.difficulty)
    hindrance = round_injuries.hindrance_for(ruleset, sheet.injuries, terms.ability)
    return resolve_hindered(ruleset, sheet.abilities[terms.ability], difficulty, judging.dice, hindrance)


def terms_document(judging: Judging, terms: Terms, rolled: HinderedCheck) -> dict:
    """
    판에 적힌 판정을 결과에 적을 모양. 무엇으로 굴렸는지(능력, 난이도)와 판정, 부상의 영향이다.

    난이도는 판에 비워 뒀으면 규칙의 기본 난이도의 이름표다. 판정하는 행동의 결과와 같은 모양이다.
    """
    return {
        'ability': terms.ability,
        'difficulty': find_difficulty(judging.ruleset, terms.difficulty).key,
        **asdict(rolled.check),
        'hindrance': round_injuries.hindrance_document(rolled),
    }


def fall(judging: Judging, member: TableMember, cross: CrossSnapshot) -> dict | None:
    """넘기에 실패한 사람이 판에 적힌 실패의 피해만큼 다친다. 적지 않았으면 None. 바뀐 것을 문서로 돌려준다."""
    if cross.harm is None:
        return None
    return change_sheet(judging, member, ChangeKind.DAMAGE, cross.harm)


def cross_route(judging: Judging, member: TableMember, cross: CrossSnapshot | None) -> tuple[bool, dict]:
    """
    길을 넘는다. (넘었는가, 결과에 더할 칸들)을 돌려준다. 넘기 판정이 없는 길이면 굴리지 않고 넘는다.

    칸은 넘기 판정(cross)과 실패해서 다친 것(effect)이다.
    """
    if cross is None:
        return True, {'cross': None, 'effect': None}
    rolled = roll_terms(judging, member, cross)
    passed = rolled.check.success
    effect = None if passed else fall(judging, member, cross)
    return passed, {'cross': terms_document(judging, cross, rolled), 'effect': effect}


def lift_bar(judging: Judging, member: TableMember, route: RouteSnapshot) -> tuple[bool, bool]:
    """
    길의 빗장을 지나간다. (지나갈 수 있는가, 풀었는가)를 돌려준다.

    걸려 있지 않으면 그냥 지나간다. 걸려 있으면 빗장 쪽에 선 사람만 풀고 지나간다. 반대쪽에서는 지나가지 못한다.
    """
    if not route_locks.is_barred(judging.table, route):
        return True, False
    if member.sheet.place_id != route.bar.side:
        return False, False
    route_locks.unbar(judging.table, route)
    return True, True


# 아무 조건도 지나가지 않은 결과의 칸들
UNTOUCHED = {'unbarred': False, 'unlocked': False, 'cross': None, 'effect': None}


def pass_route(judging: Judging, member: TableMember, route: RouteSnapshot | None) -> tuple[str | None, dict]:
    """
    길을 지나간다. (못 간 까닭, 결과에 더할 칸들)을 돌려준다. 갔으면 까닭이 None 이다.

    빗장, 자물쇠, 넘기 판정의 차례로 본다. 아는 길이 없으면 not_adjacent, 빗장이 반대쪽에 걸렸으면 barred,
    잠겼는데 열쇠가 없으면 locked, 넘기에 실패하면 cross_failed 다.
    칸은 빗장을 풀었는지(unbarred), 자물쇠를 열었는지(unlocked)와 넘기의 것(cross_route)이다.
    """
    if route is None:
        return Reason.NOT_ADJACENT, UNTOUCHED
    lifted, unbarred = lift_bar(judging, member, route)
    if not lifted:
        return Reason.BARRED, UNTOUCHED
    open_, unlocked = open_lock(judging, member, route)
    if not open_:
        return Reason.LOCKED, {**UNTOUCHED, 'unbarred': unbarred}
    crossed, fields = cross_route(judging, member, route.cross)
    return (None if crossed else Reason.CROSS_FAILED), {'unbarred': unbarred, 'unlocked': unlocked, **fields}


def judge_move(judging: Judging, member: TableMember, action: MoveAction) -> dict:
    """
    한 칸 간다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    차례가 왔을 때의 장소에서 아는 길로 이어져 있고, 길의 조건을 채워야 간다(pass_route). 가면 그곳이 서 본 곳이 된다.
    시간이 걸리는 길이면 다음 라운드가 열릴 때 적어도 그만큼 흐르게 한다(travel_time).
    """
    snapshot = judging.snapshot
    here = member.sheet.place_id
    known = places.known_map(snapshot, places.knowledge(judging.table))
    route = places.route_between(known, here, action.place)
    reason, fields = pass_route(judging, member, route)
    moved = reason is None
    travel = travel_time(judging, route) if moved else None
    if moved:
        places.stand(judging.table, member.sheet, action.place)
    move = places.describe_move(snapshot, member, here, action.place)
    outcome = {**move, 'moved': moved, 'reason': reason, 'travel_minutes': travel, **fields}
    if action.carry is not None:
        carried = find_member(judging.table, action.carry)
        outcome['carry'] = carry_along(judging, carried, action.carry, here, action.place if moved else None)
    return {'move': outcome}


def carry_problem(carried: TableMember | None, here: uuid.UUID, to: uuid.UUID | None) -> str | None:
    """차례가 왔을 때 업고 가지 못하는 까닭. 업을 수 있으면 None. 업을 사람이 못 갔으면 to 가 None 이다."""
    if to is None:
        return CarryReason.NOT_MOVED
    if carried is None or carried.sheet is None or carried.sheet.place_id != here:
        return CarryReason.ELSEWHERE
    if sheets.is_dead(carried):
        return CarryReason.DEAD
    if not sheets.is_downed_alive(carried):
        return CarryReason.STANDING
    return None


def carry_along(
    judging: Judging, carried: TableMember | None, user_id: uuid.UUID, here: uuid.UUID, to: uuid.UUID | None
) -> dict:
    """
    쓰러진 동료를 함께 데려간다. 결과의 carry 에 넣을 문서를 돌려준다.

    to 는 업은 사람이 간 곳이다. 가지 못했으면 None 이다. 업힌 사람도 그곳이 서 본 곳이 된다.
    """
    reason = carry_problem(carried, here, to)
    if reason is None:
        places.stand(judging.table, carried.sheet, to)
    name = carried.character_name if carried is not None else None
    return {'user_id': str(user_id), 'character_name': name, 'carried': reason is None, 'reason': reason}


def travel_time(judging: Judging, route: RouteSnapshot) -> int | None:
    """
    지나간 길에 걸리는 시간(분). 걸리는 길이면 다음 라운드가 열릴 때 적어도 그만큼 흐르게 한다. 안 걸리면 None.

    같은 라운드에 여럿이 갔으면 가장 긴 길이 남는다(calendar.stretch_next_step 이 긴 쪽만 받는다).
    """
    if route.travel_minutes is None:
        return None
    calendar.stretch_next_step(judging.table, route.travel_minutes)
    return route.travel_minutes


def finds(judging: Judging, member: TableMember, route: RouteSnapshot) -> bool:
    """
    숨긴 길 하나를 찾는 판정을 굴린다. 찾았는가.

    판에 적힌 능력과 난이도(비웠으면 규칙의 기본 난이도)로 굴린다. 입은 부상이 그 능력에 주는 영향을 받는다.
    판에 굳을 때 규칙에 있는 능력과 난이도인지 봤다(게시의 route_find_invalid).
    """
    ruleset = judging.ruleset
    sheet = member.sheet
    difficulty = find_difficulty(ruleset, route.find.difficulty)
    hindrance = round_injuries.hindrance_for(ruleset, sheet.injuries, route.find.ability)
    score = sheet.abilities[route.find.ability]
    return resolve_hindered(ruleset, score, difficulty, judging.dice, hindrance).check.success


def judge_search(judging: Judging, member: TableMember) -> dict:
    """
    지금 장소에서 숨긴 길을 찾는다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    찾은 길만 적는다. 굴린 판정, 못 찾은 길의 수는 적지 않는다.
    같은 라운드에 앞사람이 먼저 찾은 길은 다시 굴리지 않는다.
    """
    snapshot = judging.snapshot
    here = member.sheet.place_id
    found = []
    if here is not None:
        for route in places.hidden_routes_at(snapshot, places.knowledge(judging.table), here):
            if finds(judging, member, route):
                places.find_route(judging.table, route)
                found.append(places.describe_route(snapshot, route))
    return {'search': {'place': places.describe(snapshot, here), 'found': found}}
