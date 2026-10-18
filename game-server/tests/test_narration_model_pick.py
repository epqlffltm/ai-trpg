# game-server/tests/test_narration_model_pick.py

"""
방장이 테이블의 서술 모델을 고르는 것(app/tables/model_picker.py, app/tables/narration_models.py)을 검증한다.

보는 것.
  - 만들 때: 고르지 않으면 null(서버의 기본, 서술 등급).
    고를 수 있는 모델만 된다(GET /tables/narration-models 와 같은 규칙).
    모델을 고르지 않으면 결제 서버의 가격 목록을 묻지 않는다. 고르는데 목록을 받지 못하면 503 이다.
  - 바꾸기: 방장만, 고를 수 있는 모델만, null 이면 기본으로. 이벤트로 남는다. 같은 값이면 아무것도 적지 않는다.
  - 라운드에 굳기: 열 때의 모델로 값을 걸고 서술한다. 열려 있는 동안 바꿔도 그 라운드는 그대로, 다음 라운드부터 바뀐다.
  - 값: 모델의 가격표 이름(narration.<이름표>.i0.o0)으로 건다. 모델이 없는 라운드는 등급의 것이다.
  - 서술자: 모델이 굳은 라운드는 그 모델의 서술자, 아니면 등급의 서술자.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.price_list import PriceListUnavailable
from app.billing.prices import FREE_BOOK, narration_code
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.rounds.picked_narrator import PickedNarrator
from app.tables.router import utc_now
from tests.billing import PRICES, FakeBillingServer
from tests.signing import SigningKey
from tests.test_model_offers import LUNA, OPUS, FixedPrices, add_enabled, book, on_sale
from tests.test_narration_billing import charges_of, tick
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_round_time_limit import current, open_with, start_with
from tests.test_tables_api import TABLES_URL

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)

LAUGH = '크게 웃는다.'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture(autouse=True)
async def models(app: FastAPI, session: AsyncSession, clean_tables) -> None:
    """켜진 모델 둘(Luna, Opus). 결제 서버 없이 도는 서버라 둘 다 값 없이 고를 수 있다."""
    await add_enabled(session, LUNA)
    await add_enabled(session, OPUS)
    app.state.price_list = FixedPrices(FREE_BOOK)
    app.dependency_overrides[utc_now] = lambda: NOW


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 방장(ME)에게 1000 크레딧이 있다."""
    server = FakeBillingServer(balances={ME: 1000})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


class RecordingNarrator:
    """받은 요청을 적어 두는 서술자."""

    def __init__(self) -> None:
        self.requests: list[NarrationRequest] = []

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        return '장면이 이어진다.'


@pytest.fixture
def recording(app: FastAPI) -> RecordingNarrator:
    """앱에 꽂은, 받은 요청을 적는 서술자."""
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    return narrator


async def set_model(client: AsyncClient, headers: dict[str, str], table: dict, model: str | None):
    """서술 모델을 바꾼다. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, '/narration-model'), json={'narration_model': model}, headers=headers)


async def close_solo(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """혼자 앉은 테이블의 라운드를 선언으로 닫고, 서술이 끝날 때까지 기다린다."""
    await declare(client, me, table, LAUGH)
    await narrated()


# --- 만들 때 ---


async def test_without_a_pick_the_table_uses_the_default(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    # 모델을 고르지 않으면 가격 목록을 묻지 않는다. 결제 서버가 내려가 있어도 테이블을 만든다
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('unreachable'))

    response = await open_with(client, me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['narration_model'] is None


async def test_an_offered_model_can_be_picked(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me, narration_model='gpt-6-luna')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['narration_model'] == 'gpt-6-luna'


@pytest.mark.parametrize('model', ['not-in-catalog', 'Not-A-Slug', 'narration.gpt-6-luna'])
async def test_a_model_not_in_the_catalog_cannot_be_picked(client: AsyncClient, me: dict[str, str], model: str):
    response = await open_with(client, me, narration_model=model)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_model_the_billing_server_does_not_sell_cannot_be_picked(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    app.state.price_list = FixedPrices(book(on_sale('gpt-6-luna')))

    sold = await open_with(client, me, narration_model='gpt-6-luna')
    unsold = await open_with(client, me, narration_model='claude-opus-5-5')

    assert sold.status_code == status.HTTP_201_CREATED, sold.text
    assert unsold.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'narration_model' in unsold.json()['detail']


async def test_without_the_price_list_a_model_cannot_be_picked(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('status_503'))

    response = await open_with(client, me, narration_model='gpt-6-luna')

    # 값을 모르는 모델을 고르게 하지 않는다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# --- 바꾸기 ---


async def test_the_host_changes_the_model_and_it_is_recorded(client: AsyncClient, me: dict[str, str]):
    table = (await open_with(client, me)).json()

    response = await set_model(client, me, table, 'claude-opus-5-5')
    (changed,) = await events_of(client, me, table, 'narration_model_changed')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['narration_model'] == 'claude-opus-5-5'
    assert changed['payload'] == {'narration_model': 'claude-opus-5-5'}


async def test_null_goes_back_to_the_default(client: AsyncClient, me: dict[str, str]):
    table = (await open_with(client, me, narration_model='gpt-6-luna')).json()

    response = await set_model(client, me, table, None)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['narration_model'] is None


async def test_the_same_model_writes_nothing(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = (await open_with(client, me, narration_model='gpt-6-luna')).json()
    # 같은 값이면 가격 목록도 묻지 않는다
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('unreachable'))

    response = await set_model(client, me, table, 'gpt-6-luna')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert await events_of(client, me, table, 'narration_model_changed') == []


async def test_only_the_host_changes_the_model(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = (await open_with(client, me)).json()
    joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert joined.status_code == status.HTTP_200_OK, joined.text

    response = await set_model(client, friend, table, 'gpt-6-luna')

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert await events_of(client, me, table, 'narration_model_changed') == []


async def test_a_model_that_cannot_be_picked_is_rejected_later(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = (await open_with(client, me)).json()
    app.state.price_list = FixedPrices(book(on_sale('gpt-6-luna')))

    response = await set_model(client, me, table, 'claude-opus-5-5')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await events_of(client, me, table, 'narration_model_changed') == []


@pytest.mark.parametrize('body', [{}, {'narration_model': 'gpt-6-luna', 'extra': 1}, {'narration_model': 7}])
async def test_a_bad_change_is_rejected(client: AsyncClient, me: dict[str, str], body: dict):
    table = (await open_with(client, me)).json()

    response = await client.put(table_url(table, '/narration-model'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 라운드에 굳기 ---


async def test_a_round_takes_the_model_of_the_table_when_it_opens(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    round_ = await current(client, me, table)
    (opened,) = await events_of(client, me, table, 'round_opened')

    assert round_['narration_model'] == 'gpt-6-luna'
    assert opened['payload']['narration_model'] == 'gpt-6-luna'


async def test_the_change_waits_for_the_next_round(
    client: AsyncClient, me: dict[str, str], recording: RecordingNarrator, narrated
):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    await set_model(client, me, table, 'claude-opus-5-5')
    unchanged = await current(client, me, table)
    await close_solo(client, me, table, narrated)
    second = await current(client, me, table)

    # 열려 있던 라운드는 Luna 의 값을 걸었으니 Luna 로 서술한다. 다음 라운드부터 Opus 다
    assert unchanged['narration_model'] == 'gpt-6-luna'
    assert [request.model for request in recording.requests] == ['gpt-6-luna']
    assert second['narration_model'] == 'claude-opus-5-5'


async def test_a_round_without_a_model_is_narrated_by_its_tier(
    client: AsyncClient, me: dict[str, str], recording: RecordingNarrator, narrated
):
    table = await start_with(client, me)

    await close_solo(client, me, table, narrated)

    assert [(request.model, request.tier) for request in recording.requests] == [(None, 'standard')]


# --- 값 ---


async def test_each_round_holds_the_price_of_its_model(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    billing: FakeBillingServer,
    narrated,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setitem(PRICES, narration_code('gpt-6-luna'), 20)
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await tick(app)
    await set_model(client, me, table, None)
    await close_solo(client, me, table, narrated)
    await tick(app)

    charges = await charges_of(session, table)

    # 1 라운드는 Luna 의 가격표로 걸고 확정했다. 2 라운드는 모델이 없어 등급의 가격표로 걸었다
    assert [charge.price_code for charge in charges] == ['narration.gpt-6-luna.i0.o0', 'narration.standard']
    assert [charge.status for charge in charges] == ['captured', 'held']
    assert billing.balance(ME) == 1000 - 20 - PRICES['narration.standard']


# --- 서술자 ---


async def test_the_picked_narrator_uses_the_model_of_the_round():
    made: dict[str, RecordingNarrator] = {}

    def chain_for(model: str) -> RecordingNarrator:
        return made.setdefault(model, RecordingNarrator())

    default = RecordingNarrator()
    narrator = PickedNarrator(chain_for=chain_for, default=default)

    await narrator.narrate(NarrationRequest(round_number=1, scene='장면', moves=[], model='gpt-6-luna'))
    await narrator.narrate(NarrationRequest(round_number=2, scene='장면', moves=[]))

    # 모델이 굳은 라운드는 그 모델의 서술자만, 아닌 라운드는 등급의 서술자만 받는다
    assert [request.round_number for request in made['gpt-6-luna'].requests] == [1]
    assert [request.round_number for request in default.requests] == [2]
