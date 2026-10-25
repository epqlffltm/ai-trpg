# story-server/app/billing/routing.py

"""
라우터들이 함께 쓰는 결제의 의존성. 결제 서버의 가격 목록이다.

모델 목록 API(값을 붙인다)와 세션(모델을 고를 때 팔고 있는지 본다)가 함께 쓴다.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.billing.price_list import PriceList


def get_price_list(request: Request) -> PriceList:
    """결제 서버의 가격 목록을 받아 두는 것. 앱을 만들 때 설정으로 정해 꽂아 둔 것이다(app/main.py)."""
    return request.app.state.price_list


Prices = Annotated[PriceList, Depends(get_price_list)]
