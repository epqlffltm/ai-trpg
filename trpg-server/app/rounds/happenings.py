# trpg-server/app/rounds/happenings.py

"""
판의 사건 규칙(#367). 라운드가 닫힐 때 조건이 채워진 사건을 한 번 일으켜 효과를 낸다.

방장이 캐릭터를 손으로 옮기던 것(잡혀 끌려감, 함정, 휩쓸림)을 판이 미리 적은 규칙으로 엔진이 한다.
방장은 PC 라서 결과를 정하지 않고, AI 는 상태를 바꾸지 못한다.
  - 조건(when)과 맞추는 법(match)은 퀘스트의 것과 같다(app/rounds/quest_goals.py 의 all_met). 지금의 상태로 본다.
  - 한 번만 일어난다. 일어난 것은 테이블에 적는다(table_happenings). 다시 채워져도 일어나지 않는다.
  - 효과는 캐릭터 옮기기(move)와 인물 옮기기(move_npc, #282), 길의 문 다루기(#281)다.
    move 는 모두이거나(from_place 가 없다) 그 장소에 서 있던 죽지 않은 캐릭터를 to_place 로 옮긴다.
    쓰러진 캐릭터도 옮겨진다(끌려간다). 죽은 캐릭터는 쓰러진 곳에 남는다.
    길로 이어져 있지 않아도 된다. 옮겨진 곳은 서 본 곳이 된다. 이미 그곳에 있던 사람은 옮겼다고 적지 않는다.
    move_npc 는 인물 하나의 자리를 to_place 로 바꾼다. 쓰러진 인물도 옮겨지고, 죽은 인물은 남는다.
    자리가 없던 인물이면 그 뒤로 자리가 있는 인물이 된다(장면의 글이 아니라 장소로 장면에 든다, app/rounds/cast.py).
    이미 그곳에 있던 인물은 옮겼다고 적지 않는다. 옮긴 인물은 이벤트에 적지 않는다(NPC 의 상태는 이벤트에 적지 않는다).
    그 라운드의 서술은 일행이 본 것만 받는다(app/rounds/narration_request.py).
  - 길의 문을 다루는 효과(#281): lock_route 는 잠그고, unlock_route 는 열고, repair_route 는 부서진 문을 고친다.
    NPC 와 몬스터가 문을 다루는 것을 판이 이것으로 적는다. 열쇠도 서 있는 쪽도 보지 않는다.
    장치(device)를 적었으면 그것만, 비웠으면 그 문의 장치 모두다.
    부서진 문은 잠그지 않는다(고치는 효과가 앞서야 한다).
    고친 문은 열린 채다. 이미 그렇게 되어 있는 장치는 적지 않는다. 문의 상태가 없는 테이블(문이 생기기 전에 시작)이면
    아무것도 하지 않는다. 다룬 문은 이벤트에 적지 않는다. 길의 상태는 테이블을 읽으면 보이고(아는 길만),
    서술은 일행이 그 길의 끝에 있을 때만 받는다.
  - 판의 순서로 하나씩 본다. 앞 사건이 옮긴 위치를 뒤 사건이 본다.
  - 라운드가 닫힐 때 퀘스트를 본 뒤, 기한을 보기 전에 본다(app/rounds/service.py 의 begin_closing).
    퀘스트의 성공과 실패로 일어나는 사건이 같은 라운드에 일어난다. 사건이 옮긴 곳에 닿아 이루는 퀘스트는
    다음 라운드가 닫힐 때 본다.

DB 를 모른다. 시트의 위치와 테이블의 서 본 곳, 인물의 자리, 길의 문, 일어난 사건의 줄을 고친다.
저장과 이벤트는 부른 쪽이 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import HappeningEffectKind
from app.assets.scenarios.snapshot import (
    ROUTE_EFFECTS,
    HappeningEffectSnapshot,
    HappeningSnapshot,
    RouteSnapshot,
    Snapshot,
    door_devices,
    quest_entries,
    read_snapshot,
    route_between,
)
from app.engine.action import DoorDevice
from app.events import recorder
from app.events.models import EventType
from app.rounds.quest_goals import all_met
from app.tables import npcs as table_npcs
from app.tables import places, route_locks, sheets
from app.tables.models import GameTable, TableHappening, TableMember, TableMonster, TableNpc


def may_happen(table: GameTable) -> bool:
    """
    이 테이블의 판에 사건 규칙이 있는가. 판을 통째로 읽지 않고 문서의 칸만 본다.

    판을 읽는 것은 싸지 않다. 라운드마다 닫힐 때 부르므로 사건이 없는 판(대부분, 형식 44 보다 옛 판)은 여기서 끝낸다.
    """
    return bool(table.content.get('happenings'))


def happened(table: GameTable) -> set[uuid.UUID]:
    """이 테이블에서 이미 일어난 사건들."""
    return {row.entry_id for row in table.happenings}


def movers(table: GameTable, effect: HappeningEffectSnapshot) -> list[TableMember]:
    """
    옮기기의 효과가 옮길 사람들. 앉은 순서다.

    맵에 서 있는 죽지 않은 캐릭터다. from_place 가 있으면 그 장소에 서 있던 사람만이다.
    """
    return [
        member
        for member in table.members
        if member.sheet is not None
        and member.sheet.place_id is not None
        and not sheets.is_dead(member)
        and (effect.from_place is None or member.sheet.place_id == effect.from_place)
    ]


def move_all(table: GameTable, snapshot: Snapshot, effect: HappeningEffectSnapshot) -> list[dict]:
    """
    옮기기의 효과를 낸다. 옮긴 사람마다 이벤트에 적을 모양(누가, 어디에서, 어디로)을 돌려준다.

    이미 그곳에 있는 사람은 옮기지 않고 적지 않는다.
    """
    moves = []
    for member in movers(table, effect):
        previous = member.sheet.place_id
        if previous == effect.to_place:
            continue
        places.stand(table, member.sheet, effect.to_place)
        moves.append(places.describe_move(snapshot, member, previous, effect.to_place))
    return moves


def move_npc(npc: TableNpc | None, effect: HappeningEffectSnapshot) -> dict | None:
    """
    인물 옮기기의 효과를 낸다. 옮겼으면 적을 모양(누구, 어디에서, 어디로)을, 아니면 None 을 돌려준다.

    상태가 없는 인물(이 기능 전에 시작한 테이블), 죽은 인물, 이미 그곳에 있는 인물은 옮기지 않는다.
    """
    if npc is None or table_npcs.is_dead(npc) or npc.place_id == effect.to_place:
        return None
    previous = npc.place_id
    npc.place_id = effect.to_place
    return {
        'entry_id': str(npc.entry_id),
        'from': str(previous) if previous is not None else None,
        'to': str(effect.to_place),
    }


def character_moves(table: GameTable, snapshot: Snapshot, rule: HappeningSnapshot) -> list[dict]:
    """사건 하나의 캐릭터 옮기기(move)를 차례로 낸다. 옮긴 사람들을 돌려준다."""
    return [
        move
        for effect in rule.effects
        if effect.kind == HappeningEffectKind.MOVE
        for move in move_all(table, snapshot, effect)
    ]


def npc_moves(npcs: list[TableNpc], rule: HappeningSnapshot) -> list[dict]:
    """사건 하나의 인물 옮기기(move_npc)를 차례로 낸다. 옮긴 인물들을 돌려준다."""
    states = {npc.entry_id: npc for npc in npcs}
    moved = [
        move_npc(states.get(effect.npc), effect)
        for effect in rule.effects
        if effect.kind == HappeningEffectKind.MOVE_NPC
    ]
    return [move for move in moved if move is not None]


def effect_devices(route: RouteSnapshot, effect: HappeningEffectSnapshot) -> list[DoorDevice]:
    """문을 잠그고 여는 효과가 다룰 장치들. 적었으면 그것만, 비웠으면 그 문의 장치 모두(자물쇠, 빗장의 차례)다."""
    return [effect.device] if effect.device is not None else door_devices(route)


def set_device(table: GameTable, route: RouteSnapshot, device: DoorDevice, shut: bool) -> bool:
    """
    문의 장치 하나를 잠그거나(shut 참) 연다. 바꿨으면 참이다.

    이미 그렇게 되어 있으면 그대로 둔다. 부서진 문은 잠그지 않는다.
    """
    if shut and route_locks.is_broken(table, route):
        return False
    if route_locks.is_shut(table, route, device) == shut:
        return False
    route_locks.set_shut(table, route, device, shut)
    return True


def repair_door(table: GameTable, route: RouteSnapshot) -> bool:
    """부서진 문을 고친다. 열린 채다. 고쳤으면 참, 부서지지 않은 문이면 그대로 두고 거짓이다."""
    if not route_locks.is_broken(table, route):
        return False
    route_locks.repair(table, route)
    return True


def door_change(effect: HappeningEffectSnapshot, act: str, device: DoorDevice | None) -> dict:
    """다룬 문 하나를 테이블의 줄에 적을 모양으로. 무엇을(act, device), 어느 길의(from, to, 장소의 ID)."""
    return {
        'act': act,
        'device': device,
        'from': str(effect.from_place),
        'to': str(effect.to_place),
    }


def change_door(table: GameTable, snapshot: Snapshot, effect: HappeningEffectSnapshot) -> list[dict]:
    """
    문을 다루는 효과 하나를 낸다. 바꾼 장치마다 적을 모양을 돌려준다(고치기는 하나).

    길은 판이 게시될 때 본 것이라 있다. 그 문의 상태가 없는 테이블(문이 생기기 전에 시작)이면 아무것도 하지 않는다.
    """
    route = route_between(snapshot, effect.from_place, effect.to_place)
    if route_locks.find_lock(table, route) is None:
        return []
    if effect.kind == HappeningEffectKind.REPAIR_ROUTE:
        return [door_change(effect, 'repair', None)] if repair_door(table, route) else []
    shut = effect.kind == HappeningEffectKind.LOCK_ROUTE
    act = 'lock' if shut else 'unlock'
    return [
        door_change(effect, act, device)
        for device in effect_devices(route, effect)
        if set_device(table, route, device, shut)
    ]


def door_changes(table: GameTable, snapshot: Snapshot, rule: HappeningSnapshot) -> list[dict]:
    """사건 하나의 문 다루기(#281)를 효과의 차례로 낸다. 앞의 고치기를 뒤의 잠그기가 본다. 다룬 문들을 돌려준다."""
    return [
        change
        for effect in rule.effects
        if effect.kind in ROUTE_EFFECTS
        for change in change_door(table, snapshot, effect)
    ]


def entry_name(snapshot: Snapshot, entry_id: uuid.UUID) -> str:
    """사건 항목의 이름."""
    return next(entry.name for entry in quest_entries(snapshot) if entry.id == entry_id)


def happen(
    table: GameTable, snapshot: Snapshot, rule: HappeningSnapshot, round_number: int, npcs: list[TableNpc]
) -> dict:
    """
    사건 하나를 일으킨다. 효과를 내고, 일어났다고 테이블에 적는다. 이벤트에 적을 모양을 돌려준다.

    캐릭터를 옮기고, 인물을 옮기고, 문을 다룬다(#281). 셋은 서로를 보지 않으므로 순서가 결과를 바꾸지 않는다.
    옮긴 인물과 다룬 문은 테이블의 줄에만 적고 이벤트의 모양에는 싣지 않는다.
    """
    moves = character_moves(table, snapshot, rule)
    moved_npcs = npc_moves(npcs, rule)
    doors = door_changes(table, snapshot, rule)
    table.happenings.append(
        TableHappening(
            table_id=table.id,
            entry_id=rule.entry_id,
            round_number=round_number,
            moves=moves,
            npc_moves=moved_npcs,
            doors=doors,
        )
    )
    return {
        'round': round_number,
        'entry_id': str(rule.entry_id),
        'name': entry_name(snapshot, rule.entry_id),
        'moves': moves,
    }


def settle_happenings(
    table: GameTable, round_number: int, monsters: list[TableMonster], npcs: list[TableNpc]
) -> list[dict]:
    """
    아직 일어나지 않은 사건 중 조건이 채워진 것을 판의 순서로 일으킨다. 일어난 차례로 이벤트의 모양을 돌려준다.

    monsters 와 npcs 는 테이블의 상태 전부다(장면 밖도). 사건 규칙이 없는 판이면 판을 읽지 않는다.
    """
    if not may_happen(table):
        return []
    snapshot = read_snapshot(table.content)
    done = happened(table)
    occurred = []
    for rule in snapshot.happenings:
        if rule.entry_id in done:
            continue
        if all_met(tuple(rule.when), rule.match, table, monsters, npcs):
            occurred.append(happen(table, snapshot, rule, round_number, npcs))
    return occurred


def record_happenings(session: AsyncSession, table: GameTable, occurred: list[dict], group: uuid.UUID) -> None:
    """
    일어난 사건마다 이벤트를 적는다. 닫힘의 묶음(group)에 넣는다. 행한 사람은 없다(엔진이 일으켰다).

    사건(happening_occurred) 뒤에 옮긴 사람마다 character_moved 를 잇는다. 어느 사건이 옮겼는지(happening)가 적힌다.
    """
    for payload in occurred:
        event = recorder.record(session, table, EventType.HAPPENING_OCCURRED, payload=payload, group=group)
        for move in payload['moves']:
            moved = {'round': payload['round'], **move, 'travel_minutes': None, 'happening': payload['entry_id']}
            recorder.record(session, table, EventType.CHARACTER_MOVED, payload=moved, cause=event)
