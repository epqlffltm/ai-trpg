# trpg-server/app/rounds/monster_roams.py

"""
싸우지 않는 몬스터의 움직임(#254). 사냥하기와 배회하기다. 라운드를 닫을 때 상태의 피해와 부상의 끝 다음에 본다
(app/rounds/service.py). 엔진이 정한다. 서술(AI)이 정하지 않는다.

  - 움직이는 마리: 살아 있고 움직일 수 있고(기절 같은 부상이 없다), 이번 라운드에 싸우지 않은 마리다.
    라운드를 닫기 시작할 때 장면에 없었고(살아 있는 캐릭터가 선 곳에 없었다), 지금도 그 자리에 캐릭터가 없다.
    장면에 있던 마리는 차례를 받았다(치거나 쫓는다, app/rounds/monster_chase.py)
  - 사냥(시트의 hunts): 길의 칸 수가 hunts 안인 곳에 살아 있는 캐릭터가 서 있으면 가장 가까운 그곳으로 한 칸 간다
  - 배회(시트의 roams): 사냥할 것이 없으면 백분율의 주사위(d100)를 굴려 chance 이하이면 이웃한 장소 하나로 간다.
    처음 놓인 곳(home_place_id)에서 reach 칸 안인 곳만 고른다. 여럿이면 서버의 주사위다
  - 한 라운드에 한 칸만 간다. 사냥이 배회보다 먼저다(2026-11-09 결정)
  - 길은 판의 길 전부다(몬스터는 자기 던전을 안다). 한쪽으로만 가는 길은 그쪽으로만 간다. 쫓기와 같이
    잠긴 길, 빗장이 걸린 길, 넘기 판정이 있는 길은 지나지 못한다. 아직 열리지 않은 장(#481)의 장소로도 가지 않는다
  - 같으면 판의 길 순서가 앞인 쪽이다(가장 가까운 곳이 여럿이거나, 한 칸의 길이 여럿일 때). 주사위를 쓰지 않는다
  - 들어간 곳에 캐릭터가 있으면 다음 라운드에 장면에 들어 차례를 받는다. 들어간 라운드에는 치지 않는다
    (쫓기와 같다, 2026-11-09 결정). 기습은 없다(옮겨진 마리는 조우를 찾지 못한다, app/rounds/initiative.py)

플레이어에게 보이는 것은 캐릭터가 선 곳에 들어온 움직임뿐이다(2026-11-09 결정, record). 아무도 없는 곳의 움직임은
마리의 자리만 바뀌고 적지 않는다. 온 곳은 테이블이 아는 장소일 때만 이름을 적는다.
DB 를 모른다(record 만 이벤트를 적는다). 마리의 장소를 고친다. 저장하지는 않는다.
"""

import enum
import uuid
from collections import deque
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import RouteSnapshot, Snapshot, has_map, place_entries, read_snapshot
from app.engine.dice import Dice, choose
from app.engine.ruleset import Ruleset
from app.events import recorder
from app.events.models import EventType
from app.rounds import injuries as round_injuries
from app.rounds.cast import Scene
from app.rounds.monster_scene import SceneMonster, every_monster, occupied_places
from app.tables import chapters, places, route_locks
from app.tables.models import GameTable, NpcStatus

# 배회의 확률을 굴리는 주사위의 면 수. 백분율이다
PERCENT = 100


class Way(enum.StrEnum):
    """움직인 까닭."""

    HUNT = 'hunt'
    ROAM = 'roam'


@dataclass(frozen=True)
class Roamed:
    """한 마리가 움직인 것. 온 곳(origin)과 까닭(way)이다. 간 곳은 마리의 지금 자리다."""

    monster: SceneMonster
    origin: uuid.UUID
    way: Way


def passable(table: GameTable, route: RouteSnapshot, locked: frozenset[uuid.UUID]) -> bool:
    """
    몬스터가 지날 수 있는 길인가. 넘기 판정이 없고, 잠기지 않았고, 빗장이 걸리지 않았고,
    아직 열리지 않은 장의 장소에 닿지 않아야 한다.
    """
    if route.cross is not None or locked & {route.from_place, route.to_place}:
        return False
    return not route_locks.is_locked(table, route) and not route_locks.is_barred(table, route)


def walkable_routes(snapshot: Snapshot, table: GameTable) -> list[RouteSnapshot]:
    """몬스터가 지날 수 있는 판의 길들. 판의 길 순서다."""
    locked = chapters.locked_ids(table)
    return [route for route in snapshot.routes if passable(table, route, locked)]


def next_places(routes: list[RouteSnapshot], place_id: uuid.UUID) -> list[uuid.UUID]:
    """그 장소에서 한 칸에 갈 수 있는 장소들. 길 순서이고 겹치지 않는다. 한쪽으로만 가는 길은 그쪽으로만 간다."""
    found: list[uuid.UUID] = []
    for route in routes:
        there = None
        if route.from_place == place_id:
            there = route.to_place
        elif route.two_way and route.to_place == place_id:
            there = route.from_place
        if there is not None and there not in found:
            found.append(there)
    return found


def walk(routes: list[RouteSnapshot], start: uuid.UUID, limit: int) -> dict[uuid.UUID, uuid.UUID | None]:
    """
    start 에서 limit 칸 안에 갈 수 있는 장소마다 그곳에 가는 가장 짧은 길의 바로 앞 장소. start 는 None 이다.

    넓이 우선이라 사전의 순서는 가까운 순서이고, 같은 거리는 길 순서다.
    """
    before: dict[uuid.UUID, uuid.UUID | None] = {start: None}
    frontier = deque([(start, 0)])
    while frontier:
        here, steps = frontier.popleft()
        if steps == limit:
            continue
        for there in next_places(routes, here):
            if there not in before:
                before[there] = here
                frontier.append((there, steps + 1))
    return before


def first_step(before: dict[uuid.UUID, uuid.UUID | None], start: uuid.UUID, goal: uuid.UUID) -> uuid.UUID:
    """start 에서 goal 로 가는 가장 짧은 길의 첫 칸. goal 은 walk 가 찾은 곳이고 start 가 아니다."""
    step = goal
    while before[step] != start:
        step = before[step]
    return step


def hunt_step(
    routes: list[RouteSnapshot], here: uuid.UUID, reach: int | None, occupied: set[uuid.UUID]
) -> uuid.UUID | None:
    """사냥하는 한 칸. reach 칸 안의 가장 가까운 캐릭터가 선 곳으로 간다. 사냥하지 않거나 없으면 None."""
    if reach is None:
        return None
    before = walk(routes, here, reach)
    goal = next((place for place in before if place != here and place in occupied), None)
    return first_step(before, here, goal) if goal is not None else None


def roam_step(routes: list[RouteSnapshot], monster: SceneMonster, dice: Dice) -> uuid.UUID | None:
    """
    배회하는 한 칸. 확률을 굴려 들면 처음 자리에서 reach 칸 안인 이웃 하나로 간다. 배회하지 않거나 안 들면 None.

    갈 곳이 없어도 확률은 굴린다(굴림의 수가 마리의 자리에 따라 달라지지 않게).
    """
    roams = monster.definition.roams
    if roams is None or dice.roll(PERCENT) > roams.chance:
        return None
    near_home = walk(routes, monster.state.home_place_id, roams.reach)
    options = [place for place in next_places(routes, monster.state.place_id) if place in near_home]
    return choose(options, dice) if options else None


def is_idle(ruleset: Ruleset, monster: SceneMonster, fought: set[uuid.UUID], occupied: set[uuid.UUID]) -> bool:
    """이번 라운드에 싸우지 않았고 움직일 수 있는 마리인가. 장면에 없었고 지금 자리에 캐릭터가 없어야 한다."""
    state = monster.state
    if state.status != NpcStatus.ALIVE or state.id in fought or state.place_id in occupied:
        return False
    return not round_injuries.is_incapacitated(ruleset, state.injuries)


def moves(monster: SceneMonster) -> bool:
    """사냥하거나 배회하는 몬스터인가. 시트에 적었어야 한다."""
    return monster.definition.hunts is not None or monster.definition.roams is not None


def step_of(
    routes: list[RouteSnapshot], monster: SceneMonster, occupied: set[uuid.UUID], dice: Dice
) -> tuple[uuid.UUID, Way] | None:
    """이 마리가 갈 한 칸과 그 까닭. 사냥을 먼저 보고, 없으면 배회한다. 가지 않으면 None."""
    hunted = hunt_step(routes, monster.state.place_id, monster.definition.hunts, occupied)
    if hunted is not None:
        return hunted, Way.HUNT
    roamed = roam_step(routes, monster, dice)
    return (roamed, Way.ROAM) if roamed is not None else None


def any_mover(scene: Scene) -> bool:
    """판을 읽기 전에 볼 것. 장면 밖에 살아 있는 마리가 있는가(없으면 움직일 것이 없다)."""
    fought = {monster.state.id for monster in scene.monsters}
    return any(state.status == NpcStatus.ALIVE and state.id not in fought for state in scene.all_monsters)


def settle(table: GameTable, scene: Scene, dice: Dice) -> list[Roamed]:
    """
    싸우지 않는 마리들을 움직인다. 움직인 것들을 돌려준다. 판의 몬스터 순서, 그 안의 번호 순서로 본다.

    맵이 없는 판이거나 장면 밖에 살아 있는 마리가 없으면 판을 읽지 않고 빈 목록이다.
    """
    if not any_mover(scene):
        return []
    snapshot = read_snapshot(table.content)
    if not has_map(snapshot):
        return []
    fought = {monster.state.id for monster in scene.monsters}
    occupied = occupied_places(table)
    ruleset = snapshot.rulebook.rules
    routes = walkable_routes(snapshot, table)
    roamed: list[Roamed] = []
    for monster in every_monster(snapshot, scene.all_monsters):
        if not moves(monster) or not is_idle(ruleset, monster, fought, occupied):
            continue
        step = step_of(routes, monster, occupied, dice)
        if step is None:
            continue
        origin = monster.state.place_id
        monster.state.place_id = step[0]
        roamed.append(Roamed(monster=monster, origin=origin, way=step[1]))
    return roamed


def arrivals(table: GameTable, roamed: list[Roamed]) -> list[Roamed]:
    """캐릭터가 선 곳에 들어온 움직임. 플레이어에게 보이는 것은 이것뿐이다."""
    occupied = occupied_places(table)
    return [one for one in roamed if one.monster.state.place_id in occupied]


def place_document(snapshot: Snapshot, known: places.KnownMap | None, place_id: uuid.UUID) -> dict | None:
    """결과에 적을 장소. 항목의 ID 와 이름이다. 테이블이 모르는 장소면 None(드러나면 안 된다)."""
    if known is None or not known.has(place_id):
        return None
    names = {entry.id: entry.name for entry in place_entries(snapshot)}
    return {'entry_id': str(place_id), 'name': names.get(place_id, '')}


def arrival_document(snapshot: Snapshot, table: GameTable, one: Roamed, round_number: int) -> dict:
    """들어온 움직임의 이벤트 문서. 마리, 까닭, 온 곳(모르면 None), 간 곳이다."""
    known = places.known_map(snapshot, places.knowledge(table))
    return {
        'round': round_number,
        'monster_id': str(one.monster.state.id),
        'name': one.monster.name,
        'way': one.way,
        'from_place': place_document(snapshot, known, one.origin),
        'to_place': place_document(snapshot, known, one.monster.state.place_id),
    }


def documents(table: GameTable, roamed: list[Roamed], round_number: int) -> list[dict]:
    """보이는 움직임(arrivals)마다의 문서. 없으면 판을 읽지 않는다."""
    seen = arrivals(table, roamed)
    if not seen:
        return []
    snapshot = read_snapshot(table.content)
    return [arrival_document(snapshot, table, one, round_number) for one in seen]


def record(session: AsyncSession, table: GameTable, arrived: list[dict], group: uuid.UUID) -> None:
    """들어온 움직임마다 이벤트를 적는다(monster_roamed). 닫힘의 묶음에 넣는다. 행한 사람은 없다(엔진이 정했다)."""
    for payload in arrived:
        recorder.record(session, table, EventType.MONSTER_ROAMED, payload=payload, group=group)
