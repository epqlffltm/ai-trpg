# story-server/tests/test_model_catalog.py

"""
이 서버의 표에서 하는 모델 목록의 일(app/catalog/service.py, repository.py, choice.py)을 검증한다.
파일의 모양은 ai-core 의 tests/test_catalog_file.py 가, 파일을 들여오기는 tests/test_catalog_sync.py 가,
관리 명령(scripts/models.py)은 tests/test_models_script.py 가 본다. 은퇴와 쓸 수 있나의 판단은 ai-core 가 본다.

"오늘"은 테스트가 정한다. 실제 시계를 읽지 않는다.

넷을 본다.
  - 고를 수 있나: 켜져 있고 은퇴하지 않았다. 성인 등급의 세션에는 allows_adult 가 참인 모델만이다.
    값과 판매는 아직 없다(결제를 붙이는 PR).
  - 켜고 끄기: 켜려면 원가가 있고 은퇴하지 않아야 한다. 없는 모델은 찾지 못한다.
  - 성인 스위치: 약관이 막는 창구(anthropic, gemini)는 켜지 못한다. 끄는 것은 늘 된다.
  - 원가: 덧붙이기만 한다. 그날의 단가는 그날 이전에 시작한 것 중 가장 늦은 것, 같은 날이면 나중에 적은 것이다.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from ai_core.catalog_contract import Grade, Provider, ReasoningStyle, TokenLimitField
from ai_core.catalog_file import CostEntry, ModelEntry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import FREE_PRICES
from app.catalog import offers, repository, service
from app.catalog.choice import is_choosable, may_allow_adult, suits_rating
from app.catalog.errors import CatalogConflictError, Conflict, ModelNotFoundError
from app.catalog.models import AiModel
from app.ratings import Rating
from tests.catalog_rows import add_cost, put_models, retire

pytestmark = pytest.mark.usefixtures('clean_tables')

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
FLASH = ModelEntry(
    slug='gemini-4-flash',
    provider=Provider.GEMINI,
    api_model_id='gemini-4-flash',
    display_name='Gemini 4 Flash',
    vendor='google',
    grade=Grade.STANDARD,
    reasoning_style=ReasoningStyle.LEVEL_LOW,
)
GLM = ModelEntry(
    slug='glm-5-3',
    provider=Provider.ZAI,
    api_model_id='glm-5.3',
    display_name='GLM-5.3',
    vendor='zai',
    grade=Grade.STANDARD,
    reasoning_style=ReasoningStyle.THINKING_TYPE,
)


@dataclass(frozen=True)
class Card:
    """고를 수 있나를 볼 때 쓰는 칸만 가진 모델."""

    provider: str = Provider.OPENAI
    enabled: bool = True
    retires_on: date | None = None
    allows_adult: bool = False


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


async def enabled(session: AsyncSession, *entries: ModelEntry) -> None:
    """들여오고 원가를 적어 켠 모델들."""
    await put_models(session, *entries)
    for entry in entries:
        await add_cost(session, entry.slug, cost())
        await service.enable_model(session, entry.slug, TODAY)


# --- 고를 수 있나 ---


@pytest.mark.parametrize(
    ('card', 'rating', 'choosable'),
    [
        (Card(), Rating.ALL, True),
        (Card(), Rating.ADULT, False),
        (Card(allows_adult=True), Rating.ADULT, True),
        (Card(allows_adult=True), Rating.ALL, True),
        (Card(enabled=False, allows_adult=True), Rating.ALL, False),
        (Card(retires_on=TODAY), Rating.ALL, False),
        (Card(retires_on=TODAY + timedelta(days=1)), Rating.ALL, True),
    ],
)
def test_a_model_is_choosable_when_offered_and_fit_for_the_rating(card: Card, rating: Rating, choosable: bool):
    assert is_choosable(card, rating, TODAY) is choosable


def test_an_adult_model_suits_every_rating_and_others_only_all():
    assert [suits_rating(Card(allows_adult=adult), rating) for adult in (False, True) for rating in Rating] == [
        True,
        False,
        True,
        True,
    ]


@pytest.mark.parametrize(
    ('provider', 'may'),
    [
        (Provider.ANTHROPIC, False),
        (Provider.GEMINI, False),
        (Provider.OPENAI, True),
        (Provider.ZAI, True),
        (Provider.DEEPINFRA, True),
        (Provider.LOCAL, True),
    ],
)
def test_providers_whose_terms_forbid_sexual_content_cannot_allow_adult(provider: Provider, may: bool):
    assert may_allow_adult(Card(provider=provider)) is may


# --- 켜고 끄기 ---


@pytest.mark.parametrize('call', ['enable', 'disable', 'show', 'allow', 'forbid'])
async def test_unknown_models_are_not_found(session: AsyncSession, call: str):
    calls = {
        'enable': lambda: service.enable_model(session, 'nothing', TODAY),
        'disable': lambda: service.disable_model(session, 'nothing'),
        'show': lambda: service.show_model(session, 'nothing'),
        'allow': lambda: service.allow_adult(session, 'nothing'),
        'forbid': lambda: service.forbid_adult(session, 'nothing'),
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
    await enabled(session, LUNA)
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


# --- 성인 스위치 ---


async def test_the_adult_switch_turns_on_and_off(session: AsyncSession):
    await put_models(session, GLM)

    await service.allow_adult(session, 'glm-5-3')
    allowed = (await fresh_model(session, 'glm-5-3')).allows_adult
    await service.forbid_adult(session, 'glm-5-3')

    assert (allowed, (await fresh_model(session, 'glm-5-3')).allows_adult) == (True, False)


@pytest.mark.parametrize('entry', [OPUS, FLASH])
async def test_a_refusing_provider_cannot_allow_adult(session: AsyncSession, entry: ModelEntry):
    await put_models(session, entry)

    with pytest.raises(CatalogConflictError) as caught:
        await service.allow_adult(session, entry.slug)

    assert caught.value.reason == Conflict.ADULT_REFUSED
    assert not (await fresh_model(session, entry.slug)).allows_adult


async def test_a_refusing_provider_can_still_forbid_adult(session: AsyncSession):
    await put_models(session, OPUS)

    model = await service.forbid_adult(session, 'claude-opus-5-5')

    assert not model.allows_adult


# --- 고를 수 있는 모델들 ---


async def test_only_enabled_unretired_models_are_offered(session: AsyncSession):
    await enabled(session, LUNA, OPUS, GLM)
    await put_models(session, FLASH)
    await retire(session, 'glm-5-3', TODAY)

    noon = datetime.combine(TODAY, time(12), UTC)
    offered = await offers.list_offered(session, FREE_PRICES, noon)
    before_retiring = await offers.list_offered(session, FREE_PRICES, noon - timedelta(days=1))

    # 회사, 이름표 순서다. 꺼진 것(Flash)과 은퇴한 것(GLM, 은퇴일 당일부터)은 없다. 결제 서버가 없으니 값이 없다
    assert [found.model.slug for found in offered.offers] == ['claude-opus-5-5', 'gpt-6-luna']
    assert [found.model.slug for found in before_retiring.offers] == ['claude-opus-5-5', 'gpt-6-luna', 'glm-5-3']
    assert offered.free and offered.offers[0].sale is None


async def test_models_are_found_by_their_slugs(session: AsyncSession):
    await put_models(session, LUNA, OPUS)

    found = await repository.models_in(session, {'gpt-6-luna', 'nothing'})

    # 표에 없는 것은 들지 않는다
    assert list(found) == ['gpt-6-luna']
    assert await repository.models_in(session, set()) == {}


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
    await put_models(session, LUNA, OPUS)
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
