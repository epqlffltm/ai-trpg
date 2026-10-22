# chat-server/app/catalog/offers.py

"""
대화에 고를 수 있는 모델들과 그 값. 모델 목록(DB)과 결제 서버의 가격 목록을 맞춰 붙인다.
게임 서버의 것(trpg-server/app/catalog/offers.py)을 줄여 옮겼다. 회사의 대체 모델이 없다.

고를 수 있는 모델은 둘 다에 있어야 한다.
  - 모델 목록에서 켜져 있고 은퇴하지 않았다(ai_core/catalog_contract.py 의 is_offered).
  - 가격 목록에 그 이름표의 가격표 이름(chat.<이름표>.i0.o0)이 있고 지금 팔고 있다.
    값이 바뀌는 예약(next)이 있으면 함께 내준다. 화면이 "12월 1일부터 40"처럼 미리 알린다.
판매가는 결제 서버만 안다. 이 서버는 받은 값을 그대로 붙여 보여 줄 뿐이다. 실제로 빠지는 값은 홀드를 걸 때 정해진다.

결제 서버 없이 도는 서버(가격 목록이 free)는 켜진 모델을 모두 값 없이 내준다. 말도 공짜로 돈다.
성인 등급의 대화에 쓸 수 있나(allows_adult)는 여기서 거르지 않는다. 모델의 속성으로 싣고 화면이 거른다.
"""

from dataclasses import dataclass
from datetime import datetime

from ai_core.catalog_contract import is_offered
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceList
from app.billing.prices import Change, Price, PriceBook, Sale, chat_code, price_at
from app.catalog import repository
from app.catalog.models import AiModel


@dataclass(frozen=True)
class ModelOffer:
    """
    고를 수 있는 모델 하나와 그 값. 결제 서버 없이 도는 서버면 sale 이 None 이다.

    next 는 예약된 바뀜이다. next.sale 이 None 이면 그 시각부터 팔지 않는다.
    """

    model: AiModel
    sale: Sale | None
    next: Change | None = None


@dataclass(frozen=True)
class Offering:
    """고를 수 있는 모델들. free 는 결제 서버 없이 도는 서버라 값이 없다는 뜻이다."""

    free: bool
    offers: list[ModelOffer]


def current_price(book: PriceBook, slug: str, now: datetime) -> Price | None:
    """그 모델의 now 의 값. 가격 목록에 없거나 지금 팔지 않으면(예약만 있거나 판매를 멈췄다) None."""
    price = book.prices.get(chat_code(slug))
    if price is None:
        return None
    price = price_at(price, now)
    return price if price.current is not None else None


def is_sold(book: PriceBook, slug: str, now: datetime) -> bool:
    """그 모델을 now 에 팔고 있나. 결제 서버 없이 도는 서버는 모두 판다(값 없이)."""
    return book.free or current_price(book, slug, now) is not None


def offer(model: AiModel, book: PriceBook, now: datetime) -> ModelOffer | None:
    """그 모델을 지금 내줄 수 있으면 값을 붙여 돌려준다. 꺼졌거나 은퇴했거나 팔지 않으면 None."""
    if not is_offered(model, now.date()):
        return None
    if book.free:
        return ModelOffer(model, None)
    price = current_price(book, model.slug, now)
    if price is None:
        return None
    return ModelOffer(model, price.current, price.next)


async def list_offered(session: AsyncSession, prices: PriceList, now: datetime) -> Offering:
    """
    고를 수 있는 모델들. 회사, 이름표 순서다. 모델 목록을 DB 에서 읽고, 가격 목록(받아 둔 것)을 맞춰 붙인다.

    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다(503).
    """
    models = await repository.list_models(session)
    book = await prices.book()
    offers = [found for model in models if (found := offer(model, book, now)) is not None]
    return Offering(free=book.free, offers=offers)
