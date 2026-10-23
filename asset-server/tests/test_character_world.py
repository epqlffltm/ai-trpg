# asset-server/tests/test_character_world.py

"""
캐릭터의 지도(장소, 길, 처음 있는 장소)와 물건(물건, 시작 소지품)을 검증한다(chat 의 만드는 순서 4).
실제 DB(asset_test)에서 돈다.

보는 것.
  - 만들고 고치고 게시하면 판(형식 2)에 굳는다. 보낸 칸만 바뀌고, 처음 있는 장소는 null 로 비운다
  - 칸의 검사: id 의 모양, 같은 id, 제자리 길, 같은 두 장소의 길(차례를 가리지 않는다), 시간과 수의 범위, 개수
  - 게시를 막는 것: 없는 장소를 가리키는 길과 처음 있는 장소, 장소가 있는데 처음 있는 장소가 없음,
    없는 물건을 가리키는 시작 소지품. 초안에는 둘 수 있다(고치는 중이다)
  - 그림: 장소와 물건의 그림도 자기 그림만 붙인다. 게시하면 판에 쓰인 그림으로 적힌다
  - 형식 1 의 판(지도와 물건이 없다)도 읽힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import CHARACTER_MAX_PLACES, Character, CharacterVersion
from app.images.models import ImageUse
from app.main import API_PREFIX
from tests.images import own_image

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
LIBRARY = {
    'id': 'library',
    'name': '도서관',
    'description': '오래된 책 냄새가 난다.',
    'image_id': None,
    'backgrounds': {},
}
CAFE = {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None, 'backgrounds': {}}
BOOK = {
    'id': 'book',
    'name': '시집',
    'description': '낡은 시집.',
    'kind': 'thing',
    'consumable': False,
    'image_id': None,
}
SCARF = {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'consumable': False, 'image_id': None}
COOKIE = {'id': 'cookie', 'name': '쿠키', 'description': '', 'kind': 'thing', 'consumable': True, 'image_id': None}
WORLD = {
    'places': [LIBRARY, CAFE],
    'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 15}],
    'start_place': 'library',
    'items': [BOOK, SCARF, COOKIE],
    'start_items': [{'item': 'book', 'count': 2}],
}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {'name': '세라', 'starts': [START], **WORLD, **fields}
    response = await client.post(CHARACTERS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def patch(client: AsyncClient, headers: dict, character: dict, body: dict):
    return await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json=body, headers=headers)


async def problems(client: AsyncClient, headers: dict, character: dict) -> list[str]:
    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/publish-check', headers=headers)
    return response.json()['problems']


async def publish(client: AsyncClient, headers: dict, character: dict):
    return await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)


# --- 만들고 게시하기 ---


async def test_the_world_is_kept_in_the_draft_and_frozen_in_the_version(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    response = await publish(client, operator, character)

    assert response.status_code == status.HTTP_201_CREATED
    document = response.json()['document']
    assert document['format'] == DOCUMENT_FORMAT
    assert {name: document[name] for name in WORLD} == WORLD
    assert {name: character[name] for name in WORLD} == WORLD


async def test_only_sent_fields_change_and_the_start_place_can_be_cleared(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    moved = (await patch(client, operator, character, {'start_place': 'cafe'})).json()
    cleared = (await patch(client, operator, character, {'start_place': None, 'places': []})).json()

    assert (moved['start_place'], moved['items']) == ('cafe', WORLD['items'])
    assert (cleared['start_place'], cleared['places'], cleared['paths']) == (None, [], WORLD['paths'])


async def test_a_character_without_a_world_is_still_published(client: AsyncClient, operator: dict):
    character = await create(client, operator, places=[], paths=[], start_place=None, items=[], start_items=[])

    response = await publish(client, operator, character)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['document']['places'] == []


# --- 칸의 검사 ---


@pytest.mark.parametrize(
    'body',
    [
        {'places': [{**LIBRARY, 'id': '도서관'}]},
        {'places': [{**LIBRARY, 'id': 'x' * 41}]},
        {'places': [LIBRARY, {**CAFE, 'id': 'library'}]},
        {'places': [{**LIBRARY, 'name': ' '}]},
        {'places': [LIBRARY] * (CHARACTER_MAX_PLACES + 1)},
        {'paths': [{'a': 'library', 'b': 'library', 'minutes': 1}]},
        {'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 1}, {'a': 'cafe', 'b': 'library', 'minutes': 2}]},
        {'paths': [{'a': 'library', 'b': 'cafe', 'minutes': 1441}]},
        {'paths': [{'a': 'library', 'b': 'cafe', 'minutes': -1}]},
        {'items': [BOOK, {**SCARF, 'id': 'book'}]},
        {'items': [{**BOOK, 'kind': 'weapon'}]},
        {'start_items': [{'item': 'book', 'count': 0}]},
        {'start_items': [{'item': 'book', 'count': 100}]},
        {'start_items': [{'item': 'book'}, {'item': 'book', 'count': 2}]},
        {'places': None},
        {'start_place': '없는 곳'},
        {'places': [{**LIBRARY, 'secret': 1}]},
    ],
)
async def test_a_bad_world_is_refused(client: AsyncClient, operator: dict, body: dict):
    character = await create(client, operator)

    response = await patch(client, operator, character, body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 게시를 막는 것 ---


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        ({'places': [LIBRARY]}, ['place_missing']),
        ({'start_place': 'garden'}, ['place_missing']),
        ({'start_place': None}, ['start_place_missing']),
        ({'start_items': [{'item': 'ring', 'count': 1}]}, ['item_missing']),
        (
            {'starts': [], 'places': [CAFE], 'start_place': None},
            ['start_missing', 'place_missing', 'start_place_missing'],
        ),
    ],
)
async def test_a_world_that_does_not_fit_together_blocks_publishing(
    client: AsyncClient, operator: dict, body: dict, expected: list[str]
):
    character = await create(client, operator)
    saved = await patch(client, operator, character, body)

    refused = await publish(client, operator, character)

    # 초안에는 둘 수 있다. 판에는 맞는 것만 들어간다
    assert saved.status_code == status.HTTP_200_OK
    assert await problems(client, operator, character) == expected
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['problems'] == expected


# --- 그림 ---


async def test_place_and_item_images_must_be_mine(client: AsyncClient, operator: dict, session: AsyncSession):
    mine = await own_image(session, OPERATOR)
    theirs = await own_image(session, OTHER)
    character = await create(client, operator)

    own = await patch(client, operator, character, {'places': [{**LIBRARY, 'image_id': mine}, CAFE]})
    foreign_place = await patch(client, operator, character, {'places': [{**LIBRARY, 'image_id': theirs}, CAFE]})
    foreign_item = await patch(client, operator, character, {'items': [{**BOOK, 'image_id': theirs}]})

    assert own.json()['places'][0]['image_id'] == mine
    assert foreign_place.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert foreign_item.json()['code'] == 'image_not_owned'


async def test_publishing_records_place_and_item_images(client: AsyncClient, operator: dict, session: AsyncSession):
    background = await own_image(session, OPERATOR)
    picture = await own_image(session, OPERATOR)
    character = await create(
        client, operator, places=[{**LIBRARY, 'image_id': background}, CAFE], items=[{**BOOK, 'image_id': picture}]
    )

    await publish(client, operator, character)

    used = {str(image) for image in (await session.scalars(select(ImageUse.image_id))).all()}
    assert used == {background, picture}


async def test_a_foreign_image_left_in_the_draft_blocks_publishing(
    client: AsyncClient, operator: dict, session: AsyncSession
):
    theirs = await own_image(session, OTHER)
    character = await create(client, operator)
    # 붙일 때는 자기 그림이었다고 치고 초안에 바로 적는다(그사이 주인이 바뀐 것과 같다)
    row = await session.get(Character, uuid.UUID(character['id']))
    row.items = [{**BOOK, 'image_id': theirs}]
    await session.commit()

    assert await problems(client, operator, character) == ['image_not_owned']


# --- 형식 1 ---


async def test_a_format_one_version_is_still_read(client: AsyncClient, operator: dict, session: AsyncSession):
    character = await create(client, operator)
    published = (await publish(client, operator, character)).json()
    version = await session.get(CharacterVersion, uuid.UUID(published['id']))
    old = {key: value for key, value in version.document.items() if key not in WORLD}
    version.document = {**old, 'format': 1}
    await session.commit()

    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/versions/1', headers=operator)

    assert response.status_code == status.HTTP_200_OK
    document = response.json()['document']
    assert (document['format'], document['places'], document['start_place']) == (1, [], None)
