# game-server/app/billing/settling.py

"""
청구 하나를 결제 서버에 맡기고, 그 결과로 청구의 상태를 옮긴다.

부르는 쪽은 둘이다. 서술을 맡은 작업(app/rounds/closing.py)과 정리 작업(app/billing/settler.py).
둘 다 같은 함수를 쓰고, 같은 청구를 동시에 불러도 된다.
  - 결제 서버는 같은 이름표를 한 번만 처리한다. 두 번 걸어도 한 번만 빠진다
  - 상태는 "지금 이 상태일 때만" 옮긴다(repository.move). 늦게 온 결과가 먼저 적힌 결과를 덮지 못한다.
    걸렸다(held)는 결과는 걸어야 함(pending)과 모자람(short) 어느 쪽에서든 옮긴다.
    결제 서버가 잡았다고 한 것이 가장 확실하다

결제 서버를 부르는 동안에는 세션을 열어 두지 않는다. 읽고 닫고, 부르고, 새 세션으로 적는다.

걸린 홀드는 만료되기 전에 연장한다(try_extend). 결제 서버에 홀드가 없거나(404) 만료되어 이미 돌려줬으면(409)
아직 서술 전이므로 다시 건다. 없으면 같은 이름표로, 돌려줬으면 새 이름표로(renew).
서술 뒤의 확정이 409 면 받지 못한다(failed).

로그는 공통 관측 규격을 따른다(docs/observability.md). operation 은 billing.hold, billing.capture, billing.release,
billing.extend 다.
답을 받지 못한 것은 warning(billing.unavailable), 서명이 거절된 것과 결제 서버가 받아들이지 않은 것은 error 다.
"""

import enum
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing import repository
from app.billing.charges import EXTEND_REJECTED_RETRY, next_extension, reference_for, retry_delay
from app.billing.client import Billing, BillingRejected, BillingUnavailable, ExtendResult, HoldResult
from app.billing.models import SECURED_STATUSES, ChargeStatus, NarrationCharge
from app.events import recorder
from app.events.models import EventType
from app.tables import repository as table_repository
from app.tables import service as tables

logger = logging.getLogger(__name__)

# 로그의 operation 과 오류 코드. 정해진 이름이다(docs/observability.md)
HOLD_OPERATION = 'billing.hold'
CAPTURE_OPERATION = 'billing.capture'
RELEASE_OPERATION = 'billing.release'
EXTEND_OPERATION = 'billing.extend'
UNAVAILABLE_ERROR_CODE = 'billing.unavailable'
REJECTED_ERROR_CODE = 'billing.rejected'


class Readiness(enum.StrEnum):
    """서술해도 되는가. 서술을 맡은 작업이 서술자를 부르기 전에 본다."""

    # 값을 잡아 두었다
    READY = 'ready'
    # 크레딧이 모자란다. 충전한 뒤 방장이 다시 맡기면 된다
    SHORT = 'insufficient_credits'
    # 결제 서버의 답을 받지 못했거나, 이 청구는 더 걸 수 없다(돌려줬다, 거절됐다)
    UNAVAILABLE = 'billing_unavailable'


def now_utc() -> datetime:
    """지금 시각(UTC)."""
    return datetime.now(UTC)


async def write_move(
    session_factory: async_sessionmaker[AsyncSession],
    charge: NarrationCharge,
    allowed: tuple[ChargeStatus, ...],
    to: ChargeStatus,
    **values: object,
) -> bool:
    """새 세션으로 상태를 옮기고 저장한다. 옮겼으면 True."""
    async with session_factory() as session:
        moved = await repository.move(session, charge.id, allowed, to, **values)
        await session.commit()
        return moved


def log_fields(charge: NarrationCharge, operation: str) -> dict[str, object]:
    """로그에 싣는 칸. 누가 내는지는 번호로, 무엇인지는 청구의 번호로 적는다."""
    return {'operation': operation, 'charge_id': str(charge.id), 'payer_id': str(charge.payer_id)}


async def note_unavailable(
    session_factory: async_sessionmaker[AsyncSession],
    charge: NarrationCharge,
    operation: str,
    error: BillingUnavailable,
    now: datetime,
) -> None:
    """답을 받지 못했다. 상태는 그대로 두고, 다시 부를 때를 늦춘다. 서명이 거절된 것은 설정의 문제라 오류로 남긴다."""
    attempts = charge.attempts + 1
    level = logging.ERROR if error.reason == 'unauthorized' else logging.WARNING
    logger.log(
        level,
        '결제 서버의 답을 받지 못했습니다',
        extra={
            **log_fields(charge, operation),
            'reason': error.reason,
            'attempts': attempts,
            'result': 'server_error',
            'error_code': UNAVAILABLE_ERROR_CODE,
        },
    )
    await write_move(
        session_factory,
        charge,
        (ChargeStatus(charge.status),),
        ChargeStatus(charge.status),
        attempts=NarrationCharge.attempts + 1,
        next_attempt_at=now + retry_delay(attempts),
        last_error=error.reason,
    )


async def note_rejected(
    session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, operation: str, error: BillingRejected
) -> None:
    """결제 서버가 받아들이지 않았다. 다시 불러도 같으므로 실패로 적고 오류로 남긴다. 사람이 봐야 한다."""
    logger.error(
        '결제 서버가 요청을 받아들이지 않았습니다',
        extra={
            **log_fields(charge, operation),
            'status_code': error.status_code,
            'result': 'server_error',
            'error_code': REJECTED_ERROR_CODE,
        },
    )
    await write_move(
        session_factory,
        charge,
        (ChargeStatus(charge.status),),
        ChargeStatus.FAILED,
        last_error=f'rejected_{error.status_code}',
    )


async def note_short(session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge) -> None:
    """
    크레딧이 모자란 것을 적는다. 처음 모자란 것을 알았을 때(걸어야 함 → 모자람)만 앉은 사람 모두에게 이벤트로 알린다.

    테이블을 잠그고 적는다. 이벤트의 번호를 매기는 일이 테이블의 잠금 아래에서만 일어난다.
    """
    async with session_factory() as session:
        table_id, number = await repository.find_round_of(session, charge)
        table = await table_repository.lock_table(session, table_id)
        moved = await repository.move(session, charge.id, (ChargeStatus.PENDING,), ChargeStatus.SHORT)
        if table is None or not moved:
            await session.commit()
            return
        recorder.record(session, table, EventType.NARRATION_CREDITS_SHORT, payload={'round': number})
        await tables.commit(session, table)


async def release_again(
    session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, now: datetime
) -> None:
    """
    걸고 왔더니 그사이 테이블이 끝나 돌려준 청구다. 방금 건 홀드가 반환보다 늦게 결제 서버에 닿았을 수 있다.

    돌려준 것(released)을 다시 돌려줄 것으로 되돌린다. 정리 작업이 한 번 더 돌려준다. 반환은 몇 번 해도 해가 없다.
    """
    await write_move(session_factory, charge, (ChargeStatus.RELEASED,), ChargeStatus.RELEASE_DUE, next_attempt_at=now)


async def reload(session_factory: async_sessionmaker[AsyncSession], charge_id: uuid.UUID) -> NarrationCharge:
    """청구를 새로 읽는다. 다른 쪽이 옮겼을 수 있다."""
    async with session_factory() as session:
        return await session.get_one(NarrationCharge, charge_id)


async def current_status(session_factory: async_sessionmaker[AsyncSession], charge_id: uuid.UUID) -> ChargeStatus:
    """청구의 지금 상태. 다른 쪽이 옮겼을 수 있어 새로 읽는다."""
    return ChargeStatus((await reload(session_factory, charge_id)).status)


async def after_lost_race(
    session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, now: datetime
) -> Readiness:
    """
    걸렸다고 적으려 했는데 다른 쪽이 먼저 상태를 옮겼다. 지금 상태를 보고 정한다.

    이미 잡혀 있으면(다른 쪽도 걸었다) 된 것이다. 돌려줄 것이 됐으면 방금 건 홀드도 돌려줘야 한다(release_again).
    """
    status = await current_status(session_factory, charge.id)
    if status in SECURED_STATUSES:
        return Readiness.READY
    if status == ChargeStatus.RELEASED:
        await release_again(session_factory, charge, now)
    return Readiness.UNAVAILABLE


async def try_hold(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, charge: NarrationCharge, now: datetime
) -> Readiness:
    """청구의 홀드를 걸어 보고 결과를 적는다. 걸렸으면 READY."""
    try:
        outcome = await billing.hold(charge.reference, charge.payer_id, charge.price_code)
    except BillingUnavailable as error:
        await note_unavailable(session_factory, charge, HOLD_OPERATION, error, now)
        return Readiness.UNAVAILABLE
    except BillingRejected as error:
        await note_rejected(session_factory, charge, HOLD_OPERATION, error)
        return Readiness.UNAVAILABLE
    if outcome.result == HoldResult.SHORT:
        await note_short(session_factory, charge)
        return Readiness.SHORT
    allowed = (ChargeStatus.PENDING, ChargeStatus.SHORT)
    extend_at = next_extension(now, outcome.expires_at)
    if await write_move(
        session_factory, charge, allowed, ChargeStatus.HELD, attempts=0, last_error=None, next_attempt_at=extend_at
    ):
        return Readiness.READY
    return await after_lost_race(session_factory, charge, now)


def log_rehold(charge: NarrationCharge, reason: str) -> None:
    """연장하려니 홀드가 없거나 만료되어 다시 거는 것을 남긴다. 결제 서버나 게임 서버가 오래 멈췄다는 표시다."""
    logger.warning(
        '연장할 홀드가 없어 다시 겁니다',
        extra={**log_fields(charge, EXTEND_OPERATION), 'reason': reason, 'renewals': charge.renewals},
    )


async def rehold_missing(
    session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, now: datetime
) -> None:
    """결제 서버에 그 이름표의 홀드가 없다. 같은 이름표로 다시 걸게 걸어야 함으로 되돌린다."""
    log_rehold(charge, 'missing')
    await write_move(
        session_factory,
        charge,
        (ChargeStatus.HELD,),
        ChargeStatus.PENDING,
        attempts=0,
        last_error='missing',
        next_attempt_at=now,
    )


async def renew(session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, now: datetime) -> None:
    """
    만료되어 결제 서버가 돌려준 홀드다. 새 이름표로 다시 걸게 걸어야 함으로 되돌린다.

    같은 이름표는 결제 서버에서 끝난 홀드라 다시 걸면 끝난 것을 돌려받는다. 다시 건 횟수를 이름표 끝에 붙인다.
    """
    log_rehold(charge, 'expired')
    async with session_factory() as session:
        table_id, number = await repository.find_round_of(session, charge)
    renewals = charge.renewals + 1
    await write_move(
        session_factory,
        charge,
        (ChargeStatus.HELD,),
        ChargeStatus.PENDING,
        reference=reference_for(table_id, number, charge.payer_id, renewals),
        renewals=renewals,
        attempts=0,
        last_error='expired',
        next_attempt_at=now,
    )


async def note_extend_rejected(
    session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, error: BillingRejected, now: datetime
) -> None:
    """
    결제 서버가 연장을 받아들이지 않았다(버그). 오류로 남기고 걸린 채로 둔다. 한 시간 뒤에 다시 부른다.

    실패로 적지 않는다. 홀드는 아직 살아 있을 수 있고, 실패로 적으면 그 라운드를 서술할 수 없다.
    """
    logger.error(
        '결제 서버가 연장을 받아들이지 않았습니다',
        extra={
            **log_fields(charge, EXTEND_OPERATION),
            'status_code': error.status_code,
            'result': 'server_error',
            'error_code': REJECTED_ERROR_CODE,
        },
    )
    await write_move(
        session_factory,
        charge,
        (ChargeStatus.HELD,),
        ChargeStatus.HELD,
        last_error=f'rejected_{error.status_code}',
        next_attempt_at=now + EXTEND_REJECTED_RETRY,
    )


async def try_extend(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, charge: NarrationCharge, now: datetime
) -> ExtendResult | None:
    """
    걸린 홀드를 연장해 보고 결과를 적는다. 답을 받지 못했거나 받아들이지 않았으면 None(걸린 채로 둔다).

    연장했으면 새 만료 시각까지 남은 시간의 절반 뒤에 다시 연장한다(charges.next_extension).
    홀드가 없으면 같은 이름표로, 만료되어 돌려줬으면 새 이름표로 다시 걸게 한다.
    """
    try:
        outcome = await billing.extend(charge.reference)
    except BillingUnavailable as error:
        await note_unavailable(session_factory, charge, EXTEND_OPERATION, error, now)
        return None
    except BillingRejected as error:
        await note_extend_rejected(session_factory, charge, error, now)
        return None
    result = outcome.result
    if result == ExtendResult.MISSING:
        await rehold_missing(session_factory, charge, now)
    elif result == ExtendResult.ENDED:
        await renew(session_factory, charge, now)
    else:
        extend_at = next_extension(now, outcome.expires_at)
        allowed = (ChargeStatus.HELD,)
        await write_move(
            session_factory, charge, allowed, ChargeStatus.HELD, attempts=0, last_error=None, next_attempt_at=extend_at
        )
    return result


async def try_finish(
    session_factory: async_sessionmaker[AsyncSession],
    charge: NarrationCharge,
    call: Callable[[str], Awaitable[None]],
    operation: str,
    done: ChargeStatus,
    now: datetime,
) -> None:
    """확정이나 반환(call)을 불러 보고 결과를 적는다. 됐으면 done 으로 옮긴다."""
    try:
        await call(charge.reference)
    except BillingUnavailable as error:
        await note_unavailable(session_factory, charge, operation, error, now)
        return
    except BillingRejected as error:
        await note_rejected(session_factory, charge, operation, error)
        return
    await write_move(session_factory, charge, (ChargeStatus(charge.status),), done, last_error=None)


async def settle(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, charge: NarrationCharge, now: datetime
) -> None:
    """
    청구를 그 상태에 맞게 결제 서버에 맡긴다. 걸어야 하면 걸고, 걸렸으면 연장하고, 확정할 것이면 확정하고,
    돌려줄 것이면 돌려준다.

    그 밖의 상태(모자람, 끝남)면 아무것도 하지 않는다. 정리 작업이 차례가 된 것마다 부른다.
    """
    status = ChargeStatus(charge.status)
    if status == ChargeStatus.PENDING:
        await try_hold(session_factory, billing, charge, now)
    elif status == ChargeStatus.HELD:
        await try_extend(session_factory, billing, charge, now)
    elif status == ChargeStatus.CAPTURE_DUE:
        await try_finish(session_factory, charge, billing.capture, CAPTURE_OPERATION, ChargeStatus.CAPTURED, now)
    elif status == ChargeStatus.RELEASE_DUE:
        await try_finish(session_factory, charge, billing.release, RELEASE_OPERATION, ChargeStatus.RELEASED, now)


async def secure_held(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, charge: NarrationCharge, now: datetime
) -> Readiness:
    """연장할 때가 지난 걸린 청구를 연장해 보고, 홀드가 없거나 만료됐으면 다시 건다."""
    result = await try_extend(session_factory, billing, charge, now)
    if result in (ExtendResult.MISSING, ExtendResult.ENDED):
        return await try_hold(session_factory, billing, await reload(session_factory, charge.id), now)
    return Readiness.READY


async def secure(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, charge: NarrationCharge, now: datetime
) -> Readiness:
    """
    청구 하나의 값을 잡아 둔다. 이미 잡혀 있으면 부르지 않는다.

    걸어야 함이나 모자람이면 지금 걸어 본다. 정리 작업이 아직 걸지 못했거나(결제 서버가 잠깐 죽었다),
    모자랐던 사람이 그사이 충전했을 수 있다. 돌려줬거나 거절된 청구는 더 걸 수 없다.

    걸려 있어도 연장할 때가 지났으면 먼저 연장해 본다. 정리 작업이 오래 멈췄던 사이 만료됐을 수 있다.
    홀드가 없거나 만료됐으면 다시 걸고, 결제 서버의 답이 없으면 걸린 것으로 보고 서술한다(만료까지 여유가 있다).
    """
    status = ChargeStatus(charge.status)
    if status == ChargeStatus.HELD and charge.next_attempt_at <= now:
        return await secure_held(session_factory, billing, charge, now)
    if status in SECURED_STATUSES:
        return Readiness.READY
    if status in (ChargeStatus.PENDING, ChargeStatus.SHORT):
        return await try_hold(session_factory, billing, charge, now)
    return Readiness.UNAVAILABLE


async def secure_round(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, table_id: uuid.UUID, number: int
) -> Readiness:
    """
    라운드의 서술 값을 모두 잡아 둔다. 하나라도 못 잡았으면 그 까닭을 돌려준다.

    청구가 없는 라운드(이 기록이 생기기 전에 연 라운드)는 받지 않고 서술한다.
    """
    async with session_factory() as session:
        charges = await repository.find_round_charges(session, table_id, number)
    for charge in charges:
        readiness = await secure(session_factory, billing, charge, now_utc())
        if readiness != Readiness.READY:
            return readiness
    return Readiness.READY


async def settle_round(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, table_id: uuid.UUID, number: int
) -> None:
    """닫은 라운드의 청구를 바로 확정하거나 돌려준다. 못 하면 정리 작업이 마저 한다."""
    async with session_factory() as session:
        charges = await repository.find_round_charges(session, table_id, number)
    for charge in charges:
        await settle(session_factory, billing, charge, now_utc())
