# trpg-server/app/rounds/credit_waits.py

"""
크레딧이 모자란 사람을 기다린다(#181). 서버의 시계가 몇 초마다 부른다(app/rounds/clock.py).

앉은 사람 모두가 각자 내므로(#180) 한 사람이라도 모자라면 그 라운드는 서술하지 않는다(insufficient_credits).
그동안 낼 수 있는 사람의 값도 묶여 있다. 그래서 정해 둔 시간(테이블의 credit_wait_seconds, 기본 5분)만 기다린다.
서술이 실패한 때부터 센다. 그 안에 모자란 사람이 충전하거나 방장이 그 사람을 내보내면 방장이 다시 맡긴다.

시간이 지나면 테이블의 규칙(remove_short_payers)에 따라 둘 중 하나를 한다.
  - 켬(기본): 모자란 사람을 자리에서 빼고 나머지로 바로 다시 서술한다. 뺀 사람의 청구는 돌려준다.
    모자란 사람이 방장이면 방장을 넘긴다(나가기와 같다).
  - 끔: 낼 수 있는 사람의 값을 돌려준다(release_due). 라운드는 멈춘 채로 둔다.
    방장이 다시 맡기면 그때 앉아 있는 사람 모두에게 새 이름표로 다시 건다(app/billing/settling.py 의 restore).
앉은 사람 모두가 모자라면 아무것도 하지 않는다. 묶인 값이 없고, 모두 빼면 앉은 사람이 없어진다.

볼 때마다 테이블의 지금 규칙을 읽는다. 기다리는 동안 방장이 시간을 늘리거나 줄이면 그대로 따른다.
한 번 한 뒤에는 다시 하지 않는다. 뺐으면 모자란 청구가 없고, 돌려줬으면 낼 수 있는 청구가 없다.

찾을 때는 잠그지 않고, 하기 전에 테이블을 잠그고 다시 본다. 서버가 여럿이어도 한 번만 한다.
그사이 모자란 사람이 충전해 방장이 다시 맡겼으면(실패의 표시가 지워졌다) 할 일이 없다.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import charges
from app.billing import repository as billing_repository
from app.billing.models import ChargeStatus
from app.events import recorder
from app.events.models import EventType
from app.rounds import repository
from app.rounds.models import Round, RoundStatus
from app.rounds.service import NarrationScheduler, hand_over, save
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables.models import GameTable, TableMember, TableStatus
from app.tables.seating import hand_over as hand_over_host
from app.tables.seating import record_hand_over

# 기다리는 청구. 모자란 사람의 것이다
WAITED_FOR = (ChargeStatus.SHORT,)
# 낼 수 있는(또는 곧 걸릴) 청구. 기다리는 동안 묶여 있는 값이다
PAYABLE = (ChargeStatus.PENDING, ChargeStatus.HELD)


def wait_over(table: GameTable, round_: Round, now: datetime) -> bool:
    """서술이 실패한 때부터 테이블의 기다리는 시간이 지났는가."""
    failed_at = round_.narration_failed_at
    return failed_at is not None and failed_at + timedelta(seconds=table.credit_wait_seconds) <= now


async def lock_failed_round(session: AsyncSession, table_id: uuid.UUID) -> tuple[GameTable, Round] | None:
    """
    테이블을 잠그고, 서술이 실패한 채 닫는 중인 라운드를 찾는다.

    테이블이 없거나, 진행 중이 아니거나, 가장 최근 라운드가 그런 라운드가 아니면 None.
    """
    table = await table_repository.lock_table(session, table_id)
    if table is None or table.status != TableStatus.PLAYING:
        return None
    round_ = await repository.find_latest_round(session, table_id)
    if round_ is None or round_.status != RoundStatus.CLOSING or round_.narration_failed_at is None:
        return None
    return table, round_


def short_members(table: GameTable, short_ids: list[uuid.UUID]) -> list[TableMember]:
    """모자란 사람 중 아직 앉아 있는 사람들. 앉은 차례다."""
    wanted = set(short_ids)
    return [member for member in table.members if member.user_id in wanted]


def can_drop(table: GameTable, short: list[TableMember]) -> bool:
    """
    모자란 사람을 뺄 수 있는가. 규칙이 켜져 있고 뺄 사람이 있다.

    빼도 앉은 사람이 남는다. 낼 수 있는 청구가 있어야 여기 오고(is_waiting), 그 청구는 앉은 사람의 것이다.
    """
    return table.remove_short_payers and bool(short)


async def drop_member(session: AsyncSession, table: GameTable, round_: Round, member: TableMember) -> None:
    """
    모자란 사람 하나를 자리에서 뺀다. 그 사람의 청구를 돌려주고 이벤트로 알린다. 방장이면 방장을 넘긴다.

    그 사람의 선언은 닫기 시작할 때 굳었으므로 장면에는 들어간다. 값을 걸지 못했으니 받지 않는다.
    """
    table.members.remove(member)
    await charges.release_departed(session, table.id, member.user_id, datetime.now(UTC))
    payload = {'round': round_.number, 'user_id': str(member.user_id), 'character_name': member.character_name}
    dropped = recorder.record(session, table, EventType.MEMBER_DROPPED, payload=payload)
    if table.host_id == member.user_id:
        record_hand_over(session, table, hand_over_host(table), dropped)


def retry_narration(round_: Round) -> None:
    """라운드의 서술을 다시 맡길 수 있게 한다. 방장이 다시 맡길 때와 같다(service.force_close)."""
    round_.closing_at = datetime.now(UTC)
    round_.narration_failed_at = None


async def drop_short(
    session: AsyncSession, table: GameTable, round_: Round, short: list[TableMember], scheduler: NarrationScheduler
) -> None:
    """모자란 사람들을 빼고 나머지로 다시 서술한다. 저장하고 서술을 맡긴다."""
    for member in short:
        await drop_member(session, table, round_, member)
    retry_narration(round_)
    hand_over(scheduler, await save(session, table))


async def release_payable(session: AsyncSession, table: GameTable, round_: Round) -> None:
    """
    낼 수 있는 사람의 값을 돌려준다. 라운드는 멈춘 채로 둔다. 저장한다.

    결제 서버는 부르지 않는다. 정리 작업이 곧 돌려준다. 다시 맡기면 그때 다시 건다.
    """
    await billing_repository.move_round(session, round_.id, PAYABLE, ChargeStatus.RELEASE_DUE, datetime.now(UTC))
    recorder.record(session, table, EventType.NARRATION_CREDITS_RELEASED, payload={'round': round_.number})
    await tables.commit(session, table)


async def is_waiting(session: AsyncSession, table: GameTable, round_: Round, now: datetime) -> bool:
    """이 라운드가 크레딧을 기다리다 시간이 지났는가. 모자란 청구와 낼 수 있는 청구가 함께 있다."""
    if not wait_over(table, round_, now):
        return False
    short = await billing_repository.find_round_payers(session, round_.id, WAITED_FOR)
    payable = await billing_repository.find_round_payers(session, round_.id, PAYABLE)
    return bool(short) and bool(payable)


async def settle_credit_wait(
    session: AsyncSession, table_id: uuid.UUID, now: datetime, scheduler: NarrationScheduler
) -> bool:
    """
    크레딧을 기다리는 시간이 지난 라운드를 마무리한다. 했으면 True. 서버의 시계가 부른다.

    잠근 뒤에 다시 본다. 그사이 방장이 다시 맡겼거나, 모자란 사람이 떠났거나, 다른 서버가 먼저 했으면 할 일이 없다.
    """
    found = await lock_failed_round(session, table_id)
    if found is None or not await is_waiting(session, *found, now):
        # 잠금을 푼다. 바꾼 것이 없다
        await session.commit()
        return False
    table, round_ = found
    short = short_members(table, await billing_repository.find_round_payers(session, round_.id, WAITED_FOR))
    if can_drop(table, short):
        await drop_short(session, table, round_, short, scheduler)
    else:
        await release_payable(session, table, round_)
    return True
