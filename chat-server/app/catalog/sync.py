# chat-server/app/catalog/sync.py

"""
모델 목록의 원본 파일(ai_core/model_catalog.toml)을 이 서버의 표(ai_models, ai_model_costs)에 들여온다(#499).

게임 서버의 것(trpg-server/app/catalog/sync.py)을 줄여 옮겼다. 규칙이 같다. 회사의 대체 모델이 없는 것만 다르다.
story 서버가 생겨 세 벌이 되면 공용 코드로 올릴지 정한다.

파일이 원본이고 표는 그 사본에 이 서버의 스위치(켜짐, 성인 등급의 대화에 쓰기)를 더한 것이다.
들여오기는 몇 번을 해도 같다. 바뀐 것만 고친다.
  - 표에 없는 모델: 꺼진 채로 넣는다. 원가를 보고 평가 장면을 통과한 뒤에 사람이 켠다(scripts.models enable).
  - 표에 있는 모델: 보이는 이름, 회사, 분류, 받는 것, 은퇴일을 파일대로 고친다. 이 서버의 스위치는 건드리지 않는다.
  - API 모델 이름(날짜판)이 바뀌면 바꾼 일을 기록(ai_model_snapshots)하고 모델을 끈다.
    같은 상품이라도 말투가 바뀔 수 있어 평가 장면(말투 검사 포함)을 다시 통과한 뒤에 켠다.
  - 원가: 날마다 그날부터의 단가가 표에서 쓰는 값과 다르면 줄을 더한다. 표의 줄은 고치지도 지우지도 않는다.
    같은 날의 줄이 둘이면 나중에 적은 것이 이긴다(app/catalog/repository.py 의 latest_first).
    확인한 날만 바뀐 것은 더하지 않는다.
  - 파일에 없는 표의 모델은 그대로 둔다(대화와 청구 기록이 가리킨다). 알리기만 한다.
  - 창구는 바꾸지 않는다. 파일과 표의 창구가 다르면 거절한다(이름표를 새로 정한다).

한 번의 들여오기는 트랜잭션 하나다. 하나라도 거절되면 아무것도 바뀌지 않는다.
dry_run 이면 끝에 되돌린다(무엇이 바뀔지 보기만 한다).
모델마다 줄을 잠그고 고친다. 둘이 동시에 들여와도 날짜판 기록의 사슬(앞의 이름 → 새 이름)이 끊기지 않는다.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ai_core.catalog_file import CostEntry, ModelCatalog, ModelEntry
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository
from app.catalog.errors import CatalogConflictError, Conflict
from app.catalog.models import AiModel, AiModelCost, AiModelSnapshot

# 파일대로 고치는 칸들. 이름표와 창구(바꾸지 않는다), 날짜판(따로 기록한다), 이 서버의 스위치(켜짐, 성인)는 없다
SYNCED_FIELDS = (
    'display_name',
    'vendor',
    'grade',
    'supports_reasoning',
    'supports_temperature',
    'token_limit_field',
    'reasoning_style',
    'retires_on',
)

# 원가 단가 하나를 견주는 칸들. 확인한 날과 덧붙인 말은 견주지 않는다(값이 같으면 줄을 더하지 않는다)
PRICE_FIELDS = ('input_per_mtok', 'cached_input_per_mtok', 'cache_write_per_mtok', 'output_per_mtok')


@dataclass(frozen=True)
class SnapshotChange:
    """날짜판을 바꾼 모델 하나. 앞의 이름과 새 이름."""

    slug: str
    previous: str
    current: str


@dataclass
class SyncReport:
    """들여오기로 바뀐 것. dry_run 이면 바뀔 것이다."""

    added: list[str] = field(default_factory=list)
    changed: dict[str, list[str]] = field(default_factory=dict)
    switched: list[SnapshotChange] = field(default_factory=list)
    costs: list[tuple[str, date]] = field(default_factory=list)
    # 표에는 있지만 파일에 없는 모델. 지우지 않는다
    not_in_file: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """바뀐 것이 없나."""
        return not (self.added or self.changed or self.switched or self.costs)


def synced_values(entry: ModelEntry) -> dict[str, object]:
    """파일대로 고치는 칸과 그 값."""
    return {name: getattr(entry, name) for name in SYNCED_FIELDS}


def differing(model: AiModel, values: dict[str, object]) -> dict[str, object]:
    """표의 값과 다른 칸만."""
    return {name: value for name, value in values.items() if getattr(model, name) != value}


def apply_values(model: AiModel, values: dict[str, object]) -> None:
    """칸들을 고친다."""
    for name, value in values.items():
        setattr(model, name, value)


def new_model(entry: ModelEntry) -> AiModel:
    """파일의 모델로 표의 줄을 만든다. 꺼진 채다."""
    return AiModel(
        slug=entry.slug,
        provider=entry.provider,
        api_model_id=entry.api_model_id,
        enabled=False,
        **synced_values(entry),
    )


async def require_free_api_model(session: AsyncSession, entry: ModelEntry) -> None:
    """같은 창구의 그 API 모델을 다른 이름표가 쓰고 있으면 거절한다."""
    if await repository.api_model_taken(session, entry.provider, entry.api_model_id):
        raise CatalogConflictError(entry.slug, Conflict.API_MODEL_TAKEN)


def require_same_provider(model: AiModel, entry: ModelEntry) -> None:
    """창구는 바꾸지 않는다. 다르면 거절한다."""
    if model.provider != entry.provider:
        raise CatalogConflictError(entry.slug, Conflict.PROVIDER_CHANGED)


async def switch_snapshot(session: AsyncSession, model: AiModel, api_model_id: str) -> SnapshotChange:
    """날짜판을 바꾼다. 바꾼 일을 기록하고 모델을 끈다."""
    change = SnapshotChange(model.slug, model.api_model_id, api_model_id)
    snapshot = AiModelSnapshot(model_slug=model.slug, previous_api_model_id=change.previous, api_model_id=api_model_id)
    await repository.add_snapshot(session, snapshot)
    model.api_model_id = api_model_id
    model.enabled = False
    return change


def prices_of(cost: CostEntry | AiModelCost) -> tuple[Decimal | None, ...]:
    """견주는 단가들."""
    return tuple(getattr(cost, name) for name in PRICE_FIELDS)


def in_effect_by_day(history: list[AiModelCost]) -> dict[date, AiModelCost]:
    """날마다 그날부터 쓰는 단가. history 는 늦게 시작한 것, 같은 날이면 나중에 적은 것이 앞이다."""
    by_day: dict[date, AiModelCost] = {}
    for cost in history:
        by_day.setdefault(cost.effective_from, cost)
    return by_day


def costs_to_add(entry: ModelEntry, history: list[AiModelCost]) -> list[CostEntry]:
    """표에 더할 파일의 단가들. 그날부터 쓰는 표의 단가가 없거나 값이 다른 것이다."""
    by_day = in_effect_by_day(history)
    return [
        cost
        for cost in entry.costs
        if cost.effective_from not in by_day or prices_of(by_day[cost.effective_from]) != prices_of(cost)
    ]


async def add_costs(session: AsyncSession, slug: str, costs: list[CostEntry]) -> None:
    """단가들을 덧붙인다."""
    for cost in costs:
        await repository.add_cost(session, AiModelCost(model_slug=slug, **cost.model_dump()))


async def sync_existing(session: AsyncSession, model: AiModel, entry: ModelEntry, report: SyncReport) -> None:
    """표에 있는 모델을 파일대로 고친다. 모델의 줄은 잠가 두었다."""
    require_same_provider(model, entry)
    if model.api_model_id != entry.api_model_id:
        await require_free_api_model(session, entry)
        report.switched.append(await switch_snapshot(session, model, entry.api_model_id))
    changes = differing(model, synced_values(entry))
    if changes:
        apply_values(model, changes)
        report.changed[entry.slug] = list(changes)


async def sync_model(session: AsyncSession, entry: ModelEntry, report: SyncReport) -> None:
    """파일의 모델 하나를 들여온다. 없으면 넣고, 있으면 고치고, 모자란 단가를 더한다."""
    model = await repository.lock_model(session, entry.slug)
    if model is None:
        await require_free_api_model(session, entry)
        await repository.add_model(session, new_model(entry))
        report.added.append(entry.slug)
    else:
        await sync_existing(session, model, entry, report)
    costs = costs_to_add(entry, await repository.cost_history(session, entry.slug))
    await add_costs(session, entry.slug, costs)
    report.costs.extend((entry.slug, cost.effective_from) for cost in costs)


async def slugs_not_in(session: AsyncSession, catalog: ModelCatalog) -> list[str]:
    """표에는 있지만 파일에 없는 모델의 이름표들."""
    in_file = {entry.slug for entry in catalog.models}
    return [model.slug for model in await repository.list_models(session) if model.slug not in in_file]


async def sync_catalog(session: AsyncSession, catalog: ModelCatalog, dry_run: bool = False) -> SyncReport:
    """
    파일의 모델들을 표에 들여온다. 모두 되거나 하나도 되지 않는다. dry_run 이면 바뀔 것만 알리고 되돌린다.

    거절되면(창구가 바뀌었다, 다른 이름표가 그 API 모델을 쓴다) CatalogConflictError 이고 되돌린다.
    """
    report = SyncReport()
    try:
        for entry in catalog.models:
            await sync_model(session, entry, report)
        report.not_in_file = await slugs_not_in(session, catalog)
    except Exception:
        await session.rollback()
        raise
    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    return report
