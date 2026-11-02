# chat-server/tests/test_billing_mix_api.py

"""
말 보내기, 멈추기, 다시 생성, 이어서 출력을 섞어 눌렀을 때 대화와 청구가 맞는지(#811) API 로 검증한다.
실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

길 하나하나의 동작은 test_turns_api.py, test_branches_api.py, test_continue_api.py 가 본다. 여기서는 섞인 차례를 본다.

지킬 것(시험마다 끝에 장부로 본다).
  - 한 대화에서 동시에 생성 중인 답은 하나다. 다른 생성 요청은 409 이고 홀드를 걸지 않는다
  - 글을 받은 호출(complete, partial)마다 확정이 한 번이다. 이어서 출력은 새 호출이라 따로 한 번이다
  - 실패한 생성(글자 없음)은 홀드를 돌려주고, 홀드가 걸리지 않은 요청은 답을 저장하지 않는다
  - 잔액은 처음 값에서 확정한 호출 수 × 값만큼 줄었다. 도중인 기록(pending, held)이 남지 않는다

보는 것.
  - 멈춤 → 이어서 → 다시 생성 → 또 다시 생성
  - 다시 생성을 동시에 둘 보내면 하나만 들어간다
  - 다시 생성이 도는 동안의 이어서 출력과 다시 생성과 새 말은 409 다
  - 도중에 홀드가 걸리지 않으면 그 답은 저장되지 않고 앞의 답이 그대로 보인다
  - 도중에 모델이 실패하면 홀드가 돌아오고 차례를 놓아 다음 생성이 된다
"""

import asyncio
import uuid
from collections.abc import Awaitable

import pytest
from ai_core.provider import ProviderError
from fastapi import FastAPI, status
from httpx import AsyncClient, Response
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.turns.models import Generation
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

START = 1000
PRICE = 30
# 글을 받아 저장되는 호출의 끝
SAVED = frozenset({'complete', 'partial'})
OPEN = frozenset({'pending', 'held'})
# 차례를 못 잡은 요청이 돌아오기를 기다리는 시간(초)
REFUSAL_SECONDS = 5


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
def billing(app: FastAPI) -> FakeBillingServer:
    """가짜 결제 서버. 나는 크레딧 START 가 있고, luna 의 말 한 번은 PRICE 다."""
    server = FakeBillingServer(balances={ME: START})
    server.prices[PRICE_CODE] = PRICE
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    """luna 로 시작한 내 대화. 인사말이 첫 말이다."""
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


def send(client: AsyncClient, headers: dict, conversation: dict, content: str = '안녕'):
    return client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json={'content': content}, headers=headers)


def regenerate(client: AsyncClient, headers: dict, message_id: str):
    return client.post(f'{API_PREFIX}/messages/{message_id}/regenerate', headers=headers)


def go_on(client: AsyncClient, headers: dict, message_id: str):
    return client.post(f'{API_PREFIX}/messages/{message_id}/continue', headers=headers)


def stop(client: AsyncClient, headers: dict, generation_id: uuid.UUID):
    return client.post(f'{API_PREFIX}/generations/{generation_id}/stop', headers=headers)


async def done_message(app: FastAPI, response: Response) -> dict:
    """끝까지 기다린 응답의 마지막 말."""
    await finished(app)
    assert response.status_code == status.HTTP_200_OK, response.text
    name, data = parse_sse(response.text)[-1]
    assert name == 'done', data
    return data['message']


async def refused_at_once(request: Awaitable[Response]) -> Response:
    """차례를 못 잡은 요청은 모델을 기다리지 않고 바로 돌아온다. 차례가 풀리면 모델을 기다리다 시간이 넘는다."""
    return await asyncio.wait_for(request, timeout=REFUSAL_SECONDS)


async def calling(provider: ScriptedProvider, calls: int) -> None:
    """모델이 calls 번째로 불려 조각을 다 흘릴 때까지 기다린다."""
    while len(provider.calls) < calls:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)


async def generations(session: AsyncSession) -> list[Generation]:
    session.expire_all()
    return list((await session.scalars(select(Generation).order_by(Generation.created_at))).all())


async def running(session: AsyncSession) -> list[Generation]:
    return [generation for generation in await generations(session) if generation.billing_status == 'held']


async def alternatives(client: AsyncClient, headers: dict, conversation: dict) -> list[str]:
    detail = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()
    return detail['messages'][-1]['alternatives']


async def assert_ledger(session: AsyncSession, billing: FakeBillingServer) -> int:
    """지킬 것을 장부로 본다. 확정한 호출의 수."""
    rows = await generations(session)
    assert not [row for row in rows if row.billing_status in OPEN]
    saved = [row for row in rows if row.outcome in SAVED]
    assert all(row.billing_status == 'captured' and row.message_id is not None for row in saved)
    assert all(row.billing_status != 'captured' for row in rows if row.outcome not in SAVED)
    holds = billing.statuses()
    assert sorted(reference for reference, state in holds.items() if state == 'captured') == sorted(
        row.reference for row in saved
    )
    assert all(holds[row.reference] == 'released' for row in rows if row.outcome == 'failed' and row.reference in holds)
    assert billing.balance(ME) == START - PRICE * len(saved)
    return len(saved)


async def test_stop_continue_and_two_regenerations_charge_each_call_once(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    # 쓰는 도중에 멈춘다
    router.provider = ScriptedProvider(pieces=['문을'], hold=asyncio.Event())
    sending = asyncio.create_task(send(client, mine, conversation))
    await calling(router.provider, 1)
    (generation,) = await running(session)
    assert (await stop(client, mine, generation.id)).status_code == status.HTTP_204_NO_CONTENT
    cut = await done_message(app, await sending)
    assert (cut['content'], cut['status']) == ('문을', 'partial')
    # 이어서 다 쓴다. 같은 말이다
    router.provider = ScriptedProvider(pieces=[' 열었다.'])
    whole = await done_message(app, await go_on(client, mine, cut['id']))
    assert (whole['id'], whole['content'], whole['status']) == (cut['id'], '문을 열었다.', 'complete')
    # 다시 생성을 연달아 둘
    router.provider = ScriptedProvider(pieces=['다른 답.'])
    second = await done_message(app, await regenerate(client, mine, whole['id']))
    third = await done_message(app, await regenerate(client, mine, second['id']))

    assert await alternatives(client, mine, conversation) == [cut['id'], second['id'], third['id']]
    assert await assert_ledger(session, billing) == 4


async def test_two_regenerations_at_once_let_only_one_through(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    answer = await done_message(app, await send(client, mine, conversation))
    router.provider = ScriptedProvider(pieces=['다시.'], hold=asyncio.Event())

    pressing = [asyncio.create_task(regenerate(client, mine, answer['id'])) for _ in range(2)]
    await calling(router.provider, 1)
    done, _ = await asyncio.wait(pressing, timeout=REFUSAL_SECONDS, return_when=asyncio.FIRST_COMPLETED)
    # 하나는 모델이 붙잡고 있고, 하나는 바로 돌아왔다
    assert len(done) == 1
    router.provider.hold.set()
    responses = await asyncio.gather(*pressing)
    await finished(app)

    codes = sorted(response.status_code for response in responses)
    assert codes == [status.HTTP_200_OK, status.HTTP_409_CONFLICT]
    refused = next(response for response in responses if response.status_code == status.HTTP_409_CONFLICT)
    assert refused.json()['code'] == 'generation_in_progress'
    assert len(router.provider.calls) == 1
    assert len(await alternatives(client, mine, conversation)) == 2
    assert await assert_ledger(session, billing) == 2


async def test_nothing_else_generates_while_a_regeneration_runs(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    router.provider = ScriptedProvider(pieces=['문을 '], truncated=True)
    cut = await done_message(app, await send(client, mine, conversation))
    router.provider = ScriptedProvider(pieces=['다시.'], hold=asyncio.Event())
    regenerating = asyncio.create_task(regenerate(client, mine, cut['id']))
    await calling(router.provider, 1)

    others = [
        await refused_at_once(go_on(client, mine, cut['id'])),
        await refused_at_once(regenerate(client, mine, cut['id'])),
        await refused_at_once(send(client, mine, conversation, '그리고')),
    ]
    assert [response.status_code for response in others] == [status.HTTP_409_CONFLICT] * 3
    assert len(await running(session)) == 1
    router.provider.hold.set()
    again = await done_message(app, await regenerating)

    assert (again['parent_id'], again['status']) == (cut['parent_id'], 'complete')
    assert len(router.provider.calls) == 1
    assert await assert_ledger(session, billing) == 2


async def test_a_hold_that_does_not_take_mid_session_saves_no_answer(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    answer = await done_message(app, await send(client, mine, conversation))
    second = await done_message(app, await regenerate(client, mine, answer['id']))
    billing.balances[ME] = PRICE - 1

    response = await regenerate(client, mine, second['id'])
    await finished(app)

    assert (response.status_code, response.json()['code']) == (status.HTTP_402_PAYMENT_REQUIRED, 'credit_short')
    assert await alternatives(client, mine, conversation) == [answer['id'], second['id']]
    assert len(router.provider.calls) == 2
    # 잔액을 바꿔 끼웠으니 장부의 잔액 식 대신 홀드와 기록만 본다
    rows = await generations(session)
    assert [row.billing_status for row in rows] == ['captured', 'captured', 'declined']
    assert billing.balance(ME) == PRICE - 1
    # 차례를 놓았다
    billing.balances[ME] = START
    assert (await done_message(app, await regenerate(client, mine, second['id'])))['status'] == 'complete'


async def test_a_model_failure_mid_session_returns_the_hold(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    answer = await done_message(app, await send(client, mine, conversation))
    router.provider = ScriptedProvider(pieces=[], error=ProviderError('timeout'))

    failed = await regenerate(client, mine, answer['id'])
    await finished(app)

    assert parse_sse(failed.text)[-1] == ('failed', {'code': 'timeout'})
    assert await alternatives(client, mine, conversation) == [answer['id']]
    router.provider = ScriptedProvider(pieces=['이번엔 된다.'])
    again = await done_message(app, await regenerate(client, mine, answer['id']))
    assert await alternatives(client, mine, conversation) == [answer['id'], again['id']]
    assert [row.outcome for row in await generations(session)] == ['complete', 'failed', 'complete']
    assert await assert_ledger(session, billing) == 2
