# chat-server/tests/test_event_scenes_api.py

"""
이벤트 씬을 API 로 검증한다(#669). 실제 DB(chat_test)에서 돈다. asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 행동으로 조건이 맞으면 그 행동 말에 이벤트 씬이 붙는다(SSE 의 turn 과 대화 읽기). 모델의 "[지금]" 에 장면이 간다
  - 해금 대상은 계정에 연 것으로 적힌다(GET /event_scenes). 아닌 것은 나오기만 하고 적히지 않는다
  - 한 가지에서 한 번만 나온다. 다른 가지에서는 다시 나오지만 연 기록은 하나다
  - 행동 말의 답을 다시 생성하거나 이어 써도 그 장면이 간다
  - 대화를 지워도 연 기록은 남는다. 목록은 내 것만, 캐릭터로 거르고, 쪽으로 나눈다
  - 상태의 캐릭터 그림(sprite)은 상대가 입은 옷을 따른다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Message
from app.gallery.models import SceneUnlock
from app.main import API_PREFIX
from tests.assets import FakeAsset, make_character
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, parse_sse, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
GALLERY_URL = f'{API_PREFIX}/gallery'
PICTURE = '7a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
BASE_SPRITE = '1a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
SCARF_SPRITE = '2a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
WORLD = {
    'places': [
        {'id': 'library', 'name': '도서관', 'description': '', 'image_id': None},
        {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None},
    ],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 10}],
    'start_place': 'library',
    'items': [{'id': 'umbrella', 'name': '우산', 'description': '', 'kind': 'thing', 'image_id': None}],
    'start_items': [{'item': 'umbrella', 'count': 1}],
    'event_scenes': [
        {
            'id': 'first-date',
            'title': '첫 데이트',
            'image_id': PICTURE,
            'description': '창가 자리에서 마주 앉는다.',
            'collectible': True,
            'when': {'kind': 'reach_place', 'target': 'cafe'},
        },
        {
            'id': 'umbrella',
            'title': '우산',
            'image_id': PICTURE,
            'description': '',
            'collectible': False,
            'when': {'kind': 'give_item', 'target': 'umbrella'},
        },
    ],
}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['어서 와요.']))
    app.state.model_router = fake
    return fake


async def start(client: AsyncClient, asset: FakeAsset, headers: dict, character_id: uuid.UUID | None = None) -> dict:
    character = asset.add_character(make_character(character_id, world=WORLD))
    body = {'character_id': str(character.id), 'model': 'luna'}
    response = await client.post(CONVERSATIONS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


@pytest.fixture
async def conversation(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    await turn_on_luna(session)
    return await start(client, asset, mine)


async def act(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, body: dict) -> list:
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/actions'
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)


async def move(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, place: str) -> dict:
    """이동하고 SSE 의 turn 에 실린 행동 말을 돌려준다."""
    return (await act(client, app, headers, conversation, {'kind': 'move', 'place': place}))[0][1]['user_message']


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


async def unlocks(client: AsyncClient, headers: dict, **params) -> dict:
    response = await client.get(GALLERY_URL, params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def count_unlocks(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(SceneUnlock))


# --- 나오기 ---


async def test_reaching_the_place_attaches_the_event_scene(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    action = await move(client, app, mine, conversation, 'cafe')

    assert (action['role'], action['event_scene']) == ('action', 'first-date')
    messages = (await read(client, mine, conversation))['messages']
    assert [message['event_scene'] for message in messages] == [None, 'first-date', None]
    card = router.provider.calls[0][0][0].content
    assert '\n장면: 창가 자리에서 마주 앉는다.' in card


async def test_a_collectible_is_recorded_for_the_account(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await move(client, app, mine, conversation, 'cafe')

    page = await unlocks(client, mine)

    assert page['total'] == 1
    (unlock,) = page['items']
    assert (unlock['character_id'], unlock['scene_id']) == (conversation['character']['id'], 'first-date')


async def test_a_non_collectible_shows_but_is_not_recorded(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    events = await act(client, app, mine, conversation, {'kind': 'give', 'item': 'umbrella', 'words': '쓰세요'})

    # 한마디를 덧붙이면 답하는 말은 그 한마디다. 이벤트 씬은 그 말에 붙는다
    (_, turn) = events[0]
    assert (turn['user_message']['event_scene'], turn['action']['event_scene']) == ('umbrella', None)
    assert '\n장면: 우산' in router.provider.calls[0][0][0].content
    assert await count_unlocks(session) == 0


async def test_it_shows_once_on_a_branch(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await move(client, app, mine, conversation, 'cafe')
    await move(client, app, mine, conversation, 'library')
    again = await move(client, app, mine, conversation, 'cafe')

    assert again['event_scene'] is None
    assert '장면:' not in router.provider.calls[-1][0][0].content


async def say(client: AsyncClient, app: FastAPI, headers: dict, conversation: dict, body: dict) -> dict:
    """말을 보내고 SSE 의 turn 에 실린 사람의 말을 돌려준다."""
    response = await client.post(f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return parse_sse(response.text)[0][1]['user_message']


async def test_another_branch_shows_it_again_but_records_once(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    first = await say(client, app, mine, conversation, {'content': '안녕'})
    await move(client, app, mine, conversation, 'cafe')
    # 첫 말을 고쳐 카페에 가기 전의 다른 가지로 간다
    await say(client, app, mine, conversation, {'content': '다시', 'edit_of': first['id']})

    again = await move(client, app, mine, conversation, 'cafe')

    assert again['event_scene'] == 'first-date'
    assert await count_unlocks(session) == 1


async def test_regenerating_the_reaction_sends_the_scene_again(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    action = await move(client, app, mine, conversation, 'cafe')

    response = await client.post(f'{API_PREFIX}/messages/{action["id"]}/regenerate', headers=mine)
    await asyncio.gather(*list(app.state.turns))

    assert response.status_code == status.HTTP_200_OK
    assert '\n장면: 창가 자리에서 마주 앉는다.' in router.provider.calls[-1][0][0].content


# --- 목록 ---


async def test_deleting_the_conversation_keeps_the_record(
    client: AsyncClient, app: FastAPI, conversation: dict, router: FakeRouter, mine: dict
):
    await move(client, app, mine, conversation, 'cafe')

    await client.delete(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)

    assert (await unlocks(client, mine))['total'] == 1


async def test_the_list_is_mine_filtered_and_paged(
    client: AsyncClient,
    app: FastAPI,
    asset: FakeAsset,
    conversation: dict,
    router: FakeRouter,
    mine: dict,
    theirs: dict,
):
    await move(client, app, mine, conversation, 'cafe')
    other = await start(client, asset, mine)
    await move(client, app, mine, other, 'cafe')

    everything = await unlocks(client, mine)
    one_character = await unlocks(client, mine, character_id=conversation['character']['id'])
    first_page = await unlocks(client, mine, limit=1, offset=0)

    assert everything['total'] == 2
    # 최근에 연 것부터다
    assert [item['character_id'] for item in everything['items']] == [
        other['character']['id'],
        conversation['character']['id'],
    ]
    assert one_character['total'] == 1
    assert (len(first_page['items']), first_page['total']) == (1, 2)
    assert (await unlocks(client, theirs))['total'] == 0


async def test_the_list_needs_a_token(client: AsyncClient):
    response = await client.get(GALLERY_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_continuing_the_reaction_sends_the_scene_again(
    client: AsyncClient, app: FastAPI, session: AsyncSession, conversation: dict, router: FakeRouter, mine: dict
):
    await move(client, app, mine, conversation, 'cafe')
    reaction = (await read(client, mine, conversation))['messages'][-1]
    # 끊긴 답으로 만든다(이어서 출력은 끊긴 답에만 된다)
    await session.execute(update(Message).where(Message.id == uuid.UUID(reaction['id'])).values(status='partial'))
    await session.commit()

    response = await client.post(f'{API_PREFIX}/messages/{reaction["id"]}/continue', headers=mine)
    await asyncio.gather(*list(app.state.turns))

    assert response.status_code == status.HTTP_200_OK
    assert '\n장면: 창가 자리에서 마주 앉는다.' in router.provider.calls[-1][0][0].content


# --- 캐릭터 그림 ---


async def test_the_sprite_follows_what_the_character_wears(
    client: AsyncClient, app: FastAPI, session: AsyncSession, asset: FakeAsset, router: FakeRouter, mine: dict
):
    await turn_on_luna(session)
    scarf = {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None}
    sprites = [
        {'id': 'base', 'image_id': BASE_SPRITE, 'expression': '', 'outfit': None},
        {'id': 'scarf', 'image_id': SCARF_SPRITE, 'expression': '', 'outfit': 'scarf'},
    ]
    world = {**WORLD, 'items': [*WORLD['items'], scarf], 'start_items': [{'item': 'scarf', 'count': 1}]}
    character = asset.add_character(make_character(world={**world, 'sprites': sprites}))
    started = await client.post(
        CONVERSATIONS_URL, json={'character_id': str(character.id), 'model': 'luna'}, headers=mine
    )
    conversation = started.json()

    await act(client, app, mine, conversation, {'kind': 'give', 'item': 'scarf'})

    assert conversation['state']['sprite'] == BASE_SPRITE
    assert (await read(client, mine, conversation))['state']['sprite'] == SCARF_SPRITE
