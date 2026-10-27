# story-server/tests/test_continue_api.py

"""
이어서 출력(POST /messages/{id}/continue)을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 끊긴 답에 이어 쓴 것이 그 답에 붙는다(새 말이 아니다). 첫 줄은 마지막 조각을 잇고 그 뒤 줄은 새 조각이다.
    다 쓰면 complete 다. 새로 청구한다. turn 에 continues 가 실리고 모델에는 끊긴 답 뒤에 이어 쓰라는 지시가 간다
  - 모델이 끊긴 답의 끝을 되풀이하면 겹친 만큼 뗀다. 또 잘리면 partial 로 남는다
  - 이어 쓴 것이 없으면 끊긴 답은 그대로이고 돌려준다
  - 끊긴 답이 아닌 말, 가지의 끝이 아닌 답은 422 not_continuable, 남의 말이나 없는 말은 404 다
"""

import asyncio
import uuid

import pytest
from ai_core.provider import ProviderError
from conversation_core import continuation
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Message
from app.main import API_PREFIX, STREAMS
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
# 길이 상한에서 끊긴 답. 미나의 말이 중간에 끊겼다
CUT = ['@narration: 바람이 분다.\n', '@mina: 늦었']


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
    """가짜 결제 서버. 나는 크레딧 100 이 있고, luna 의 말 한 번은 30 이다."""
    server = FakeBillingServer(balances={ME: 100})
    server.prices[PRICE_CODE] = 30
    app.state.billing = server.billing(server.make_client())
    return server


@pytest.fixture
async def conversation(
    clean_tables: None,
    session: AsyncSession,
    client: AsyncClient,
    asset: FakeAsset,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
) -> dict:
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def streamed(app: FastAPI, response) -> list:
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def cut_answer(app: FastAPI, client: AsyncClient, router: FakeRouter, headers: dict, conversation: dict) -> dict:
    """길이 상한에서 끊긴 답 하나를 받는다."""
    router.provider.pieces, router.provider.truncated = CUT, True
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    answer = (await streamed(app, await client.post(url, json={'content': '안녕'}, headers=headers)))[-1][1]['message']
    assert answer['status'] == 'partial'
    return answer


async def carry_on(client: AsyncClient, headers: dict, message_id: str):
    return await client.post(f'{MESSAGES_URL}/{message_id}/continue', headers=headers)


async def test_continuing_carries_on_the_cut_answer(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    cut = await cut_answer(app, client, router, mine, conversation)
    router.provider.pieces, router.provider.truncated = ['네. 기다렸어.\n', '@narration: 해가 진다.'], False

    events = await streamed(app, await carry_on(client, mine, cut['id']))

    turn, done = events[0][1], events[-1][1]['message']
    assert (turn['continues'], turn['user_message']['id'], turn['cast']) == (cut['id'], cut['parent_id'], ['mina'])
    # 첫 segment 앞의 delta 는 미나의 조각에 붙는다
    assert events[1] == ('delta', {'text': '네. 기다렸어.'})
    assert (done['id'], done['status']) == (cut['id'], 'complete')
    assert done['segments'] == [
        {'speaker': None, 'text': '바람이 분다.', 'expression': None},
        {'speaker': 'mina', 'text': '늦었네. 기다렸어.', 'expression': None},
        {'speaker': None, 'text': '해가 진다.', 'expression': None},
    ]
    assert done['content'] == '@narration: 바람이 분다.\n@mina: 늦었네. 기다렸어.\n@narration: 해가 진다.'
    # 모델에는 끊긴 답까지의 말과 이어 쓰라는 지시가 갔다
    messages, _ = router.provider.calls[1]
    assert [message.content for message in messages[-2:]] == [cut['content'], continuation.instruction()]
    # 새 말은 없다. 새로 청구했다
    count = select(func.count()).select_from(Message).where(Message.role == 'assistant')
    assert await session.scalar(count) == 1
    assert billing.balance(ME) == 40


async def test_a_repeated_tail_is_trimmed_and_another_cut_stays_partial(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(app, client, router, mine, conversation)
    router.provider.pieces = ['@mina: 늦었', '네. 기다렸']

    done = (await streamed(app, await carry_on(client, mine, cut['id'])))[-1][1]['message']

    # 끊긴 답의 끝(@mina: 늦었)을 되풀이한 만큼 떼고 미나의 조각을 잇는다. 또 잘려 partial 이다
    assert done['segments'][-1] == {'speaker': 'mina', 'text': '늦었네. 기다렸', 'expression': None}
    assert done['status'] == 'partial'


async def test_nothing_carried_on_keeps_the_cut_answer_and_releases(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    cut = await cut_answer(app, client, router, mine, conversation)
    router.provider.pieces, router.provider.error = [], ProviderError('timeout')

    events = await streamed(app, await carry_on(client, mine, cut['id']))

    assert events[-1] == ('failed', {'code': 'timeout'})
    stored = await session.get(Message, uuid.UUID(cut['id']))
    assert (stored.content, stored.status) == (cut['content'], 'partial')
    assert billing.balance(ME) == 70


async def test_only_the_cut_answer_at_the_end_of_the_branch_can_be_continued(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    cut = await cut_answer(app, client, router, mine, conversation)
    # 끊긴 답 뒤에 말을 더 했다. 그 답은 가지의 끝이 아니다
    router.provider.pieces, router.provider.truncated = ['@mina: 응.'], False
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    later = (await streamed(app, await client.post(url, json={'content': '그래'}, headers=mine)))[-1][1]['message']

    for message_id in (cut['id'], later['id'], later['parent_id']):
        response = await carry_on(client, mine, message_id)
        assert (response.status_code, response.json()['code']) == (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'not_continuable',
        )


async def test_a_message_that_is_not_mine_is_404(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict, signing_key: SigningKey
):
    cut = await cut_answer(app, client, router, mine, conversation)

    theirs = await carry_on(client, bearer(signing_key, OTHER), cut['id'])
    unknown = await carry_on(client, mine, str(uuid.uuid4()))

    assert (theirs.status_code, theirs.json()['code']) == (status.HTTP_404_NOT_FOUND, 'message_not_found')
    assert unknown.status_code == status.HTTP_404_NOT_FOUND


def test_continuing_is_a_stream():
    assert STREAMS.matches(f'{MESSAGES_URL}/{uuid.uuid4()}/continue')
