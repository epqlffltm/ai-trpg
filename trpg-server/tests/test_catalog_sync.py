# trpg-server/tests/test_catalog_sync.py

"""
모델 목록의 파일을 표에 들여오기(app/catalog/sync.py)를 검증한다.
파일의 모양은 ai-core 의 tests/test_catalog_file.py 가 본다.

보는 것.
  - 넣기: 표에 없는 모델은 꺼진 채 들어간다. 몇 번을 들여와도 같다.
  - 고치기: 파일의 칸대로 고치고 켜짐은 그대로다. 회사가 바뀌면 대체 모델 표시를 내린다. 은퇴일도 파일대로다.
  - 날짜판: 바뀌면 기록이 남고 모델이 꺼진다. 같은 상품이라 값은 그대로이고 다시 켤 수 있다.
  - 원가: 그날부터 쓰는 표의 단가와 값이 다를 때만 줄을 더한다. 고친 값을 되돌려도 더한다.
    확인한 날만 바뀐 것은 더하지 않는다.
  - 거절: 창구가 바뀌었거나 다른 이름표가 그 API 모델을 쓰면 거절하고 아무것도 바꾸지 않는다.
  - 파일에 없는 표의 모델은 지우지 않고 알린다. 미리 보기는 표를 바꾸지 않는다.
  - 둘이 동시에 들여와도 날짜판 기록의 사슬이 이어진다.
  - 저장소의 파일(ai_core/model_catalog.toml)이 표의 제약을 모두 지나 들어간다.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest
from ai_core.catalog_contract import Grade, Provider, ReasoningStyle, TokenLimitField
from ai_core.catalog_file import CostEntry, ModelEntry, load_catalog
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository, service, sync
from app.catalog.errors import CatalogConflictError, Conflict
from app.catalog.models import AiModel, AiModelCost, AiModelSnapshot
from app.catalog.sync import SnapshotChange, sync_catalog
from tests.catalog_rows import catalog_of, put_models

pytestmark = pytest.mark.usefixtures('empty_catalog')

TODAY = date(2026, 10, 17)
NEXT_LUNA = 'gpt-6-luna-2026-12-01'


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
OPUS = ModelEntry(
    slug='claude-opus-5-5',
    provider=Provider.ANTHROPIC,
    api_model_id='claude-opus-5-5-20260901',
    display_name='Claude Opus 5.5',
    vendor='anthropic',
    grade=Grade.PREMIUM,
    supports_reasoning=True,
    supports_temperature=False,
    reasoning_style=ReasoningStyle.ALWAYS,
)


def luna_with(**changes) -> ModelEntry:
    """LUNA 에서 몇 칸만 바꾼 것. 모양을 다시 본다."""
    return ModelEntry(**{**LUNA.model_dump(), **changes})


async def fresh_model(session: AsyncSession, slug: str) -> AiModel:
    """DB 에 저장된 모델을 새로 읽는다."""
    session.expire_all()
    return await session.scalar(select(AiModel).where(AiModel.slug == slug))


async def cost_rows(session: AsyncSession, slug: str) -> list[tuple[date, Decimal]]:
    """그 모델의 단가 줄들(시작일, 입력). 적은 순서다."""
    query = select(AiModelCost.effective_from, AiModelCost.input_per_mtok).where(AiModelCost.model_slug == slug)
    return [tuple(row) for row in await session.execute(query.order_by(AiModelCost.id))]


async def enabled_luna(session: AsyncSession) -> None:
    """들여오고 켠 LUNA."""
    await put_models(session, LUNA)
    await service.enable_model(session, 'gpt-6-luna', TODAY)


# --- 넣기 ---


async def test_a_new_model_comes_in_disabled_with_its_costs(session: AsyncSession):
    report = await put_models(session, LUNA, OPUS)

    model = await fresh_model(session, 'gpt-6-luna')
    assert (model.enabled, model.vendor_fallback, model.api_model_id, model.grade, model.token_limit_field) == (
        False,
        False,
        'gpt-6-luna-2026-09-22',
        'standard',
        'max_completion_tokens',
    )
    assert (model.supports_reasoning, model.supports_temperature, model.retires_on) == (True, True, None)
    assert (report.added, report.costs, report.changed, report.switched) == (
        ['gpt-6-luna', 'claude-opus-5-5'],
        [('gpt-6-luna', TODAY)],
        {},
        [],
    )
    assert await cost_rows(session, 'gpt-6-luna') == [(TODAY, Decimal('0.1'))]


async def test_syncing_again_changes_nothing(session: AsyncSession):
    await put_models(session, LUNA, OPUS)

    report = await put_models(session, LUNA, OPUS)

    assert report.is_empty()
    assert await cost_rows(session, 'gpt-6-luna') == [(TODAY, Decimal('0.1'))]


# --- 고치기 ---


async def test_the_fields_follow_the_file_and_the_switch_stays(session: AsyncSession):
    await enabled_luna(session)

    report = await put_models(session, luna_with(display_name='루나', supports_temperature=False, grade=Grade.BASIC))

    model = await fresh_model(session, 'gpt-6-luna')
    assert (model.display_name, model.supports_temperature, model.grade, model.enabled) == (
        '루나',
        False,
        'basic',
        True,
    )
    assert report.changed == {'gpt-6-luna': ['display_name', 'grade', 'supports_temperature']}


async def test_the_reasoning_style_follows_the_file(session: AsyncSession):
    await put_models(session, OPUS)

    await put_models(session, ModelEntry(**{**OPUS.model_dump(), 'reasoning_style': ReasoningStyle.ADAPTIVE}))

    assert (await fresh_model(session, 'claude-opus-5-5')).reasoning_style == 'adaptive'


async def test_the_retirement_day_follows_the_file(session: AsyncSession):
    await enabled_luna(session)

    await put_models(session, luna_with(retires_on=date(2027, 6, 1)))
    set_day = (await fresh_model(session, 'gpt-6-luna')).retires_on
    await put_models(session, LUNA)

    # 공급자가 내리는 날을 미루면 파일에서 지우고 다시 들여온다
    assert (set_day, (await fresh_model(session, 'gpt-6-luna')).retires_on) == (date(2027, 6, 1), None)
    assert (await fresh_model(session, 'gpt-6-luna')).enabled


async def test_moving_vendor_drops_the_fallback(session: AsyncSession):
    await put_models(session, LUNA)
    await service.set_fallback(session, 'gpt-6-luna', TODAY)
    await put_models(session, luna_with(display_name='루나'))
    kept = (await fresh_model(session, 'gpt-6-luna')).vendor_fallback

    await put_models(session, luna_with(vendor='other'))

    # 대체 모델은 회사마다 정한다. 다른 회사로 옮기면 옛 회사의 표시를 들고 가지 않는다
    assert (kept, (await fresh_model(session, 'gpt-6-luna')).vendor_fallback) == (True, False)


# --- 날짜판 ---


async def test_a_new_snapshot_is_recorded_and_disables_the_model(session: AsyncSession):
    await enabled_luna(session)

    report = await put_models(session, luna_with(api_model_id=NEXT_LUNA))

    model = await fresh_model(session, 'gpt-6-luna')
    assert (model.api_model_id, model.enabled) == (NEXT_LUNA, False)
    assert report.switched == [SnapshotChange('gpt-6-luna', 'gpt-6-luna-2026-09-22', NEXT_LUNA)]
    assert report.changed == {}
    # 같은 상품이라 값은 그대로다. 평가를 다시 통과하면 그대로 켤 수 있다
    await service.enable_model(session, 'gpt-6-luna', TODAY)


async def test_the_switches_make_a_chain(session: AsyncSession):
    await put_models(session, LUNA)
    await put_models(session, luna_with(api_model_id=NEXT_LUNA))
    await put_models(session, luna_with(api_model_id='gpt-6-luna-2027-03-01'))

    detail = await service.show_model(session, 'gpt-6-luna')

    # 나중에 바꾼 것부터
    assert [(row.previous_api_model_id, row.api_model_id) for row in detail.snapshots] == [
        (NEXT_LUNA, 'gpt-6-luna-2027-03-01'),
        ('gpt-6-luna-2026-09-22', NEXT_LUNA),
    ]


async def test_syncs_at_the_same_time_keep_the_chain(
    app: FastAPI, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    await put_models(session, LUNA)
    record = sync.switch_snapshot

    async def slow_switch(*args):
        # 읽고 나서 잠깐 쉰다. 잠그지 않으면 그사이에 다른 쪽도 옛 이름을 읽는다
        await asyncio.sleep(0.05)
        return await record(*args)

    monkeypatch.setattr(sync, 'switch_snapshot', slow_switch)

    async def sync_to(api_model_id: str) -> None:
        async with app.state.session_factory() as own:
            await sync_catalog(own, catalog_of(luna_with(api_model_id=api_model_id)))

    await asyncio.gather(sync_to(NEXT_LUNA), sync_to('gpt-6-luna-2027-03-01'))

    # 모델의 줄을 잠그므로 뒤에 바꾼 쪽은 앞에서 바꾼 이름을 "앞의 이름"으로 적는다
    session.expire_all()
    detail = await service.show_model(session, 'gpt-6-luna')
    later, earlier = detail.snapshots
    assert earlier.previous_api_model_id == LUNA.api_model_id
    assert later.previous_api_model_id == earlier.api_model_id
    assert detail.model.api_model_id == later.api_model_id


# --- 원가 ---


async def test_a_new_day_adds_a_cost(session: AsyncSession):
    await put_models(session, LUNA)
    later = TODAY + timedelta(days=30)

    report = await put_models(session, luna_with(costs=(price('0.1'), price('0.2', later, note='값을 올린다'))))

    assert report.costs == [('gpt-6-luna', later)]
    assert await cost_rows(session, 'gpt-6-luna') == [(TODAY, Decimal('0.1')), (later, Decimal('0.2'))]
    assert (await repository.cost_on(session, 'gpt-6-luna', later)).note == '값을 올린다'


async def test_a_corrected_price_is_appended_and_wins(session: AsyncSession):
    await put_models(session, LUNA)

    await put_models(session, luna_with(costs=(price('0.15'),)))
    corrected = await repository.cost_on(session, 'gpt-6-luna', TODAY)
    await put_models(session, LUNA)
    reverted = await repository.cost_on(session, 'gpt-6-luna', TODAY)

    # 표의 줄은 고치지 않는다. 같은 날의 줄을 더하고 나중 것이 이긴다. 되돌려도 다시 더한다
    assert (corrected.input_per_mtok, reverted.input_per_mtok) == (Decimal('0.15'), Decimal('0.1'))
    assert len(await cost_rows(session, 'gpt-6-luna')) == 3


@pytest.mark.parametrize(
    'changed',
    [
        {'cached_input_per_mtok': Decimal('0.01')},
        {'cache_write_per_mtok': Decimal('0.2')},
        {'output_per_mtok': Decimal('0.6')},
    ],
    ids=['cached-input', 'cache-write', 'output'],
)
async def test_any_changed_price_adds_a_row(session: AsyncSession, changed: dict):
    await put_models(session, LUNA)

    report = await put_models(session, luna_with(costs=(CostEntry(**{**price('0.1').model_dump(), **changed}),)))

    assert report.costs == [('gpt-6-luna', TODAY)]


async def test_a_new_check_day_alone_adds_nothing(session: AsyncSession):
    await put_models(session, LUNA)

    report = await put_models(session, luna_with(costs=(price('0.1', checked_on=TODAY + timedelta(days=3)),)))

    assert report.is_empty()


async def test_a_cost_dropped_from_the_file_stays(session: AsyncSession):
    await put_models(session, LUNA)

    await put_models(session, luna_with(costs=()))

    assert await cost_rows(session, 'gpt-6-luna') == [(TODAY, Decimal('0.1'))]


# --- 거절 ---


async def test_a_changed_provider_is_refused_and_nothing_changes(session: AsyncSession):
    await put_models(session, LUNA, OPUS)
    moved = ModelEntry(
        **{**OPUS.model_dump(), 'provider': Provider.GEMINI, 'reasoning_style': ReasoningStyle.LEVEL_LOW}
    )

    with pytest.raises(CatalogConflictError) as caught:
        await put_models(session, luna_with(display_name='루나'), moved)

    # 앞의 모델을 고친 것도 되돌린다
    assert caught.value.reason == Conflict.PROVIDER_CHANGED
    assert (await fresh_model(session, 'gpt-6-luna')).display_name == 'GPT-6 Luna'


async def test_an_api_model_another_slug_uses_is_refused(session: AsyncSession):
    await put_models(session, LUNA)

    with pytest.raises(CatalogConflictError) as caught:
        await put_models(session, luna_with(slug='luna-again'))

    assert caught.value.reason == Conflict.API_MODEL_TAKEN
    assert await fresh_model(session, 'luna-again') is None


async def test_a_snapshot_another_model_uses_is_refused(session: AsyncSession):
    await put_models(session, LUNA, luna_with(slug='gpt-6-luna-mini', api_model_id=NEXT_LUNA))

    with pytest.raises(CatalogConflictError) as caught:
        await put_models(session, luna_with(api_model_id=NEXT_LUNA))

    assert caught.value.reason == Conflict.API_MODEL_TAKEN
    assert (await service.show_model(session, 'gpt-6-luna')).snapshots == []


async def test_the_same_api_model_id_on_another_provider_is_a_different_model(session: AsyncSession):
    await put_models(session, LUNA)

    await put_models(session, luna_with(slug='luna-local', provider=Provider.LOCAL, grade=Grade.BASIC))

    assert len(await repository.list_models(session)) == 2


# --- 파일에 없는 것, 미리 보기 ---


async def test_models_missing_from_the_file_stay(session: AsyncSession):
    await put_models(session, LUNA, OPUS)

    report = await put_models(session, LUNA)

    assert report.not_in_file == ['claude-opus-5-5']
    assert await fresh_model(session, 'claude-opus-5-5') is not None


async def test_a_dry_run_reports_and_keeps_the_table(session: AsyncSession):
    await put_models(session, LUNA)

    report = await sync_catalog(session, catalog_of(luna_with(api_model_id=NEXT_LUNA), OPUS), dry_run=True)

    assert (report.added, len(report.switched)) == (['claude-opus-5-5'], 1)
    assert (await fresh_model(session, 'gpt-6-luna')).api_model_id == LUNA.api_model_id
    assert await fresh_model(session, 'claude-opus-5-5') is None
    assert await session.scalar(select(func.count()).select_from(AiModelSnapshot)) == 0


# --- 저장소의 파일 ---


async def test_the_repository_file_fits_the_table(session: AsyncSession):
    catalog = load_catalog()

    report = await sync_catalog(session, catalog)

    # 표의 CHECK(창구, 분류, 칸, 방식)와 단가의 자릿수를 모두 지난다. 다시 들여오면 바뀌는 것이 없다
    assert len(report.added) == len(catalog.models) > 0
    assert (await sync_catalog(session, catalog)).is_empty()
