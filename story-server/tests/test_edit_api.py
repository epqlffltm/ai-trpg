# story-server/tests/test_edit_api.py

"""
답 고치기(PATCH /messages/{id})를 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다(tests/assets.py, tests/billing.py, tests/models.py).

보는 것.
  - 조각마다 글만 바뀌고 말하는 사람은 그대로다. 본문은 그 조각들로 다시 쓰이고 고친 표시가 붙는다.
    글의 앞뒤 빈칸은 걷는다. 다음 호출부터 고친 글이 모델에 간다. 청구하지 않는다
  - 조각의 수가 다르면 422 segments_mismatch, 사람의 말과 행동 말은 422 not_editable. 아무것도 바꾸지 않는다
  - 줄바꿈, 빈 글, 모르는 칸은 입력 오류다
  - 없는 말, 남의 말은 404, 답을 쓰는 중이면 409 다
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation, Message
from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.billing import FakeBillingServer
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, PRICE_CODE, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')


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
    """집과 해변이 길로 이어진 세계관의 내 세션."""
    await turn_on_luna(session)
    return await start_with_luna(client, asset, mine, {'paths': [{'a': 'home', 'b': 'beach', 'minutes': 30}]})


async def post(app: FastAPI, client: AsyncClient, headers: dict, url: str, body: dict) -> list:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def answer(app: FastAPI, client: AsyncClient, headers: dict, conversation: dict) -> dict:
    """말을 보내고 받은 답. 조각은 서술 '바람이 분다.' 와 미나의 '왔구나.' 다(tests/models.py)."""
    events = await post(app, client, headers, f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', {'content': '안녕'})
    return events[-1][1]['message']


async def edit(client: AsyncClient, headers: dict, message_id: str, body: dict):
    return await client.patch(f'{MESSAGES_URL}/{message_id}', json=body, headers=headers)


async def test_editing_changes_only_the_text_of_each_segment(
    client: AsyncClient,
    app: FastAPI,
    conversation: dict,
    router: FakeRouter,
    billing: FakeBillingServer,
    mine: dict,
):
    answered = await answer(app, client, mine, conversation)

    response = await edit(client, mine, answered['id'], {'segments': ['  노을이 졌다.  ', '기다렸어.']})

    assert response.status_code == status.HTTP_200_OK, response.text
    edited = response.json()
    assert edited['segments'] == [{'speaker': None, 'text': '노을이 졌다.'}, {'speaker': 'mina', 'text': '기다렸어.'}]
    assert (edited['content'], edited['edited']) == ('@narration: 노을이 졌다.\n@mina: 기다렸어.', True)
    read = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()
    assert read['messages'][-1]['edited'] is True
    # 고친 것은 청구하지 않는다. 다음 호출에는 고친 글이 간다
    assert billing.balance(ME) == 70
    await answer(app, client, mine, conversation)
    assert router.provider.calls[1][0][-2].content == '@narration: 노을이 졌다.\n@mina: 기다렸어.'


async def test_a_different_number_of_segments_is_refused(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, mine: dict
):
    answered = await answer(app, client, mine, conversation)

    response = await edit(client, mine, answered['id'], {'segments': ['하나만']})

    assert (response.status_code, response.json()['code']) == (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        'segments_mismatch',
    )
    stored = await session.get(Message, uuid.UUID(answered['id']))
    assert (stored.content, stored.edited) == (answered['content'], False)


async def test_user_and_action_messages_are_not_editable(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict
):
    said = await answer(app, client, mine, conversation)
    moved = await post(
        app, client, mine, f'{CONVERSATIONS_URL}/{conversation["id"]}/actions', {'kind': 'move', 'place': 'beach'}
    )

    for message_id in (said['parent_id'], moved[0][1]['user_message']['id']):
        response = await edit(client, mine, message_id, {'segments': ['고친 말']})
        assert (response.status_code, response.json()['code']) == (
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'not_editable',
        )


@pytest.mark.parametrize(
    'body',
    [
        {'segments': ['한 줄\n두 줄', '왔구나.']},
        {'segments': ['   ', '왔구나.']},
        {'segments': []},
        {'segments': ['바람', '왔구나.'], 'speaker': 'jun'},
        {'content': '@jun: 끼어든다'},
    ],
)
async def test_a_malformed_edit_is_an_input_error(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict, body: dict
):
    answered = await answer(app, client, mine, conversation)

    response = await edit(client, mine, answered['id'], body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'errors' in response.json()


async def test_a_message_that_is_not_mine_is_404(
    client: AsyncClient, app: FastAPI, conversation: dict, mine: dict, signing_key: SigningKey
):
    answered = await answer(app, client, mine, conversation)

    theirs = await edit(client, bearer(signing_key, OTHER), answered['id'], {'segments': ['가', '나']})
    unknown = await edit(client, mine, str(uuid.uuid4()), {'segments': ['가', '나']})

    assert (theirs.status_code, theirs.json()['code']) == (status.HTTP_404_NOT_FOUND, 'message_not_found')
    assert unknown.status_code == status.HTTP_404_NOT_FOUND


async def test_editing_while_answering_is_409(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, mine: dict
):
    answered = await answer(app, client, mine, conversation)
    await session.execute(update(Conversation).values(generating_since=datetime.now(UTC)))
    await session.commit()

    response = await edit(client, mine, answered['id'], {'segments': ['가', '나']})

    assert (response.status_code, response.json()['code']) == (status.HTTP_409_CONFLICT, 'generation_in_progress')
    session.expire_all()
    assert (await session.scalars(select(Message.edited).where(Message.id == uuid.UUID(answered['id'])))).one() is False
