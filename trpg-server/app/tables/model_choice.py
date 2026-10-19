# trpg-server/app/tables/model_choice.py

"""
테이블을 만들 때 쓸 서술 모델을 정한다(유저 결정, 2026-10-18).

  1. 방장이 골랐으면 그 모델. 지금 고를 수 있어야 한다(app/tables/model_picker.py).
  2. 아니면 시나리오의 추천 모델(app/assets/scenarios/recommended_model.py). 지금 고를 수 있으면 그것.
  3. 추천 모델을 쓸 수 없으면 같은 회사의 대신 쓸 모델(app/catalog/offers.py 의 replacement_for).
     운영자가 정한 대체 모델이 먼저고, 없으면 같은 회사의 standard 중 가장 싼 모델이다.
  4. 셋 다 없으면 만들지 않는다(TableOptionError(narration_model)). 방장이 모델을 골라 다시 만든다.
     추천 모델이 없는 옛 시나리오와, 같은 회사에 대신할 모델이 없는 경우다.

가격 목록은 여기서 본다. 시나리오를 저장할 때는 모델 목록만 봤다. 팔지 않는 모델로 테이블을 만들지 않는다.
대신 쓴 것은 테이블을 만든 이벤트에 추천 모델과 함께 남긴다. 방장이 바뀐 것을 안다(몰래 바꾸지 않는다).

테이블 서비스를 불러오지 않는다. 테이블 서비스가 이것을 불러온다.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import offers
from app.catalog import repository as catalog
from app.tables.errors import TableOptionError
from app.tables.model_picker import ModelPicker, require_pickable

# 모델을 정하지 못했을 때 틀렸다고 알리는 입력의 칸
MODEL_FIELD = 'narration_model'


@dataclass(frozen=True)
class ModelChoice:
    """정한 모델과 시나리오의 추천 모델(없으면 None). 둘이 다르면 방장이 골랐거나 대신 쓴 것이다."""

    slug: str
    recommended: str | None


async def replacement_slug(session: AsyncSession, picker: ModelPicker, recommended: str) -> str | None:
    """쓸 수 없는 추천 모델 대신 쓸 같은 회사의 모델. 모델 목록에서 지워져 회사를 모르면 None."""
    model = await catalog.get_model(session, recommended)
    if model is None:
        return None
    found = await offers.find_replacement(session, picker.prices, model.vendor, picker.now, excluding=recommended)
    return found.slug if found else None


async def recommended_or_replacement(session: AsyncSession, picker: ModelPicker, recommended: str | None) -> str:
    """추천 모델을 지금 고를 수 있으면 그것, 아니면 대신 쓸 모델. 둘 다 없으면 TableOptionError."""
    if recommended is None:
        raise TableOptionError(MODEL_FIELD)
    if await offers.find_offered(session, picker.prices, recommended, picker.now) is not None:
        return recommended
    slug = await replacement_slug(session, picker, recommended)
    if slug is None:
        raise TableOptionError(MODEL_FIELD)
    return slug


async def choose_model(
    session: AsyncSession, picker: ModelPicker, chosen: str | None, recommended: str | None
) -> ModelChoice:
    """
    테이블의 서술 모델을 정한다. chosen 은 방장이 고른 모델, recommended 는 시나리오의 추천 모델이다.

    정하지 못하면 TableOptionError(narration_model).
    가격 목록을 받지 못했고 받아 둔 것도 없으면 PriceListUnavailable 이 그대로 올라간다(503).
    """
    if chosen is not None:
        await require_pickable(session, picker, chosen)
        return ModelChoice(chosen, recommended)
    return ModelChoice(await recommended_or_replacement(session, picker, recommended), recommended)
