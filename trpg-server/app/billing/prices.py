# trpg-server/app/billing/prices.py

"""
결제 서버의 가격 목록(GET /api/v1/billing/service/prices)의 값과, 그것을 읽는 순수 함수.

모양은 결제 서버가 정했다(billing-server/README.md 의 "가격 목록").
  - 가격표의 이름(code)마다 지금 값(credits, tier)과 다음에 바뀔 값(next) 하나.
  - 지금 팔지 않으면(예약만 있으면) credits, tier 가 null 이다.
  - next.credits 가 null 이면 그 시각부터 판매를 멈춘다.
  - credits 는 글자다("120"). 게임 서버는 셈하지 않고 보여 주기만 하므로 글자 그대로 둔다.
  - promo 는 그 값이 행사가(끝나는 때가 정해진 값)인지다. 행사가면 next 가 행사가 끝나는 때와 그 뒤의 값이다.
    비어 있으면 정가다. 이 칸이 생기기 전의 결제 서버는 싣지 않는다.

목록은 보여 주는 값이다. 실제로 빠지는 값은 홀드를 걸 때 결제 서버가 그 시각의 가격표로 정한다.
이 파일은 DB 도 네트워크도 모른다. 받아 오는 것은 app/billing/price_list.py 다.
"""

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

from app.catalog.steps import BASE_STEPS, NarrationSteps, steps_code

# 서술의 가격표 이름의 앞부분(narration.<이름표>.i<입력>.o<출력>)
PRICE_CODE_PREFIX = 'narration'

# 값의 글자. 결제 서버의 credit.Amount 가 만드는 모양이다("120", "0.0120")
Credits = Annotated[str, StringConstraints(pattern=r'^\d+(\.\d+)?$')]


class Tier(enum.StrEnum):
    """
    결제 서버 가격표의 등급. 결제에 쓰는 등급은 이것이 기준이다(model-pricing-plan 9-1).

    결제 서버가 모르는 등급을 보내면 목록 전체를 읽지 못한다(503).
    그래서 결제 서버는 게임 서버가 등급을 안 뒤에 그 줄을 넣는다.
    """

    # 가장 싼 모델의 묶음. 내는 방법은 standard 와 같다. 이벤트로 묶음째 내리거나 무료로 열려고 따로 둔다
    BASIC = 'basic'

    # 실버(무료 크레딧)를 먼저 쓰고, 모자라면 골드
    STANDARD = 'standard'
    # 골드(유료 크레딧)로만 낸다
    PREMIUM = 'premium'


class NextPriceBody(BaseModel):
    """응답의 다음에 바뀔 값. 모르는 칸은 버린다(결제 서버가 칸을 더해도 깨지지 않게)."""

    model_config = ConfigDict(extra='ignore')

    credits: Credits | None
    tier: Tier | None
    promo: bool | None = None
    effective_at: AwareDatetime


class PriceBody(BaseModel):
    """응답의 가격표 이름 하나."""

    model_config = ConfigDict(extra='ignore')

    code: str
    credits: Credits | None
    tier: Tier | None
    promo: bool | None = None
    next: NextPriceBody | None = None


class PriceListBody(BaseModel):
    """응답 전체."""

    model_config = ConfigDict(extra='ignore')

    prices: list[PriceBody]


@dataclass(frozen=True)
class Sale:
    """팔고 있는 값. credits 는 1인 1번의 값(글자)이다. promo 면 행사가다(끝나는 때와 그 뒤의 값은 다음 값)."""

    credits: str
    tier: Tier
    promo: bool = False


@dataclass(frozen=True)
class Change:
    """예약된 바뀜. sale 이 None 이면 effective_at 부터 판매를 멈춘다."""

    sale: Sale | None
    effective_at: datetime


@dataclass(frozen=True)
class Price:
    """가격표 이름 하나의 지금 값과 다음 값. current 가 None 이면 지금은 팔지 않는다."""

    code: str
    current: Sale | None
    next: Change | None = None


@dataclass(frozen=True)
class PriceBook:
    """
    가격 목록 전체. 가격표 이름으로 찾는다.

    free 는 결제 서버 없이 도는 서버(BILLING_URL 이 비었다)라는 뜻이다. 홀드를 걸지 않으니 값도 없다.
    """

    prices: Mapping[str, Price] = field(default_factory=dict)
    free: bool = False


# 결제 서버 없이 도는 서버의 목록
FREE_BOOK = PriceBook(free=True)


def narration_code(slug: str, steps: NarrationSteps = BASE_STEPS) -> str:
    """
    모델 이름표와 단계의 가격표 이름(narration.claude-sonnet-5-5.i1.o0). 이름표 문자열 그대로 넣는다(9절).

    단계는 입력·출력 옵션이다(#387, app/catalog/steps.py). 단계마다 결제 서버의 가격표에 줄이 따로 있다.
    """
    return f'{PRICE_CODE_PREFIX}.{slug}.{steps_code(steps)}'


def sale_of(credits: str | None, tier: Tier | None, promo: bool | None) -> Sale | None:
    """값과 등급으로 판매를 만든다. 둘 중 하나라도 없으면 팔지 않는 것이다. 행사가 표시가 비었으면 정가다."""
    if credits is None or tier is None:
        return None
    return Sale(credits=credits, tier=tier, promo=bool(promo))


def to_price(body: PriceBody) -> Price:
    """응답의 이름 하나를 값으로."""
    change = None
    if body.next is not None:
        sale = sale_of(body.next.credits, body.next.tier, body.next.promo)
        change = Change(sale=sale, effective_at=body.next.effective_at)
    return Price(code=body.code, current=sale_of(body.credits, body.tier, body.promo), next=change)


def parse_price_list(raw: bytes) -> PriceBook:
    """응답의 본문을 가격 목록으로. 모양이 틀리면 pydantic.ValidationError."""
    body = PriceListBody.model_validate_json(raw)
    return PriceBook(prices={price.code: to_price(price) for price in body.prices})


def price_at(price: Price, now: datetime) -> Price:
    """
    now 의 값. 예약된 바뀜의 시각이 지났으면 그것을 지금 값으로 갈아 끼운다.

    결제 서버의 목록은 1분쯤마다 다시 받는다. 그 사이에 바뀜의 시각이 지나도 늦게 보이지 않게 스스로 갈아 끼운다.
    """
    if price.next is None or now < price.next.effective_at:
        return price
    return Price(code=price.code, current=price.next.sale)
