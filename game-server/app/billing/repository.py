# game-server/app/billing/repository.py

"""
청구 기록을 읽고 쓴다. 저장(commit)은 부른 쪽이 한다.

상태를 바꾸는 것은 move 하나다. "지금 이 상태일 때만 바꾼다"를 UPDATE 의 조건으로 건다(compare-and-set).
결제 서버를 부르는 동안에는 잠금을 쥐지 않으므로, 그사이에 다른 쪽(서술 작업, 정리 작업, 다른 서버)이
먼저 상태를 옮겼을 수 있다. 그러면 조건이 맞지 않아 아무것도 바꾸지 않고 False 다. 먼저 옮긴 쪽이 이긴다.
"""

import uuid
from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.billing.models import DUE_STATUSES, OPEN_STATUSES, ChargeStatus, NarrationCharge
from app.rounds.models import Round
from app.tables.models import GameTable, TableMember, TableStatus


def add_charges(session: AsyncSession, charges: list[NarrationCharge]) -> None:
    """청구들을 더한다. 저장하지는 않는다."""
    session.add_all(charges)


async def find_round_charges(session: AsyncSession, table_id: uuid.UUID, number: int) -> list[NarrationCharge]:
    """테이블의 이 라운드의 청구들. 이 기록이 생기기 전에 연 라운드면 빈 목록이다."""
    query = (
        select(NarrationCharge)
        .join(Round, Round.id == NarrationCharge.round_id)
        .where(Round.table_id == table_id, Round.number == number)
        .order_by(NarrationCharge.created_at, NarrationCharge.id)
    )
    return list(await session.scalars(query))


async def find_round_payers(
    session: AsyncSession, round_id: uuid.UUID, statuses: tuple[ChargeStatus, ...]
) -> list[uuid.UUID]:
    """라운드의 청구 중 statuses 의 상태인 것의 내는 사람들. 청구를 만든 차례다."""
    query = (
        select(NarrationCharge.payer_id)
        .where(NarrationCharge.round_id == round_id, NarrationCharge.status.in_(statuses))
        .order_by(NarrationCharge.created_at, NarrationCharge.id)
    )
    return list(await session.scalars(query))


async def find_seated(session: AsyncSession, table_id: uuid.UUID) -> set[uuid.UUID]:
    """테이블에 지금 앉아 있는 사람들."""
    return set(await session.scalars(select(TableMember.user_id).where(TableMember.table_id == table_id)))


def has_charge(statuses: tuple[ChargeStatus, ...]) -> ColumnElement[bool]:
    """라운드에 statuses 의 상태인 청구가 있다는 조건."""
    return exists().where(NarrationCharge.round_id == Round.id, NarrationCharge.status.in_(statuses))


async def find_waiting_table_ids(
    session: AsyncSession,
    now: datetime,
    waited_for: tuple[ChargeStatus, ...],
    payable: tuple[ChargeStatus, ...],
    limit: int,
) -> list[uuid.UUID]:
    """
    크레딧이 모자란 사람을 기다리는 시간이 지난 라운드의 테이블들. 오래 기다린 것부터 limit 개.

    서술이 실패한 채 닫히지 않은 진행 중인 테이블의 라운드 중에서, 모자란 청구(waited_for)와 낼 수 있는 청구(payable)가
    함께 있고, 실패한 때부터 테이블의 기다리는 시간이 지난 것이다. 잠그지 않는다. 고른 뒤 테이블을 잠그고 다시 본다.
    색인(ix_table_rounds_failed)이 서술이 실패한 채 닫히지 않은 라운드만 담는다.
    """
    deadline = Round.narration_failed_at + func.make_interval(0, 0, 0, 0, 0, 0, GameTable.credit_wait_seconds)
    query = (
        select(Round.table_id)
        .join(GameTable, GameTable.id == Round.table_id)
        .where(
            Round.narration_failed_at.is_not(None),
            Round.closed_at.is_(None),
            GameTable.status == TableStatus.PLAYING,
            deadline <= now,
            has_charge(waited_for),
            has_charge(payable),
        )
        .order_by(Round.narration_failed_at)
        .limit(limit)
    )
    return list(await session.scalars(query))


async def find_round_of(session: AsyncSession, charge: NarrationCharge) -> tuple[uuid.UUID, int]:
    """청구가 속한 라운드의 테이블과 번호."""
    row = (await session.execute(select(Round.table_id, Round.number).where(Round.id == charge.round_id))).one()
    return row.table_id, row.number


async def find_due(session: AsyncSession, now: datetime, limit: int) -> list[NarrationCharge]:
    """결제 서버를 부를 차례가 된 청구들. 오래 기다린 것부터. 잠그지 않는다."""
    query = (
        select(NarrationCharge)
        .where(NarrationCharge.status.in_(DUE_STATUSES), NarrationCharge.next_attempt_at <= now)
        .order_by(NarrationCharge.next_attempt_at, NarrationCharge.id)
        .limit(limit)
    )
    return list(await session.scalars(query))


def ended_rounds() -> ColumnElement[bool]:
    """끝난 테이블의 라운드라는 조건."""
    ended = (
        select(Round.id).join(GameTable, GameTable.id == Round.table_id).where(GameTable.status == TableStatus.ENDED)
    )
    return NarrationCharge.round_id.in_(ended)


async def release_abandoned(session: AsyncSession, now: datetime) -> int:
    """
    끝난 테이블의 끝나지 않은 청구(걸어야 함, 걸림, 모자람)를 모두 "돌려줄 것"으로 바꾼다. 바꾼 수를 돌려준다.

    끝난 테이블의 서술은 다음 장면이 되지 않는다(app/rounds/service.py 의 finish_closing). 받을 까닭이 없다.
    모자람(short)도 넣는다. 결제 서버에 홀드가 없을 것이지만, 돌려주기는 없는 홀드에도 해가 없다.
    """
    statement = (
        update(NarrationCharge)
        .where(NarrationCharge.status.in_(OPEN_STATUSES), ended_rounds())
        .values(status=ChargeStatus.RELEASE_DUE, next_attempt_at=now, attempts=0, last_error=None)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).rowcount


def unfinished_rounds(table_id: uuid.UUID, still_open: bool) -> ColumnElement[bool]:
    """
    이 테이블의 닫히지 않은 라운드라는 조건. still_open 이면 그중 선언을 받는 중인 것(닫기 시작하기 전)만.
    """
    rounds = select(Round.id).where(Round.table_id == table_id, Round.closed_at.is_(None))
    if still_open:
        rounds = rounds.where(Round.closing_at.is_(None))
    return NarrationCharge.round_id.in_(rounds)


async def release_departed(
    session: AsyncSession,
    table_id: uuid.UUID,
    payer_id: uuid.UUID,
    always: tuple[ChargeStatus, ...],
    while_open: tuple[ChargeStatus, ...],
    now: datetime,
) -> int:
    """
    떠난 사람의 닫히지 않은 라운드의 청구를 "돌려줄 것"으로 바꾼다. 바꾼 수를 돌려준다.

    always 의 상태는 라운드가 닫는 중이어도 바꾸고, while_open 의 상태는 라운드가 선언을 받는 중일 때만 바꾼다.
    """
    statement = (
        update(NarrationCharge)
        .where(
            NarrationCharge.payer_id == payer_id,
            or_(
                and_(NarrationCharge.status.in_(always), unfinished_rounds(table_id, still_open=False)),
                and_(NarrationCharge.status.in_(while_open), unfinished_rounds(table_id, still_open=True)),
            ),
        )
        .values(status=ChargeStatus.RELEASE_DUE, next_attempt_at=now, attempts=0, last_error=None)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).rowcount


async def move(
    session: AsyncSession,
    charge_id: uuid.UUID,
    allowed: tuple[ChargeStatus, ...],
    to: ChargeStatus,
    **values: object,
) -> bool:
    """
    청구가 allowed 의 상태일 때만 to 로 옮긴다. 옮겼으면 True. values 는 함께 고칠 칸이다(attempts, last_error …).

    읽어 둔 객체는 고치지 않는다. 바뀐 것은 다시 읽어서 본다.
    """
    statement = (
        update(NarrationCharge)
        .where(NarrationCharge.id == charge_id, NarrationCharge.status.in_(allowed))
        .values(status=to, **values)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).rowcount == 1


async def move_round(
    session: AsyncSession, round_id: uuid.UUID, allowed: tuple[ChargeStatus, ...], to: ChargeStatus, now: datetime
) -> int:
    """라운드의 청구 중 allowed 의 상태인 것을 모두 to 로 옮기고 정리 작업이 바로 부르게 한다. 옮긴 수."""
    statement = (
        update(NarrationCharge)
        .where(NarrationCharge.round_id == round_id, NarrationCharge.status.in_(allowed))
        .values(status=to, next_attempt_at=now, attempts=0, last_error=None)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).rowcount


async def has_failed_with(session: AsyncSession, round_id: uuid.UUID, errors: tuple[str, ...]) -> bool:
    """라운드의 청구 중 errors 의 까닭으로 실패한(failed) 것이 있는가."""
    query = select(
        exists().where(
            NarrationCharge.round_id == round_id,
            NarrationCharge.status == ChargeStatus.FAILED,
            NarrationCharge.last_error.in_(errors),
        )
    )
    return bool(await session.scalar(query))


async def reprice_round(
    session: AsyncSession, round_id: uuid.UUID, allowed: tuple[ChargeStatus, ...], price_code: str, now: datetime
) -> int:
    """
    라운드의 청구 중 allowed 의 상태인 것을 새 가격표로 다시 걸게 돌려줄 것(release_due)으로 옮긴다. 옮긴 수.

    옛 이름표의 홀드는 정리 작업이 돌려준다(걸린 적이 없으면 결제 서버가 404 로 답하고 된 것으로 본다).
    그 뒤 서술 전에 새 이름표, 새 가격표로 다시 건다(app/billing/settling.py 의 restore).
    """
    statement = (
        update(NarrationCharge)
        .where(NarrationCharge.round_id == round_id, NarrationCharge.status.in_(allowed))
        .values(
            status=ChargeStatus.RELEASE_DUE,
            price_code=price_code,
            next_attempt_at=now,
            attempts=0,
            last_error=None,
            held_credits=None,
        )
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(statement)).rowcount
