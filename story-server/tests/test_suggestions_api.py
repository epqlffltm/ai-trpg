# story-server/tests/test_suggestions_api.py

"""
다음 답 추천(답 끝의 선택지)을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 카드에 지시가 들어가고, 표식 뒤의 선택지는 흘리지 않는다(표식이 조각의 경계에 걸려도). 말 조각에도 들어가지 않는다
  - 선택지는 걸러서(번호, 따옴표, 같은 것) 답의 suggestions 에 둔다. 세션 읽기에도 실린다
  - 다음 호출에는 본문만 간다(선택지는 가지 않는다)
  - 끊긴 답에는 선택지가 없다. 이어서 출력으로 다 쓰면 그때 붙는다
  - 답을 고치면 선택지를 지운다
  - 설정으로 끄면 카드에 지시가 없다
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
# 본문 두 줄과 선택지. 표식이 조각의 경계에 걸려 있다
WITH_SUGGESTIONS = [
    '@narration: 바람이 분다.\n@mina: 왔구나.\n<sugg',
    'estions>\n1. 어디 가?\n"같이 걷자"\n- 어디 가?\n</suggestions>',
]


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


async def send(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict) -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    return await streamed(app, await client.post(url, json={'content': '안녕'}, headers=headers))


async def test_suggestions_are_kept_apart_from_the_segments(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider.pieces = WITH_SUGGESTIONS

    events = await send(app, client, mine, conversation)

    streamed_text = ''.join(data['text'] for name, data in events if name == 'delta')
    assert streamed_text == '바람이 분다.왔구나.'
    done = events[-1][1]['message']
    assert done['segments'] == [
        {'speaker': None, 'text': '바람이 분다.', 'expression': None},
        {'speaker': 'mina', 'text': '왔구나.', 'expression': None},
    ]
    assert done['content'] == '@narration: 바람이 분다.\n@mina: 왔구나.'
    assert done['suggestions'] == ['어디 가?', '같이 걷자']
    read = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()
    assert read['messages'][-1]['suggestions'] == ['어디 가?', '같이 걷자']
    assert read['messages'][0]['suggestions'] == []
    # 카드에 지시가 들어갔다
    assert '[다음 답 추천]' in router.provider.calls[0][0][0].content


async def test_the_next_call_gets_only_the_body(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider.pieces = WITH_SUGGESTIONS
    await send(app, client, mine, conversation)

    await send(app, client, mine, conversation)

    history = [message.content for message in router.provider.calls[1][0]]
    assert history[-2] == '@narration: 바람이 분다.\n@mina: 왔구나.'
    assert not any('어디 가?' in content for content in history[1:])


async def test_a_cut_answer_has_no_suggestions_until_it_is_finished(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider.pieces, router.provider.truncated = ['@mina: 늦었'], True
    cut = (await send(app, client, mine, conversation))[-1][1]['message']
    router.provider.pieces, router.provider.truncated = ['네.\n<suggestions>\n미안해\n</suggestions>'], False

    response = await client.post(f'{MESSAGES_URL}/{cut["id"]}/continue', headers=mine)
    done = (await streamed(app, response))[-1][1]['message']

    assert cut['suggestions'] == []
    assert (done['segments'], done['suggestions']) == (
        [{'speaker': 'mina', 'text': '늦었네.', 'expression': None}],
        ['미안해'],
    )
    read = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()
    assert read['messages'][-1]['suggestions'] == ['미안해']


async def test_a_cut_answer_drops_the_suggestions_it_wrote(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider.pieces, router.provider.truncated = WITH_SUGGESTIONS, True

    done = (await send(app, client, mine, conversation))[-1][1]['message']

    assert (done['status'], done['suggestions']) == ('partial', [])


async def test_editing_the_answer_clears_its_suggestions(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider.pieces = WITH_SUGGESTIONS
    answered = (await send(app, client, mine, conversation))[-1][1]['message']

    response = await client.patch(
        f'{MESSAGES_URL}/{answered["id"]}', json={'segments': ['해가 진다.', '늦었네.']}, headers=mine
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['suggestions'] == []


async def test_suggestions_can_be_turned_off(
    client: AsyncClient, app: FastAPI, settings: Settings, conversation: dict, router: FakeRouter, mine: dict
):
    app.state.settings = settings.model_copy(update={'story_suggestions': False})

    await send(app, client, mine, conversation)

    assert '[다음 답 추천]' not in router.provider.calls[0][0][0].content
