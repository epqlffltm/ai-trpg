# trpg-server/app/rounds/presence.py

"""
선언을 내지 않는 사람(자리 비움)을 센다(#1345). 오래 비운 사람에게는 서술 값을 걸지 않고, 더 오래 비우면 뺀다.

나가기를 누르지 않고 떠난 사람(탭 닫기, 앱 종료, 끊김)은 서버가 모른다. 그대로 앉은 사람이라
남은 사람이 플레이하는 동안 라운드마다 서술 값이 걸렸다(app/billing/charges.py 의 payers_of).
  - 세기(count): 라운드를 닫기 시작할 때. 기다렸는데 내지 않은 사람(waiting_for)은 하나 늘리고, 낸 사람은 0 으로 돌린다.
    기다리지 않은 사람(쓰러짐, 이번 라운드에 새 캐릭터를 들임, 차례대로 진행하는 테이블에서 차례가 아님)은 그대로 둔다.
    라운드를 닫은 방장은 낸 것으로 본다. 자리에 있다.
    아무도 내지 않아 멈춘 라운드(app/rounds/pauses.py)는 닫히지 않으므로 세지 않는다.
  - 값을 걸지 않기(app/tables/away.py 의 is_away): 연속 AWAY_ROUNDS 번 내지 않았으면 다음 라운드부터 값을 걸지 않는다.
    자리는 그대로다.
    돌아와 선언하면 그 라운드는 값 없이 받고, 닫힐 때 0 으로 돌아가 다음 라운드부터 다시 건다.
  - 빼기(remove_away): 연속 REMOVE_ROUNDS 번 내지 않았으면 나가기와 같이 뺀다(떠난 길 away). 방장이면 방장을 넘긴다.
    빼면 앉은 사람이 없어지면 빼지 않는다. 테이블을 끝내는 것은 사람이 한다.
  - 둘 다 이벤트로 남긴다(member_away, member_away_removed). 왜 값이 안 걸렸는지, 누가 빠졌는지 모두 본다.
센 수는 테이블의 행(away_counts)에 둔다. 닫기 직전의 사진에 함께 찍혀 되돌리면 같이 돌아간다(app/rounds/snapshots.py).

세기는 DB 를 모른다. 빼기는 떠나는 일(청구 돌려주기, 떠난 사람 적기)을 부르지만 저장은 부른 쪽이 한다.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import charges
from app.events import recorder
from app.events.models import EventType
from app.rounds.models import Round
from app.rounds.state import waiting_for
from app.tables import departures
from app.tables.away import AWAY_ROUNDS, REMOVE_ROUNDS, missed
from app.tables.models import DepartureKind, GameTable, TableMember
from app.tables.seating import hand_over as hand_over_host
from app.tables.seating import record_hand_over


def count(table: GameTable, round_: Round, closer_id: uuid.UUID | None) -> list[TableMember]:
    """
    닫기 시작하는 라운드에서 내지 않은 수를 센다. 이번에 막 자리 비움이 된 사람들을 돌려준다(이벤트를 적을 몫).

    테이블의 칸을 통째로 바꾼다. JSON 칸 안을 고치면 SQLAlchemy 가 바뀐 줄 모른다.
    """
    idle = set(waiting_for(table, round_)) - ({closer_id} if closer_id is not None else set())
    declared = {declaration.user_id for declaration in round_.declarations}
    counts = dict(table.away_counts)
    newly_away = []
    for member in table.members:
        key = str(member.user_id)
        if member.user_id in idle:
            counts[key] = counts.get(key, 0) + 1
            if counts[key] == AWAY_ROUNDS:
                newly_away.append(member)
        elif member.user_id in declared or member.user_id == closer_id:
            counts.pop(key, None)
    table.away_counts = counts
    return newly_away


def record_away(
    session: AsyncSession, table: GameTable, round_: Round, members: list[TableMember], group: uuid.UUID
) -> None:
    """
    막 자리 비움이 된 사람마다 이벤트를 적는다. 다음 라운드부터 그 사람의 서술 값을 걸지 않는다.
    닫힘의 묶음(group)에 넣는다. 되돌리면 센 수와 함께 없던 일이 된다.
    """
    for member in members:
        recorder.record(session, table, EventType.MEMBER_AWAY, payload=member_payload(round_, member), group=group)


def to_remove(table: GameTable) -> list[TableMember]:
    """빼야 할 사람들. 연속 REMOVE_ROUNDS 번 내지 않았다. 모두 빼면 앉은 사람이 없어지면 아무도 빼지 않는다."""
    gone = [member for member in table.members if missed(table, member.user_id) >= REMOVE_ROUNDS]
    return gone if len(gone) < len(table.members) else []


async def remove_away(session: AsyncSession, table: GameTable, round_: Round) -> None:
    """오래 비운 사람들을 자리에서 뺀다. 나가기와 같다. 청구를 돌려주고 떠난 사람으로 적고 방장이면 넘긴다."""
    for member in to_remove(table):
        await remove_member(session, table, round_, member)


async def remove_member(session: AsyncSession, table: GameTable, round_: Round, member: TableMember) -> None:
    """한 사람을 뺀다. 센 수도 지운다."""
    table.members.remove(member)
    counts = dict(table.away_counts)
    counts.pop(str(member.user_id), None)
    table.away_counts = counts
    await charges.release_departed(session, table.id, member.user_id, datetime.now(UTC))
    removed = recorder.record(session, table, EventType.MEMBER_AWAY_REMOVED, payload=member_payload(round_, member))
    departures.record_departure(session, table, member, DepartureKind.AWAY, removed)
    if table.host_id == member.user_id:
        record_hand_over(session, table, hand_over_host(table), removed)


def member_payload(round_: Round, member: TableMember) -> dict:
    """자리 비움 이벤트의 칸. 어느 라운드에서, 누가."""
    return {'round': round_.number, 'user_id': str(member.user_id), 'character_name': member.character_name}
