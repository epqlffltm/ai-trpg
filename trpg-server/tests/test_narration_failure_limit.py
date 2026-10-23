# trpg-server/tests/test_narration_failure_limit.py

"""
서술의 실패에 상한을 두는 것(app/rounds/service.py 의 NARRATION_FAILURE_LIMIT, abandon_narration)을 검증한다.

보는 것.
  - 서술이 실패할 때마다 센다. 방장이 다시 맡겨도 0 으로 돌리지 않는다. 라운드의 응답에 보인다.
  - 처음과 다시 맡긴 두 번, 모두 세 번 실패하면 서술을 그만둔다. 엔진의 결과의 줄로 다음 라운드를 연다.
    앉은 사람 모두에게 이벤트로 알린다.
  - 그만둔 라운드의 값은 받지 않는다(돌려준다).
  - 서술 값을 잡지 못한 실패(크레딧이 모자람)는 모델을 부르지 않았으니 세지 않는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds.llm_narrator import NarrationError
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.rounds.service import NARRATION_FAILURE_LIMIT
from tests.billing import PRICES, FakeBillingServer
from tests.test_narration_billing import charges_of, tick
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_round_time_limit import current, start_with

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
LAUGH = '크게 웃는다.'


class FailingNarrator:
    """늘 잘려서 실패하는 서술자. 불린 횟수를 센다."""

    def __init__(self) -> None:
        self.calls = 0

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.calls += 1
        raise NarrationError('cut_off')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장."""
    return bearer(signing_key, ME)


@pytest.fixture
def failing(app: FastAPI) -> FailingNarrator:
    """앱에 꽂은, 늘 실패하는 서술자."""
    narrator = FailingNarrator()
    app.state.narrator = narrator
    return narrator


async def billing_with(app: FastAPI, balance: int) -> FakeBillingServer:
    """앱에 가짜 결제 서버를 꽂는다. 방장(ME)에게 balance 크레딧이 있다."""
    server = FakeBillingServer(balances={ME: balance})
    app.state.billing = server.billing(server.make_client())
    return server


async def retry(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """실패한 서술을 방장이 다시 맡기고 끝날 때까지 기다린다."""
    response = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    await narrated()


async def fail_times(client: AsyncClient, me: dict[str, str], table: dict, narrated, times: int) -> None:
    """선언으로 닫아 한 번 실패시키고, 그 뒤로 times - 1 번 다시 맡겨 실패시킨다."""
    await declare(client, me, table, LAUGH)
    await narrated()
    for _ in range(times - 1):
        await retry(client, me, table, narrated)


def test_the_limit_is_the_first_try_and_two_retries():
    assert NARRATION_FAILURE_LIMIT == 3


async def test_each_failure_is_counted_and_retries_do_not_reset_it(
    client: AsyncClient, me: dict[str, str], failing: FailingNarrator, narrated
):
    table = await start_with(client, me)

    await fail_times(client, me, table, narrated, 2)
    round_ = await current(client, me, table)

    # 화면은 이것으로 "다시 맡기기 1 번 남음"을 보여 준다
    assert (round_['number'], round_['narration_failures']) == (1, 2)
    assert round_['narration_failed_at'] is not None
    assert failing.calls == 2


async def test_the_third_failure_abandons_the_narration(
    client: AsyncClient, me: dict[str, str], failing: FailingNarrator, narrated
):
    table = await start_with(client, me)

    await fail_times(client, me, table, narrated, NARRATION_FAILURE_LIMIT)
    second = await current(client, me, table)
    (abandoned,) = await events_of(client, me, table, 'narration_abandoned')
    failed = await events_of(client, me, table, 'narration_failed')

    # 테이블은 멈추지 않는다. 엔진이 정한 결과의 줄로 다음 라운드가 열린다
    assert second['number'] == 2
    assert second['scene'].startswith('[1 라운드의 결과]')
    assert LAUGH in second['scene']
    assert abandoned['payload'] == {'round': 1, 'reason': 'cut_off', 'failures': NARRATION_FAILURE_LIMIT}
    # 앞의 두 번은 실패로 적혀 방장이 다시 맡겼다. 세 번째는 실패로 적지 않고 그만뒀다
    assert len(failed) == NARRATION_FAILURE_LIMIT - 1


async def test_an_abandoned_round_is_not_charged(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, failing: FailingNarrator, narrated
):
    billing = await billing_with(app, 1000)
    table = await start_with(client, me)
    await tick(app)

    await fail_times(client, me, table, narrated, NARRATION_FAILURE_LIMIT)
    await tick(app)
    first, second = await charges_of(session, table)

    # 그만둔 1 라운드의 값은 돌려줬다. 2 라운드는 새로 걸었다. 빠진 것은 2 라운드의 값뿐이다
    assert (first.status, second.status) == ('released', 'held')
    assert billing.statuses() == {first.reference: 'released', second.reference: 'held'}
    assert billing.balance(ME) == 1000 - PRICES[second.price_code]


async def test_a_failure_to_secure_the_payment_is_not_counted(
    client: AsyncClient, app: FastAPI, me: dict[str, str], failing: FailingNarrator, narrated
):
    await billing_with(app, 0)
    table = await start_with(client, me)

    await fail_times(client, me, table, narrated, NARRATION_FAILURE_LIMIT + 1)
    round_ = await current(client, me, table)

    # 크레딧이 모자라 모델을 부르지 않았다. 원가가 들지 않았으니 세지 않는다. 충전하면 다시 맡길 수 있다
    assert (round_['number'], round_['narration_failures']) == (1, 0)
    assert failing.calls == 0
    assert await events_of(client, me, table, 'narration_abandoned') == []
