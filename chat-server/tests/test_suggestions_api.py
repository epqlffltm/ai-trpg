# chat-server/tests/test_suggestions_api.py

"""
다음 답 추천을 API 로 검증한다. 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 표식 뒤는 흘리지 않는다. 답의 본문과 선택지를 따로 저장하고 done 과 대화 읽기에 싣는다
  - 다음 호출에는 본문만 간다(선택지를 흉내 내지 않게)
  - 잘린 답은 선택지를 버린다. 표식만 쓴 답은 빈 답(failed empty)이다. 사람이 멈추면 본문만 저장한다
  - 켜면 카드에 지시가 들어가고, 끄면 빠진다(CHAT_SUGGESTIONS)
  - 선택지는 넷 이상 저장되지 않는다(표의 CHECK)
"""

import asyncio
import uuid

import pytest
from ai_core.provider import Role
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversation.suggestions import MARKER
from app.conversations.models import Message
from app.main import API_PREFIX
from app.turns.models import Generation
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

# 본문 뒤에 표식과 선택지. 표식은 조각의 경계에 걸려 있다
PIECES = ['어서 와요.\n<sugg', 'estions>\n1. 책을 보여 줘\n- "산책 갈래?"\n']


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=PIECES))
    app.state.model_router = fake
    return fake


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    """luna 로 시작한 내 대화. 결제 서버는 없다(공짜)."""
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine)


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str = '안녕') -> list:
    """말을 보내고 따로 도는 작업까지 끝나기를 기다린다. SSE 의 (event, data) 들."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    await asyncio.gather(*list(app.state.turns))
    assert response.status_code == status.HTTP_200_OK, response.text
    return parse_sse(response.text)


def card_of(provider: ScriptedProvider, call: int = 0) -> str:
    """그 호출에 보낸 카드(시스템 메시지)."""
    return provider.calls[call][0][0].content


async def test_the_body_streams_and_the_suggestions_are_saved_apart(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    events = await say(client, app, mine, conversation)

    streamed = ''.join(data['text'] for event, data in events if event == 'delta')
    assert MARKER not in streamed
    assert '책을 보여 줘' not in streamed
    done = events[-1][1]['message']
    assert (done['content'], done['suggestions']) == ('어서 와요.', ['책을 보여 줘', '산책 갈래?'])
    detail = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()
    assert detail['messages'][-1]['suggestions'] == ['책을 보여 줘', '산책 갈래?']
    # 사람의 말과 인사말에는 선택지가 없다
    assert [message['suggestions'] for message in detail['messages'][:-1]] == [[], []]


async def test_only_the_body_goes_back_to_the_model(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await say(client, app, mine, conversation)
    await say(client, app, mine, conversation, '책을 보여 줘')

    history = router.provider.calls[1][0]
    answers = [message.content for message in history if message.role == Role.ASSISTANT]
    assert answers[-1] == '어서 와요.'


async def test_the_card_asks_for_suggestions_only_when_they_are_on(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await say(client, app, mine, conversation)
    app.state.settings = app.state.settings.model_copy(update={'chat_suggestions': False})
    await say(client, app, mine, conversation)

    assert MARKER in card_of(router.provider, 0)
    assert MARKER not in card_of(router.provider, 1)


async def test_a_truncated_answer_drops_its_suggestions(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider = ScriptedProvider(pieces=PIECES, truncated=True)

    done = (await say(client, app, mine, conversation))[-1][1]['message']

    assert (done['content'], done['status'], done['suggestions']) == ('어서 와요.', 'partial', [])


async def test_an_answer_with_only_suggestions_is_empty(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider = ScriptedProvider(pieces=[f'  {MARKER}\n가\n나'])

    events = await say(client, app, mine, conversation)

    assert events[-1] == ('failed', {'code': 'empty'})
    generation = (await session.scalars(select(Generation))).one()
    assert (generation.billing_status, generation.message_id) == ('released', None)


async def test_a_stopped_answer_keeps_only_its_body(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    router.provider = ScriptedProvider(pieces=['어서 와요.', f'{MARKER}\n가'], hold=asyncio.Event())
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    sending = asyncio.create_task(client.post(url, json={'content': '안녕'}, headers=mine))
    while not router.provider.calls:
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)
    generation_id = (await session.scalars(select(Generation.id))).one()

    await client.post(f'{API_PREFIX}/generations/{generation_id}/stop', headers=mine)
    response = await sending
    await asyncio.gather(*list(app.state.turns))

    done = parse_sse(response.text)[-1][1]['message']
    assert (done['content'], done['status'], done['suggestions']) == ('어서 와요.', 'partial', [])


async def test_more_than_three_suggestions_are_refused_by_the_table(
    session: AsyncSession, conversation: dict, mine: dict
):
    greeting = await session.get(Message, uuid.UUID(conversation['messages'][0]['id']))
    greeting.suggestions = ['가', '나', '다', '라']

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_text_held_back_at_the_end_is_still_streamed(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    # 끝의 "<" 는 표식의 앞부분일 수 있어 붙잡았다가, 다 받은 뒤에 흘린다
    router.provider = ScriptedProvider(pieces=['1 ', '< 2'])

    events = await say(client, app, mine, conversation)

    assert [data['text'] for event, data in events if event == 'delta'] == ['1 ', '< 2']
    router.provider = ScriptedProvider(pieces=['1 <'])
    events = await say(client, app, mine, conversation)
    assert ''.join(data['text'] for event, data in events if event == 'delta') == '1 <'
