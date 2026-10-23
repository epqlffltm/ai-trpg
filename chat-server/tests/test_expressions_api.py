# chat-server/tests/test_expressions_api.py

"""
표정 고르기를 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 고를 수 있는 표정이 있는 캐릭터면 카드에 "[표정]" 지시가 간다. 없으면 지시도 없고 표식을 떼지 않는다
  - 모델이 답의 맨 앞에 쓴 표식을 떼고, 고른 표정과 그 캐릭터 그림을 첫 delta 보다 먼저 알린다(SSE 의 expression).
    답의 expression 에 적고, 대화 읽기의 state.sprite 가 그 표정의 그림이 된다
  - 모르는 표정이면 알리지 않고 기본 표정이다. 표식은 그래도 뗀다
  - 고를 수 있는 표정은 지금 차림의 그림에 있는 것이다
  - 이어서 출력은 표정을 고르지 않고 끊긴 답의 표정을 그대로 둔다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Message
from app.main import API_PREFIX
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

BASE = '1b1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
SMILE = '2b1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
ANGRY = '3b1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
SCARF_SMILE = '4b1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
SCARF = {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None}
WORLD = {
    'items': [SCARF],
    'start_items': [{'item': 'scarf', 'count': 1}],
    'sprites': [
        {'id': 'base', 'image_id': BASE, 'expression': '', 'outfit': None},
        {'id': 'smile', 'image_id': SMILE, 'expression': '웃음', 'outfit': None},
        {'id': 'angry', 'image_id': ANGRY, 'expression': '화남', 'outfit': None},
        {'id': 'scarf-smile', 'image_id': SCARF_SMILE, 'expression': '설렘', 'outfit': 'scarf'},
    ],
}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


def answering(app: FastAPI, pieces: list[str]) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=pieces))
    app.state.model_router = fake
    return fake


async def start(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, headers: dict, world: dict | None
) -> dict:
    await turn_on_luna(session)
    character = asset.add_character(make_character(world=world))
    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'model': 'luna'}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def finished(app: FastAPI) -> None:
    await asyncio.gather(*list(app.state.turns))


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict) -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': '안녕'}, headers=headers)
    await finished(app)
    return parse_sse(response.text)


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def test_the_chosen_expression_comes_first_and_is_kept(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    router = answering(app, ['<expre', 'ssion>웃음</expression>', '\n', '반가워요.'])

    events = await say(client, app, mine, conversation)

    assert [name for name, _ in events] == ['turn', 'expression', 'delta', 'done']
    assert events[1][1] == {'expression': '웃음', 'sprite': SMILE}
    assert events[2][1] == {'text': '반가워요.'}
    done = events[-1][1]['message']
    assert (done['content'], done['expression']) == ('반가워요.', '웃음')
    detail = await read(client, mine, conversation)
    assert (detail['messages'][-1]['expression'], detail['state']['sprite']) == ('웃음', SMILE)
    card = router.provider.calls[0][0][0].content
    assert '[표정]\n' in card
    assert '기본, 웃음, 화남' in card


async def test_an_unknown_expression_is_the_base_one(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    answering(app, ['<expression>슬픔</expression>그래요.'])

    events = await say(client, app, mine, conversation)

    assert [name for name, _ in events] == ['turn', 'delta', 'done']
    done = events[-1][1]['message']
    assert (done['content'], done['expression']) == ('그래요.', None)
    assert (await read(client, mine, conversation))['state']['sprite'] == BASE


async def test_without_expressions_nothing_is_stripped(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, None)
    router = answering(app, ['<expression>웃음</expression>안녕'])

    events = await say(client, app, mine, conversation)

    assert events[-1][1]['message']['content'] == '<expression>웃음</expression>안녕'
    assert '[표정]' not in router.provider.calls[0][0][0].content


async def test_the_choices_follow_the_outfit(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    router = answering(app, ['<expression>설렘</expression>따뜻해요.'])
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/actions'

    response = await client.post(url, json={'kind': 'give', 'item': 'scarf'}, headers=mine)
    await finished(app)

    events = parse_sse(response.text)
    assert events[1] == ('expression', {'expression': '설렘', 'sprite': SCARF_SMILE})
    card = router.provider.calls[0][0][0].content
    assert '기본, 설렘' in card
    assert (await read(client, mine, conversation))['state']['sprite'] == SCARF_SMILE


async def test_continuing_keeps_the_expression(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    answering(app, ['<expression>화남</expression>그만'])
    reply = (await say(client, app, mine, conversation))[-1][1]['message']
    await session.execute(update(Message).where(Message.id == uuid.UUID(reply['id'])).values(status='partial'))
    await session.commit()
    router = answering(app, ['<expression>웃음</expression> 해요.'])

    response = await client.post(f'{API_PREFIX}/messages/{reply["id"]}/continue', headers=mine)
    await finished(app)

    events = parse_sse(response.text)
    assert 'expression' not in [name for name, _ in events]
    assert '[표정]' not in router.provider.calls[0][0][0].content
    detail = await read(client, mine, conversation)
    assert detail['messages'][-1]['expression'] == '화남'
    assert detail['state']['sprite'] == ANGRY
