# chat-server/app/turns/charging.py

"""
말 한 번의 값을 결제 서버에 맡기는 일(docs/architecture/chat-server.md 의 "과금").
결제 서버의 답을 이 서버의 뜻으로 바꾼다. DB 를 모른다.
바꾼 뜻을 기록에 적는 것은 부르는 쪽(app/turns/service.py, settler.py)이다.

  - 홀드: 말을 보내기 전에 건다. 걸리지 않으면 HoldDeclined 이고, 그 까닭(code)을 사람에게 알린다. 모델을 부르지 않는다.
  - 확정과 반환: 답이 끝난 뒤에 한다. 답을 받지 못했으면(결제 서버가 잠깐 죽었다) 나중에 다시 부를 일이다(RETRY).
    받아들이지 않으면(다시 불러도 같다) 사람이 볼 일이다(FAILED).
이름표(reference)는 말 한 번에 하나다(chat:gen:<기록의 id>).
결제 서버는 같은 이름표를 한 번만 처리하므로 몇 번을 불러도 된다.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from app.billing.client import Billing, BillingRejected, BillingUnavailable, HoldResult

logger = logging.getLogger(__name__)

# 확정이나 반환을 다시 부르기까지 기다리는 시간(초). 맡기지 못할수록 두 배로 늘고, 이보다 길어지지 않는다
FIRST_RETRY_SECONDS = 5
MAX_RETRY_SECONDS = 300

# 홀드가 걸리지 않은 까닭의 이름. 사람에게 보내는 답의 code 다(app/turns/router.py)
CREDIT_SHORT = 'credit_short'
GOLD_REQUIRED = 'gold_required'
MODEL_UNAVAILABLE = 'model_unavailable'
BILLING_UNAVAILABLE = 'billing_unavailable'

DECLINED_CODES = {HoldResult.SHORT: CREDIT_SHORT, HoldResult.GOLD_REQUIRED: GOLD_REQUIRED}


class HoldDeclined(Exception):
    """홀드가 걸리지 않았다. code 는 까닭이다(credit_short, gold_required, model_unavailable, billing_unavailable)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Settled(enum.StrEnum):
    """확정이나 반환을 맡겨 본 결과."""

    DONE = 'done'
    RETRY = 'retry'
    FAILED = 'failed'


@dataclass(frozen=True)
class Settlement:
    """맡겨 본 결과와, 받아들이지 않았으면 그 까닭의 이름(rejected_409 …)."""

    result: Settled
    error_code: str | None = None


def hold_reference(generation_id: uuid.UUID) -> str:
    """홀드의 이름표. 결제 서버가 받는 모양(영문자, 숫자, : - 로 된 8~200자)이다."""
    return f'chat:gen:{generation_id}'


def retry_delay(attempts: int) -> timedelta:
    """attempts 번 맡기지 못한 뒤 다시 부르기까지. 5초, 10초, 20초 … 5분에서 멈춘다."""
    return timedelta(seconds=min(FIRST_RETRY_SECONDS * 2**attempts, MAX_RETRY_SECONDS))


def rejected_code(error: BillingRejected) -> str:
    """받아들이지 않은 까닭의 이름. 가격표를 팔지 않는 것이면 모델을 쓸 수 없는 것이다."""
    return MODEL_UNAVAILABLE if error.price_unavailable else BILLING_UNAVAILABLE


async def place_hold(billing: Billing, reference: str, owner_id: uuid.UUID, price_code: str) -> None:
    """홀드를 건다. 걸리지 않으면 HoldDeclined. 결제 서버가 받아들이지 않은 것(버그일 수 있다)은 로그에 남긴다."""
    try:
        outcome = await billing.hold(reference, owner_id, price_code)
    except BillingUnavailable as error:
        raise HoldDeclined(BILLING_UNAVAILABLE) from error
    except BillingRejected as error:
        if not error.price_unavailable:
            logger.error(
                '결제 서버가 홀드를 받아들이지 않았습니다',
                extra={'reference': reference, 'status_code': error.status_code, 'code': error.code},
            )
        raise HoldDeclined(rejected_code(error)) from error
    if outcome.result in DECLINED_CODES:
        raise HoldDeclined(DECLINED_CODES[outcome.result])


async def settle(billing: Billing, reference: str, capture: bool) -> Settlement:
    """확정하거나(capture) 돌려준다. 답을 받지 못했으면 RETRY, 받아들이지 않으면 FAILED 다."""
    try:
        if capture:
            await billing.capture(reference)
        else:
            await billing.release(reference)
    except BillingUnavailable:
        return Settlement(Settled.RETRY)
    except BillingRejected as error:
        logger.error(
            '결제 서버가 확정이나 반환을 받아들이지 않았습니다',
            extra={'reference': reference, 'status_code': error.status_code, 'capture': capture},
        )
        return Settlement(Settled.FAILED, f'rejected_{error.status_code}')
    return Settlement(Settled.DONE)
