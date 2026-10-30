# story-server/tests/test_world_genre.py

"""
판의 형식 4 와 세계관의 장르(world.genre)를 검증한다. API 는 실제 DB(story_test)에서 돌고, asset 서버는 가짜다.

보는 것.
  - 형식 4 의 판을 받는다(asset 서버의 답을 검사하는 모양)
  - 세션의 시작, 읽기, 목록의 world 에 판의 장르가 실린다
  - 형식 3 까지의 판(장르가 없다)과 글자가 아닌 장르는 null 이다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.assets.schemas import WORLD_FORMAT_MAX, WorldDocument
from app.conversations.router import genre_of
from tests.assets import FakeAsset, make_world, world_document
from tests.turns import CONVERSATIONS_URL, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


async def start(client: AsyncClient, asset: FakeAsset, headers: dict, **fields) -> dict:
    world = asset.add_world(make_world(fields=fields))
    response = await client.post(CONVERSATIONS_URL, json={'world_id': str(world.id)}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def test_format_four_is_read():
    document = WorldDocument.model_validate(world_document(fmt=4, genre='romance'))

    assert (WORLD_FORMAT_MAX, document.format, document.model_dump()['genre']) == (4, 4, 'romance')


@pytest.mark.parametrize(
    ('document', 'expected'),
    [({'genre': 'wuxia'}, 'wuxia'), ({}, None), ({'genre': None}, None), ({'genre': ''}, None), ({'genre': 3}, None)],
)
def test_the_genre_is_a_word_or_null(document: dict, expected: str | None):
    assert genre_of(document) == expected


async def test_the_session_carries_the_genre(client: AsyncClient, asset: FakeAsset, mine: dict):
    made = await start(client, asset, mine, format=4, genre='horror')

    read = (await client.get(f'{CONVERSATIONS_URL}/{made["id"]}', headers=mine)).json()
    listed = (await client.get(CONVERSATIONS_URL, headers=mine)).json()['items']

    assert (made['world']['genre'], read['world']['genre'], listed[0]['world']['genre']) == ('horror',) * 3


async def test_an_older_version_has_no_genre(client: AsyncClient, asset: FakeAsset, mine: dict):
    made = await start(client, asset, mine)

    assert made['world']['genre'] is None
