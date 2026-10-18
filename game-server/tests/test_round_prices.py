# game-server/tests/test_round_prices.py

"""
라운드를 열 때 1인 1라운드의 값을 알리는 것(app/rounds/round_price.py)과 사람마다 홀드한 값(#379)을 검증한다.

보는 것.
  - 알린 값: 라운드를 열 때 결제 서버의 가격 목록의 값을 round_opened 와 라운드의 응답에 싣는다.
    테이블을 시작할 때, 서술이 끝나 다음 라운드가 열릴 때, 서술을 그만두고 다음 라운드를 열 때 모두.
  - 홀드한 값: 사람마다 결제 서버가 실제로 홀드한 값(GET .../rounds/{n}/charges). 알린 값과 같다.
  - 모델을 바꾸면 지금 라운드의 알린 값도 바뀌고, 홀드한 값은 다시 걸 때까지 비운다.
  - 알릴 수 없으면(결제 서버 없이 도는 서버, 가격 목록을 받지 못함) 비우고 라운드는 연다.
"""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.http_billing import amount_of
from app.billing.price_list import PriceListUnavailable
from app.billing.prices import narration_code
from app.billing.routing import utc_now
from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.rounds.service import NARRATION_FAILURE_LIMIT
from tests.billing import PRICES, FakeBillingServer
from tests.signing import SigningKey
from tests.test_model_offers import LUNA, OPUS, FixedPrices, add_enabled, book, on_sale
from tests.test_narration_billing import tick
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_round_time_limit import current, start_with

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
LAUGH = '크게 웃는다.'
LUNA_PRICE = {'credits': '30', 'tier': 'standard'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
async def models(app: FastAPI, session: AsyncSession, clean_tables, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    켜진 모델 둘(Luna 30, Opus 60). 가격 목록과 가짜 결제 서버가 같은 값을 판다.

    가격 목록은 알리는 값이고 가짜 결제 서버는 홀드하는 값이다. 실제로는 둘 다 결제 서버의 가격표에서 나온다.
    """
    for data in (LUNA, OPUS):
        await add_enabled(session, data)
    app.state.price_list = FixedPrices(book(on_sale('gpt-6-luna', '30'), on_sale('claude-opus-5-5', '60')))
    monkeypatch.setitem(PRICES, narration_code('gpt-6-luna'), 30)
    monkeypatch.setitem(PRICES, narration_code('claude-opus-5-5'), 60)
    app.dependency_overrides[utc_now] = lambda: NOW


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 방장과 친구에게 1000 크레딧씩 있다."""
    server = FakeBillingServer(balances={ME: 1000, FRIEND: 1000})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


async def charges_out(client: AsyncClient, headers: dict[str, str], table: dict, number: int):
    """그 라운드의 청구들의 응답."""
    return await client.get(table_url(table, f'/rounds/{number}/charges'), headers=headers)


class FailingNarrator:
    """늘 잘려서 실패하는 서술자."""

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        raise NarrationError('cut_off')


# --- 알린 값 ---


@pytest.mark.usefixtures('models')
async def test_the_first_round_announces_the_price(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    (opened,) = await events_of(client, me, table, 'round_opened')

    assert opened['payload']['price'] == LUNA_PRICE
    assert (await current(client, me, table))['price'] == LUNA_PRICE


@pytest.mark.usefixtures('models', 'billing')
async def test_each_payer_is_held_the_announced_price(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_with(client, me, friend, narration_model='gpt-6-luna')
    before = await charges_out(client, me, table, 1)
    await tick(app)

    held = await charges_out(client, friend, table, 1)
    announced = (await current(client, me, table))['price']['credits']

    # 걸기 전에는 값이 없다. 건 뒤에는 사람마다 결제 서버가 실제로 홀드한 값이다. 알린 값과 같다
    assert [(charge['status'], charge['credits']) for charge in before.json()] == [('pending', None)] * 2
    assert held.status_code == status.HTTP_200_OK
    assert sorted((charge['user_id'], charge['status'], charge['credits']) for charge in held.json()) == [
        (str(ME), 'held', announced),
        (str(FRIEND), 'held', announced),
    ]


@pytest.mark.usefixtures('models', 'billing')
async def test_the_next_round_after_narration_announces_its_price(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await tick(app)

    await declare(client, me, table, LAUGH)
    await narrated()

    second = await current(client, me, table)
    assert (second['number'], second['price']) == (2, LUNA_PRICE)


@pytest.mark.usefixtures('models')
async def test_an_abandoned_narration_announces_the_next_price(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    app.state.narrator = FailingNarrator()
    table = await start_with(client, me, narration_model='gpt-6-luna')

    await declare(client, me, table, LAUGH)
    await narrated()
    for _ in range(NARRATION_FAILURE_LIMIT - 1):
        await client.post(table_url(table, '/rounds/current/close'), headers=me)
        await narrated()

    # 서술을 그만두고 엔진의 결과로 연 다음 라운드에도 값을 알린다
    second = await current(client, me, table)
    assert (second['number'], second['price']) == (2, LUNA_PRICE)


@pytest.mark.usefixtures('models', 'billing')
async def test_changing_the_model_announces_the_new_price(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await tick(app)
    # Luna 를 더는 팔지 않는다. 시작한 테이블은 지금 모델을 쓸 수 없을 때만 바꾼다(app/tables/narration_models.py)
    app.state.price_list = FixedPrices(book(on_sale('claude-opus-5-5', '60')))

    await client.put(table_url(table, '/narration-model'), json={'narration_model': 'claude-opus-5-5'}, headers=me)
    repriced = await charges_out(client, me, table, 1)
    (changed,) = await events_of(client, me, table, 'narration_model_changed')
    await declare(client, me, table, LAUGH)
    await narrated()

    # 아직 서술하지 않은 라운드라 그 라운드의 값도 바뀐다. 홀드한 값은 새 가격표로 다시 걸 때까지 비운다.
    # 다시 거는 것은 서술 전이다(app/billing/settling.py 의 restore). 서술한 뒤에는 새 값으로 잡혀 있다
    opus_price = {'credits': '60', 'tier': 'standard'}
    assert changed['payload']['price'] == opus_price
    assert (await client.get(table_url(table, '/rounds/1'), headers=me)).json()['price'] == opus_price
    assert repriced.json()[0]['credits'] is None
    assert (await charges_out(client, me, table, 1)).json()[0]['credits'] == '60'


# --- 알릴 수 없을 때 ---


async def test_without_a_billing_server_there_is_no_price(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me)

    (opened,) = await events_of(client, me, table, 'round_opened')

    # 결제 서버 없이 도는 서버는 값이 없다. 라운드는 연다
    assert opened['payload']['price'] is None
    assert (await current(client, me, table))['price'] is None


@pytest.mark.usefixtures('models')
async def test_without_the_price_list_the_round_still_opens(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    app.state.price_list = FixedPrices(app.state.price_list.fixed, error=PriceListUnavailable('unreachable'))

    await declare(client, me, table, LAUGH)
    await narrated()

    # 값을 모르면 알리지 않는다. 다음 라운드를 여는 것은 막지 않는다
    second = await current(client, me, table)
    assert (second['number'], second['price']) == (2, None)


# --- 청구의 응답 ---


@pytest.mark.usefixtures('models')
async def test_only_seated_people_see_the_charges(client: AsyncClient, signing_key: SigningKey, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    stranger = await charges_out(client, bearer(signing_key, STRANGER), table, 1)
    missing = await charges_out(client, me, table, 9)

    assert stranger.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
    assert missing.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize(
    ('body', 'amount'),
    [({'amount': '120'}, '120'), ({'amount': 50}, '50'), ({}, None), ({'amount': None}, None)],
)
def test_the_held_amount_is_read_as_given(body: dict, amount: str | None):
    assert amount_of(httpx.Response(201, json=body)) == amount
