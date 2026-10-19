# trpg-server/app/billing/settling.py

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

import asyncio
import enum
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing import repository
from app.billing.charges import EXTEND_REJECTED_RETRY, next_extension, reference_for, retry_delay
from app.billing.client import (
    PRICE_UNAVAILABLE,
    Billing,
    BillingRejected,
    BillingUnavailable,
    ExtendResult,
    HoldResult,
)
from app.billing.models import SECURED_STATUSES, ChargeStatus, NarrationCharge
from app.events import recorder
from app.events.models import EventType
from app.rounds.models import Round
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


# 모자람의 까닭. 청구(last_error)와 이벤트(narration_credits_short 의 reason)에 적는다
SHORT_INSUFFICIENT = 'insufficient'
SHORT_GOLD = 'gold_required'

# 돌려줄 것이거나 돌려준 청구. 떠난 사람의 것이거나, 크레딧을 기다리다 돌려준 앉은 사람의 것이다(secure_charge)
RETURNED_STATUSES = (ChargeStatus.RELEASE_DUE, ChargeStatus.RELEASED)


class Readiness(enum.StrEnum):
    """서술해도 되는가. 서술을 맡은 작업이 서술자를 부르기 전에 본다."""

    # 값을 잡아 두었다
    READY = 'ready'
    # 테이블의 서술 모델을 결제 서버가 팔지 않는다(판매를 멈췄거나 아직 열지 않았다). 방장이 모델을 바꾸면 된다
    NOT_FOR_SALE = 'model_not_for_sale'
    # 내는 사람 중 누가 골드가 모자란다. 프리미엄 모델은 골드로만 낸다. 골드를 사거나, 방장이 그 사람을 내보내거나
    # 모델을 바꾸면 된다
    GOLD_REQUIRED = 'gold_required'
    # 내는 사람 중 누가 크레딧이 모자란다. 그 사람이 충전하거나 방장이 그 사람을 내보낸 뒤 다시 맡기면 된다
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


async def note_short(
    session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, reason: str = SHORT_INSUFFICIENT
) -> None:
    """
    크레딧이 모자란 것을 적는다. 처음 모자란 것을 알았을 때(걸어야 함 → 모자람)만 앉은 사람 모두에게 이벤트로 알린다.
    누가 모자란지(user_id)와 무엇이 모자란지(reason: 크레딧 insufficient, 골드 gold_required)를 싣는다.
    모자란 사람이 충전하거나 방장이 그 사람을 내보내면 서술할 수 있다. 골드가 모자라면 방장이 모델을 바꿔도 된다.
    무엇이 모자란지는 청구에도 적는다(last_error). 다시 걸어 볼 때까지 그대로다.

    테이블을 잠그고 적는다. 이벤트의 번호를 매기는 일이 테이블의 잠금 아래에서만 일어난다.
    """
    async with session_factory() as session:
        table_id, number = await repository.find_round_of(session, charge)
        table = await table_repository.lock_table(session, table_id)
        moved = await repository.move(
            session, charge.id, (ChargeStatus.PENDING,), ChargeStatus.SHORT, last_error=reason
        )
        if table is None or not moved:
            await session.commit()
            return
        payload = {'round': number, 'user_id': str(charge.payer_id), 'reason': reason}
        recorder.record(session, table, EventType.NARRATION_CREDITS_SHORT, payload=payload)
        await tables.commit(session, table)


async def note_price_unavailable(
    session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, error: BillingRejected
) -> None:
    """
    결제 서버가 그 가격표의 이름을 팔지 않는다(price.not_for_sale, price.unknown). 청구를 실패로 적는다.

    버그가 아니라 판매를 멈췄거나 아직 열지 않은 모델이다. 그래서 오류가 아니라 warning 으로 남긴다.
    라운드마다 처음 알았을 때만 앉은 사람 모두에게 이벤트로 알린다(narration_model_not_for_sale). 내는 사람마다
    같은 일이라 한 번이면 된다. 방장이 테이블의 모델을 바꾸면 그 라운드의 청구를 새 가격표로 다시 건다
    (app/tables/narration_models.py). 테이블을 잠그고 적는다.
    """
    logger.warning(
        '결제 서버가 서술 모델의 가격표를 팔지 않는다',
        extra={**log_fields(charge, HOLD_OPERATION), 'reason': error.code, 'result': 'not_for_sale'},
    )
    async with session_factory() as session:
        table_id, number = await repository.find_round_of(session, charge)
        table = await table_repository.lock_table(session, table_id)
        first = not await repository.has_failed_with(session, charge.round_id, tuple(PRICE_UNAVAILABLE))
        moved = await repository.move(
            session, charge.id, (ChargeStatus(charge.status),), ChargeStatus.FAILED, last_error=error.code
        )
        if table is None or not moved or not first:
            await session.commit()
            return
        round_ = await session.get_one(Round, charge.round_id)
        payload = {'round': number, 'narration_model': round_.narration_model}
        recorder.record(session, table, EventType.NARRATION_MODEL_NOT_FOR_SALE, payload=payload)
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
        if error.price_unavailable:
            await note_price_unavailable(session_factory, charge, error)
            return Readiness.NOT_FOR_SALE
        await note_rejected(session_factory, charge, HOLD_OPERATION, error)
        return Readiness.UNAVAILABLE
    if outcome.result == HoldResult.GOLD_REQUIRED:
        await note_short(session_factory, charge, SHORT_GOLD)
        return Readiness.GOLD_REQUIRED
    if outcome.result == HoldResult.SHORT:
        await note_short(session_factory, charge)
        return Readiness.SHORT
    allowed = (ChargeStatus.PENDING, ChargeStatus.SHORT)
    extend_at = next_extension(now, outcome.expires_at)
    if await write_move(
        session_factory,
        charge,
        allowed,
        ChargeStatus.HELD,
        attempts=0,
        last_error=None,
        next_attempt_at=extend_at,
        held_credits=outcome.amount,
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


async def rename(
    session_factory: async_sessionmaker[AsyncSession],
    charge: NarrationCharge,
    allowed: tuple[ChargeStatus, ...],
    reason: str | None,
    now: datetime,
) -> bool:
    """
    끝난 홀드의 청구를 새 이름표로 다시 걸게 걸어야 함으로 되돌린다. 옮겼으면 True.

    같은 이름표는 결제 서버에서 끝난 홀드라 다시 걸면 끝난 것을 돌려받는다. 다시 건 횟수를 이름표 끝에 붙인다.
    """
    async with session_factory() as session:
        table_id, number = await repository.find_round_of(session, charge)
    renewals = charge.renewals + 1
    return await write_move(
        session_factory,
        charge,
        allowed,
        ChargeStatus.PENDING,
        reference=reference_for(table_id, number, charge.payer_id, renewals),
        renewals=renewals,
        attempts=0,
        last_error=reason,
        next_attempt_at=now,
    )


async def renew(session_factory: async_sessionmaker[AsyncSession], charge: NarrationCharge, now: datetime) -> None:
    """만료되어 결제 서버가 돌려준 홀드다. 새 이름표로 다시 걸게 한다."""
    log_rehold(charge, 'expired')
    await rename(session_factory, charge, (ChargeStatus.HELD,), 'expired', now)


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
    if status == ChargeStatus.FAILED and charge.last_error in PRICE_UNAVAILABLE:
        return Readiness.NOT_FOR_SALE
    return Readiness.UNAVAILABLE


async def restore(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, charge: NarrationCharge, now: datetime
) -> Readiness:
    """
    돌려줬던 청구를 다시 건다. 크레딧을 기다리다 시간이 지나 낼 수 있는 사람의 값을 돌려준 라운드다(#181).
    방장이 그 라운드를 다시 맡기면 아직 앉아 있는 사람의 것을 이것으로 다시 건다.

    아직 돌려주지 않았으면(release_due) 먼저 돌려준다. 같은 청구에 홀드 둘이 살아 있지 않게 한다.
    그 뒤 새 이름표로 걸어야 함으로 되돌려 건다. 돌려주지 못했으면(결제 서버의 답이 없다) 서술하지 않는다.
    """
    if ChargeStatus(charge.status) == ChargeStatus.RELEASE_DUE:
        await try_finish(session_factory, charge, billing.release, RELEASE_OPERATION, ChargeStatus.RELEASED, now)
        charge = await reload(session_factory, charge.id)
    if ChargeStatus(charge.status) != ChargeStatus.RELEASED:
        return Readiness.UNAVAILABLE
    await rename(session_factory, charge, (ChargeStatus.RELEASED,), None, now)
    return await try_hold(session_factory, billing, await reload(session_factory, charge.id), now)


async def secure_charge(
    session_factory: async_sessionmaker[AsyncSession],
    billing: Billing,
    charge: NarrationCharge,
    seated: set[uuid.UUID],
    now: datetime,
) -> Readiness:
    """
    라운드의 청구 하나를 서술 전에 잡아 둔다.

    돌려줄 것·돌려준 청구는 두 가지다. 떠난 사람의 것이면 보지 않는다(그 사람 때문에 서술이 막히지 않는다).
    아직 앉아 있는 사람의 것이면 크레딧을 기다리다 돌려준 것이라 다시 건다(restore).
    """
    if ChargeStatus(charge.status) in RETURNED_STATUSES:
        if charge.payer_id in seated:
            return await restore(session_factory, billing, charge, now)
        return Readiness.READY
    return await secure(session_factory, billing, charge, now)


def worst(results: list[Readiness]) -> Readiness:
    """
    여럿의 결과를 하나로. 사람이 움직여야 풀리는 것을 앞에 둔다. 모두 잡았으면 READY.

    팔지 않는 모델(방장이 모델을 바꿔야 한다), 골드가 모자람, 크레딧이 모자람, 답을 못 받음 차례다.
    답을 못 받은 것은 정리 작업이 저절로 다시 하지만, 앞의 것들은 사람이 움직여야 풀린다.
    """
    order = (Readiness.NOT_FOR_SALE, Readiness.GOLD_REQUIRED, Readiness.SHORT, Readiness.UNAVAILABLE)
    for readiness in order:
        if readiness in results:
            return readiness
    return Readiness.READY


async def secure_round(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, table_id: uuid.UUID, number: int
) -> Readiness:
    """
    라운드의 서술 값을 모두 잡아 둔다. 하나라도 못 잡았으면 그 까닭을 돌려준다(worst).

    내는 사람마다 함께 해 본다. 한 사람씩 하면 결제 서버가 느릴 때 서술 값을 잡는 시간의 상한을 넘는다.
    모자란 사람이 여럿이면 모두에게 걸어 봐야 누가 모자란지 모두 알린다.
    떠난 사람의 것은 보지 않고, 돌려줬던 앉은 사람의 것은 다시 건다(secure_charge).
    청구가 없는 라운드(이 기록이 생기기 전에 연 라운드)는 받지 않고 서술한다.
    """
    async with session_factory() as session:
        charges = await repository.find_round_charges(session, table_id, number)
        seated = await repository.find_seated(session, table_id)
    now = now_utc()
    results = await asyncio.gather(
        *(secure_charge(session_factory, billing, charge, seated, now) for charge in charges)
    )
    return worst(list(results))


async def settle_round(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, table_id: uuid.UUID, number: int
) -> None:
    """닫은 라운드의 청구를 바로 확정하거나 돌려준다. 못 하면 정리 작업이 마저 한다."""
    async with session_factory() as session:
        charges = await repository.find_round_charges(session, table_id, number)
    for charge in charges:
        await settle(session_factory, billing, charge, now_utc())
