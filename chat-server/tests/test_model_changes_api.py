# chat-server/tests/test_model_changes_api.py

"""
모델이 제안한 상태의 변화(#676)를 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 할 수 있는 것이 있으면 카드에 "[상태 바꾸기]" 지시가 간다. 없으면 지시가 없다
  - 답 끝의 블록은 흘리지도 본문에 남기지도 않는다. 받아들인 것만 답의 changes(칩)에 붙고 대화의 state 가 바뀐다
  - 버린 제안은 칩도 상태의 변화도 없다. 단계로 보이는 캐릭터의 칩에는 크기가 없다
  - 바뀐 상태는 그 답에 붙는다. 다시 생성한 답은 제 상태이고, 앞 가지로 돌아가면 그 가지의 상태다
  - 잘린 답의 제안은 버린다. 이어서 출력이 끝나면 그때 받아들인다
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

ROSE = {'id': 'rose', 'name': '장미', 'description': '', 'kind': 'thing', 'giftable': True, 'image_id': None}
STONE = {'id': 'stone', 'name': '돌', 'description': '', 'kind': 'thing', 'image_id': None}
WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None},
        {'id': 'park', 'name': '공원', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'park', 'minutes': 15}],
    'start_place': 'library',
    'items': [ROSE, STONE],
}
CHANGES = '\n<changes>\naffection +9\ngive rose\nmove park\n</changes>\n<suggestions>\n가자\n'


def affection(display: str = 'number') -> dict:
    return {'display': display, 'start': 50, 'stages': [{'name': '보통', 'at': 0}], 'rules': [], 'model_step': 3}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


def answering(app: FastAPI, pieces: list[str], truncated: bool = False) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=pieces, truncated=truncated))
    app.state.model_router = fake
    return fake


async def start(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, headers: dict, world: dict | None = None
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
    response = await client.post(url, json={'content': '산책 갈래?'}, headers=headers)
    await finished(app)
    return parse_sse(response.text)


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


def summary(state: dict) -> tuple:
    """장소, 소지품, 호감도의 값."""
    holdings = [(holding['item'], holding['count']) for holding in state['inventory']]
    return state['place'], holdings, state['affection']['value'] if state['affection'] else None


async def test_accepted_changes_become_chips_and_state(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, {**WORLD, 'affection': affection()})
    router = answering(app, ['좋아요, 가요.', CHANGES])

    events = await say(client, app, mine, conversation)

    deltas = ''.join(data['text'] for name, data in events if name == 'delta')
    assert '<changes>' not in deltas
    done = events[-1][1]['message']
    assert done['content'] == '좋아요, 가요.'
    assert done['suggestions'] == ['가자']
    assert done['changes'] == [
        {'kind': 'gift', 'item': 'rose'},
        {'kind': 'move', 'place': 'park', 'minutes': 15},
        {'kind': 'affection', 'rising': True, 'delta': 3},
    ]
    detail = await read(client, mine, conversation)
    assert detail['messages'][-1]['changes'] == done['changes']
    assert summary(detail['state']) == ('park', [('rose', 1)], 53)
    card = router.provider.calls[0][0][0].content
    assert '[상태 바꾸기]\n' in card
    assert 'rose(장미)' in card and 'stone' not in card
    assert 'park(공원)' in card


async def test_the_next_turn_knows_the_new_state(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, {**WORLD, 'affection': affection()})
    answering(app, ['좋아요.', CHANGES])
    await say(client, app, mine, conversation)
    router = answering(app, ['도착했네요.'])

    await say(client, app, mine, conversation)

    card = router.provider.calls[0][0][0].content
    # 받은 장미는 다시 줄 수 없고, 공원에서는 도서관으로 갈 수 있다
    assert 'rose(장미)' not in card
    assert 'library(도서관)' in card


async def test_rejected_proposals_change_nothing(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, {**WORLD, 'affection': affection()})
    before = (await read(client, mine, conversation))['state']
    answering(app, ['여기 돌이요.\n<changes>\ngive stone\nmove moon\n'])

    events = await say(client, app, mine, conversation)

    assert events[-1][1]['message']['changes'] == []
    assert (await read(client, mine, conversation))['state'] == before


async def test_a_stage_character_hides_the_size(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, {**WORLD, 'affection': affection('stage')})
    answering(app, ['고마워요.\n<changes>\naffection -1\n'])

    events = await say(client, app, mine, conversation)

    assert events[-1][1]['message']['changes'] == [{'kind': 'affection', 'rising': False, 'delta': None}]


async def test_without_anything_to_offer_there_is_no_instruction(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine)
    router = answering(app, ['안녕.\n<changes>\naffection +2\n'])

    events = await say(client, app, mine, conversation)

    done = events[-1][1]['message']
    assert (done['content'], done['changes']) == ('안녕.', [])
    assert '[상태 바꾸기]' not in router.provider.calls[0][0][0].content


async def test_each_answer_keeps_its_own_state(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, {**WORLD, 'affection': affection()})
    answering(app, ['좋아요.', CHANGES])
    first = (await say(client, app, mine, conversation))[-1][1]['message']
    answering(app, ['다음에요.'])

    response = await client.post(f'{API_PREFIX}/messages/{first["id"]}/regenerate', headers=mine)
    await finished(app)

    assert response.status_code == status.HTTP_200_OK
    assert summary((await read(client, mine, conversation))['state']) == ('library', [], 50)
    back = await client.put(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/branch', json={'message_id': first['id']}, headers=mine
    )
    assert summary(back.json()['state']) == ('park', [('rose', 1)], 53)


async def test_a_cut_answer_drops_the_proposals(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, {**WORLD, 'affection': affection()})
    answering(app, ['좋아요.', CHANGES], truncated=True)

    events = await say(client, app, mine, conversation)

    assert events[-1][1]['message']['changes'] == []
    assert summary((await read(client, mine, conversation))['state']) == ('library', [], 50)


async def test_finishing_a_cut_answer_accepts_the_proposals(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, {**WORLD, 'affection': affection()})
    answering(app, ['좋아요, 같이'])
    answer = (await say(client, app, mine, conversation))[-1][1]['message']
    await session.execute(update(Message).where(Message.id == uuid.UUID(answer['id'])).values(status='partial'))
    await session.commit()
    answering(app, [' 가요.\n<changes>\ngive rose\n'])

    response = await client.post(f'{API_PREFIX}/messages/{answer["id"]}/continue', headers=mine)
    await finished(app)

    assert response.status_code == status.HTTP_200_OK
    detail = await read(client, mine, conversation)
    last = detail['messages'][-1]
    assert (last['content'], last['changes']) == ('좋아요, 같이 가요.', [{'kind': 'gift', 'item': 'rose'}])
    assert summary(detail['state']) == ('library', [('rose', 1)], 50)
