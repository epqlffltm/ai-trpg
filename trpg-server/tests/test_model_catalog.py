# trpg-server/tests/test_model_catalog.py

"""
이 서버의 표에서 하는 모델 목록의 일(app/catalog/service.py, repository.py, rules.py)을 검증한다.
파일의 모양은 ai-core 의 tests/test_catalog_file.py 가, 파일을 들여오기는 tests/test_catalog_sync.py 가,
관리 명령(scripts/models.py)은 tests/test_models_script.py 가 본다.

"오늘"은 테스트가 정한다. 실제 시계를 읽지 않는다.

셋을 본다.
  - 판단: 생각을 끌 수 없나, 은퇴, 쓸 수 있나, 1라운드 원가 어림.
  - 켜고 끄기: 켜려면 원가가 있고 은퇴하지 않아야 한다. 없는 모델은 찾지 못한다.
  - 원가: 덧붙이기만 한다. 그날의 단가는 그날 이전에 시작한 것 중 가장 늦은 것, 같은 날이면 나중에 적은 것이다.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from ai_core.catalog_contract import (
    Grade,
    Provider,
    ReasoningStyle,
    TokenLimitField,
    always_thinks,
    is_offered,
    is_retired,
)
from ai_core.catalog_file import CostEntry, ModelEntry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import repository, service
from app.catalog.errors import CatalogConflictError, Conflict, ModelNotFoundError
from app.catalog.models import AiModel, AiModelCost
from app.catalog.rules import round_cost_usd
from tests.catalog_rows import add_cost, put_models, retire

pytestmark = pytest.mark.usefixtures('empty_catalog')

TODAY = date(2026, 10, 17)

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
)
OPUS = ModelEntry(
    slug='claude-opus-5-5',
    provider=Provider.ANTHROPIC,
    api_model_id='claude-opus-5-5-20260901',
    display_name='Claude Opus 5.5',
    vendor='anthropic',
    grade=Grade.PREMIUM,
    supports_temperature=False,
    reasoning_style=ReasoningStyle.ALWAYS,
)


def cost(input_price: str = '0.1', output_price: str = '0.5', starts: date = TODAY, **extra) -> CostEntry:
    """단가 하나. 확인한 날은 오늘이다."""
    return CostEntry(
        input_per_mtok=Decimal(input_price),
        output_per_mtok=Decimal(output_price),
        effective_from=starts,
        checked_on=TODAY,
        **extra,
    )


async def fresh_model(session: AsyncSession, slug: str) -> AiModel:
    """DB 에 저장된 모델을 새로 읽는다."""
    session.expire_all()
    return await session.scalar(select(AiModel).where(AiModel.slug == slug))


# --- 판단 ---


@pytest.mark.parametrize(
    ('style', 'always'),
    [
        (ReasoningStyle.ALWAYS, True),
        (ReasoningStyle.LEVEL_MINIMAL, True),
        (ReasoningStyle.LEVEL_LOW, True),
        (ReasoningStyle.BUDGET_MIN, True),
        (ReasoningStyle.ADAPTIVE, False),
        (ReasoningStyle.BETWEEN_TOOLS, False),
        (ReasoningStyle.BUDGET, False),
        (ReasoningStyle.THINKING_TYPE, False),
        (None, False),
    ],
)
def test_the_styles_that_cannot_stop_thinking(style: ReasoningStyle | None, always: bool):
    # 이 모델들은 판매가와 출력 상한에 생각의 몫을 넣는다
    assert always_thinks(style) is always


def model_row(enabled: bool = True, retires_on: date | None = None) -> AiModel:
    """DB 에 넣지 않은 모델 한 줄."""
    return AiModel(**LUNA.model_dump(exclude={'costs', 'retires_on'}), enabled=enabled, retires_on=retires_on)


def test_a_model_retires_on_its_retirement_day():
    model = model_row(retires_on=TODAY)

    assert is_retired(model, TODAY)
    assert not is_retired(model, TODAY - timedelta(days=1))


def test_a_model_without_a_retirement_day_never_retires():
    assert not is_retired(model_row(), date(2099, 1, 1))


@pytest.mark.parametrize(
    ('enabled', 'retires_on', 'offered'),
    [(True, None, True), (False, None, False), (True, TODAY, False), (True, TODAY + timedelta(days=1), True)],
)
def test_a_model_is_offered_when_enabled_and_not_retired(enabled: bool, retires_on: date | None, offered: bool):
    assert is_offered(model_row(enabled, retires_on), TODAY) is offered


def test_a_round_costs_twelve_thousand_inputs_and_twelve_hundred_outputs():
    # GPT-6 Luna: $0.1/$0.5 → 0.0012 + 0.0006. 1500원이면 2.7원이다(model-pricing-plan 의 표와 같다)
    row = AiModelCost(input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'))

    assert round_cost_usd(row) == Decimal('0.0018')


# --- 모델 ---


@pytest.mark.parametrize('call', ['enable', 'disable', 'show', 'fallback', 'clear'])
async def test_unknown_models_are_not_found(session: AsyncSession, call: str):
    calls = {
        'enable': lambda: service.enable_model(session, 'nothing', TODAY),
        'disable': lambda: service.disable_model(session, 'nothing'),
        'show': lambda: service.show_model(session, 'nothing'),
        'fallback': lambda: service.set_fallback(session, 'nothing', TODAY),
        'clear': lambda: service.clear_fallback(session, 'nothing'),
    }

    with pytest.raises(ModelNotFoundError):
        await calls[call]()


async def test_a_model_without_a_cost_cannot_be_enabled(session: AsyncSession):
    await put_models(session, LUNA)

    with pytest.raises(CatalogConflictError) as caught:
        await service.enable_model(session, 'gpt-6-luna', TODAY)
    assert caught.value.reason == Conflict.NO_COST


async def test_a_cost_that_starts_later_does_not_count_for_enabling(session: AsyncSession):
    await put_models(session, LUNA)
    await add_cost(session, 'gpt-6-luna', cost(starts=TODAY + timedelta(days=1)))

    with pytest.raises(CatalogConflictError):
        await service.enable_model(session, 'gpt-6-luna', TODAY)


async def test_a_model_with_a_cost_can_be_enabled_and_disabled(session: AsyncSession):
    await put_models(session, LUNA)
    await add_cost(session, 'gpt-6-luna', cost())

    await service.enable_model(session, 'gpt-6-luna', TODAY)
    assert (await fresh_model(session, 'gpt-6-luna')).enabled

    await service.disable_model(session, 'gpt-6-luna')
    assert not (await fresh_model(session, 'gpt-6-luna')).enabled


async def test_a_retired_model_cannot_be_enabled(session: AsyncSession):
    await put_models(session, LUNA)
    await add_cost(session, 'gpt-6-luna', cost())
    await retire(session, 'gpt-6-luna', TODAY)

    with pytest.raises(CatalogConflictError) as caught:
        await service.enable_model(session, 'gpt-6-luna', TODAY)
    assert caught.value.reason == Conflict.RETIRED


# --- 원가 ---


async def test_costs_are_appended_and_all_kept(session: AsyncSession):
    await put_models(session, LUNA)
    await add_cost(session, 'gpt-6-luna', cost('0.1', '0.5', TODAY - timedelta(days=30)))
    await add_cost(session, 'gpt-6-luna', cost('0.2', '1', TODAY, note='값을 올렸다'))

    detail = await service.show_model(session, 'gpt-6-luna')

    # 늦게 시작하는 것부터
    assert [(row.input_per_mtok, row.note) for row in detail.costs] == [
        (Decimal('0.2'), '값을 올렸다'),
        (Decimal('0.1'), None),
    ]


async def test_the_cost_of_a_day_is_the_latest_that_started(session: AsyncSession):
    await put_models(session, LUNA)
    # GPT-5.6 Sol 처럼 행사가 끝나는 날의 값을 미리 적어 둔다
    await add_cost(session, 'gpt-6-luna', cost('4', '20', date(2026, 10, 1)))
    await add_cost(session, 'gpt-6-luna', cost('5', '30', date(2026, 11, 21)))

    before = await repository.cost_on(session, 'gpt-6-luna', date(2026, 11, 20))
    after = await repository.cost_on(session, 'gpt-6-luna', date(2026, 11, 21))

    assert (before.input_per_mtok, after.input_per_mtok) == (Decimal('4'), Decimal('5'))
    assert await repository.cost_on(session, 'gpt-6-luna', date(2026, 9, 30)) is None


async def test_a_correction_on_the_same_day_wins(session: AsyncSession):
    await put_models(session, LUNA)
    await add_cost(session, 'gpt-6-luna', cost('1', '5'))
    await add_cost(session, 'gpt-6-luna', cost('0.1', '0.5', note='잘못 적은 것을 고친다'))

    current = await repository.cost_on(session, 'gpt-6-luna', TODAY)

    assert current.input_per_mtok == Decimal('0.1')


async def test_the_list_shows_each_model_with_the_cost_of_the_day(session: AsyncSession):
    await put_models(session, LUNA)
    await put_models(session, OPUS)
    await add_cost(session, 'gpt-6-luna', cost('0.1', '0.5', TODAY - timedelta(days=1)))
    await add_cost(session, 'gpt-6-luna', cost('0.2', '1', TODAY + timedelta(days=1)))

    entries = await service.list_entries(session, TODAY)

    # 회사 순서다. Opus 에는 단가가 없다
    assert [(entry.model.slug, entry.cost and entry.cost.input_per_mtok) for entry in entries] == [
        ('claude-opus-5-5', None),
        ('gpt-6-luna', Decimal('0.1')),
    ]


async def test_cache_prices_are_kept(session: AsyncSession):
    await put_models(session, OPUS)

    await add_cost(
        session,
        'claude-opus-5-5',
        cost('4', '20', cached_input_per_mtok=Decimal('0.4'), cache_write_per_mtok=Decimal('5')),
    )

    current = await repository.cost_on(session, 'claude-opus-5-5', TODAY)
    assert (current.cached_input_per_mtok, current.cache_write_per_mtok) == (Decimal('0.4'), Decimal('5'))


# --- DB ---


async def test_the_database_takes_a_zai_model_with_its_thinking_switch(session: AsyncSession):
    data = ModelEntry(
        slug='glm-4-7-flash',
        provider=Provider.ZAI,
        api_model_id='glm-4.7-flash',
        display_name='GLM-4.7-Flash',
        vendor='zai',
        grade=Grade.BASIC,
        reasoning_style=ReasoningStyle.THINKING_TYPE,
    )

    await put_models(session, data)
    model = await fresh_model(session, 'glm-4-7-flash')

    # DB 의 CHECK 도 새 창구와 새 방식을 받는다
    assert (model.provider, model.reasoning_style, model.enabled) == ('zai', 'thinking_type', False)
