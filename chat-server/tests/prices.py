# chat-server/tests/prices.py

"""
테스트가 결제 서버의 가격 목록 자리에 끼우는 가짜(app.state.price_list). 진짜 HTTP 를 거치지 않는다.

가격 목록을 받는 것 자체(서명, ETag, 받아 두기)는 tests/test_price_list.py 가 본다.
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.billing.price_list import PriceListUnavailable
from app.billing.prices import Change, Price, PriceBook, Sale, Tier, chat_code


def sale(credits: str = '30', tier: Tier = Tier.STANDARD, promo: bool = False) -> Sale:
    """팔고 있는 값 하나."""
    return Sale(credits=credits, tier=tier, promo=promo)


def selling(*slugs: str, **values) -> dict[str, Price]:
    """그 모델들을 같은 값으로 판다."""
    return {chat_code(slug): Price(code=chat_code(slug), current=sale(**values)) for slug in slugs}


def stopping(slug: str, at: datetime, current: Sale | None = None) -> dict[str, Price]:
    """그 모델을 at 부터 팔지 않는다. 그 전에는 current(없으면 기본값)로 판다."""
    return {chat_code(slug): Price(code=chat_code(slug), current=current or sale(), next=Change(None, at))}


@dataclass
class StaticPrices:
    """정해 둔 가격 목록을 주는 것. down 이면 받지 못했고 받아 둔 것도 없는 것이다(PriceListUnavailable)."""

    prices: dict[str, Price] = field(default_factory=dict)
    down: bool = False

    async def book(self) -> PriceBook:
        if self.down:
            raise PriceListUnavailable('unreachable')
        return PriceBook(prices=self.prices)
