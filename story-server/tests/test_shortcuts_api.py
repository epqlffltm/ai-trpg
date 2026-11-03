# story-server/tests/test_shortcuts_api.py

"""
단축어를 API 로 검증한다(#981). 실제 DB(story_test)에서 돈다. asset 서버, 모델은 가짜다.

보는 것.
  - "/이름"으로 부르면 그 턴의 사람의 말 끝에 본문이 붙는다. 카드(시스템 지시)에는 들어가지 않는다
  - 기록(말의 본문)에는 적은 그대로 남고 응답에 본문이 실리지 않는다. 말이 엔진의 상태를 바꾸지 않는다
  - 다음 턴에는 본문이 붙지 않고 부른 이름을 뗀 글만 간다. 그 말을 다시 쓰거나 끊긴 답을 이어 쓰면 다시 붙는다
  - 세계관의 것이 내 것보다 먼저다. 없는 이름이면 그냥 글이다. asset 서버가 죽어도 말은 간다
  - 단축어를 부르지 않은 말에는 asset 서버를 부르지 않는다
  - 세션을 복사하면 적어 둔 본문도 옮겨진다
  - 목록은 세계관의 것, 내 것(같은 이름은 빼고)의 차례이고 본문을 싣지 않는다. 남의 세션은 404
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
from app.conversations.models import Message
from app.main import API_PREFIX
from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

MESSAGES_URL = f'{API_PREFIX}/messages'
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
DIARY = {'name': '일기', 'description': '오늘의 일기', 'body': '미나가 오늘 하루를 일기로 적는다.'}
FLASHBACK = {'name': '회상', 'description': '', 'body': '미나가 어릴 적 여름을 떠올린다.'}
SHORTCUTS = {'shortcuts': [DIARY, FLASHBACK]}
# 길이 상한에서 끊긴 답
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
async def model_on(clean_tables: None, session: AsyncSession) -> None:
    await turn_on_luna(session)


async def streamed(app: FastAPI, response) -> list:
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def send(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, content: str) -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    return await streamed(app, await client.post(url, json={'content': content}, headers=headers))


def sent(router: FakeRouter, call: int = -1) -> list[str]:
    """그 호출에 보낸 메시지의 글들. 첫째가 카드다."""
    return [message.content for message in router.provider.calls[call][0]]


def mine_of(*shortcuts: dict) -> list[ShortcutDocument]:
    return [ShortcutDocument.model_validate(shortcut) for shortcut in shortcuts]


async def test_a_called_shortcut_joins_only_that_turn_as_the_users_words(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)
    before = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()['state']

    events = await send(client, app, mine, conversation, '/일기 비가 왔어')
    first = sent(router)
    await send(client, app, mine, conversation, '그다음은?')
    second = sent(router)
    after = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()['state']

    assert first[-1] == '비가 왔어\n\n[단축어] 미나가 오늘 하루를 일기로 적는다.'
    assert DIARY['body'] not in first[0]
    assert events[0][1]['user_message']['content'] == '/일기 비가 왔어'
    assert DIARY['body'] not in str(events)
    assert '비가 왔어' in second and all(DIARY['body'] not in text for text in second)
    # 말은 엔진의 상태를 바꾸지 않는다(단축어를 불러도 같다)
    assert after == before


async def test_regenerating_and_continuing_keep_the_body(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)
    router.provider.pieces, router.provider.truncated = CUT, True
    events = await send(client, app, mine, conversation, '/회상 바다에서')
    cut = events[-1][1]['message']

    await streamed(app, await client.post(f'{MESSAGES_URL}/{cut["id"]}/continue', headers=mine))
    continued = sent(router)
    await streamed(app, await client.post(f'{MESSAGES_URL}/{cut["id"]}/regenerate', headers=mine))
    regenerated = sent(router)

    body = '바다에서\n\n[단축어] 미나가 어릴 적 여름을 떠올린다.'
    assert body in continued
    assert regenerated[-1] == body


async def test_the_worlds_shortcut_wins_and_unknown_names_are_plain(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    asset.shortcuts = mine_of({'name': '일기', 'body': '내 일기.'}, {'name': '독백', 'body': '혼잣말을 한다.'})
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)

    await send(client, app, mine, conversation, '/일기')
    await send(client, app, mine, conversation, '/독백 조용히')
    await send(client, app, mine, conversation, '/없음 안녕')

    assert sent(router, 0)[-1] == '[단축어] 미나가 오늘 하루를 일기로 적는다.'
    assert sent(router, 1)[-1] == '조용히\n\n[단축어] 혼잣말을 한다.'
    assert sent(router, 2)[-1] == '/없음 안녕'


async def test_a_dead_asset_server_still_sends_and_plain_words_do_not_call_it(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)
    before = len(asset.calls)
    await send(client, app, mine, conversation, '안녕')
    plain_calls = len(asset.calls) - before
    asset.down = True

    await send(client, app, mine, conversation, '/일기')
    await send(client, app, mine, conversation, '/독백')

    assert plain_calls == 0
    assert sent(router, 1)[-1] == '[단축어] 미나가 오늘 하루를 일기로 적는다.'
    assert sent(router, 2)[-1] == '/독백'


async def test_a_copy_keeps_the_body(
    client: AsyncClient,
    app: FastAPI,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
):
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)
    await send(client, app, mine, conversation, '/일기')

    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/copy', headers=mine)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    copied = response.json()['id']
    bodies = await session.scalars(
        select(Message.shortcut_body).where(Message.conversation_id == uuid.UUID(copied), Message.role == 'user')
    )
    assert bodies.all() == [DIARY['body']]


async def test_the_list_puts_the_worlds_first_without_bodies(
    client: AsyncClient, model_on: None, asset: FakeAsset, mine: dict
):
    asset.shortcuts = mine_of(
        {'name': '일기', 'body': '내 일기.'}, {'name': '독백', 'description': '혼잣말', 'body': '.'}
    )
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)

    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/shortcuts', headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {'name': '일기', 'description': '오늘의 일기', 'source': 'work'},
        {'name': '회상', 'description': '', 'source': 'work'},
        {'name': '독백', 'description': '혼잣말', 'source': 'mine'},
    ]


async def test_the_list_without_the_asset_server_has_only_the_worlds(
    client: AsyncClient, model_on: None, asset: FakeAsset, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)
    asset.down = True

    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/shortcuts', headers=mine)

    assert [item['name'] for item in response.json()] == ['일기', '회상']


async def test_a_broken_copy_of_the_shortcuts_is_no_shortcuts(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(client, asset, mine, {'shortcuts': [{'name': '일기'}]})

    response = await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}/shortcuts', headers=mine)
    await send(client, app, mine, conversation, '/일기')

    assert response.json() == []
    assert sent(router)[-1] == '/일기'


async def test_someone_elses_list_is_404(
    client: AsyncClient, model_on: None, asset: FakeAsset, mine: dict, signing_key: SigningKey
):
    conversation = await start_with_luna(client, asset, mine, SHORTCUTS)

    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/shortcuts'
    response = await client.get(url, headers=bearer(signing_key, SOMEONE_ELSE))

    assert response.status_code == status.HTTP_404_NOT_FOUND
