# chat-server/tests/test_my_achievements.py

"""
내가 받은 업적 전부(GET /achievements/mine, app/achievements/)를 검증한다. 마이페이지의 "내 업적"이 읽는다.
실제 DB(chat_test)에서 돈다.

보는 것.
  - 모든 캐릭터의 것을 받은 때가 늦은 것부터 쪽으로 준다. total 은 모두의 수다. 남의 것은 없다. 로그인해야 한다
  - 이름, 받는 법, 그림은 받은 때의 판의 것이다(숨긴 업적도). 캐릭터의 이름은 내가 가져온 마지막 판의 것이다
  - 가져온 판이 없으면 캐릭터의 이름이 null 이다(기록은 남는다)
  - 답으로 받은 업적은 그 대화와 캐릭터의 이름과 함께 보인다
기록의 시험은 기록을 직접 적는다(엔진을 돌리지 않고 때와 차례를 정하려고).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements import repository
from app.assets.schemas import AchievementDocument
from app.conversations.models import ImportedCharacter
from app.main import API_PREFIX
from tests import test_achievements_api as api
from tests.assets import FakeAsset
from tests.models import FakeRouter
from tests.turns import ME, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

router = api.router
model_on = api.model_on

MINE_URL = f'{API_PREFIX}/achievements/mine'
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
LUNA = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000001')
SERA = uuid.UUID('aaaaaaaa-0000-4000-8000-000000000002')
EARLY = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def others(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, OTHER)


def achievement(achievement_id: str, **fields) -> AchievementDocument:
    return AchievementDocument.model_validate({'id': achievement_id, 'name': f'{achievement_id} 업적', **fields})


async def earned(session: AsyncSession, owner: uuid.UUID, character: uuid.UUID, when: datetime, *achievements):
    """그 사람이 그 캐릭터에서 그 업적들을 그때 받았다고 적는다."""
    await repository.add_achievements(session, owner, character, achievements, None, when)
    await session.commit()


async def imported(session: AsyncSession, owner: uuid.UUID, character: uuid.UUID, version: int, name: str) -> None:
    """그 사람이 그 캐릭터의 판을 가져왔다고 적는다."""
    copy = ImportedCharacter(owner_id=owner, source_id=character, version=version, name=name, rating='all', document={})
    session.add(copy)
    await session.commit()


async def read_mine(client: AsyncClient, headers: dict, **query) -> dict:
    response = await client.get(MINE_URL, params=query, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_it_lists_mine_from_every_character_latest_first(
    client: AsyncClient, session: AsyncSession, mine: dict, others: dict
):
    await imported(session, ME, LUNA, 1, '루나')
    await imported(session, ME, LUNA, 2, '루나 2판')
    await imported(session, OTHER, LUNA, 3, '남이 가져온 판')
    await imported(session, ME, SERA, 1, '세라')
    await earned(session, ME, LUNA, EARLY, achievement('first'))
    await earned(session, ME, SERA, EARLY + timedelta(days=1), achievement('sera', description='세라와 이야기했다'))
    await earned(session, ME, LUNA, EARLY + timedelta(days=2), achievement('secret', hidden=True))
    await earned(session, OTHER, LUNA, EARLY, achievement('first'))

    page = await read_mine(client, mine)

    assert page['total'] == 3
    assert [(item['character_id'], item['achievement_id'], item['character_name']) for item in page['items']] == [
        (str(LUNA), 'secret', '루나 2판'),
        (str(SERA), 'sera', '세라'),
        (str(LUNA), 'first', '루나 2판'),
    ]
    assert (page['items'][0]['name'], page['items'][1]['description']) == ('secret 업적', '세라와 이야기했다')
    assert page['items'][0]['conversation_id'] is None
    assert [item['achievement_id'] for item in (await read_mine(client, others))['items']] == ['first']


async def test_it_pages_and_keeps_ties_in_order(client: AsyncClient, session: AsyncSession, mine: dict):
    await earned(session, ME, LUNA, EARLY, achievement('b'), achievement('a'))

    one = await read_mine(client, mine, limit=1)
    two = await read_mine(client, mine, limit=1, offset=1)

    assert [item['achievement_id'] for item in one['items'] + two['items']] == ['a', 'b']
    assert (one['total'], two['total']) == (2, 2)
    # 가져온 판이 없으면 캐릭터의 이름이 없다
    assert one['items'][0]['character_name'] is None
    assert (await read_mine(client, mine, offset=9))['items'] == []


async def test_it_needs_a_login_and_a_sane_page(client: AsyncClient, mine: dict):
    assert (await client.get(MINE_URL)).status_code == status.HTTP_401_UNAUTHORIZED
    for query in ({'limit': 0}, {'limit': 101}, {'offset': -1}):
        assert (await client.get(MINE_URL, params=query, headers=mine)).status_code == 422
    assert await read_mine(client, mine) == {'items': [], 'total': 0}


async def test_an_answer_shows_up_with_its_conversation_and_character(
    client: AsyncClient, app: FastAPI, model_on: None, asset: FakeAsset, router: FakeRouter, mine: dict
):
    conversation = await api.start(client, asset, mine, [api.CHATTY])
    await api.send(app, client, mine, conversation)
    await api.send(app, client, mine, conversation)

    (item,) = (await read_mine(client, mine))['items']

    assert (item['achievement_id'], item['conversation_id']) == ('chatty', conversation['id'])
    assert (item['character_id'], item['character_name']) == (conversation['source'], '세라')
    assert item['image_id'] == api.PICTURE
