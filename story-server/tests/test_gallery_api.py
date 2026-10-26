# story-server/tests/test_gallery_api.py

"""
연 일러스트의 기록(app/records/repository.py 의 add_illustrations)과 그 목록(GET /gallery)을 검증한다.
실제 DB(story_test)에서 돈다. 기록은 저장소의 함수로 적는다. 행동이 열 때 적는 것은 tests/test_actions_api.py 가 본다.

보는 것.
  - 연 차례로, 장면의 종류와 id, 그림, 인물, 처음 연 세션이 나온다
  - 같은 장면을 다시 열어도 처음 연 때 그대로다(그림, 시각, 세션)
  - 이벤트와 엔딩의 id 가 같아도 다른 장면이다
  - 내 기록, 그 세계관의 기록만이다. 로그인을 요구하고, 모르는 세계관은 빈 목록이다
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.records import repository
from app.records.illustrations import SceneKind, Unlock
from tests.assets import FakeAsset
from tests.turns import ME, bearer, start_with_luna, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

GALLERY_URL = f'{API_PREFIX}/gallery'
WORLD = uuid.UUID('cccccccc-1111-4222-8333-444444444444')
OTHER_WORLD = uuid.UUID('dddddddd-1111-4222-8333-444444444444')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
PICTURE = uuid.UUID('aaaaaaaa-1111-4222-8333-444444444444')
NEW_PICTURE = uuid.UUID('bbbbbbbb-1111-4222-8333-444444444444')
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
async def conversation_id(clean_tables: None, session: AsyncSession, client: AsyncClient, asset: FakeAsset, mine: dict):
    """연 세션으로 적을 내 세션 하나."""
    await turn_on_luna(session)
    return uuid.UUID((await start_with_luna(client, asset, mine))['id'])


async def add(session: AsyncSession, owner: uuid.UUID, world: uuid.UUID, unlocks: list, conversation, at: datetime):
    await repository.add_illustrations(session, owner, world, unlocks, conversation, at)
    await session.commit()


async def gallery(client: AsyncClient, headers: dict, world: uuid.UUID) -> list[dict]:
    response = await client.get(GALLERY_URL, params={'world_id': str(world)}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


async def test_opened_illustrations_come_in_the_order_they_were_opened(
    client: AsyncClient, session: AsyncSession, conversation_id: uuid.UUID, mine: dict
):
    beach = Unlock(SceneKind.EVENT, 'beach', PICTURE, ('mina', 'jun'))
    parting = Unlock(SceneKind.ENDING, 'parting', NEW_PICTURE, ())
    await add(session, ME, WORLD, [parting], conversation_id, NOW + timedelta(minutes=1))
    await add(session, ME, WORLD, [beach], conversation_id, NOW)

    items = await gallery(client, mine, WORLD)

    assert [(item['kind'], item['scene_id'], item['image_id'], item['cast']) for item in items] == [
        ('event', 'beach', str(PICTURE), ['mina', 'jun']),
        ('ending', 'parting', str(NEW_PICTURE), []),
    ]
    assert items[0]['conversation_id'] == str(conversation_id)


async def test_opening_a_scene_again_keeps_the_first_time(
    client: AsyncClient, session: AsyncSession, conversation_id: uuid.UUID, mine: dict
):
    await add(session, ME, WORLD, [Unlock(SceneKind.EVENT, 'beach', PICTURE, ('mina',))], conversation_id, NOW)

    # 제작자가 새 판에서 그림과 인물을 바꿨고 다른 세션에서 다시 열었다
    later = NOW + timedelta(days=1)
    await add(session, ME, WORLD, [Unlock(SceneKind.EVENT, 'beach', NEW_PICTURE, ('jun',))], None, later)

    items = await gallery(client, mine, WORLD)
    assert [(item['image_id'], item['cast'], item['conversation_id']) for item in items] == [
        (str(PICTURE), ['mina'], str(conversation_id))
    ]
    assert datetime.fromisoformat(items[0]['first_seen_at']) == NOW


async def test_an_event_and_an_ending_with_the_same_id_are_different_scenes(
    client: AsyncClient, session: AsyncSession, conversation_id: uuid.UUID, mine: dict
):
    unlocks = [Unlock(SceneKind.EVENT, 'farewell', PICTURE, ()), Unlock(SceneKind.ENDING, 'farewell', NEW_PICTURE, ())]
    await add(session, ME, WORLD, unlocks, conversation_id, NOW)

    items = await gallery(client, mine, WORLD)

    assert [(item['kind'], item['scene_id']) for item in items] == [('ending', 'farewell'), ('event', 'farewell')]


async def test_only_my_records_of_that_world_are_listed(
    client: AsyncClient, session: AsyncSession, conversation_id: uuid.UUID, mine: dict
):
    await add(session, OTHER, WORLD, [Unlock(SceneKind.EVENT, 'theirs', PICTURE, ())], None, NOW)
    await add(session, ME, OTHER_WORLD, [Unlock(SceneKind.EVENT, 'elsewhere', PICTURE, ())], None, NOW)

    assert await gallery(client, mine, WORLD) == []


async def test_nothing_to_add_writes_nothing(session: AsyncSession, client: AsyncClient, mine: dict):
    await add(session, ME, WORLD, [], None, NOW)

    assert await gallery(client, mine, WORLD) == []


async def test_gallery_needs_login(client: AsyncClient):
    response = await client.get(GALLERY_URL, params={'world_id': str(WORLD)})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
