# game-server/tests/test_narration_tiers.py

"""
서술 등급(app/rounds/tiers.py)을 검증한다.

보는 것.
  - 테이블의 설정: 고르지 않으면 standard. 이 서버가 내주는 등급만 고를 수 있다. 목록과 상세에 보인다.
    DB 도 값을 지킨다.
  - 내주는 등급의 목록(GET /tables/narration-tiers).
  - 바꾸기: 방장만, 끝나기 전까지, 내주는 등급만. 이벤트로 남는다. 같은 값이면 아무것도 적지 않는다.
  - 라운드에 굳기: 열 때의 등급으로 값을 걸고 서술한다. 열려 있는 동안 바꿔도 그 라운드는 그대로다.
    다음 라운드부터 바뀐다.
  - 서술자: 라운드의 등급의 서술자를 부른다. 그 등급의 서술자가 없으면 서술하지 않는다(tier_unavailable).
  - 값: 등급의 가격표 이름으로 건다. 결제 서버의 가격표에 없으면 받지 않는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.charges import price_code_for
from app.rounds.fake_narrator import FakeNarrator
from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.rounds.tiered_narrator import TIER_UNAVAILABLE, TieredNarrator
from app.rounds.tiers import NarrationTier
from tests.billing import PRICES, FakeBillingServer
from tests.signing import SigningKey
from tests.test_narration_billing import charges_of, tick
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_round_time_limit import current, open_with, start_with
from tests.test_tables_api import TABLES_URL

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

LAUGH = '크게 웃는다.'
TIERS_URL = f'{TABLES_URL}/narration-tiers'
STANDARD_ONLY = frozenset({NarrationTier.STANDARD})


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 방장(ME)에게 1000 크레딧이 있다."""
    server = FakeBillingServer(balances={ME: 1000})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


class RecordingNarrator:
    """받은 요청을 적어 두는 서술자. 등급을 가리지 않는다."""

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


async def set_tier(client: AsyncClient, headers: dict[str, str], table: dict, tier):
    """서술 등급을 바꾼다. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, '/narration-tier'), json={'narration_tier': tier}, headers=headers)


async def close_solo(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """혼자 앉은 테이블의 라운드를 선언으로 닫고, 서술이 끝날 때까지 기다린다."""
    await declare(client, me, table, LAUGH)
    await narrated()


# --- 테이블의 설정 ---


async def test_the_default_tier_is_standard(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['narration_tier'] == 'standard'


async def test_an_offered_tier_can_be_chosen(client: AsyncClient, me: dict[str, str]):
    response = await open_with(client, me, narration_tier='premium')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert response.json()['narration_tier'] == 'premium'


async def test_a_tier_the_server_does_not_offer_is_rejected(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    app.state.narration_tiers = STANDARD_ONLY

    response = await open_with(client, me, narration_tier='premium')

    # 모델이 없는 등급의 테이블을 만들면 첫 라운드부터 서술할 수 없다. 만들 때 막는다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'narration_tier' in response.json()['detail']
    assert (await client.get(TABLES_URL, headers=me)).json()['total'] == 0


@pytest.mark.parametrize('tier', ['gold', '', None, 'STANDARD'])
async def test_an_unknown_tier_is_rejected(client: AsyncClient, me: dict[str, str], tier):
    response = await open_with(client, me, narration_tier=tier)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_list_shows_the_tier(client: AsyncClient, me: dict[str, str]):
    await open_with(client, me, narration_tier='premium')

    listed = (await client.get(TABLES_URL, headers=me)).json()

    assert [table['narration_tier'] for table in listed['items']] == ['premium']


async def test_the_database_keeps_the_tiers(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = (await open_with(client, me)).json()

    with pytest.raises(IntegrityError):
        await session.execute(
            text("UPDATE game_tables SET narration_tier = 'gold' WHERE id = :id"), {'id': uuid.UUID(table['id'])}
        )
    await session.rollback()


# --- 내주는 등급 ---


async def test_the_server_lists_the_tiers_it_offers(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    every = (await client.get(TIERS_URL, headers=me)).json()
    app.state.narration_tiers = STANDARD_ONLY
    standard_only = (await client.get(TIERS_URL, headers=me)).json()

    # 늘 같은 차례다(싼 것부터)
    assert every == {'tiers': ['standard', 'premium']}
    assert standard_only == {'tiers': ['standard']}


async def test_the_tiers_need_a_login(client: AsyncClient):
    response = await client.get(TIERS_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 바꾸기 ---


async def test_the_host_changes_the_tier_and_it_is_recorded(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me)

    response = await set_tier(client, me, table, 'premium')
    (changed,) = await events_of(client, me, table, 'narration_tier_changed')

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['narration_tier'] == 'premium'
    assert (changed['actor_id'], changed['payload']) == (str(ME), {'narration_tier': 'premium'})


async def test_the_same_tier_writes_nothing(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me)

    response = await set_tier(client, me, table, 'standard')

    assert response.status_code == status.HTTP_200_OK
    assert await events_of(client, me, table, 'narration_tier_changed') == []


async def test_only_the_host_changes_the_tier(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_with(client, me, friend)

    response = await set_tier(client, friend, table, 'premium')

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_an_ended_table_keeps_its_tier(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me)
    await client.post(table_url(table, '/end'), headers=me)

    response = await set_tier(client, me, table, 'premium')

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_a_tier_the_server_does_not_offer_cannot_be_chosen_later(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    table = await start_with(client, me)
    app.state.narration_tiers = STANDARD_ONLY

    response = await set_tier(client, me, table, 'premium')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await client.get(table_url(table), headers=me)).json()['narration_tier'] == 'standard'


@pytest.mark.parametrize('body', [{}, {'narration_tier': None}, {'narration_tier': 'premium', 'now': True}])
async def test_a_bad_change_is_rejected(client: AsyncClient, me: dict[str, str], body: dict):
    table = await start_with(client, me)

    response = await client.put(table_url(table, '/narration-tier'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 라운드에 굳기 ---


async def test_a_round_takes_the_tier_of_the_table_when_it_opens(client: AsyncClient, me: dict[str, str]):
    table = await start_with(client, me, narration_tier='premium')

    round_ = await current(client, me, table)
    (opened,) = await events_of(client, me, table, 'round_opened')

    assert round_['narration_tier'] == 'premium'
    assert opened['payload']['narration_tier'] == 'premium'


async def test_the_change_waits_for_the_next_round(
    client: AsyncClient, me: dict[str, str], recording: RecordingNarrator, narrated
):
    table = await start_with(client, me, narration_tier='premium')

    await set_tier(client, me, table, 'standard')
    unchanged = await current(client, me, table)
    await close_solo(client, me, table, narrated)
    second = await current(client, me, table)

    # 열려 있던 라운드는 premium 으로 값을 걸었으니 premium 으로 서술한다. 다음 라운드부터 standard 다
    assert unchanged['narration_tier'] == 'premium'
    assert [request.tier for request in recording.requests] == [NarrationTier.PREMIUM]
    assert second['narration_tier'] == 'standard'


async def test_the_database_keeps_the_tiers_of_rounds(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = await start_with(client, me)

    with pytest.raises(IntegrityError):
        await session.execute(
            text("UPDATE table_rounds SET narration_tier = 'gold' WHERE table_id = :id"),
            {'id': uuid.UUID(table['id'])},
        )
    await session.rollback()


# --- 서술자 ---


async def test_the_tiered_narrator_calls_the_narrator_of_the_tier():
    standard, premium = RecordingNarrator(), RecordingNarrator()
    narrator = TieredNarrator({NarrationTier.STANDARD: standard, NarrationTier.PREMIUM: premium})
    request = NarrationRequest(round_number=1, scene='장면', moves=[], tier=NarrationTier.PREMIUM)

    await narrator.narrate(request)

    assert (len(standard.requests), len(premium.requests)) == (0, 1)


async def test_a_tier_without_a_narrator_is_not_narrated_more_cheaply():
    standard = RecordingNarrator()
    narrator = TieredNarrator({NarrationTier.STANDARD: standard})
    request = NarrationRequest(round_number=1, scene='장면', moves=[], tier=NarrationTier.PREMIUM)

    # 값을 premium 으로 걸어 둔 라운드다. standard 로 서술하면 낸 값과 받은 서술이 어긋난다
    with pytest.raises(NarrationError, match=TIER_UNAVAILABLE):
        await narrator.narrate(request)
    assert standard.requests == []


async def test_a_round_whose_tier_lost_its_models_fails_and_can_be_retried(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    table = await start_with(client, me, narration_tier='premium')
    # 설정에서 premium 의 모델을 지우고 다시 띄운 것과 같다
    app.state.narrator = TieredNarrator({NarrationTier.STANDARD: FakeNarrator()})

    await close_solo(client, me, table, narrated)
    (failed,) = await events_of(client, me, table, 'narration_failed')
    app.state.narrator = TieredNarrator({NarrationTier.STANDARD: FakeNarrator(), NarrationTier.PREMIUM: FakeNarrator()})
    retried = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    # 실패로 적혀 방장이 바로 다시 맡길 수 있다. 설정을 되돌린 뒤 다시 맡기면 서술한다
    assert failed['payload']['reason'] == TIER_UNAVAILABLE
    assert retried.status_code == status.HTTP_202_ACCEPTED, retried.text
    assert (await current(client, me, table))['number'] == 2


# --- 값 ---


async def test_each_round_holds_the_price_of_its_tier(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, billing: FakeBillingServer, narrated
):
    table = await start_with(client, me, narration_tier='premium')
    await tick(app)
    await set_tier(client, me, table, 'standard')
    await close_solo(client, me, table, narrated)
    await tick(app)

    charges = await charges_of(session, table)

    # 1 라운드는 premium 으로 걸고 확정했다. 2 라운드는 standard 로 걸었다
    assert [charge.price_code for charge in charges] == ['narration.premium', 'narration.standard']
    assert [charge.status for charge in charges] == ['captured', 'held']
    assert billing.balance(ME) == 1000 - PRICES['narration.premium'] - PRICES['narration.standard']


async def test_a_tier_missing_from_the_price_table_is_not_narrated(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    billing: FakeBillingServer,
    narrated,
    monkeypatch: pytest.MonkeyPatch,
):
    # 결제 서버에 premium 의 가격을 적지 않고 게임 서버에서 premium 을 내준 것이다
    monkeypatch.delitem(PRICES, price_code_for(NarrationTier.PREMIUM))
    table = await start_with(client, me, narration_tier='premium')
    await tick(app)

    await close_solo(client, me, table, narrated)
    (failed,) = await events_of(client, me, table, 'narration_failed')
    (charge,) = await charges_of(session, table)

    # 결제 서버가 받지 않는다(400 price.unknown). 외상으로 서술하지 않는다. 팔지 않는 가격표로 알린다
    assert (charge.status, charge.last_error) == ('failed', 'price.unknown')
    assert failed['payload']['reason'] == 'model_not_for_sale'
    assert billing.balance(ME) == 1000
