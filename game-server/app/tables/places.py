# game-server/app/tables/places.py

"""
테이블의 맵을 다루는 규칙. 무엇을 아는가, 캐릭터가 어디에 서는가.

DB 를 모른다. 이미 읽어 온 테이블과 판을 받아 시트의 위치(TableSheet.place_id)와 서 본 곳(TableVisit)을 고친다.
저장은 부르는 쪽이 한다.

맵의 무엇을 아는지는 저장하지 않고 계산한다. 재료는 판의 규칙과 서 본 곳이다. 아는 것은 테이블의 모두가 함께 안다.
  - 길: 열린 길(open)은 처음부터 안다. 안개 길(fog)은 누가 그 길의 한쪽 끝에 서 본 뒤부터 안다.
        숨긴 길(hidden)은 모른다. 찾는 것은 선언 행동(search)이 맡는다.
  - 장소: 시작 장소, 명소, 서 본 곳, 아는 길의 두 끝을 안다. 길을 알면 그 길이 어디로 가는지도 안다.
숨긴 길과, 숨긴 길로만 닿는 장소는 방장도 모른다. 시나리오를 만든 사람과 AI GM 만 안다.
그래서 아는 것만 응답과 이벤트에 싣는다. 캐릭터는 아는 곳에만 서므로 위치가 모르는 곳을 드러내는 일도 없다.
"""

import uuid
from dataclasses import dataclass

from app.assets.models import RouteVisibility
from app.assets.scenarios.snapshot import EntrySnapshot, RouteSnapshot, Snapshot, has_map, place_entries
from app.tables.errors import TableOptionError
from app.tables.models import GameTable, TableMember, TableSheet, TableVisit


@dataclass(frozen=True)
class KnownMap:
    """테이블이 아는 맵. 장소는 판의 장소 항목 순서, 길은 판의 길 순서다."""

    places: list[EntrySnapshot]
    routes: list[RouteSnapshot]

    def has(self, place_id: uuid.UUID) -> bool:
        """아는 장소인가."""
        return any(place.id == place_id for place in self.places)


def visited(table: GameTable) -> frozenset[uuid.UUID]:
    """이 테이블의 캐릭터가 서 본 장소들."""
    return frozenset(visit.entry_id for visit in table.visits)


def route_known(route: RouteSnapshot, seen: frozenset[uuid.UUID]) -> bool:
    """
    이 길을 아는가. 열린 길은 늘, 안개 길은 한쪽 끝에 서 본 적이 있으면 안다. 숨긴 길은 모른다.

    한쪽으로만 가는 길도 양쪽 끝 어디에서든 보인다. 내려가는 구멍은 아래에서도 올려다보인다.
    """
    if route.visibility == RouteVisibility.OPEN:
        return True
    if route.visibility == RouteVisibility.FOG:
        return route.from_place in seen or route.to_place in seen
    return False


def known_map(snapshot: Snapshot, seen: frozenset[uuid.UUID]) -> KnownMap | None:
    """테이블이 아는 맵. 맵이 없는 판이면 None."""
    if not has_map(snapshot):
        return None
    routes = [route for route in snapshot.routes if route_known(route, seen)]
    known = {snapshot.start_place, *snapshot.landmarks, *seen}
    known.update(end for route in routes for end in (route.from_place, route.to_place))
    return KnownMap(places=[entry for entry in place_entries(snapshot) if entry.id in known], routes=routes)


def require_known(known: KnownMap | None, place_id: uuid.UUID) -> None:
    """
    아는 장소인지 확인한다. 아니면 TableOptionError(place_id).

    판에 없는 장소, 장소가 아닌 항목, 아직 모르는 장소, 맵이 없는 판을 가르지 않고 같은 답을 준다.
    가르면 숨긴 장소가 있다는 것이 드러난다.
    """
    if known is None or not known.has(place_id):
        raise TableOptionError('place_id')


def visit(table: GameTable, place_id: uuid.UUID) -> None:
    """서 본 곳으로 적는다. 이미 적힌 곳이면 그대로 둔다."""
    if place_id not in visited(table):
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
