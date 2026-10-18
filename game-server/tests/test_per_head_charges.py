# game-server/tests/test_per_head_charges.py

"""
앉은 사람 모두가 서술 값을 각자 내는 것(#180)을 검증한다. 결제 서버 자리에 가짜를 꽂는다(tests/billing.py).

보는 것.
  - 라운드를 열면 앉은 사람마다 청구가 하나씩 생긴다. 이름표가 사람마다 다르다. 각자의 크레딧에서 빠진다.
  - 한 사람이라도 모자라면 서술하지 않는다. 누가 모자란지 앉은 사람 모두가 이벤트로 본다. 모자란 사람이 여럿이면 모두.
    다른 사람의 홀드는 그대로 둔다. 모자란 사람이 충전하면 같은 홀드로 서술한다.
  - 떠난 사람(나가기, 내보내기)의 청구
      - 아직 안 걸림·모자람: 돌려줄 것이 된다. 서술을 막지 않는다. 모자란 사람을 내보내면 바로 다시 맡겨 서술한다
      - 걸림, 라운드가 열려 있음: 돌려준다
      - 걸림, 닫기 시작한 뒤: 그대로 두고 서술되면 확정한다
  - 여럿의 결과를 하나로 모으는 규칙(worst).
청구 하나의 흐름(연장, 만료, 거절)은 tests/test_narration_billing.py 가 본다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.settling import Readiness, worst
from tests.billing import FakeBillingServer
from tests.narration_model import TEST_PRICE_CODE
from tests.signing import SigningKey
from tests.test_narration_billing import PRICE, charges_of, close_round, tick
from tests.test_npc_actions import events_of
from tests.test_round_closing import (
    FRIEND,
    FRIENDS_ACTION,
    ME,
    MY_ACTION,
    RESULT,
    GatedNarrator,
    bearer,
    current,
    declare,
    start_duo,
    table_url,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

# 각자의 처음 크레딧
CREDITS = 1000


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """함께 앉는 사람."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
async def billing(app: FastAPI) -> FakeBillingServer:
    """앱에 꽂은 가짜 결제 서버. 둘 다 CREDITS 만큼 있다."""
    server = FakeBillingServer(balances={ME: CREDITS, FRIEND: CREDITS})
    client = server.make_client()
    app.state.billing = server.billing(client)
    yield server
    await client.aclose()


@pytest.fixture
def narrator(app: FastAPI) -> GatedNarrator:
    """앱에 꽂은 문 앞의 서술자. 문이 열려 있다. 테스트가 닫을 수 있다."""
    gated = GatedNarrator()
    gated.release()
    app.state.narrator = gated
    yield gated
    gated.release()


async def statuses(session: AsyncSession, table: dict, payer: uuid.UUID) -> list[str]:
    """그 사람의 청구들의 상태. 라운드 순서다."""
    return [charge.status for charge in await charges_of(session, table, payer)]


async def short_names(client: AsyncClient, headers: dict[str, str], table: dict) -> list[str]:
    """크레딧이 모자란다고 알린 사람들. 알린 순서다."""
    return [event['payload']['user_id'] for event in await events_of(client, headers, table, 'narration_credits_short')]


async def retry(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """방장이 서술을 다시 맡기고 끝날 때까지 기다린다."""
    response = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    await narrated()


# --- 각자 낸다 ---


async def test_opening_a_round_charges_everyone_seated(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)

    mine, theirs = await charges_of(session, table, ME), await charges_of(session, table, FRIEND)

    # 사람마다 한 줄, 같은 가격표, 다른 이름표(결제 서버가 따로 받는다)
    assert [charge.status for charge in mine + theirs] == ['pending', 'pending']
    assert mine[0].price_code == theirs[0].price_code == TEST_PRICE_CODE
    assert mine[0].reference.endswith(str(ME))
    assert theirs[0].reference.endswith(str(FRIEND))


async def test_each_pays_from_their_own_credits(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, billing: FakeBillingServer, narrator, narrated
):
    table = await start_duo(client, me, friend)
    await tick(app)

    await close_round(client, me, friend, table, narrated)

    # 나눠 내지 않는다. 각자 서술 한 번의 값을 낸다
    assert (await current(client, me, table))['scene'] == RESULT
    assert (billing.balance(ME), billing.balance(FRIEND)) == (CREDITS - PRICE, CREDITS - PRICE)


# --- 모자랄 때 ---


async def test_one_short_stops_the_narration_and_names_who(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    billing.balances[FRIEND] = PRICE - 1
    table = await start_duo(client, me, friend)
    await tick(app)

    await close_round(client, me, friend, table, narrated)
    (failed,) = await events_of(client, me, table, 'narration_failed')

    # 누가 모자란지 모두가 본다. 낼 수 있는 사람의 홀드는 그대로 둔다(충전하면 같은 홀드로 서술한다)
    assert await short_names(client, me, table) == [str(FRIEND)]
    assert failed['payload']['reason'] == 'insufficient_credits'
    assert (await statuses(session, table, ME), await statuses(session, table, FRIEND)) == (['held'], ['short'])


async def test_everyone_short_is_named(
    client: AsyncClient, me: dict, friend: dict, billing: FakeBillingServer, narrator, narrated
):
    billing.balances[ME] = 0
    billing.balances[FRIEND] = 0
    table = await start_duo(client, me, friend)

    await close_round(client, me, friend, table, narrated)

    # 한 사람에서 멈추지 않고 모두에게 걸어 본다. 모자란 사람 모두를 알린다
    assert sorted(await short_names(client, me, table)) == sorted([str(ME), str(FRIEND)])


async def test_after_the_short_one_tops_up_the_round_is_narrated_once_each(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    billing.balances[FRIEND] = 0
    table = await start_duo(client, me, friend)
    await tick(app)
    await close_round(client, me, friend, table, narrated)

    billing.balances[FRIEND] = CREDITS
    await retry(client, me, table, narrated)

    # 방장의 홀드는 다시 걸지 않았다. 둘 다 한 번씩만 빠졌다
    assert (await current(client, me, table))['number'] == 2
    assert (await statuses(session, table, ME))[0] == 'captured'
    assert (await statuses(session, table, FRIEND))[0] == 'captured'
    assert (billing.balance(ME), billing.balance(FRIEND)) == (CREDITS - PRICE, CREDITS - PRICE)


# --- 떠난 사람 ---


async def test_kicking_the_short_one_lets_the_others_go_on(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    billing.balances[FRIEND] = 0
    table = await start_duo(client, me, friend)
    await tick(app)
    await close_round(client, me, friend, table, narrated)

    kicked = await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)
    await retry(client, me, table, narrated)
    await tick(app)

    # 내보낸 사람의 모자란 청구는 서술을 막지 않는다. 방장만 냈다(1 라운드 확정, 2 라운드는 방장 혼자 걸었다)
    assert kicked.status_code == status.HTTP_200_OK, kicked.text
    assert (await current(client, me, table))['scene'] == RESULT
    assert await statuses(session, table, FRIEND) == ['released']
    assert await statuses(session, table, ME) == ['captured', 'held']
    assert (billing.balance(ME), billing.balance(FRIEND)) == (CREDITS - 2 * PRICE, 0)


async def test_leaving_an_open_round_gives_the_credits_back(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
):
    table = await start_duo(client, me, friend)
    await tick(app)

    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    await tick(app)

    # 선언을 받는 중이었다. 나간 사람은 이 라운드의 장면에 나오지 않으니 받지 않는다
    assert left.status_code == status.HTTP_204_NO_CONTENT, left.text
    assert await statuses(session, table, FRIEND) == ['released']
    assert await statuses(session, table, ME) == ['held']
    assert billing.balance(FRIEND) == CREDITS


async def test_leaving_before_the_hold_leaves_no_hold_behind(
    client: AsyncClient, app: FastAPI, session: AsyncSession, me: dict, friend: dict, billing: FakeBillingServer
):
    table = await start_duo(client, me, friend)

    await client.delete(table_url(table, '/members/me'), headers=friend)
    await tick(app)

    # 정리 작업이 걸기 전에 나갔다. 걸지 않고 돌려줄 것으로 끝낸다(없는 홀드를 돌려줘도 해가 없다)
    assert await statuses(session, table, FRIEND) == ['released']
    assert billing.balance(FRIEND) == CREDITS
    assert ('holds', f'narration:{table["id"]}:1:{FRIEND}') not in billing.calls


async def test_leaving_after_closing_began_still_pays_for_the_scene(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator: GatedNarrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    await tick(app)
    narrator.hold()
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrator.wait_until_called()

    await client.delete(table_url(table, '/members/me'), headers=friend)
    narrator.release()
    await narrated()
    await tick(app)

    # 닫기 시작할 때 그 사람의 선언도 굳었다. 장면에 들어갔으니 확정한다
    assert (await current(client, me, table))['scene'] == RESULT
    assert (await statuses(session, table, FRIEND)) == ['captured']
    assert billing.balance(FRIEND) == CREDITS - PRICE


async def test_the_next_round_charges_only_those_still_seated(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    me: dict,
    friend: dict,
    billing: FakeBillingServer,
    narrator,
    narrated,
):
    table = await start_duo(client, me, friend)
    await client.delete(table_url(table, '/members/me'), headers=friend)

    await declare(client, me, table, MY_ACTION)
    await narrated()

    # 2 라운드는 남은 방장만 낸다
    assert await statuses(session, table, ME) == ['captured', 'pending']
    assert await statuses(session, table, FRIEND) == ['released']


# --- 결과를 모으는 규칙 ---


@pytest.mark.parametrize(
    ('results', 'expected'),
    [
        ([], Readiness.READY),
        ([Readiness.READY, Readiness.READY], Readiness.READY),
        ([Readiness.READY, Readiness.UNAVAILABLE], Readiness.UNAVAILABLE),
        ([Readiness.UNAVAILABLE, Readiness.SHORT], Readiness.SHORT),
        ([Readiness.SHORT, Readiness.READY], Readiness.SHORT),
    ],
)
def test_short_outweighs_unavailable_outweighs_ready(results: list[Readiness], expected: Readiness):
    # 모자람은 사람이 움직여야 풀린다. 답을 못 받은 것은 정리 작업이 저절로 다시 한다. 그래서 모자람을 알린다
    assert worst(results) == expected
