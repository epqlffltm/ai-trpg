# trpg-server/app/rounds/round_price.py

"""
라운드를 열 때 앉은 사람에게 알리는 1인 1라운드의 값(#379).

값은 결제 서버의 가격 목록이 정한다(app/catalog/offers.py 의 find_offered). 게임 서버는 따로 계산하지 않는다.
알린 값은 라운드에 적고(announced_credits, announced_tier) 라운드를 연 이벤트(round_opened)와 라운드의 응답에 싣는다.
실제로 홀드한 값은 사람마다 청구에 적힌다(narration_charges.held_credits). 둘은 같은 가격 목록에서 나오므로 같다.
예외는 열고 홀드하기 사이에 결제 서버가 값을 바꾼 경우다(예약된 인상의 시각). 그때 실제 값은 청구의 것이다.

알리지 못하는 때는 비워 둔다(None). 결제 서버 없이 도는 서버(값이 없다), 모델이 없는 옛 테이블,
지금 팔지 않는 모델(홀드가 막히고 따로 알린다), 가격 목록을 받지 못한 때다. 라운드를 여는 것은 막지 않는다.

HTTP 를 모른다.
"""

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceList, PriceListUnavailable
from app.catalog import offers
from app.catalog.offers import OfferedModel
from app.catalog.steps import BASE_STEPS, NarrationSteps
from app.rounds.models import Round

logger = logging.getLogger(__name__)


async def price_of(
    session: AsyncSession, prices: PriceList, slug: str | None, now: datetime, steps: NarrationSteps = BASE_STEPS
) -> OfferedModel | None:
    """그 모델과 단계(#387)의 지금 값. 알릴 수 없으면 None. 가격 목록을 받지 못했으면 warning 을 남기고 None."""
    if slug is None:
        return None
    try:
        return await offers.find_offered(session, prices, slug, now, steps)
    except PriceListUnavailable:
        logger.warning('라운드의 값을 알리지 못했습니다. 가격 목록을 받지 못했습니다', extra={'model': slug})
        return None


def announce(round_: Round, found: OfferedModel | None) -> None:
    """라운드에 알린 값을 적는다. 값이 없으면 비운다."""
    round_.announced_credits = found.credits if found else None
    round_.announced_tier = str(found.tier) if found and found.tier else None


def price_payload(round_: Round) -> dict[str, str] | None:
    """이벤트에 싣는 알린 값. 비어 있으면 None."""
    if round_.announced_credits is None:
        return None
    return {'credits': round_.announced_credits, 'tier': round_.announced_tier}
