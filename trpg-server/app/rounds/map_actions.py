# trpg-server/app/rounds/map_actions.py

"""
맵에서 가고(move) 찾는(search) 행동. 선언을 받을 때 보고(accept_*), 라운드가 닫힐 때 결과를 정한다(judge_*).

  - 가기: 지금 서 있는 장소에서 아는 길로 이어진 장소로 한 칸 간다. 판정이 없다. 한 라운드에 한 칸이다.
    받을 때 이어진 곳인지 보고, 차례가 오면 다시 본다. 받은 뒤로 위치가 바뀌었을 수 있다.
    그때는 가지 않고 왜 못 갔는지(reason)를 적는다.
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

from app.assets.scenarios.snapshot import RouteSnapshot, read_snapshot
from app.calendar import state as calendar
from app.engine.action import MoveAction, SearchAction
from app.engine.check import find_difficulty, resolve_hindered
from app.rounds import injuries as round_injuries
from app.rounds.effects import Judging
from app.rounds.errors import ActionTargetError, Conflict, RoundConflictError
from app.tables import places, sheets
from app.tables.models import GameTable, TableMember
from app.tables.state import find_member


class Reason:
    """가지 못한 까닭. 결과의 reason 에 적는다."""

    # 차례가 왔을 때 서 있는 곳에서 그 장소로 가는 아는 길이 없었다
    NOT_ADJACENT = 'not_adjacent'


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


def judge_move(judging: Judging, member: TableMember, action: MoveAction) -> dict:
    """
    한 칸 간다. 결과를 선언의 outcome 에 넣을 문서로 돌려준다.

    차례가 왔을 때의 장소에서 아는 길로 이어져 있어야 간다. 가면 그곳이 서 본 곳이 된다.
    시간이 걸리는 길이면 다음 라운드가 열릴 때 적어도 그만큼 흐르게 한다(travel_time).
    """
    snapshot = judging.snapshot
    here = member.sheet.place_id
    known = places.known_map(snapshot, places.knowledge(judging.table))
    route = places.route_between(known, here, action.place)
    moved = route is not None
    travel = travel_time(judging, route) if moved else None
    if moved:
        places.stand(judging.table, member.sheet, action.place)
    move = places.describe_move(snapshot, member, here, action.place)
    reason = None if moved else Reason.NOT_ADJACENT
    outcome = {**move, 'moved': moved, 'reason': reason, 'travel_minutes': travel}
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
