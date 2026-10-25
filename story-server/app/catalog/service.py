# story-server/app/catalog/service.py

"""
이 서버의 표에서 하는 모델 목록의 일. 켜기, 끄기, 성인 등급의 세션에 쓰기, 목록 보기.
고를 수 있는 모델과 그 값은 app/catalog/offers.py 다.
chat 서버의 것(chat-server/app/catalog/service.py)과 같다. 회사의 대체 모델이 없고 성인 스위치가 있다.

모델을 넣고 고치고 원가를 적는 일은 여기 없다. 원본 파일(ai_core/model_catalog.toml)을 고치고 들여온다
(app/catalog/sync.py). 켜짐과 성인 등급의 세션에 쓰기(allows_adult)는 이 서버만의 스위치라 파일에 없고 여기서 바꾼다.

HTTP 를 모른다. SQL 을 모른다. 일마다 commit 하나로 저장한다.
관리 명령(scripts/models.py)이 부른다. 나중에 관리 서버가 생기면 같은 함수들을 관리 API 로 연다.

잠그지 않는다. 부딪혀도 망가지는 것이 없다.
  - 원가는 덧붙이기만 하므로, 켤 때 본 "오늘의 단가가 있다"는 그 뒤에도 참이다.
  - 켜는 것과 들여오기(은퇴일, 날짜판)가 겹쳐도, 쓸 수 있나는 켜짐과 은퇴일을 함께 본다
    (ai_core/catalog_contract.py 의 is_offered). 날짜판이 바뀐 들여오기는 모델을 끄므로 나중에 끝난 쪽이 남는다.
"""

from dataclasses import dataclass
from datetime import date

from ai_core.catalog_contract import is_retired
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository
from app.catalog.choice import may_allow_adult
from app.catalog.errors import CatalogConflictError, Conflict, ModelNotFoundError
from app.catalog.models import AiModel, AiModelCost, AiModelSnapshot


@dataclass(frozen=True)
class CatalogEntry:
    """목록의 한 줄. 모델과 그날의 단가(없으면 None)."""

    model: AiModel
    cost: AiModelCost | None


@dataclass(frozen=True)
class ModelDetail:
    """모델 하나와 그 단가들(앞으로 쓸 것까지, 늦게 시작하는 것부터), 날짜판을 바꾼 일들(나중 것부터)."""

    model: AiModel
    costs: list[AiModelCost]
    snapshots: list[AiModelSnapshot]


async def require_model(session: AsyncSession, slug: str) -> AiModel:
    """그 이름표의 모델. 없으면 ModelNotFoundError."""
    model = await repository.get_model(session, slug)
    if model is None:
        raise ModelNotFoundError(slug)
    return model


async def enable_model(session: AsyncSession, slug: str, today: date) -> AiModel:
    """모델을 켠다. 은퇴하지 않았고 그날의 단가가 있어야 한다."""
    model = await require_model(session, slug)
    if is_retired(model, today):
        raise CatalogConflictError(slug, Conflict.RETIRED)
    if await repository.cost_on(session, slug, today) is None:
        raise CatalogConflictError(slug, Conflict.NO_COST)
    model.enabled = True
    await session.commit()
    return model


async def disable_model(session: AsyncSession, slug: str) -> AiModel:
    """모델을 끈다. 지우지 않는다."""
    model = await require_model(session, slug)
    model.enabled = False
    await session.commit()
    return model


async def allow_adult(session: AsyncSession, slug: str) -> AiModel:
    """모델을 성인 등급의 세션에 쓰게 한다. 약관이 성적인 콘텐츠를 막는 창구의 모델은 거절한다."""
    model = await require_model(session, slug)
    if not may_allow_adult(model):
        raise CatalogConflictError(slug, Conflict.ADULT_REFUSED)
    model.allows_adult = True
    await session.commit()
    return model


async def forbid_adult(session: AsyncSession, slug: str) -> AiModel:
    """모델을 성인 등급의 세션에 쓰지 않게 한다. 이미 그 모델을 고른 성인 세션는 다른 모델을 골라야 한다."""
    model = await require_model(session, slug)
    model.allows_adult = False
    await session.commit()
    return model


async def list_entries(session: AsyncSession, today: date) -> list[CatalogEntry]:
    """모든 모델과 그날의 단가."""
    models = await repository.list_models(session)
    costs = await repository.costs_on(session, today)
    return [CatalogEntry(model, costs.get(model.slug)) for model in models]


async def show_model(session: AsyncSession, slug: str) -> ModelDetail:
    """모델 하나와 그 단가들, 날짜판을 바꾼 일들."""
    model = await require_model(session, slug)
    costs = await repository.cost_history(session, slug)
    return ModelDetail(model, costs, await repository.snapshot_history(session, slug))
