# story-server/tests/test_personas_api.py

"""
세션의 페르소나(계정 페르소나의 사본)를 API 로 검증한다. 실제 DB(story_test)에서 돈다.
asset 서버, 모델은 가짜다(tests/assets.py, tests/models.py).

보는 것.
  - 고른 페르소나를 asset 서버에서 가져와 세션에 복사한다. 세션 읽기에 실리고, 카드의 [사용자]에 들어간다
  - 고르지 않으면 지난번 세션의 것이다. 지난번 것이 지워졌으면 페르소나 없이 시작한다
  - null 을 보내면 페르소나 없이 시작한다(카드에 [사용자]가 없다)
  - 고른 페르소나가 없으면(남의 것도) 404 persona_not_found 이고 세션을 만들지 않는다
  - 시작한 뒤에 asset 서버에서 고쳐도 세션의 사본은 그대로다
"""

import asyncio
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Conversation
from tests.assets import FakeAsset, make_persona, make_world
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, WORLD_FIELDS, bearer, parse_sse, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

NO_SUCH_PERSONA = uuid.UUID('00000000-0000-4000-8000-00000000abcd')


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


@pytest.fixture
def world_id(asset: FakeAsset) -> str:
    return str(asset.add_world(make_world(fields=WORLD_FIELDS)).id)


async def start(client: AsyncClient, headers: dict, world_id: str, **choices):
    """세션을 시작한다. choices 는 persona_id 같은 고른 값이다(보내지 않은 칸은 지난번 것)."""
    body = {'world_id': world_id, 'model': 'luna', **choices}
    return await client.post(CONVERSATIONS_URL, json=body, headers=headers)


async def started(client: AsyncClient, headers: dict, world_id: str, **choices) -> dict:
    response = await start(client, headers, world_id, **choices)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def card_after_a_message(
    app: FastAPI, client: AsyncClient, router: FakeRouter, headers: dict, conversation: dict
):
    """말을 하나 보내고 모델에 간 카드를 돌려준다."""
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': '안녕'}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    assert parse_sse(response.text)[-1][0] == 'done'
    return router.provider.calls[-1][0][0].content


async def test_a_chosen_persona_is_copied_into_the_session_and_the_card(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
    world_id: str,
):
    persona = asset.add_persona(make_persona(revision=3))

    conversation = await started(client, mine, world_id, persona_id=str(persona.id))

    assert conversation['persona'] == {
        'id': str(persona.id),
        'revision': 3,
        'name': '하루',
        'description': '전학 온 학생.',
        'image_id': None,
        'age': '17',
        'gender': '',
        'form_of_address': '하루야',
        'speech_examples': '',
        'personality': '조용하다.',
    }
    assert (persona.id, mine['Authorization'].removeprefix('Bearer ')) in asset.calls
    card = await card_after_a_message(app, client, router, mine, conversation)
    # 빈 칸(성별, 말투의 예)은 빼고 적는다
    assert '[사용자]\n이름: 하루\n인물들이 부르는 호칭: 하루야\n나이: 17\n설명: 전학 온 학생.\n성격: 조용하다.' in card


async def test_the_last_persona_is_used_when_none_is_chosen(
    client: AsyncClient, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict, world_id: str
):
    persona = asset.add_persona(make_persona())
    await started(client, mine, world_id, persona_id=str(persona.id))
    # 그사이에 asset 서버에서 고쳤다. 새 세션은 지금의 것을 가져온다
    asset.add_persona(make_persona(persona.id, revision=2, name='하루카'))

    second = await started(client, mine, world_id)

    assert (second['persona']['id'], second['persona']['revision'], second['persona']['name']) == (
        str(persona.id),
        2,
        '하루카',
    )


async def test_null_starts_without_a_persona(
    client: AsyncClient,
    app: FastAPI,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
    world_id: str,
):
    persona = asset.add_persona(make_persona())
    await started(client, mine, world_id, persona_id=str(persona.id))

    conversation = await started(client, mine, world_id, persona_id=None)

    assert conversation['persona'] is None
    assert '[사용자]' not in await card_after_a_message(app, client, router, mine, conversation)


async def test_a_deleted_last_persona_starts_without_one(
    client: AsyncClient, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict, world_id: str
):
    persona = asset.add_persona(make_persona())
    await started(client, mine, world_id, persona_id=str(persona.id))
    del asset.personas[persona.id]

    second = await started(client, mine, world_id)

    assert second['persona'] is None


async def test_a_missing_chosen_persona_is_404_and_starts_nothing(
    client: AsyncClient,
    session: AsyncSession,
    model_on: None,
    asset: FakeAsset,
    router: FakeRouter,
    mine: dict,
    world_id: str,
):
    response = await start(client, mine, world_id, persona_id=str(NO_SUCH_PERSONA))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['code'] == 'persona_not_found'
    assert await session.scalar(select(func.count()).select_from(Conversation)) == 0


async def test_the_copy_stays_when_the_persona_changes_later(
    client: AsyncClient, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict, world_id: str
):
    persona = asset.add_persona(make_persona())
    conversation = await started(client, mine, world_id, persona_id=str(persona.id))
    asset.add_persona(make_persona(persona.id, revision=2, name='하루카'))

    read = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()

    assert (read['persona']['revision'], read['persona']['name']) == (1, '하루')
