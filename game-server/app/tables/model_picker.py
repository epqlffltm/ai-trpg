# game-server/app/tables/model_picker.py

"""
방장이 테이블의 서술 모델로 고른 이름표가 지금 고를 수 있는 것인지 확인한다.

고를 수 있는 모델은 GET /tables/narration-models 의 목록과 같다(app/catalog/offers.py).
모델 목록에서 켜져 있고 은퇴하지 않았고, 결제 서버가 지금 판다. 결제 서버 없이 도는 서버면 켜진 모델 모두다.

모델을 고르지 않으면(None) 서버의 기본(서술 등급, app/rounds/tiers.py)으로 서술한다. 확인할 것이 없다.

테이블을 만들 때(app/tables/service.py)와 바꿀 때(app/tables/narration_models.py) 함께 쓴다.
테이블 서비스를 불러오지 않는다. 테이블 서비스가 이것을 불러온다.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceList
from app.catalog import offers
from app.tables.state import require_model_offered


@dataclass(frozen=True)
class ModelPicker:
    """고를 수 있는지 볼 때 쓰는 가격 목록과 지금 시각. 요청마다 라우터가 만든다."""

    prices: PriceList
    now: datetime


async def require_pickable(session: AsyncSession, picker: ModelPicker | None, slug: str | None) -> None:
    """
    고를 수 있는 모델인지 확인한다. 아니면 TableOptionError(narration_model).

    slug 가 None 이면 서버의 기본으로 서술한다는 뜻이라 확인하지 않는다.
    picker 가 None 이면 확인할 방법이 없으니 모델을 고르지 못한다.
    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다(503).
    """
    if slug is None:
        return
    found = await offers.find_offered(session, picker.prices, slug, picker.now) if picker else None
    require_model_offered(found)
