# game-server/app/assets/scenarios/recommended_model.py

"""
시나리오의 추천 서술 모델. 제작자가 이 시나리오에 어울린다고 고른 모델이다(유저 결정, 2026-10-18).

  - 저장할 때 반드시 정한다. 정하지 않으면 시나리오를 저장하지 못한다(require_recommendable).
  - 고를 수 있는 범위는 서비스 중인 모델 전부다. premium 도 된다.
  - 저장할 때는 모델 목록만 본다(켜져 있고 은퇴하지 않았다). 가격 목록은 테이블을 만들 때 본다.
    결제 서버가 잠깐 죽어도 시나리오를 저장할 수 있어야 한다. 파는지는 테이블을 만드는 순간에 정해진다.
  - 판에 굳히지 않고 시나리오에 둔다. 모델을 쓸 수 있는지는 내용과 따로 바뀐다(공급자가 모델을 내린다).
    추천 모델을 바꾸려고 다시 게시하지 않아도 되고, 상태를 보여 주는 값과 테이블이 쓰는 값이 늘 같다.
  - 테이블을 만들 때 테이블로 복사한다(app/tables/model_choice.py). 쓸 수 없으면 같은 회사의 대체 모델로 바꾼다.

작성자 화면에 추천 모델의 상태를 보인다(model_status). 알림함이 생기기 전까지 이것이 작성자에게 알리는 방법이다.
  - ok: 쓸 수 있다.
  - retiring: 은퇴일이 정해졌다. 그날부터 대체 모델로 바뀐다.
  - unavailable: 꺼졌거나 은퇴했거나 모델 목록에 없다. 지금 테이블을 만들면 대체 모델로 바뀐다.
대체 모델(replacement)은 보여 주기용이다. 가격 목록을 받지 못하면 비운다. 테이블을 만들 때 다시 정한다.

HTTP 를 모른다.
"""

import enum
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceList, PriceListUnavailable
from app.catalog import offers
from app.catalog import repository as catalog
from app.catalog.models import AiModel
from app.catalog.rules import is_offered


class RecommendedModelError(Exception):
    """추천 서술 모델을 저장할 수 없다. 정하지 않았거나(missing) 서비스 중인 모델이 아니다(not_offered)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# 추천 모델을 정하지 않았다
MISSING = 'missing'
# 모델 목록에 없거나, 꺼졌거나, 은퇴했다
NOT_OFFERED = 'not_offered'


class ModelState(enum.StrEnum):
    """작성자 화면에 보이는 추천 모델의 상태."""

    OK = 'ok'
    RETIRING = 'retiring'
    UNAVAILABLE = 'unavailable'


@dataclass(frozen=True)
class ModelStatus:
    """추천 모델의 상태. replacement 는 대신 쓸 모델의 이름표다. 쓸 수 있는 동안(ok)은 늘 None 이다."""

    state: ModelState
    retires_on: date | None
    replacement: str | None


async def require_recommendable(session: AsyncSession, slug: str | None, today: date) -> None:
    """
    저장할 수 있는 추천 모델인지 확인한다. 아니면 RecommendedModelError.

    모델 목록만 본다. 켜져 있고 은퇴하지 않았으면 된다.
    """
    if slug is None:
        raise RecommendedModelError(MISSING)
    model = await catalog.get_model(session, slug)
    if model is None or not is_offered(model, today):
        raise RecommendedModelError(NOT_OFFERED)


def state_of(model: AiModel | None, today: date) -> ModelState:
    """모델 목록의 그 모델로 상태를 정한다. 쓸 수 없으면 unavailable, 은퇴일이 정해졌으면 retiring."""
    if model is None or not is_offered(model, today):
        return ModelState.UNAVAILABLE
    if model.retires_on is not None:
        return ModelState.RETIRING
    return ModelState.OK


async def replacement_of(session: AsyncSession, prices: PriceList, model: AiModel, now: datetime) -> str | None:
    """
    그 모델 대신 쓸 같은 회사의 모델의 이름표. 보여 주기용이라 가격 목록을 받지 못하면 None 이다.

    추천 모델 자신은 빼고 고른다. 은퇴를 앞둔 모델이 그 회사의 대체 모델이어도 자신으로 대신할 수는 없다.
    """
    try:
        found = await offers.find_replacement(session, prices, model.vendor, now, excluding=model.slug)
    except PriceListUnavailable:
        return None
    return found.slug if found else None


async def model_status(session: AsyncSession, prices: PriceList, slug: str | None, now: datetime) -> ModelStatus | None:
    """
    추천 모델의 상태. 추천 모델이 없으면(이 규칙 전에 만든 시나리오) None.

    모델 목록에서 지워진 모델은 회사를 알 수 없어 대신 쓸 모델을 고르지 못한다.
    """
    if slug is None:
        return None
    model = await catalog.get_model(session, slug)
    state = state_of(model, now.date())
    if state == ModelState.OK:
        return ModelStatus(state, None, None)
    replacement = await replacement_of(session, prices, model, now) if model else None
    return ModelStatus(state, model.retires_on if model else None, replacement)
