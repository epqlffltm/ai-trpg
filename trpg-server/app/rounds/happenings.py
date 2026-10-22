# trpg-server/app/rounds/happenings.py

"""
판의 사건 규칙(#367). 라운드가 닫힐 때 조건이 채워진 사건을 한 번 일으켜 효과를 낸다.

방장이 캐릭터를 손으로 옮기던 것(잡혀 끌려감, 함정, 휩쓸림)을 판이 미리 적은 규칙으로 엔진이 한다.
방장은 PC 라서 결과를 정하지 않고, AI 는 상태를 바꾸지 못한다.
  - 조건(when)과 맞추는 법(match)은 퀘스트의 것과 같다(app/rounds/quest_goals.py 의 all_met). 지금의 상태로 본다.
  - 한 번만 일어난다. 일어난 것은 테이블에 적는다(table_happenings). 다시 채워져도 일어나지 않는다.
  - 효과는 지금 옮기기(move) 하나다. 모두이거나(from_place 가 없다) 그 장소에 서 있던 죽지 않은 캐릭터를
    to_place 로 옮긴다. 쓰러진 캐릭터도 옮겨진다(끌려간다). 죽은 캐릭터는 쓰러진 곳에 남는다.
    길로 이어져 있지 않아도 된다. 옮겨진 곳은 서 본 곳이 된다. 이미 그곳에 있던 사람은 옮겼다고 적지 않는다.
  - 판의 순서로 하나씩 본다. 앞 사건이 옮긴 위치를 뒤 사건이 본다.
  - 라운드가 닫힐 때 퀘스트를 본 뒤, 기한을 보기 전에 본다(app/rounds/service.py 의 begin_closing).
    퀘스트의 성공과 실패로 일어나는 사건이 같은 라운드에 일어난다. 사건이 옮긴 곳에 닿아 이루는 퀘스트는
    다음 라운드가 닫힐 때 본다.

DB 를 모른다. 시트의 위치와 테이블의 서 본 곳, 일어난 사건의 줄을 고친다. 저장과 이벤트는 부른 쪽이 한다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import HappeningEffectKind
from app.assets.scenarios.snapshot import (
    HappeningEffectSnapshot,
    HappeningSnapshot,
    Snapshot,
    quest_entries,
    read_snapshot,
)
from app.events import recorder
from app.events.models import EventType
from app.rounds.quest_goals import all_met
from app.tables import places, sheets
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


def apply_effect(table: GameTable, snapshot: Snapshot, effect: HappeningEffectSnapshot) -> list[dict]:
    """효과 하나를 낸다. 옮긴 것들을 돌려준다. 종류는 지금 옮기기 하나다."""
    if effect.kind == HappeningEffectKind.MOVE:
        return move_all(table, snapshot, effect)
    return []


def entry_name(snapshot: Snapshot, entry_id: uuid.UUID) -> str:
    """사건 항목의 이름."""
    return next(entry.name for entry in quest_entries(snapshot) if entry.id == entry_id)


def happen(table: GameTable, snapshot: Snapshot, rule: HappeningSnapshot, round_number: int) -> dict:
    """
    사건 하나를 일으킨다. 효과를 차례로 내고, 일어났다고 테이블에 적는다. 이벤트에 적을 모양을 돌려준다.
    """
    moves = [move for effect in rule.effects for move in apply_effect(table, snapshot, effect)]
    table.happenings.append(
        TableHappening(table_id=table.id, entry_id=rule.entry_id, round_number=round_number, moves=moves)
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
            occurred.append(happen(table, snapshot, rule, round_number))
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
