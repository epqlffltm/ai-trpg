# trpg-server/app/billing/free_billing.py

"""
받지 않는 것. 결제 서버의 주소(BILLING_URL)를 비우면 이것이다.

결제 서버 없이 개발하고, 테스트와 CI 가 돈다. 청구 기록은 똑같이 남고 똑같이 상태가 옮겨 간다.
받는 일만 하지 않는다. 그래서 결제 서버를 켜든 끄든 라운드를 열고 닫는 코드의 길이 하나다.
"""

import uuid

from app.billing.client import ExtendOutcome, ExtendResult, HoldOutcome, HoldResult


class FreeBilling:
    """언제나 잡히고, 확정과 반환은 아무것도 하지 않는다. 만료 시각을 주지 않는다."""

    async def hold(self, reference: str, user_id: uuid.UUID, price_code: str) -> HoldOutcome:
        return HoldOutcome(HoldResult.HELD)

    async def capture(self, reference: str) -> None:
        return None

    async def release(self, reference: str) -> None:
        return None

    async def extend(self, reference: str) -> ExtendOutcome:
        return ExtendOutcome(ExtendResult.EXTENDED)
