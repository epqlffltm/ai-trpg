# story-server/tests/test_my_achievements.py

"""
내가 받은 업적 전부(GET /achievements/mine, app/records/)를 검증한다. 마이페이지의 "내 업적"이 읽는다.
실제 DB(story_test)에서 돈다.

보는 것.
  - 모든 세계관의 것을 받은 때가 늦은 것부터 쪽으로 준다. total 은 모두의 수다. 남의 것은 없다. 로그인해야 한다
  - 이름, 받는 법, 그림은 받은 때의 판의 것이다(숨긴 업적도). 세계관의 이름은 내가 가져온 마지막 판의 것이다
  - 가져온 판이 없으면 세계관의 이름이 null 이다(기록은 남는다)
  - 행동으로 받은 업적은 그 세션과 세계관의 이름과 함께 보인다
기록의 시험은 기록을 직접 적는다(엔진을 돌리지 않고 때와 차례를 정하려고).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import ImportedWorld
from app.engine.world import Achievement
from app.records import repository
from tests import test_achievements_api as api
from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import CONVERSATIONS_URL, ME, bearer, start_with_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

router = api.router
model_on = api.model_on

MINE_URL = CONVERSATIONS_URL.replace('/conversations', '/achievements/mine')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
SEA = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000001')
CITY = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000002')
EARLY = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def others(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OTHER)


def achievement(achievement_id: str, **fields) -> Achievement:
    body = {'id': achievement_id, 'name': f'{achievement_id} 업적', 'description': '', 'when': {'items': []}, **fields}
    return Achievement.model_validate(body)


async def earned(session: AsyncSession, owner: uuid.UUID, world: uuid.UUID, when: datetime, *achievements: Achievement):
    """그 사람이 그 세계관에서 그 업적들을 그때 받았다고 적는다."""
    await repository.add_achievements(session, owner, world, achievements, None, when)
    await session.commit()


async def imported(session: AsyncSession, owner: uuid.UUID, world: uuid.UUID, version: int, name: str) -> None:
    """그 사람이 그 세계관의 판을 가져왔다고 적는다."""
    session.add(ImportedWorld(owner_id=owner, source_id=world, version=version, name=name, rating='all', document={}))
    await session.commit()


async def read_mine(client: AsyncClient, headers: dict, **query) -> dict:
    response = await client.get(MINE_URL, params=query, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_it_lists_mine_from_every_world_latest_first(
    client: AsyncClient, session: AsyncSession, mine: dict, others: dict
):
    await imported(session, ME, SEA, 1, '바닷가 마을')
    await imported(session, ME, SEA, 2, '바닷가 마을 2판')
    await imported(session, OTHER, SEA, 3, '남이 가져온 판')
    await imported(session, ME, CITY, 1, '도시')
    await earned(session, ME, SEA, EARLY, achievement('first'))
    await earned(session, ME, CITY, EARLY + timedelta(days=1), achievement('city', description='도시에 갔다'))
    await earned(session, ME, SEA, EARLY + timedelta(days=2), achievement('secret', hidden=True))
    await earned(session, OTHER, SEA, EARLY, achievement('first'))

    page = await read_mine(client, mine)

    assert page['total'] == 3
    assert [(item['world_id'], item['achievement_id'], item['world_name']) for item in page['items']] == [
        (str(SEA), 'secret', '바닷가 마을 2판'),
        (str(CITY), 'city', '도시'),
        (str(SEA), 'first', '바닷가 마을 2판'),
    ]
    assert (page['items'][0]['name'], page['items'][1]['description']) == ('secret 업적', '도시에 갔다')
    assert page['items'][0]['conversation_id'] is None
    assert [item['achievement_id'] for item in (await read_mine(client, others))['items']] == ['first']


async def test_it_pages_and_keeps_ties_in_order(client: AsyncClient, session: AsyncSession, mine: dict):
    await earned(session, ME, SEA, EARLY, achievement('b'), achievement('a'))

    one = await read_mine(client, mine, limit=1)
    two = await read_mine(client, mine, limit=1, offset=1)

    assert [item['achievement_id'] for item in one['items'] + two['items']] == ['a', 'b']
    assert (one['total'], two['total']) == (2, 2)
    # 가져온 판이 없으면 세계관의 이름이 없다
    assert one['items'][0]['world_name'] is None
    assert (await read_mine(client, mine, offset=9))['items'] == []


async def test_it_needs_a_login_and_a_sane_page(client: AsyncClient, mine: dict):
    assert (await client.get(MINE_URL)).status_code == status.HTTP_401_UNAUTHORIZED
    for query in ({'limit': 0}, {'limit': 101}, {'offset': -1}):
        assert (await client.get(MINE_URL, params=query, headers=mine)).status_code == 422
    assert await read_mine(client, mine) == {'items': [], 'total': 0}


async def test_an_action_shows_up_with_its_session_and_world(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await start_with_luna(
        client, asset, mine, {'paths': api.PATHS, 'achievements': [api.BEACH], 'format': 9}
    )
    await api.acted(app, client, mine, conversation, {'kind': 'move', 'place': 'beach'})
    detail = (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=mine)).json()

    (item,) = (await read_mine(client, mine))['items']

    assert (item['achievement_id'], item['conversation_id']) == ('beach', conversation['id'])
    assert (item['world_id'], item['world_name']) == (detail['world']['id'], detail['world']['name'])
