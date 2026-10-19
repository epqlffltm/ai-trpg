# trpg-server/app/tables/places.py

"""
테이블의 맵을 다루는 규칙. 무엇을 아는가, 캐릭터가 어디에 서는가, 어디로 갈 수 있는가.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 시트의 위치(TableSheet.place_id), 서 본 곳(TableVisit),
찾은 숨긴 길(TableFoundRoute)을 고친다. 저장은 부르는 쪽이 한다.

맵의 무엇을 아는지는 저장하지 않고 계산한다. 재료는 판의 규칙, 서 본 곳, 찾은 숨긴 길이다.
아는 것은 테이블의 모두가 함께 안다.
  - 길: 열린 길(open)은 처음부터 안다. 안개 길(fog)은 누가 그 길의 한쪽 끝에 서 본 뒤부터 안다.
        숨긴 길(hidden)은 찾은 뒤부터 안다. 찾는 것은 선언 행동(search)이다(app/rounds/map_actions.py).
  - 장소: 시작 장소, 명소, 서 본 곳, 아는 길의 두 끝을 안다. 길을 알면 그 길이 어디로 가는지도 안다.
아직 찾지 않은 숨긴 길과, 그런 길로만 닿는 장소는 방장도 모른다. 시나리오를 만든 사람과 AI GM 만 안다.
그래서 아는 것만 응답과 이벤트에 싣는다. 캐릭터는 아는 곳에만 서므로 위치가 모르는 곳을 드러내는 일도 없다.
"""

import uuid
from dataclasses import dataclass

from app.assets.models import RouteVisibility
from app.assets.scenarios.snapshot import EntrySnapshot, RouteSnapshot, Snapshot, has_map, place_entries
from app.tables.errors import TableOptionError
from app.tables.models import GameTable, TableFoundRoute, TableMember, TableSheet, TableVisit

# 길 하나를 가리키는 값. 판에 적힌 두 끝(from_place, to_place)이다
RouteKey = tuple[uuid.UUID, uuid.UUID]


@dataclass(frozen=True)
class Knowledge:
    """테이블이 맵에 대해 겪은 것. 서 본 곳과 찾은 숨긴 길이다. 아는 것은 이것과 판의 규칙으로 계산한다."""

    seen: frozenset[uuid.UUID]
    found: frozenset[RouteKey]


@dataclass(frozen=True)
class KnownMap:
    """테이블이 아는 맵. 장소는 판의 장소 항목 순서, 길은 판의 길 순서다."""

    places: list[EntrySnapshot]
    routes: list[RouteSnapshot]

    def has(self, place_id: uuid.UUID) -> bool:
        """아는 장소인가."""
        return any(place.id == place_id for place in self.places)


def key_of(route: RouteSnapshot) -> RouteKey:
    """길을 가리키는 값."""
    return route.from_place, route.to_place


def knowledge(table: GameTable) -> Knowledge:
    """이 테이블이 서 본 곳과 찾은 숨긴 길."""
    return Knowledge(
        seen=frozenset(visit.entry_id for visit in table.visits),
        found=frozenset((route.from_place, route.to_place) for route in table.found_routes),
    )


def touches(route: RouteSnapshot, place_id: uuid.UUID) -> bool:
    """이 길의 한쪽 끝이 그 장소인가. 방향은 보지 않는다."""
    return place_id in (route.from_place, route.to_place)


def route_known(route: RouteSnapshot, known: Knowledge) -> bool:
    """
    이 길을 아는가. 열린 길은 늘, 안개 길은 한쪽 끝에 서 본 적이 있으면, 숨긴 길은 찾았으면 안다.

    한쪽으로만 가는 길도 양쪽 끝 어디에서든 보인다. 내려가는 구멍은 아래에서도 올려다보인다.
    """
    if route.visibility == RouteVisibility.OPEN:
        return True
    if route.visibility == RouteVisibility.FOG:
        return any(touches(route, place) for place in known.seen)
    return key_of(route) in known.found


def known_map(snapshot: Snapshot, known: Knowledge) -> KnownMap | None:
    """테이블이 아는 맵. 맵이 없는 판이면 None."""
    if not has_map(snapshot):
        return None
    routes = [route for route in snapshot.routes if route_known(route, known)]
    places = {snapshot.start_place, *snapshot.landmarks, *known.seen}
    places.update(end for route in routes for end in (route.from_place, route.to_place))
    return KnownMap(places=[entry for entry in place_entries(snapshot) if entry.id in places], routes=routes)


def require_known(known: KnownMap | None, place_id: uuid.UUID) -> None:
    """
    아는 장소인지 확인한다. 아니면 TableOptionError(place_id).

    판에 없는 장소, 장소가 아닌 항목, 아직 모르는 장소, 맵이 없는 판을 가르지 않고 같은 답을 준다.
    가르면 숨긴 장소가 있다는 것이 드러난다.
    """
    if known is None or not known.has(place_id):
        raise TableOptionError('place_id')


def exits(known: KnownMap | None, place_id: uuid.UUID) -> list[uuid.UUID]:
    """
    그 장소에서 아는 길로 한 칸에 갈 수 있는 장소들. 판의 길 순서다. 맵이 없으면 빈 목록.

    한쪽으로만 가는 길은 from_place 에서 to_place 로만 간다.
    """
    if known is None:
        return []
    reachable = []
    for route in known.routes:
        if route.from_place == place_id:
            reachable.append(route.to_place)
        elif route.two_way and route.to_place == place_id:
            reachable.append(route.from_place)
    return reachable


def route_between(known: KnownMap | None, here: uuid.UUID | None, there: uuid.UUID) -> RouteSnapshot | None:
    """here 에서 there 로 한 칸에 가는 아는 길. 없으면 None. 판의 길 순서로 처음 것이다(exits 와 같은 방향 규칙)."""
    if known is None or here is None:
        return None
    for route in known.routes:
        if route.from_place == here and route.to_place == there:
            return route
        if route.two_way and route.to_place == here and route.from_place == there:
            return route
    return None


def hidden_routes_at(snapshot: Snapshot, known: Knowledge, place_id: uuid.UUID) -> list[RouteSnapshot]:
    """그 장소에 한쪽 끝이 닿은, 아직 찾지 않은 숨긴 길들. 판의 길 순서다. 찾기가 굴릴 길들이다."""
    return [
        route
        for route in snapshot.routes
        if route.visibility == RouteVisibility.HIDDEN and touches(route, place_id) and key_of(route) not in known.found
    ]


def find_route(table: GameTable, route: RouteSnapshot) -> None:
    """숨긴 길을 찾은 것으로 적는다. 아직 찾지 않은 길만 받는다(hidden_routes_at 이 고른 길)."""
    table.found_routes.append(TableFoundRoute(table_id=table.id, from_place=route.from_place, to_place=route.to_place))


def visit(table: GameTable, place_id: uuid.UUID) -> None:
    """서 본 곳으로 적는다. 이미 적힌 곳이면 그대로 둔다."""
    if place_id not in knowledge(table).seen:
        table.visits.append(TableVisit(table_id=table.id, entry_id=place_id))


def stand(table: GameTable, sheet: TableSheet, place_id: uuid.UUID) -> None:
    """캐릭터를 그 장소에 세운다. 서 본 곳으로도 적는다. 아는 곳인지는 부르는 쪽이 확인한다."""
    sheet.place_id = place_id
    visit(table, place_id)


def place_at_start(table: GameTable, snapshot: Snapshot) -> None:
    """시작할 때 모든 캐릭터를 판의 시작 장소에 세운다. 시트를 준 뒤에 부른다. 맵이 없는 판이면 아무것도 하지 않는다."""
    if not has_map(snapshot):
        return
    for member in table.members:
        stand(table, member.sheet, snapshot.start_place)


def take_over_place(member: TableMember) -> None:
    """
    새 캐릭터를 앞 캐릭터가 쓰러진 곳에 세운다. 새 시트를 준 뒤에 부른다.

    그곳은 앞 캐릭터가 서 있던 곳이라 이미 서 본 곳이다. 앞 캐릭터에게 위치가 없으면(맵이 없는 판) 새 캐릭터에게도 없다.
    """
    member.sheet.place_id = member.fallen[-1].place_id


def describe(snapshot: Snapshot, place_id: uuid.UUID | None) -> dict | None:
    """장소를 이벤트에 적을 모양. 위치가 없으면 None."""
    if place_id is None:
        return None
    name = next(entry.name for entry in place_entries(snapshot) if entry.id == place_id)
    return {'entry_id': str(place_id), 'name': name}


def describe_move(snapshot: Snapshot, member: TableMember, previous: uuid.UUID | None, place_id: uuid.UUID) -> dict:
    """
    옮겨 간 것을 이벤트에 적을 모양. 누가, 어디에서, 어디로. 맵이 생기기 전에 시작한 테이블이면 어디에서가 없다.

    방장이 옮길 때(app/tables/place_changes.py)와 선언 행동으로 갈 때(app/rounds/map_actions.py)가 같이 쓴다.
    """
    return {
        'user_id': str(member.user_id),
        'character_name': member.character_name,
        'from': describe(snapshot, previous),
        'to': describe(snapshot, place_id),
    }


def describe_route(snapshot: Snapshot, route: RouteSnapshot) -> dict:
    """길을 이벤트에 적을 모양. 두 끝과 양쪽으로 다니는지."""
    return {
        'from_place': describe(snapshot, route.from_place),
        'to_place': describe(snapshot, route.to_place),
        'two_way': route.two_way,
    }
