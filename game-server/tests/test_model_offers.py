# game-server/tests/test_model_offers.py

"""
방장이 고를 수 있는 서술 모델(app/catalog/offers.py)과 그 API(GET /tables/narration-models)를 검증한다.

모델 목록에서 켜져 있고 결제 서버가 지금 파는 모델만 나오는 것, 값과 예약된 바뀜이 붙는 것,
결제 서버 없이 도는 서버는 켜진 모델을 값 없이 모두 내주는 것, 분류와 등급이 다르면 경고하는 것,
가격 목록을 받지 못하면 503 인 것을 본다.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceListUnavailable
from app.billing.prices import FREE_BOOK, Change, Price, PriceBook, Sale, Tier, narration_code
from app.catalog import service as catalog
from app.catalog.models import Grade, Provider, ReasoningStyle, TokenLimitField
from app.catalog.offers import ModelCard, OfferedModel, grade_disagrees, offer, offered_models
from app.catalog.schemas import CostCreate, ModelCreate
from app.main import API_PREFIX
from app.tables.router import utc_now
from tests.signing import SigningKey, make_access_claims, make_token

NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
LATER = datetime(2026, 12, 1, tzinfo=UTC)
MODELS_URL = f'{API_PREFIX}/tables/narration-models'
ME = uuid.UUID('11111111-2222-4333-8444-555555555555')


def card(slug: str = 'gpt-6-luna', **changes) -> ModelCard:
    values = {
        'slug': slug,
        'display_name': 'GPT-6 Luna',
        'vendor': 'openai',
        'grade': Grade.STANDARD,
        'enabled': True,
        'retires_on': None,
    }
    return ModelCard(**{**values, **changes})


def book(*prices: Price) -> PriceBook:
    return PriceBook(prices={price.code: price for price in prices})


def on_sale(slug: str, credits: str = '20', tier: Tier = Tier.STANDARD, change: Change | None = None) -> Price:
    return Price(code=narration_code(slug), current=Sale(credits, tier), next=change)


# --- 맞춰 붙이기 ---


def test_a_model_on_sale_is_offered_with_its_price():
    found = offer(card(), book(on_sale('gpt-6-luna')), NOW)

    assert found == OfferedModel('gpt-6-luna', 'GPT-6 Luna', 'openai', Grade.STANDARD, '20', Tier.STANDARD)


@pytest.mark.parametrize(
    ('model', 'prices'),
    [
        # 꺼졌다. 원가를 적고 평가를 통과해야 켠다
        (card(enabled=False), book(on_sale('gpt-6-luna'))),
        # 은퇴했다. 은퇴일 당일부터다
        (card(retires_on=NOW.date()), book(on_sale('gpt-6-luna'))),
        # 결제 서버가 팔지 않는다
        (card(), book()),
        # 예약만 있다
        (card(), book(Price(narration_code('gpt-6-luna'), None, Change(Sale('20', Tier.STANDARD), LATER)))),
    ],
)
def test_a_model_not_offered_by_both_lists_is_not_offered(model: ModelCard, prices: PriceBook):
    assert offer(model, prices, NOW) is None


def test_a_scheduled_change_is_offered_with_the_price():
    change = Change(Sale('240', Tier.PREMIUM), LATER)

    found = offer(card(), book(on_sale('gpt-6-luna', change=change)), NOW)

    # 화면이 "12월 1일부터 240"처럼 미리 알린다
    assert found is not None and found.next == change


def test_a_change_whose_time_has_come_is_already_the_price():
    change = Change(Sale('240', Tier.PREMIUM), LATER)
    stop = Change(None, LATER)

    raised = offer(card(), book(on_sale('gpt-6-luna', change=change)), LATER)
    stopped = offer(card(), book(on_sale('gpt-6-luna', change=stop)), LATER)

    assert raised is not None and (raised.credits, raised.tier, raised.next) == ('240', Tier.PREMIUM, None)
    assert stopped is None


def test_without_a_billing_server_every_enabled_model_is_offered_free():
    found = offered_models([card(), card('local-gemma', enabled=False)], FREE_BOOK, NOW)

    assert [(model.slug, model.credits, model.tier) for model in found] == [('gpt-6-luna', None, None)]


def test_the_models_are_sorted_by_vendor_and_name():
    cards = [
        card('gpt-6-luna', display_name='GPT-6 Luna', vendor='openai'),
        card('claude-sonnet-5-5', display_name='Claude Sonnet 5.5', vendor='anthropic'),
        card('claude-haiku-5-5', display_name='Claude Haiku 5.5', vendor='anthropic'),
    ]
    prices = book(*(on_sale(model.slug) for model in cards))

    assert [model.slug for model in offered_models(cards, prices, NOW)] == [
        'claude-haiku-5-5',
        'claude-sonnet-5-5',
        'gpt-6-luna',
    ]


@pytest.mark.parametrize(
    ('grade', 'tier', 'disagrees'),
    [
        (Grade.STANDARD, Tier.STANDARD, False),
        (Grade.PREMIUM, Tier.PREMIUM, False),
        (Grade.BASIC, Tier.STANDARD, False),
        (Grade.STANDARD, Tier.PREMIUM, True),
        (Grade.PREMIUM, Tier.STANDARD, True),
        (Grade.PREMIUM, None, False),
    ],
)
def test_the_grade_disagrees_when_premium_is_on_one_side_only(grade: Grade, tier: Tier | None, disagrees: bool):
    found = OfferedModel('m', 'M', 'v', grade, '10' if tier else None, tier)

    assert grade_disagrees(found) is disagrees


# --- API ---


@dataclass
class FixedPrices:
    """정해 둔 가격 목록을 주는 것. error 가 있으면 받지 못한 것이다."""

    fixed: PriceBook
    error: PriceListUnavailable | None = None

    async def book(self) -> PriceBook:
        if self.error is not None:
            raise self.error
        return self.fixed


LUNA = ModelCreate(
    slug='gpt-6-luna',
    provider=Provider.OPENAI,
    api_model_id='gpt-6-luna-2026-09-22',
    display_name='GPT-6 Luna',
    vendor='openai',
    grade=Grade.STANDARD,
    supports_reasoning=True,
    token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
)
OPUS = ModelCreate(
    slug='claude-opus-5-5',
    provider=Provider.ANTHROPIC,
    api_model_id='claude-opus-5-5-20260901',
    display_name='Claude Opus 5.5',
    vendor='anthropic',
    grade=Grade.STANDARD,
    supports_temperature=False,
    reasoning_style=ReasoningStyle.ALWAYS,
)


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(ME)))}'}


async def add_enabled(session: AsyncSession, data: ModelCreate) -> None:
    """모델을 넣고 오늘의 원가를 적고 켠다."""
    await catalog.add_model(session, data)
    cost = CostCreate(
        input_per_mtok=Decimal('0.1'), output_per_mtok=Decimal('0.5'), effective_from=NOW.date(), checked_on=NOW.date()
    )
    await catalog.add_cost(session, data.slug, cost)
    await catalog.enable_model(session, data.slug, NOW.date())


@pytest.fixture
async def two_models(app: FastAPI, session: AsyncSession, clean_tables) -> None:
    """켜진 모델 둘. 결제 서버는 Luna 만 팔고, Opus 에는 올라갈 값이 예약돼 있다."""
    await add_enabled(session, LUNA)
    await add_enabled(session, OPUS)
    app.dependency_overrides[utc_now] = lambda: NOW


@pytest.mark.usefixtures('two_models')
async def test_the_api_lists_the_models_with_their_prices(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    prices = book(
        on_sale('gpt-6-luna'),
        on_sale('claude-opus-5-5', '300', Tier.STANDARD, Change(Sale('310', Tier.PREMIUM), LATER)),
        on_sale('not-in-catalog'),
    )
    app.state.price_list = FixedPrices(prices)

    response = await client.get(MODELS_URL, headers=me)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['free'] is False
    assert body['models'] == [
        {
            'slug': 'claude-opus-5-5',
            'display_name': 'Claude Opus 5.5',
            'vendor': 'anthropic',
            'grade': 'standard',
            'credits': '300',
            'tier': 'standard',
            'next': {'credits': '310', 'tier': 'premium', 'effective_at': '2026-12-01T00:00:00Z'},
        },
        {
            'slug': 'gpt-6-luna',
            'display_name': 'GPT-6 Luna',
            'vendor': 'openai',
            'grade': 'standard',
            'credits': '20',
            'tier': 'standard',
            'next': None,
        },
    ]


@pytest.mark.usefixtures('two_models')
async def test_a_model_the_billing_server_does_not_sell_is_not_listed(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    app.state.price_list = FixedPrices(book(on_sale('gpt-6-luna')))

    body = (await client.get(MODELS_URL, headers=me)).json()

    assert [model['slug'] for model in body['models']] == ['gpt-6-luna']


@pytest.mark.usefixtures('two_models')
async def test_without_a_billing_server_the_enabled_models_are_free(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    app.state.price_list = FixedPrices(FREE_BOOK)

    body = (await client.get(MODELS_URL, headers=me)).json()

    assert body['free'] is True
    assert [(model['slug'], model['credits'], model['tier']) for model in body['models']] == [
        ('claude-opus-5-5', None, None),
        ('gpt-6-luna', None, None),
    ]


@pytest.mark.usefixtures('two_models')
async def test_a_grade_that_disagrees_with_the_tier_is_warned(
    client: AsyncClient, app: FastAPI, me: dict[str, str], caplog
):
    app.state.price_list = FixedPrices(book(on_sale('claude-opus-5-5', '310', Tier.PREMIUM)))

    with caplog.at_level('WARNING', logger='app.catalog.offers'):
        response = await client.get(MODELS_URL, headers=me)

    # 결제는 가격표의 등급대로 된다. 고르는 것은 막지 않는다
    assert response.json()['models'][0]['tier'] == 'premium'
    (warning,) = [record for record in caplog.records if record.name == 'app.catalog.offers']
    assert (warning.model, warning.grade, warning.tier) == ('claude-opus-5-5', 'standard', 'premium')


@pytest.mark.usefixtures('two_models')
async def test_without_the_price_list_the_models_are_not_listed(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('status_401'))

    response = await client.get(MODELS_URL, headers=me)

    # 값을 모르는 모델을 내주지 않는다. 까닭(결제 서버의 사정)은 싣지 않는다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert 'status_401' not in response.text


async def test_only_a_signed_in_user_sees_the_prices(client: AsyncClient):
    # 가격을 아무나 긁어 가지 못하게 한다(유저 결정, 2026-10-17)
    assert (await client.get(MODELS_URL)).status_code == status.HTTP_401_UNAUTHORIZED


def test_now_is_utc():
    assert abs(utc_now() - datetime.now(UTC)) < timedelta(seconds=5)
