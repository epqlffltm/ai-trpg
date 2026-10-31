# story-server/tests/test_world_genre.py

"""
판의 형식 4 와 세계관의 장르(world.genre, app/conversations/genres.py)를 검증한다.
API 는 실제 DB(story_test)에서 돌고, asset 서버는 가짜다.

보는 것.
  - 형식 4 의 판을 받는다(asset 서버의 답을 검사하는 모양)
  - 세션의 시작, 읽기, 목록의 world 에 판의 장르가 늘 실린다. 사본에 없으면(형식 4 전의 사본) 기본 장르다
  - 같은 판을 다시 가져올 때 받은 판에 장르가 있으면, 장르가 없던 사본에 채운다. 그 판의 앞 세션도 함께 바뀐다.
    이미 장르가 있는 사본은 바꾸지 않는다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.schemas import WORLD_FORMAT_MAX, WorldDocument
from app.conversations.genres import DEFAULT_GENRE, filled_document, genre_of, shown_genre
from app.conversations.models import ImportedWorld
from tests.assets import FakeAsset, make_world, world_document
from tests.turns import CONVERSATIONS_URL, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


async def start(client: AsyncClient, headers: dict, world_id: object) -> dict:
    response = await client.post(CONVERSATIONS_URL, json={'world_id': str(world_id)}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


def test_format_four_is_read():
    document = WorldDocument.model_validate(world_document(fmt=4, genre='romance'))

    assert (WORLD_FORMAT_MAX, document.format, document.model_dump()['genre']) == (4, 4, 'romance')


@pytest.mark.parametrize(
    ('document', 'expected'),
    [({'genre': 'wuxia'}, 'wuxia'), ({}, None), ({'genre': None}, None), ({'genre': ''}, None), ({'genre': 3}, None)],
)
def test_the_genre_is_a_word_or_missing(document: dict, expected: str | None):
    assert genre_of(document) == expected
    assert shown_genre(document) == (expected or DEFAULT_GENRE)


def test_only_a_missing_genre_is_filled():
    assert filled_document({'name': '여름'}, {'genre': 'horror'}) == {'name': '여름', 'genre': 'horror'}
    assert filled_document({'genre': 'sf'}, {'genre': 'horror'}) is None
    assert filled_document({'name': '여름'}, {}) is None


async def test_the_session_carries_the_genre(client: AsyncClient, asset: FakeAsset, mine: dict):
    world = asset.add_world(make_world(fields={'format': 4, 'genre': 'horror'}))
    made = await start(client, mine, world.id)

    listed = (await client.get(CONVERSATIONS_URL, headers=mine)).json()['items']

    assert (made['world']['genre'], (await read(client, mine, made))['world']['genre']) == ('horror', 'horror')
    assert listed[0]['world']['genre'] == 'horror'


async def test_an_old_copy_shows_the_default_until_the_version_comes_again(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    # 형식 4 전에 가져온 사본. asset 은 그 뒤에 같은 판의 문서에 장르를 적었다
    world = asset.add_world(make_world())
    old = await start(client, mine, world.id)
    shown_before = (await read(client, mine, old))['world']['genre']
    asset.add_world(make_world(world.id, fields={'format': 4, 'genre': 'mystery'}))

    again = await start(client, mine, world.id)

    assert shown_before == DEFAULT_GENRE
    assert (again['world']['genre'], (await read(client, mine, old))['world']['genre']) == ('mystery', 'mystery')
    copies = list(await session.scalars(select(ImportedWorld)))
    assert len(copies) == 1 and copies[0].document['format'] == 3
