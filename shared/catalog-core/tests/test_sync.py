# shared/catalog-core/tests/test_sync.py

"""
모델 목록의 파일을 표에 들여오기(catalog_core/sync.py)의 규칙을 메모리의 SQLite 로 본다.

보는 것.
  - 넣기: 표에 없는 모델은 꺼진 채 들어가고 서버만의 칸은 표의 기본값이다. 몇 번을 들여와도 같다.
  - 고치기: 파일의 칸대로 고치고 켜짐은 그대로다. 회사가 바뀔 때만 서버의 자리(on_vendor_change)를 부른다.
  - 날짜판: 바뀌면 기록이 남고 모델이 꺼진다.
  - 원가: 그날부터 쓰는 표의 단가와 값이 다를 때만 줄을 더한다. 확인한 날만 바뀐 것은 더하지 않는다.
  - 거절: 창구가 바뀌었거나 다른 이름표가 그 API 모델을 쓰면 거절하고 아무것도 바꾸지 않는다.
  - 파일에 없는 표의 모델은 지우지 않고 알린다. 미리 보기는 표를 바꾸지 않는다.
PostgreSQL 에만 있는 것(줄 잠금으로 둘이 동시에 들여오기, 표의 CHECK)은 쓰는 서버의 test_catalog_sync.py 가 본다.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from ai_core.catalog_contract import Grade, Provider, TokenLimitField
from ai_core.catalog_file import FORMAT, CostEntry, ModelCatalog, ModelEntry
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_core import repository
from catalog_core.errors import CatalogConflictError, Conflict
from catalog_core.sync import SnapshotChange, SyncReport, costs_to_add, sync_catalog
from catalog_core.tables import CatalogTables
from tests.tables import PLAIN, WITH_FALLBACK, AiModel, AiModelCost, AiModelSnapshot

TODAY = date(2026, 10, 17)


def price(input_price: str, starts: date = TODAY, checked_on: date = TODAY, **extra) -> CostEntry:
    """단가 하나. 출력은 입력의 다섯 배다."""
    return CostEntry(
        input_per_mtok=Decimal(input_price),
        output_per_mtok=Decimal(input_price) * 5,
        effective_from=starts,
        checked_on=checked_on,
        **extra,
    )


# 이 테스트의 모델. API 모델 이름은 지어낸 것이다
LUNA = ModelEntry(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    display_name='GPT-6 Luna',
    vendor='openai',
    grade=Grade.STANDARD,
    supports_reasoning=True,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
    costs=(price('0.1'),),
)


def catalog_of(*entries: ModelEntry) -> ModelCatalog:
    """모델들로 된 파일."""
    return ModelCatalog(format=FORMAT, models=entries)


async def put(session: AsyncSession, *entries: ModelEntry, tables: CatalogTables = PLAIN) -> SyncReport:
    return await sync_catalog(tables, session, catalog_of(*entries))


async def count(session: AsyncSession, table: type) -> int:
    counted = await session.scalar(select(func.count()).select_from(table))
    assert counted is not None
    return counted


async def fresh(session: AsyncSession, slug: str) -> AiModel:
    """세션에 남은 것이 아니라 DB 의 지금 값."""
    model = await session.get(AiModel, slug, populate_existing=True)
    assert model is not None
    return model


async def test_a_new_model_goes_in_disabled_with_its_costs(session: AsyncSession):
    report = await put(session, LUNA)

    model = await fresh(session, 'gpt-6-luna')
    assert report.added == ['gpt-6-luna']
    assert report.costs == [('gpt-6-luna', TODAY)]
    assert not model.enabled
    assert model.vendor_fallback is False
    assert (model.display_name, model.token_limit_field) == ('GPT-6 Luna', 'max_completion_tokens')
    assert (await repository.cost_on(PLAIN, session, 'gpt-6-luna', TODAY)).input_per_mtok == Decimal('0.1')


async def test_importing_twice_changes_nothing(session: AsyncSession):
    await put(session, LUNA)

    report = await put(session, LUNA)

    assert report.is_empty()
    assert await count(session, AiModelCost) == 1


async def test_file_fields_are_updated_and_the_switch_is_kept(session: AsyncSession):
    await put(session, LUNA)
    (await fresh(session, 'gpt-6-luna')).enabled = True
    await session.commit()

    retiring = TODAY + timedelta(days=30)
    report = await put(session, LUNA.model_copy(update={'display_name': 'GPT-6 Luna (new)', 'retires_on': retiring}))

    model = await fresh(session, 'gpt-6-luna')
    assert report.changed == {'gpt-6-luna': ['display_name', 'retires_on']}
    assert (model.display_name, model.retires_on, model.enabled) == ('GPT-6 Luna (new)', retiring, True)


@pytest.mark.parametrize(('tables', 'kept'), [(PLAIN, True), (WITH_FALLBACK, False)])
async def test_a_vendor_change_calls_the_server_hook(session: AsyncSession, tables: CatalogTables, kept: bool):
    await put(session, LUNA, tables=tables)
    (await fresh(session, 'gpt-6-luna')).vendor_fallback = True
    await session.commit()

    await put(session, LUNA.model_copy(update={'vendor': 'luna-labs'}), tables=tables)

    model = await fresh(session, 'gpt-6-luna')
    assert (model.vendor, model.vendor_fallback) == ('luna-labs', kept)


async def test_other_changes_do_not_call_the_server_hook(session: AsyncSession):
    await put(session, LUNA, tables=WITH_FALLBACK)
    (await fresh(session, 'gpt-6-luna')).vendor_fallback = True
    await session.commit()

    await put(session, LUNA.model_copy(update={'display_name': 'Luna'}), tables=WITH_FALLBACK)

    assert (await fresh(session, 'gpt-6-luna')).vendor_fallback is True


async def test_a_new_snapshot_is_recorded_and_disables_the_model(session: AsyncSession):
    await put(session, LUNA)
    (await fresh(session, 'gpt-6-luna')).enabled = True
    await session.commit()

    report = await put(session, LUNA.model_copy(update={'api_model_id': 'gpt-6-luna-2026-12-01'}))

    model = await fresh(session, 'gpt-6-luna')
    history = await repository.snapshot_history(PLAIN, session, 'gpt-6-luna')
    assert report.switched == [SnapshotChange('gpt-6-luna', 'gpt-6-luna-2026-09-22', 'gpt-6-luna-2026-12-01')]
    assert (model.api_model_id, model.enabled) == ('gpt-6-luna-2026-12-01', False)
    assert [(row.previous_api_model_id, row.api_model_id) for row in history] == [
        ('gpt-6-luna-2026-09-22', 'gpt-6-luna-2026-12-01')
    ]


async def test_a_changed_price_adds_a_row_and_keeps_the_old_one(session: AsyncSession):
    await put(session, LUNA)

    report = await put(session, LUNA.model_copy(update={'costs': (price('0.1'), price('0.2', TODAY + timedelta(1)))}))

    assert report.costs == [('gpt-6-luna', TODAY + timedelta(1))]
    assert await count(session, AiModelCost) == 2
    assert (await repository.cost_on(PLAIN, session, 'gpt-6-luna', TODAY)).input_per_mtok == Decimal('0.1')


def test_only_a_new_checked_on_adds_nothing():
    row = AiModelCost(model_slug='gpt-6-luna', **price('0.1').model_dump())
    rechecked = LUNA.model_copy(update={'costs': (price('0.1', checked_on=TODAY + timedelta(3)),)})

    assert costs_to_add(rechecked, [row]) == []


def test_the_latest_row_of_a_day_is_the_one_compared():
    older = AiModelCost(model_slug='gpt-6-luna', **price('0.1').model_dump())
    newer = AiModelCost(model_slug='gpt-6-luna', **price('0.3').model_dump())
    back_to_first = LUNA.model_copy(update={'costs': (price('0.1'),)})

    # history 는 나중에 적은 것이 앞이다. 되돌린 값도 줄을 더한다
    assert costs_to_add(back_to_first, [newer, older]) == [price('0.1')]


async def test_a_changed_provider_is_refused_and_nothing_changes(session: AsyncSession):
    await put(session, LUNA)

    moved = LUNA.model_copy(update={'provider': Provider.XAI, 'display_name': 'Moved'})
    with pytest.raises(CatalogConflictError) as refused:
        await put(session, moved)

    assert refused.value.reason is Conflict.PROVIDER_CHANGED
    assert (await fresh(session, 'gpt-6-luna')).display_name == 'GPT-6 Luna'


async def test_an_api_model_used_by_another_slug_is_refused(session: AsyncSession):
    await put(session, LUNA)

    twin = LUNA.model_copy(update={'slug': 'gpt-6-luna-twin'})
    with pytest.raises(CatalogConflictError) as refused:
        await put(session, twin)

    assert refused.value.reason is Conflict.API_MODEL_TAKEN
    assert await count(session, AiModel) == 1


async def test_a_snapshot_taken_by_another_slug_is_refused(session: AsyncSession):
    other = LUNA.model_copy(update={'slug': 'gpt-6-sol', 'api_model_id': 'gpt-6-sol-2026-09-22'})
    await put(session, LUNA, other)

    with pytest.raises(CatalogConflictError) as refused:
        await put(session, LUNA.model_copy(update={'api_model_id': 'gpt-6-sol-2026-09-22'}))

    assert refused.value.reason is Conflict.API_MODEL_TAKEN
    assert await count(session, AiModelSnapshot) == 0


async def test_models_missing_from_the_file_are_kept_and_reported(session: AsyncSession):
    other = LUNA.model_copy(update={'slug': 'gpt-6-sol', 'api_model_id': 'gpt-6-sol-2026-09-22'})
    await put(session, LUNA, other)

    report = await put(session, LUNA)

    assert report.not_in_file == ['gpt-6-sol']
    assert await count(session, AiModel) == 2


async def test_a_dry_run_reports_and_changes_nothing(session: AsyncSession):
    report = await sync_catalog(PLAIN, session, catalog_of(LUNA), dry_run=True)

    assert report.added == ['gpt-6-luna']
    assert await count(session, AiModel) == 0
