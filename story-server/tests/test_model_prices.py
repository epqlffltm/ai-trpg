# story-server/tests/test_model_prices.py

"""
모델의 값과 판매(app/catalog/offers.py, app/billing/router.py, 세션의 모델 고르기)를 검증한다.
결제 서버의 가격 목록 자리에는 정해 둔 것(tests/prices.py)을 끼운다. 모델 목록은 실제 DB(story_test)다.

보는 것.
  - 모델 목록: 켜져 있고 결제 서버가 팔고 있는 모델만, 값과 예약된 바뀜을 붙여 낸다.
    예약 시각이 지나면 스스로 갈아 끼운다
  - 가격 목록을 받지 못했고 받아 둔 것도 없으면: 목록과 모델 고르기는 503 prices_unavailable(Retry-After),
    지난번 모델로 시작하는 것과 세션을 읽는 것은 그대로 된다(값을 모르면 팔고 있다고 본다)
  - 팔지 않는 모델은 고르지 못하고(422), 세션이 가리키던 모델의 판매가 멈추면 usable 이 거짓이다
"""

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from ai_core.catalog_contract import Grade, Provider, TokenLimitField
from ai_core.catalog_file import CostEntry, ModelEntry
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.prices import Change, Price, Tier, story_code
from app.catalog import service as catalog
from app.conversations.models import Conversation
from app.core.dependencies import utc_now
from app.main import API_PREFIX
from tests.assets import FakeAsset, make_world
from tests.catalog_rows import add_cost, put_models
from tests.prices import StaticPrices, sale, selling, stopping

pytestmark = pytest.mark.usefixtures('clean_tables')

MODELS_URL = f'{API_PREFIX}/models'
CONVERSATIONS_URL = f'{API_PREFIX}/conversations'
NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)
LATER = NOW + timedelta(days=14)
ME = uuid.UUID('11111111-2222-4333-8444-555555555555')


def model_entry(slug: str) -> ModelEntry:
    """OpenAI 창구로 부르는 모델 하나. API 모델 이름은 지어낸 것이다."""
    return ModelEntry(
        slug=slug,
        provider=Provider.OPENAI,
        api_model_id=f'{slug}-2026-09-22',
        display_name=slug.upper(),
        vendor='openai',
        grade=Grade.STANDARD,
        token_limit_field=TokenLimitField.MAX_COMPLETION_TOKENS,
    )


@pytest.fixture(autouse=True)
def fixed_now(app: FastAPI) -> Iterator[None]:
    """API 가 보는 "지금"을 NOW 로 둔다."""
    app.dependency_overrides[utc_now] = lambda: NOW
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def prices(app: FastAPI) -> StaticPrices:
    """결제 서버의 가격 목록 자리. 테스트가 값을 정한다. 처음에는 아무것도 팔지 않는다."""
    fake = StaticPrices()
    app.state.price_list = fake
    return fake


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    claims = make_access_claims(sub=str(ME))
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
async def enabled(clean_tables: None, session: AsyncSession) -> None:
    """LUNA, SOL, NOVA 를 들여와 켠다. 표를 비운 뒤에 넣는다(clean_tables)."""
    await put_models(session, *(model_entry(slug) for slug in ('luna', 'sol', 'nova')))
    for slug in ('luna', 'sol', 'nova'):
        cost = CostEntry(
            input_per_mtok=Decimal('1'), output_per_mtok=Decimal('5'), effective_from=NOW.date(), checked_on=NOW.date()
        )
        await add_cost(session, slug, cost)
        await catalog.enable_model(session, slug, NOW.date())


async def start(client: AsyncClient, asset: FakeAsset, headers: dict, **body):
    world = asset.add_world(make_world())
    return await client.post(CONVERSATIONS_URL, json={'world_id': str(world.id), **body}, headers=headers)


async def started(client: AsyncClient, asset: FakeAsset, headers: dict, **body) -> dict:
    response = await start(client, asset, headers, **body)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


# --- 모델 목록 ---


@pytest.mark.usefixtures('enabled')
async def test_only_sold_models_are_listed_with_their_price(client: AsyncClient, prices: StaticPrices, mine: dict):
    luna_price = selling('luna', credits='30')[story_code('luna')]
    prices.prices = {
        story_code('luna'): Price(luna_price.code, luna_price.current, Change(sale('40', Tier.PREMIUM, True), LATER)),
        **selling('nova', credits='120', tier=Tier.PREMIUM, promo=True),
        **stopping('sol', LATER),
    }

    response = await client.get(MODELS_URL, headers=mine)

    body = response.json()
    assert (response.status_code, body['free']) == (status.HTTP_200_OK, False)
    assert [(item['slug'], item['credits'], item['tier'], item['promo']) for item in body['items']] == [
        ('luna', '30', 'standard', False),
        ('nova', '120', 'premium', True),
        ('sol', '30', 'standard', False),
    ]
    # 값이 바뀌는 예약은 그 값과 등급을 함께 낸다. 화면이 "10월 31일부터 40"을 미리 알린다
    assert body['items'][0]['next'] == {
        'credits': '40',
        'tier': 'premium',
        'promo': True,
        'effective_at': '2026-10-31T12:00:00Z',
    }
    # 판매를 멈추는 예약은 값과 등급이 null 이다. 화면이 "10월 31일 종료"를 알린다
    assert body['items'][2]['next'] == {
        'credits': None,
        'tier': None,
        'promo': False,
        'effective_at': '2026-10-31T12:00:00Z',
    }


@pytest.mark.usefixtures('enabled')
async def test_a_model_without_a_price_is_not_listed(client: AsyncClient, prices: StaticPrices, mine: dict):
    prices.prices = selling('luna')

    response = await client.get(MODELS_URL, headers=mine)

    assert [item['slug'] for item in response.json()['items']] == ['luna']


@pytest.mark.usefixtures('enabled')
async def test_a_reservation_takes_over_when_its_time_comes(
    client: AsyncClient, app: FastAPI, prices: StaticPrices, mine: dict
):
    prices.prices = {**selling('luna'), **stopping('sol', LATER)}
    app.dependency_overrides[utc_now] = lambda: LATER

    response = await client.get(MODELS_URL, headers=mine)

    # 받아 둔 목록이 늦어도 예약의 시각이 지나면 스스로 갈아 끼운다
    assert [item['slug'] for item in response.json()['items']] == ['luna']


@pytest.mark.usefixtures('enabled')
async def test_without_a_price_list_the_model_list_is_503(
    client: AsyncClient, prices: StaticPrices, mine: dict, caplog: pytest.LogCaptureFixture
):
    prices.down = True

    with caplog.at_level(logging.WARNING, logger='app.billing.router'):
        response = await client.get(MODELS_URL, headers=mine)

    # 값을 모르는 모델을 내주지 않는다. 까닭은 응답에 싣지 않고 로그에 남긴다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()['code'] == 'prices_unavailable'
    assert response.headers['Retry-After'] == '30'
    warned = [record for record in caplog.records if record.name == 'app.billing.router']
    assert [record.reason for record in warned] == ['unreachable']


# --- 시작 ---


@pytest.mark.usefixtures('enabled')
async def test_a_model_that_is_not_sold_cannot_be_chosen(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.prices = selling('luna')

    response = await start(client, asset, mine, model='sol')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'model_unavailable'
    assert await session.scalar(select(func.count()).select_from(Conversation)) == 0


@pytest.mark.usefixtures('enabled')
async def test_a_sold_model_can_be_chosen(client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict):
    prices.prices = selling('luna')

    made = await started(client, asset, mine, model='luna')

    assert (made['model']['slug'], made['model']['usable']) == ('luna', True)


@pytest.mark.usefixtures('enabled')
async def test_choosing_without_a_price_list_is_503_and_saves_nothing(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.down = True

    response = await start(client, asset, mine, model='luna')

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()['code'] == 'prices_unavailable'
    assert await session.scalar(select(func.count()).select_from(Conversation)) == 0


@pytest.mark.usefixtures('enabled')
async def test_without_a_price_list_the_last_model_is_still_carried_over(
    client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.prices = selling('luna')
    await started(client, asset, mine, model='luna')
    prices.down = True

    made = await started(client, asset, mine)

    # 결제 서버가 내려가도 세션은 시작된다. 값을 모르면 팔고 있다고 본다(말을 보낼 때 결제 서버가 다시 본다)
    assert (made['model']['slug'], made['model']['usable']) == ('luna', True)


@pytest.mark.usefixtures('enabled')
async def test_starting_without_a_model_does_not_need_the_price_list(
    client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.down = True

    # 정할 모델이 없으면 결제 서버를 부르지 않는다. 처음 시작하는 사람도, null 을 보낸 사람도 그대로 시작한다
    first = await started(client, asset, mine)
    chosen_none = await started(client, asset, mine, model=None)

    assert (first['model'], chosen_none['model']) == (None, None)


@pytest.mark.usefixtures('enabled')
async def test_a_last_model_no_longer_sold_is_not_carried_over(
    client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.prices = selling('luna')
    await started(client, asset, mine, model='luna')
    prices.prices = selling('sol')

    made = await started(client, asset, mine)

    assert made['model'] is None


# --- 읽기와 바꾸기 ---


@pytest.mark.usefixtures('enabled')
async def test_a_model_whose_sale_stopped_is_not_usable(
    client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.prices = selling('luna')
    made = await started(client, asset, mine, model='luna')
    prices.prices = {}

    page = (await client.get(CONVERSATIONS_URL, headers=mine)).json()

    # 세션은 그 모델을 가리킨 채다. 몰래 바꾸지 않는다
    assert (await read(client, mine, made))['model'] == {**made['model'], 'usable': False}
    assert page['items'][0]['model']['usable'] is False


@pytest.mark.usefixtures('enabled')
async def test_reading_without_a_price_list_still_works(
    client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.prices = selling('luna')
    made = await started(client, asset, mine, model='luna')
    prices.down = True

    page = await client.get(CONVERSATIONS_URL, headers=mine)
    detail = await client.get(f'{CONVERSATIONS_URL}/{made["id"]}', headers=mine)

    assert (page.status_code, detail.status_code) == (status.HTTP_200_OK, status.HTTP_200_OK)
    assert detail.json()['model']['usable'] is True


@pytest.mark.usefixtures('enabled')
async def test_changing_to_a_model_that_is_not_sold_is_422(
    client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.prices = selling('luna')
    made = await started(client, asset, mine, model='luna')

    refused = await client.put(f'{CONVERSATIONS_URL}/{made["id"]}/model', json={'model': 'sol'}, headers=mine)
    prices.prices = selling('luna', 'sol')
    changed = await client.put(f'{CONVERSATIONS_URL}/{made["id"]}/model', json={'model': 'sol'}, headers=mine)

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert changed.status_code == status.HTTP_200_OK


@pytest.mark.usefixtures('enabled')
async def test_changing_without_a_price_list_is_503(
    client: AsyncClient, asset: FakeAsset, prices: StaticPrices, mine: dict
):
    prices.prices = selling('luna')
    made = await started(client, asset, mine, model='luna')
    prices.down = True

    response = await client.put(f'{CONVERSATIONS_URL}/{made["id"]}/model', json={'model': 'luna'}, headers=mine)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
