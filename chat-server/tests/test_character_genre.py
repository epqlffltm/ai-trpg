# chat-server/tests/test_character_genre.py

"""
캐릭터의 장르(판의 형식 9, app/genres.py)를 검증한다. API 는 실제 DB(chat_test)에서 돌고, asset 서버는 가짜다.

보는 것.
  - 대화의 시작과 읽기의 character.document 에 판의 장르가 늘 실린다. 사본에 없으면(형식 9 전의 사본) 기본 장르다
  - 사본에는 받은 그대로 둔다(asset 이 장르를 주지 않았으면 사본에도 없다)
  - 같은 판을 다시 가져올 때 받은 판에 장르가 있으면, 장르가 없던 사본에 채운다. 그 판의 앞 대화도 함께 바뀐다.
    이미 장르가 있는 사본은 바꾸지 않는다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import ImportedCharacter
from app.genres import DEFAULT_GENRE, filled_document, genre_of, shown_genre
from tests.assets import FakeAsset, make_character
from tests.turns import CONVERSATIONS_URL, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


async def start(client: AsyncClient, headers: dict, character_id: object) -> dict:
    response = await client.post(CONVERSATIONS_URL, json={'character_id': str(character_id)}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def read(client: AsyncClient, headers: dict, conversation: dict) -> dict:
    return (await client.get(f'{CONVERSATIONS_URL}/{conversation["id"]}', headers=headers)).json()


@pytest.mark.parametrize(
    ('document', 'expected'),
    [({'genre': 'wuxia'}, 'wuxia'), ({}, None), ({'genre': None}, None), ({'genre': ''}, None), ({'genre': 3}, None)],
)
def test_the_genre_is_a_word_or_missing(document: dict, expected: str | None):
    assert genre_of(document) == expected
    assert shown_genre(document) == (expected or DEFAULT_GENRE)


def test_only_a_missing_genre_is_filled():
    assert filled_document({'name': '세라'}, {'genre': 'horror'}) == {'name': '세라', 'genre': 'horror'}
    assert filled_document({'genre': 'sf'}, {'genre': 'horror'}) is None
    assert filled_document({'name': '세라'}, {'genre': None}) is None


async def test_the_conversation_carries_the_genre(client: AsyncClient, asset: FakeAsset, mine: dict):
    character = asset.add_character(make_character(world={'genre': 'horror'}))

    made = await start(client, mine, character.id)

    assert made['character']['document']['genre'] == 'horror'
    assert (await read(client, mine, made))['character']['document']['genre'] == 'horror'


async def test_an_old_copy_shows_the_default_until_the_version_comes_again(
    client: AsyncClient, session: AsyncSession, asset: FakeAsset, mine: dict
):
    # 형식 9 전에 가져온 사본. asset 은 그 뒤에 같은 판의 문서에 장르를 적었다
    character = asset.add_character(make_character())
    old = await start(client, mine, character.id)
    stored = (await session.scalars(select(ImportedCharacter.document))).one()
    shown_before = (await read(client, mine, old))['character']['document']['genre']
    asset.add_character(make_character(character.id, world={'genre': 'mystery'}))

    again = await start(client, mine, character.id)

    assert (stored.get('genre'), shown_before) == (None, DEFAULT_GENRE)
    assert again['character']['document']['genre'] == 'mystery'
    assert (await read(client, mine, old))['character']['document']['genre'] == 'mystery'
    copies = list(await session.scalars(select(ImportedCharacter)))
    assert len(copies) == 1 and copies[0].document['format'] == 1
