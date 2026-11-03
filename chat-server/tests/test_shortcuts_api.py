# chat-server/tests/test_shortcuts_api.py

"""
단축어를 API 로 검증한다(#981). 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 대화의 판 사본에 제작자 단축어가 남는다
  - "/이름"으로 부르면 그 턴의 사람의 말 끝에 본문이 붙는다. 카드(시스템 지시)에는 들어가지 않는다
  - 기록(말의 본문)에는 적은 그대로 남고 응답에 본문이 실리지 않는다
  - 다음 턴에는 본문이 붙지 않고 부른 이름을 뗀 글만 간다. 그 말을 다시 쓰면 다시 붙는다
  - 캐릭터의 것이 내 것보다 먼저다. 없는 이름이면 그냥 글이다. asset 서버가 죽어도 말은 간다
  - 단축어를 부르지 않은 말에는 asset 서버를 부르지 않는다
  - 목록은 캐릭터의 것, 내 것(같은 이름은 빼고)의 차례이고 본문을 싣지 않는다. 남의 대화는 404
  - 대화의 응답(판의 문서)에도 단축어를 싣지 않는다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.schemas import ShortcutDocument
from app.conversations.models import ImportedCharacter, Message
from app.main import API_PREFIX
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
DIARY = {'name': '일기', 'description': '오늘의 일기', 'body': '상대가 오늘 하루를 일기로 적는다.'}
FLASHBACK = {'name': '회상', 'description': '', 'body': '상대가 어릴 적을 떠올린다.'}
WORLD = {'shortcuts': [DIARY, FLASHBACK]}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['그렇군요.']))
    app.state.model_router = fake
    return fake


async def start(client: AsyncClient, session: AsyncSession, asset: FakeAsset, headers: dict, world: dict | None):
    await turn_on_luna(session)
    character = asset.add_character(make_character(world=world))
    response = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'model': 'luna'}, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def send(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str) -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


def sent(router: FakeRouter, call: int = -1) -> list[str]:
    """그 호출에 보낸 메시지의 글들. 첫째가 카드다."""
    return [message.content for message in router.provider.calls[call][0]]


def mine_of(*shortcuts: dict) -> list[ShortcutDocument]:
    return [ShortcutDocument.model_validate(shortcut) for shortcut in shortcuts]


async def test_the_copy_keeps_the_shortcuts(client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict):
    await start(client, session, asset, mine, WORLD)

    document = await session.scalar(select(ImportedCharacter.document))

    assert [shortcut['name'] for shortcut in document['shortcuts']] == ['일기', '회상']


async def test_a_called_shortcut_joins_only_that_turn_as_the_users_words(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)

    events = await send(client, app, mine, conversation, '/일기 비가 왔어')
    first = sent(router)
    await send(client, app, mine, conversation, '그다음은?')
    second = sent(router)

    assert first[-1] == '비가 왔어\n\n[단축어] 상대가 오늘 하루를 일기로 적는다.'
    assert DIARY['body'] not in first[0]
    # 기록에는 적은 그대로 남고 본문은 응답에 실리지 않는다
    user_message = events[0][1]['user_message']
    assert user_message['content'] == '/일기 비가 왔어'
    assert DIARY['body'] not in str(events)
    # 다음 턴에는 부른 이름을 뗀 글만 간다
    assert '비가 왔어' in second and all(DIARY['body'] not in text for text in second)


async def test_a_name_alone_sends_only_the_body(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)

    await send(client, app, mine, conversation, '/회상')
    await send(client, app, mine, conversation, '그래서?')

    assert sent(router, 0)[-1] == '[단축어] 상대가 어릴 적을 떠올린다.'
    # 남은 글이 없는 지난 말은 적은 그대로 간다
    assert '/회상' in sent(router, 1)


async def test_regenerating_the_answer_keeps_the_body(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    events = await send(client, app, mine, conversation, '/일기 비가 왔어')
    answer_id = events[-1][1]['message']['id']

    response = await client.post(f'{API_PREFIX}/messages/{answer_id}/regenerate', headers=mine)
    await asyncio.gather(*list(app.state.turns))

    assert response.status_code == status.HTTP_200_OK
    assert sent(router)[-1].endswith('[단축어] 상대가 오늘 하루를 일기로 적는다.')


async def test_the_characters_shortcut_wins_over_mine(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    asset.shortcuts = mine_of({'name': '일기', 'body': '내 일기.'}, {'name': '독백', 'body': '혼잣말을 한다.'})
    conversation = await start(client, session, asset, mine, WORLD)

    await send(client, app, mine, conversation, '/일기')
    await send(client, app, mine, conversation, '/독백 조용히')

    assert sent(router, 0)[-1] == '[단축어] 상대가 오늘 하루를 일기로 적는다.'
    assert sent(router, 1)[-1] == '조용히\n\n[단축어] 혼잣말을 한다.'


async def test_an_unknown_name_is_plain_words(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)

    await send(client, app, mine, conversation, '/없음 안녕')
    await send(client, app, mine, conversation, '일기 /일기')

    assert sent(router, 0)[-1] == '/없음 안녕'
    # 맨 앞이 아니면 부른 것이 아니다
    assert sent(router, 1)[-1] == '일기 /일기'
    bodies = (await session.scalars(select(Message.shortcut_body).where(Message.role == 'user'))).all()
    assert bodies == [None, None]


async def test_a_dead_asset_server_still_sends_with_the_characters_shortcuts(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    asset.down = True

    await send(client, app, mine, conversation, '/일기')
    await send(client, app, mine, conversation, '/독백')

    assert sent(router, 0)[-1] == '[단축어] 상대가 오늘 하루를 일기로 적는다.'
    assert sent(router, 1)[-1] == '/독백'


async def test_plain_words_do_not_call_the_asset_server(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    before = len(asset.calls)

    await send(client, app, mine, conversation, '안녕')

    assert len(asset.calls) == before


async def test_the_list_puts_the_characters_first_without_bodies(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    asset.shortcuts = mine_of(
        {'name': '일기', 'body': '내 일기.'}, {'name': '독백', 'description': '혼잣말', 'body': '.'}
    )
    conversation = await start(client, session, asset, mine, WORLD)

    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/shortcuts', headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {'name': '일기', 'description': '오늘의 일기', 'source': 'work'},
        {'name': '회상', 'description': '', 'source': 'work'},
        {'name': '독백', 'description': '혼잣말', 'source': 'mine'},
    ]


async def test_the_list_without_the_asset_server_has_only_the_characters(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)
    asset.down = True

    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/shortcuts', headers=mine)

    assert [item['name'] for item in response.json()] == ['일기', '회상']


async def test_someone_elses_list_is_404(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict, signing_key: SigningKey
):
    conversation = await start(client, session, asset, mine, WORLD)

    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/shortcuts'
    response = await client.get(url, headers=bearer(signing_key, SOMEONE_ELSE))

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_the_conversation_does_not_carry_the_bodies(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    conversation = await start(client, session, asset, mine, WORLD)

    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert 'shortcuts' not in response.json()['character']['document']
    assert DIARY['body'] not in response.text and DIARY['body'] not in str(conversation)
