# game-server/app/catalog/offers.py

"""
방장이 테이블의 서술 모델로 고를 수 있는 모델들. 모델 목록(DB)과 결제 서버의 가격 목록을 맞춰 붙인다.

고를 수 있는 모델은 둘 다에 있어야 한다.
  - 모델 목록에서 켜져 있고 은퇴하지 않았다(rules.is_offered). 원가를 적고 평가를 통과해 켠 모델이다.
  - 가격 목록에 그 이름표의 가격표 이름(narration.<이름표>.i0.o0)이 있고 지금 팔고 있다.
    값이 바뀌는 예약(next)이 있으면 함께 내준다. 화면이 "12월 1일부터 240"처럼 미리 알린다(유저 결정, 2026-10-18).
판매가는 결제 서버만 안다. 게임 서버는 받은 값을 그대로 붙여 보여 줄 뿐이다.

결제 서버 없이 도는 서버(가격 목록이 free)는 켜진 모델을 모두 값 없이 내준다(유저 결정, 2026-10-18).
지금도 결제 서버가 없으면 홀드 없이 서술한다. 그 동작과 맞춘다. 로컬에서 모델 고르기를 시험할 수 있다.

결제에 쓰는 등급은 가격표의 등급(tier)이 기준이다(model-pricing-plan 9-1). 모델 목록의 분류(grade)는 보여 주기용이다.
둘이 다르면(premium 이 한쪽에만) 경고를 남긴다. 고르는 것은 막지 않는다.

시나리오의 추천 모델을 쓸 수 없으면 같은 회사의 다른 모델로 대신한다(replacement_for, 유저 결정, 2026-10-18).
  1. 운영자가 그 회사의 대체 모델로 정한 모델(scripts/models.py fallback)을 지금 고를 수 있으면 그것.
  2. 아니면 그 회사에서 지금 고를 수 있는 standard 중 가장 싼 모델. 값이 같으면 이름표 순서다.
     standard 는 가격표의 등급으로 본다.
     결제 서버 없이 도는 서버는 값도 등급도 없으니 모델 목록의 분류로 보고 이름표 순서다.
  3. 둘 다 없으면 없다. 새 테이블은 방장이 고른다.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceList
from app.billing.prices import Change, PriceBook, Tier, narration_code, price_at
from app.catalog import repository
from app.catalog.models import AiModel, Grade
from app.catalog.rules import is_offered

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelCard:
    """모델 목록의 모델 하나에서 고르는 화면에 필요한 것만 담은 값."""

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    enabled: bool
    retires_on: date | None
    # 운영자가 정한 그 회사의 대체 모델인가
    vendor_fallback: bool = False


@dataclass(frozen=True)
class OfferedModel:
    """
    고를 수 있는 모델 하나와 그 값. 결제 서버 없이 도는 서버면 credits 와 tier 가 None 이다.

    next 는 예약된 바뀜이다. next.sale 이 None 이면 그 시각부터 팔지 않는다.
    """

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    credits: str | None
    tier: Tier | None
    next: Change | None = None
    # 지금 값이 행사가인가. 행사가면 next 가 행사가 끝나는 때와 그 뒤의 값이다
    promo: bool = False
    # 운영자가 정한 그 회사의 대체 모델인가
    vendor_fallback: bool = False


@dataclass(frozen=True)
class Offering:
    """고를 수 있는 모델들. free 는 결제 서버 없이 도는 서버라 값이 없다는 뜻이다."""

    free: bool
    models: list[OfferedModel]


def to_card(model: AiModel) -> ModelCard:
    """DB 의 모델을 값으로."""
    return ModelCard(
        slug=model.slug,
        display_name=model.display_name,
        vendor=model.vendor,
        grade=Grade(model.grade),
        enabled=model.enabled,
        retires_on=model.retires_on,
        vendor_fallback=model.vendor_fallback,
    )


def free_offer(card: ModelCard) -> OfferedModel:
    """결제 서버 없이 도는 서버의 내줌. 값이 없다."""
    return OfferedModel(
        card.slug, card.display_name, card.vendor, card.grade, None, None, vendor_fallback=card.vendor_fallback
    )


def offer(card: ModelCard, book: PriceBook, now: datetime) -> OfferedModel | None:
    """
    그 모델을 지금 내줄 수 있으면 값을 붙여 돌려준다. 아니면 None.

    꺼졌거나 은퇴했거나, 가격 목록에 없거나, 지금 팔지 않으면(예약만 있거나 판매를 멈췄다) 내주지 않는다.
    """
    if not is_offered(card, now.date()):
        return None
    if book.free:
        return free_offer(card)
    price = book.prices.get(narration_code(card.slug))
    if price is None:
        return None
    price = price_at(price, now)
    if price.current is None:
        return None
    sale = price.current
    return OfferedModel(
        card.slug,
        card.display_name,
        card.vendor,
        card.grade,
        sale.credits,
        sale.tier,
        price.next,
        sale.promo,
        card.vendor_fallback,
    )


def offered_models(cards: Sequence[ModelCard], book: PriceBook, now: datetime) -> list[OfferedModel]:
    """내줄 수 있는 모델들. 회사, 보이는 이름 순서다(화면이 회사별로 묶는다)."""
    offers = [found for card in cards if (found := offer(card, book, now)) is not None]
    return sorted(offers, key=lambda found: (found.vendor, found.display_name))


def is_standard(found: OfferedModel) -> bool:
    """standard 인가. 가격표의 등급으로 본다. 등급이 없으면(결제 서버 없이 도는 서버) 모델 목록의 분류로 본다."""
    if found.tier is not None:
        return found.tier == Tier.STANDARD
    return found.grade == Grade.STANDARD


def cheapness(found: OfferedModel) -> tuple[Decimal, str]:
    """싼 순서의 열쇠. 값, 그다음 이름표. 값이 없으면 0 으로 보아 이름표 순서가 된다."""
    return Decimal(found.credits or 0), found.slug


def replacement_for(offers: Sequence[OfferedModel], vendor: str) -> OfferedModel | None:
    """
    그 회사의 대신 쓸 모델. 운영자가 정한 대체 모델이 먼저고, 없으면 standard 중 가장 싼 모델이다. 없으면 None.

    offers 는 지금 고를 수 있는 모델들이다(offered_models). 고를 수 없는 대체 모델은 이미 빠져 있다.
    """
    same_vendor = [found for found in offers if found.vendor == vendor]
    chosen = next((found for found in same_vendor if found.vendor_fallback), None)
    if chosen is not None:
        return chosen
    standards = [found for found in same_vendor if is_standard(found)]
    return min(standards, key=cheapness, default=None)


def grade_disagrees(found: OfferedModel) -> bool:
    """모델 목록의 분류와 가격표의 등급이 다른가. premium 이 한쪽에만 있으면 다르다. 값이 없으면 견주지 않는다."""
    if found.tier is None:
        return False
    return (found.grade == Grade.PREMIUM) != (found.tier == Tier.PREMIUM)


def warn_disagreements(offers: Sequence[OfferedModel]) -> None:
    """분류와 등급이 다른 모델마다 경고를 남긴다. 결제는 가격표의 등급대로 되니 고르는 것은 막지 않는다."""
    for found in offers:
        if grade_disagrees(found):
            logger.warning(
                '모델 목록의 분류와 결제 서버 가격표의 등급이 다르다. 결제는 가격표의 등급대로 된다',
                extra={'model': found.slug, 'grade': str(found.grade), 'tier': str(found.tier)},
            )


async def find_offered(session: AsyncSession, prices: PriceList, slug: str, now: datetime) -> OfferedModel | None:
    """
    그 이름표의 모델을 지금 고를 수 있으면 값을 붙여 돌려준다. 모델 목록에 없거나 고를 수 없으면 None.

    방장이 테이블의 모델을 고를 때 쓴다(app/tables/model_picker.py). 목록(list_offered)과 같은 규칙이다.
    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다.
    """
    model = await repository.get_model(session, slug)
    if model is None:
        return None
    return offer(to_card(model), await prices.book(), now)


async def find_replacement(
    session: AsyncSession, prices: PriceList, vendor: str, now: datetime, excluding: str
) -> OfferedModel | None:
    """
    그 회사의 대신 쓸 모델(replacement_for). 모델 목록과 가격 목록을 읽어 지금 고를 수 있는 모델 안에서 고른다.

    excluding 은 대신하려는 모델이다. 그 모델은 후보에서 뺀다.
    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다.
    """
    cards = [to_card(model) for model in await repository.list_models(session) if model.slug != excluding]
    return replacement_for(offered_models(cards, await prices.book(), now), vendor)


async def list_offered(session: AsyncSession, prices: PriceList, now: datetime) -> Offering:
    """
    방장이 고를 수 있는 모델들. 모델 목록을 DB 에서 읽고, 가격 목록을 받아(받아 둔 것) 맞춰 붙인다.

    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다.
    """
    cards = [to_card(model) for model in await repository.list_models(session)]
    book = await prices.book()
    offers = offered_models(cards, book, now)
    warn_disagreements(offers)
    return Offering(free=book.free, models=offers)
