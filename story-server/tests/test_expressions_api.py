# story-server/tests/test_expressions_api.py

"""
말 조각의 표정을 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 그림에 표정이 있는 인물이 장면에 있으면 카드에 고르는 법과 고를 수 있는 표정이 들어간다. 없으면 들어가지 않는다
  - 줄 맨 앞의 표정의 표식은 흘리지 않는다. segment 메시지와 저장한 조각에 표정이 실리고, 본문(다음 호출)에는 없다
  - 답을 고쳐도 조각의 표정은 그대로다
"""

import asyncio

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.engine_worlds import member
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
PICTURE = 'aaaaaaaa-1111-4222-8333-444444444444'
# 미나의 그림에는 기본과 웃음, 화남이 있다
SPRITES = [
    {'id': 'base', 'image_id': PICTURE, 'expression': ''},
    {'id': 'smile', 'image_id': PICTURE, 'expression': '웃음'},
    {'id': 'angry', 'image_id': PICTURE, 'expression': '화남'},
]
MINA = {**member('mina', home='home'), 'character': {'name': '미나', 'sprites': SPRITES}}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter()
    app.state.model_router = fake
    return fake


@pytest.fixture
async def model_on(clean_tables: None, session: AsyncSession) -> None:
    await turn_on_luna(session)


async def send(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict, content: str = '안녕') -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def test_a_segment_carries_the_expression_its_line_chose(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, {'cast': [MINA]})
    router.provider.pieces = ['@narration: 바람.\n@mina: <expr', 'ession>웃음</expression> 왔구나.']

    events = await send(app, client, mine, conversation)

    assert [data for name, data in events if name == 'segment'] == [
        {'speaker': None, 'expression': None},
        {'speaker': 'mina', 'expression': '웃음'},
    ]
    assert ''.join(data['text'] for name, data in events if name == 'delta') == '바람.왔구나.'
    done = events[-1][1]['message']
    assert done['segments'] == [
        {'speaker': None, 'text': '바람.', 'expression': None},
        {'speaker': 'mina', 'text': '왔구나.', 'expression': '웃음'},
    ]
    assert done['content'] == '@narration: 바람.\n@mina: 왔구나.'
    card = router.provider.calls[0][0][0].content
    assert '고를 수 있는 표정: @mina: 기본, 웃음, 화남' in card


async def test_a_scene_without_expressions_asks_for_none(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine)

    await send(app, client, mine, conversation)

    assert '<expression>' not in router.provider.calls[0][0][0].content


async def test_editing_keeps_the_expressions(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, {'cast': [MINA]})
    router.provider.pieces = ['@mina: <expression>화남</expression>늦었잖아.']
    answered = (await send(app, client, mine, conversation))[-1][1]['message']

    response = await client.patch(f'{MESSAGES_URL}/{answered["id"]}', json={'segments': ['왜 늦었어?']}, headers=mine)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['segments'] == [{'speaker': 'mina', 'text': '왜 늦었어?', 'expression': '화남'}]
    read = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()
    assert read['messages'][-1]['segments'][0]['expression'] == '화남'
