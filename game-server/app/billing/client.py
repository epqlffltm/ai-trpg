# game-server/app/billing/client.py

"""
결제 서버를 부르는 것의 모양과 그 결과.

구현은 둘이다. 실제로 부르는 것(http_billing.py)과 받지 않는 것(free_billing.py). 설정(BILLING_URL)이 고른다(setup.py).
서술자(Narrator)처럼 모양만 여기 두고 구현을 갈아 끼운다. 테스트는 가짜 결제 서버로 가는 실제 구현을 쓴다.

세 일 모두 이름표(reference)로 홀드를 가리킨다. 결제 서버는 같은 이름표면 같은 일로 보고 한 번만 한다.
그래서 응답을 받지 못했으면 같은 것을 그대로 다시 부르면 된다.

실패는 둘로 나눈다. 다시 부르면 될 수 있는 것(BillingUnavailable)과 다시 불러도 같은 것(BillingRejected).
앞의 것은 정리 작업이 조금 뒤에 다시 부르고, 뒤의 것은 사람이 봐야 하는 일이라 오류로 남긴다.
"""

import enum
import uuid
from typing import Protocol


class HoldResult(enum.StrEnum):
    """홀드를 걸어 본 결과."""

    # 크레딧을 빼 두었다. 이미 걸어 둔 것을 돌려받은 것도 여기다
    HELD = 'held'
    # 크레딧이 모자란다. 하나도 빼지 않았고 홀드도 남지 않았다. 충전한 뒤 같은 이름표로 다시 걸 수 있다
    SHORT = 'short'


class BillingUnavailable(Exception):
    """
    결제 서버의 답을 받지 못했거나, 지금은 처리할 수 없다고 했다. 조금 뒤에 다시 부르면 될 수 있다.

    reason 은 짧은 이름이다(unreachable, timeout, server_error, unauthorized, bad_response).
    응답의 본문은 싣지 않는다. 무엇이 들어 있을지 모른다.
    unauthorized 는 서명이 거절된 것이다. 두 서버의 비밀이 다르거나 시계가 어긋났다. 설정을 고치면 낫는다.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BillingRejected(Exception):
    """
    결제 서버가 요청을 받아들이지 않았다. 다시 불러도 같다. 이름표를 짓는 코드의 버그이거나 두 서버의 기록이 어긋났다.

    status_code 는 결제 서버의 답이다(400, 404, 409 …). 본문은 싣지 않는다.
    """

    def __init__(self, status_code: int) -> None:
        super().__init__(f'billing rejected: {status_code}')
        self.status_code = status_code


class Billing(Protocol):
    """결제 서버를 부르는 것."""

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldResult:
        """user_id 의 크레딧을 가격표 price_code 의 값만큼 빼 둔다. 모자라면 SHORT."""
        ...

    async def capture(self, reference: str) -> None:
        """홀드를 확정한다. 크레딧은 돌아가지 않는다. 이미 확정했으면 아무것도 하지 않는다."""
        ...

    async def release(self, reference: str) -> None:
        """홀드를 돌려준다. 이미 돌려줬거나 걸린 적이 없으면 아무것도 하지 않는다."""
        ...
