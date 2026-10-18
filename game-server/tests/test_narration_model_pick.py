# game-server/tests/test_narration_model_pick.py

"""
방장이 테이블의 서술 모델을 고르는 것(app/tables/model_picker.py, app/tables/narration_models.py)을 검증한다.

보는 것.
  - 만들 때: 고르지 않으면 시나리오의 추천 모델이다(대신 쓰는 것은 test_recommended_model.py).
    고를 수 있는 모델만 된다(GET /tables/narration-models 와 같은 규칙). 가격 목록을 받지 못하면 503 이다.
  - 바꾸기: 방장만, 고를 수 있는 모델만, 비울 수 없다. 이벤트로 남는다. 같은 값이면 아무것도 적지 않는다.
  - 시작하면 고정: 모집 중에는 바꾼다. 시작한 뒤에는 지금 쓰는 모델을 쓸 수 없을 때만(끔, 팔지 않음) 바꾼다.
    아니면 409(narration_model_locked)다. 서술이 실패해 멈춘 라운드의 모델도 지금 쓰는 모델이다.
  - 라운드에 굳기: 열 때의 모델로 값을 걸고 서술한다. 서술이 돌고 있으면 그 라운드는 그대로, 다음 라운드부터 바뀐다.
  - 값: 모델의 가격표 이름(narration.<이름표>.i0.o0)으로 건다. 모델이 없는 옛 라운드는 옛 가격표다.
  - 서술자: 모델이 굳은 라운드는 그 모델의 서술자, 모델이 없는 옛 라운드는 서버의 기본 서술자.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.charges import LEGACY_PRICE_CODE
from app.billing.price_list import PriceListUnavailable
from app.billing.prices import FREE_BOOK, narration_code
from app.billing.routing import utc_now
from app.catalog import service as catalog
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.rounds.picked_narrator import PickedNarrator
from tests.billing import PRICES, FakeBillingServer
from tests.narration_model import TEST_MODEL, TEST_PRICE_CODE
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


def stop_selling_luna(app: FastAPI) -> None:
    """결제 서버가 Luna 를 팔지 않는다. Opus 만 판다. 시작한 테이블의 Luna 를 바꿀 수 있게 된다."""
    app.state.price_list = FixedPrices(book(on_sale('claude-opus-5-5')))


async def clear_models(session: AsyncSession, table: dict) -> None:
    """테이블과 그 라운드들의 서술 모델을 비운다. 모델을 고르는 규칙 전에 만든 테이블과 같다."""
    table_filter = {'id': uuid.UUID(table['id'])}
    await session.execute(text('UPDATE game_tables SET narration_model = NULL WHERE id = :id'), table_filter)
    await session.execute(text('UPDATE table_rounds SET narration_model = NULL WHERE table_id = :id'), table_filter)
    await session.commit()


async def close_solo(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """혼자 앉은 테이블의 라운드를 선언으로 닫고, 서술이 끝날 때까지 기다린다."""
    await declare(client, me, table, LAUGH)
    await narrated()


# --- 만들 때 ---


async def test_without_a_pick_the_table_takes_the_recommended_model(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['narration_model'] == TEST_MODEL


async def test_without_the_price_list_no_table_is_made(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('unreachable'))

    response = await open_with(client, me)

    # 고르지 않아도 추천 모델을 지금 파는지 본다. 값을 모르는 모델로 테이블을 만들지 않는다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


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
    # 아직 라운드가 없다. 테이블의 모델만 바뀌었다
    assert changed['payload'] == {'narration_model': 'claude-opus-5-5', 'round': None, 'price': None}


async def test_the_model_cannot_be_cleared(client: AsyncClient, me: dict[str, str]):
    table = (await open_with(client, me, narration_model='gpt-6-luna')).json()

    response = await set_model(client, me, table, None)

    # 서버의 기본 모델로 돌아가는 길은 없다. 늘 고를 수 있는 모델 하나로 서술한다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await events_of(client, me, table, 'narration_model_changed') == []


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


@pytest.mark.parametrize(
    'body', [{}, {'narration_model': None}, {'narration_model': 'gpt-6-luna', 'extra': 1}, {'narration_model': 7}]
)
async def test_a_bad_change_is_rejected(client: AsyncClient, me: dict[str, str], body: dict):
    table = (await open_with(client, me)).json()

    response = await client.put(table_url(table, '/narration-model'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 시작하면 고정 ---


async def test_a_started_table_keeps_a_model_it_can_use(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    response = await set_model(client, me, table, 'claude-opus-5-5')

    # 앉은 사람은 Luna 와 그 값을 보고 앉았다. 방장 혼자 모두의 값을 바꾸지 않는다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'narration_model_locked'
    assert (await current(client, me, table))['narration_model'] == 'gpt-6-luna'
    assert await events_of(client, me, table, 'narration_model_changed') == []


async def test_a_started_table_may_send_the_same_model(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    response = await set_model(client, me, table, 'gpt-6-luna')

    # 바꿀 것이 없으면 잠겼는지 보기 전에 끝난다
    assert response.status_code == status.HTTP_200_OK, response.text


async def test_a_model_the_operator_turned_off_can_be_changed(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await catalog.disable_model(session, 'gpt-6-luna')
    await session.commit()

    response = await set_model(client, me, table, 'claude-opus-5-5')

    # 지금 모델로는 서술할 수 없다. 방장이 다시 고른다
    assert response.status_code == status.HTTP_200_OK, response.text
    assert (await current(client, me, table))['narration_model'] == 'claude-opus-5-5'


async def test_a_model_no_longer_sold_can_be_changed(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    stop_selling_luna(app)

    response = await set_model(client, me, table, 'claude-opus-5-5')

    assert response.status_code == status.HTTP_200_OK, response.text


async def test_without_the_price_list_a_started_table_cannot_tell_and_says_so(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    app.state.price_list = FixedPrices(FREE_BOOK, error=PriceListUnavailable('unreachable'))

    response = await set_model(client, me, table, 'claude-opus-5-5')

    # 지금 모델을 쓸 수 있는지 모른다. 잠긴 것으로도 풀린 것으로도 답하지 않는다
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# --- 라운드에 굳기 ---


async def test_a_round_takes_the_model_of_the_table_when_it_opens(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, narration_model='gpt-6-luna')

    round_ = await current(client, me, table)
    (opened,) = await events_of(client, me, table, 'round_opened')

    assert round_['narration_model'] == 'gpt-6-luna'
    assert opened['payload']['narration_model'] == 'gpt-6-luna'


async def test_a_change_while_declaring_applies_to_the_open_round(
    client: AsyncClient, app: FastAPI, me: dict[str, str], recording: RecordingNarrator, narrated
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    stop_selling_luna(app)

    await set_model(client, me, table, 'claude-opus-5-5')
    changed = await current(client, me, table)
    (event,) = await events_of(client, me, table, 'narration_model_changed')
    await close_solo(client, me, table, narrated)

    # 아직 서술하지 않은 라운드라 그 라운드도 Opus 다. 청구는 새 가격표로 다시 건다(test_narration_blocks.py)
    # 결제 서버가 파는 Opus 의 지금 값을 함께 알린다
    assert changed['narration_model'] == 'claude-opus-5-5'
    assert event['payload'] == {
        'narration_model': 'claude-opus-5-5',
        'round': 1,
        'price': {'tier': 'standard', 'credits': '20'},
    }
    assert [request.model for request in recording.requests] == ['claude-opus-5-5']


async def test_a_change_while_narrating_waits_for_the_next_round(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    # 서술이 돌고 있는 라운드(닫는 중, 실패하지 않음)와 같다
    await session.execute(
        text('UPDATE table_rounds SET closing_at = now() WHERE table_id = :id'), {'id': uuid.UUID(table['id'])}
    )
    await session.commit()
    stop_selling_luna(app)

    response = await set_model(client, me, table, 'claude-opus-5-5')
    (event,) = await events_of(client, me, table, 'narration_model_changed')

    # 연 때의 모델의 값을 걸었고 그 모델로 서술하는 중이다. 테이블만 바뀌고 다음 라운드부터다
    assert response.json()['narration_model'] == 'claude-opus-5-5'
    assert (await current(client, me, table))['narration_model'] == 'gpt-6-luna'
    assert event['payload'] == {'narration_model': 'claude-opus-5-5', 'round': None, 'price': None}


async def test_an_old_round_without_a_model_is_narrated_by_the_default(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, recording: RecordingNarrator, narrated
):
    table = await start_with(client, me)
    await clear_models(session, table)

    await close_solo(client, me, table, narrated)

    # 모델을 고르는 규칙 전에 연 라운드다. 서버의 기본 서술자(LLM_MODEL)가 받는다
    assert [request.model for request in recording.requests] == [None]


async def test_an_old_round_without_a_model_holds_the_legacy_price(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, billing: FakeBillingServer, narrated
):
    table = await start_with(client, me)
    await clear_models(session, table)
    await close_solo(client, me, table, narrated)
    await tick(app)

    charges = await charges_of(session, table)

    # 1 라운드는 테스트 모델로 열려 걸었다. 모델이 없는 테이블이 연 2 라운드는 옛 가격표로 건다
    assert [charge.price_code for charge in charges] == [TEST_PRICE_CODE, LEGACY_PRICE_CODE]


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
    monkeypatch.setitem(PRICES, narration_code('claude-opus-5-5'), 60)
    table = await start_with(client, me, narration_model='gpt-6-luna')
    await tick(app)
    await close_solo(client, me, table, narrated)
    await tick(app)
    # 2 라운드가 Luna 로 열린 뒤 Luna 를 팔지 않게 되어 Opus 로 바꾼다. 2 라운드도 아직 서술하지 않았으니
    # Opus 의 가격표로 바뀐다
    stop_selling_luna(app)
    await set_model(client, me, table, 'claude-opus-5-5')
    await tick(app)
    await close_solo(client, me, table, narrated)
    await tick(app)

    charges = await charges_of(session, table)

    # 1 라운드는 Luna 의 가격표로 걸고 확정했다. 2 라운드는 Opus 의 가격표로 다시 걸어 확정했다. 3 라운드도 Opus 다
    assert [charge.price_code for charge in charges] == [
        'narration.gpt-6-luna.i0.o0',
        'narration.claude-opus-5-5.i0.o0',
        'narration.claude-opus-5-5.i0.o0',
    ]
    assert [charge.status for charge in charges] == ['captured', 'captured', 'held']
    assert billing.balance(ME) == 1000 - 20 - 2 * 60


# --- 서술자 ---


async def test_the_picked_narrator_uses_the_model_of_the_round():
    made: dict[str, RecordingNarrator] = {}

    def chain_for(model: str) -> RecordingNarrator:
        return made.setdefault(model, RecordingNarrator())

    default = RecordingNarrator()
    narrator = PickedNarrator(chain_for=chain_for, default=default)

    await narrator.narrate(NarrationRequest(round_number=1, scene='장면', moves=[], model='gpt-6-luna'))
    await narrator.narrate(NarrationRequest(round_number=2, scene='장면', moves=[]))

    # 모델이 굳은 라운드는 그 모델의 서술자만, 모델이 없는 옛 라운드는 기본 서술자만 받는다
    assert [request.round_number for request in made['gpt-6-luna'].requests] == [1]
    assert [request.round_number for request in default.requests] == [2]


async def test_the_same_model_still_reaches_a_round_that_kept_the_old_one(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table = await start_with(client, me, narration_model='gpt-6-luna')
    round_filter = {'id': uuid.UUID(table['id'])}
    await session.execute(text('UPDATE table_rounds SET closing_at = now() WHERE table_id = :id'), round_filter)
    await session.commit()
    stop_selling_luna(app)
    await set_model(client, me, table, 'claude-opus-5-5')
    # 그 서술이 실패해 멈췄다. 테이블은 이미 Opus 지만 라운드는 Luna 그대로다
    await session.execute(
        text('UPDATE table_rounds SET narration_failed_at = now() WHERE table_id = :id'), round_filter
    )
    await session.commit()

    await set_model(client, me, table, 'claude-opus-5-5')
    events = await events_of(client, me, table, 'narration_model_changed')

    # 같은 값이라도 멈춘 라운드에는 아직 닿지 않았으니 바꾼다.
    # 테이블의 Opus 는 팔지만 라운드의 Luna 를 쓸 수 없어 잠기지 않는다
    assert (await current(client, me, table))['narration_model'] == 'claude-opus-5-5'
    assert [event['payload']['round'] for event in events] == [None, 1]
