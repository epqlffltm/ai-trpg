# game-server/app/catalog/service.py

"""
모델 목록을 다루는 일. 모델 넣기, 바꾸기, 원가 적기, 켜기, 끄기, 은퇴일 적기, 목록 보기.

HTTP 를 모른다. SQL 을 모른다. 일마다 commit 하나로 저장한다.
지금은 관리 명령(scripts/models.py)이 부른다. 나중에 관리 서버가 생기면 같은 함수들을 관리 API 로 연다.

잠그지 않는다. 부딪혀도 망가지는 것이 없다.
  - 원가는 덧붙이기만 하므로, 켤 때 본 "오늘의 단가가 있다"는 그 뒤에도 참이다.
  - 켜는 것과 은퇴일 적기가 겹쳐 켜진 채 은퇴해도, 쓸 수 있나는 둘을 함께 본다(app/catalog/rules.py 의 is_offered).
  - 같은 이름표나 같은 API 모델을 동시에 넣으면 DB 의 제약이 하나를 막는다(먼저 본 것은 친절한 안내일 뿐이다).
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository
from app.catalog.errors import CatalogConflictError, Conflict, InvalidModelError, ModelNotFoundError
from app.catalog.models import AiModel, AiModelCost, Provider, TokenLimitField
from app.catalog.rules import is_retired, token_field_problem
from app.catalog.schemas import CostCreate, ModelCreate, ModelUpdate


@dataclass(frozen=True)
class CatalogEntry:
    """목록의 한 줄. 모델과 그날의 단가(없으면 None)."""

    model: AiModel
    cost: AiModelCost | None


@dataclass(frozen=True)
class ModelDetail:
    """모델 하나와 그 단가들(앞으로 쓸 것까지, 늦게 시작하는 것부터)."""

    model: AiModel
    costs: list[AiModelCost]


async def require_model(session: AsyncSession, slug: str) -> AiModel:
    """그 이름표의 모델. 없으면 ModelNotFoundError."""
    model = await repository.get_model(session, slug)
    if model is None:
        raise ModelNotFoundError(slug)
    return model


async def require_new(session: AsyncSession, data: ModelCreate) -> None:
    """이름표와 API 모델이 아직 없어야 한다."""
    if await repository.get_model(session, data.slug) is not None:
        raise CatalogConflictError(data.slug, Conflict.SLUG_TAKEN)
    if await repository.api_model_taken(session, data.provider, data.api_model_id):
        raise CatalogConflictError(data.slug, Conflict.API_MODEL_TAKEN)


async def add_model(session: AsyncSession, data: ModelCreate) -> AiModel:
    """모델을 넣는다. 꺼진 채로 들어간다."""
    await require_new(session, data)
    model = AiModel(**data.model_dump(), enabled=False)
    await repository.add_model(session, model)
    await session.commit()
    return model


def check_token_field(model: AiModel, changes: dict[str, object]) -> None:
    """바꾼 뒤의 출력 상한의 칸이 모델의 창구에 맞아야 한다."""
    field = changes.get('token_limit_field', model.token_limit_field)
    problem = token_field_problem(Provider(model.provider), TokenLimitField(field) if field else None)
    if problem:
        raise InvalidModelError(f'{model.slug}: {problem}')


async def update_model(session: AsyncSession, slug: str, data: ModelUpdate) -> AiModel:
    """모델에서 적은 것만 바꾼다."""
    model = await require_model(session, slug)
    changes = data.changes()
    check_token_field(model, changes)
    for name, value in changes.items():
        setattr(model, name, value)
    await session.commit()
    return model


async def add_cost(session: AsyncSession, slug: str, data: CostCreate) -> AiModelCost:
    """모델의 원가 단가를 적는다. 앞의 단가는 그대로 남는다."""
    await require_model(session, slug)
    cost = AiModelCost(model_slug=slug, **data.model_dump())
    await repository.add_cost(session, cost)
    await session.commit()
    return cost


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


async def retire_model(session: AsyncSession, slug: str, on: date | None) -> AiModel:
    """은퇴일을 적는다. None 이면 은퇴일을 지운다(공급자가 내리는 날을 미뤘다)."""
    model = await require_model(session, slug)
    model.retires_on = on
    await session.commit()
    return model


async def list_entries(session: AsyncSession, today: date) -> list[CatalogEntry]:
    """모든 모델과 그날의 단가."""
    models = await repository.list_models(session)
    costs = await repository.costs_on(session, today)
    return [CatalogEntry(model, costs.get(model.slug)) for model in models]


async def show_model(session: AsyncSession, slug: str) -> ModelDetail:
    """모델 하나와 그 단가들."""
    model = await require_model(session, slug)
    return ModelDetail(model, await repository.cost_history(session, slug))
