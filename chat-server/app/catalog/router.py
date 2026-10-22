# chat-server/app/catalog/router.py

"""
모델 목록 API. 대화에 고를 수 있는 모델들과 말 한 번의 값을 내준다.

    GET /api/v1/chat/models    고를 수 있는 모델들(켜져 있고 은퇴하지 않았고 결제 서버가 팔고 있다)

로그인을 요구한다. 다른 주소와 같다. 성인 등급을 볼 수 없는 사람에게도 allows_adult 를 그대로 싣는다.
모델의 속성일 뿐이고, 성인 등급의 대화를 거르는 것은 대화를 만들고 읽는 곳이다.
가격 목록을 받지 못했고 받아 둔 것도 없으면 503 prices_unavailable 이다(app/billing/router.py).
"""

from fastapi import APIRouter, status
from server_core.auth.dependencies import CurrentUser

from app.billing.prices import Change
from app.billing.routing import Prices
from app.catalog import offers
from app.catalog.offers import ModelOffer
from app.catalog.schemas import ModelList, ModelOut, NextPriceOut
from app.core.dependencies import Now, Session

router = APIRouter(prefix='/models', tags=['models'])


def to_next_out(change: Change | None) -> NextPriceOut | None:
    """예약된 바뀜을 응답으로. 판매를 멈추는 예약이면 값과 등급이 null 이다."""
    if change is None:
        return None
    sale = change.sale
    return NextPriceOut(
        credits=sale.credits if sale else None,
        tier=sale.tier if sale else None,
        promo=sale.promo if sale else False,
        effective_at=change.effective_at,
    )


def to_model_out(found: ModelOffer) -> ModelOut:
    """고를 수 있는 모델 하나를 응답으로. 결제 서버 없이 도는 서버면 값이 없다."""
    model, sale = found.model, found.sale
    return ModelOut(
        slug=model.slug,
        display_name=model.display_name,
        vendor=model.vendor,
        grade=model.grade,
        allows_adult=model.allows_adult,
        retires_on=model.retires_on,
        credits=sale.credits if sale else None,
        tier=sale.tier if sale else None,
        promo=sale.promo if sale else False,
        next=to_next_out(found.next),
    )


@router.get('', response_model=ModelList, status_code=status.HTTP_200_OK)
async def list_models(user: CurrentUser, session: Session, prices: Prices, now: Now) -> ModelList:
    """대화에 고를 수 있는 모델들과 그 값. 회사, 이름표 순서다."""
    offering = await offers.list_offered(session, prices, now)
    return ModelList(free=offering.free, items=[to_model_out(found) for found in offering.offers])
