# trpg-server/app/billing/routing.py

"""
라우터들이 함께 쓰는 결제의 의존성. 결제 서버의 가격 목록과 지금 시각.

테이블 API(모델 고르기)와 시나리오 API(추천 모델의 상태)가 함께 쓴다.
테스트는 utc_now 를 dependency_overrides 로 바꿔 꽂는다.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

from app.billing.price_list import PriceList


def get_price_list(request: Request) -> PriceList:
    """결제 서버의 가격 목록을 받아 두는 것. 앱을 만들 때 설정으로 정해 꽂아 둔 것이다(app/main.py)."""
    return request.app.state.price_list


def utc_now() -> datetime:
    """지금 시각(UTC). 테스트가 dependency_overrides 로 바꿔 꽂는다."""
    return datetime.now(UTC)


Prices = Annotated[PriceList, Depends(get_price_list)]
Now = Annotated[datetime, Depends(utc_now)]
