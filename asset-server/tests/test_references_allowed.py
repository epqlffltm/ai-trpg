# asset-server/tests/test_references_allowed.py

"""
캐릭터와 세계관의 참고 자료 허용(references_allowed)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 처음에는 허용하지 않는다. 만들 때와 고칠 때 켜고 끈다. null 로 비우지 못한다
  - 게시하면 판의 문서에 굳는다(캐릭터 형식 12, 세계관 형식 10). 그 뒤에 초안을 고쳐도 판의 값은 그대로다
  - 옛 형식의 판 문서는 허용하지 않은 것으로 읽는다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.characters.documents import DOCUMENT_FORMAT as CHARACTER_FORMAT
from app.characters.documents import CharacterDocument
from app.worlds.documents import DOCUMENT_FORMAT as WORLD_FORMAT
from tests.worlds import CHARACTERS_URL, OWNER, WORLDS_URL, bearer, character, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OWNER)


def test_the_formats_carry_the_permission():
    assert (CHARACTER_FORMAT, WORLD_FORMAT) == (12, 10)


def test_an_old_character_document_does_not_allow_references():
    document = CharacterDocument.model_validate(
        {
            'format': 11,
            'name': '세라',
            'intro_html': '',
            'greeting': '',
            'speech_examples': '',
            'age': '',
            'gender': '',
            'tags': [],
            'starts': [],
            'image_id': None,
            'rating': 'all',
            'genre': 'romance',
        }
    )

    assert document.references_allowed is False


async def test_a_character_allows_references_only_when_asked(client: AsyncClient, owner: dict):
    made = await character(client, owner, published=False)
    url = f'{CHARACTERS_URL}/{made["id"]}'

    turned_on = await client.patch(url, json={'references_allowed': True}, headers=owner)
    untouched = await client.patch(url, json={'name': '세라'}, headers=owner)
    cleared = await client.patch(url, json={'references_allowed': None}, headers=owner)

    assert made['references_allowed'] is False
    assert turned_on.json()['references_allowed'] is True
    assert untouched.json()['references_allowed'] is True
    assert cleared.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_publishing_freezes_the_character_permission(client: AsyncClient, owner: dict):
    made = await character(client, owner, published=False, references_allowed=True)
    await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=owner)
    await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'references_allowed': False}, headers=owner)

    frozen = (await client.get(f'{CHARACTERS_URL}/{made["id"]}/versions/1', headers=owner)).json()['document']

    assert (frozen['format'], frozen['references_allowed']) == (CHARACTER_FORMAT, True)


async def test_a_world_allows_references_only_when_asked(client: AsyncClient, owner: dict):
    world = await create_world(client, owner, {'name': '여름 학원', 'genre': 'romance'})
    url = f'{WORLDS_URL}/{world["id"]}'

    turned_on = await client.patch(url, json={'references_allowed': True}, headers=owner)
    cleared = await client.patch(url, json={'references_allowed': None}, headers=owner)

    assert world['references_allowed'] is False
    assert turned_on.json()['references_allowed'] is True
    assert cleared.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_publishing_freezes_the_world_permission(client: AsyncClient, owner: dict):
    ari, beo = await character(client, owner, '아리'), await character(client, owner, '버')
    world = await create_world(client, owner, {**full_world(ari['id'], beo['id']), 'references_allowed': True})

    response = await publish(client, owner, world)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()['document']
    assert (document['format'], document['references_allowed']) == (WORLD_FORMAT, True)
