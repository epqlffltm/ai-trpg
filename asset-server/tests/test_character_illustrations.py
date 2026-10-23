# asset-server/tests/test_character_illustrations.py

"""
캐릭터의 일러스트(#669, 판의 형식 5)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 일러스트는 초안과 판에 남는다. 해금 대상(collectible)이 기본이고, 장면의 설명은 비워도 된다
  - 칸의 검사: id 의 모양과 같은 id, 제목, 그림이 없음, 모르는 조건의 종류, 개수
  - 게시를 막는 것: 조건이 없는 장소, 물건, 호감도의 단계를 가리킨다(호감도가 없는데 단계를 가리키는 것도).
    초안에는 둘 수 있다
  - 그림: 일러스트도 자기 그림만 붙인다. 게시하면 판에 쓰인 그림으로 적힌다
  - 형식 4 의 판(일러스트가 없다)도 읽힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import CHARACTER_MAX_ILLUSTRATIONS, CharacterVersion
from app.images.models import ImageUse
from app.main import API_PREFIX
from tests.images import own_image

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.', 'hour': 21}
CAFE = {'id': 'cafe', 'name': '카페', 'description': '', 'image_id': None, 'backgrounds': {}}
SCARF = {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'consumable': False, 'image_id': None}
AFFECTION = {'stages': [{'name': '낯섦', 'at': 0}, {'name': '연인', 'at': 70}]}


def illustration(picture: str, **fields) -> dict:
    """카페에 가면 나오는 일러스트. fields 로 칸을 바꾼다."""
    return {
        'id': 'first-date',
        'title': '첫 데이트',
        'image_id': picture,
        'scene': '창가 자리에서 마주 앉는다.',
        'collectible': True,
        'when': {'kind': 'reach_place', 'target': 'cafe'},
        **fields,
    }


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
async def picture(session: AsyncSession) -> str:
    return await own_image(session, OPERATOR)


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {
        'name': '세라',
        'starts': [START],
        'places': [CAFE],
        'start_place': 'cafe',
        'items': [SCARF],
        'affection': AFFECTION,
        **fields,
    }
    response = await client.post(CHARACTERS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def patch(client: AsyncClient, headers: dict, character: dict, body: dict):
    return await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json=body, headers=headers)


async def publish(client: AsyncClient, headers: dict, character: dict):
    return await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)


# --- 만들고 게시하기 ---


async def test_illustrations_are_kept_and_frozen(client: AsyncClient, operator: dict, picture: str):
    shown = [
        illustration(picture),
        illustration(picture, id='gift', when={'kind': 'give_item', 'target': 'scarf'}, collectible=False),
        illustration(picture, id='love', scene='', when={'kind': 'affection_stage', 'target': '연인'}),
    ]
    character = await create(client, operator, illustrations=shown)

    response = await publish(client, operator, character)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()['document']
    assert (document['format'], document['illustrations']) == (DOCUMENT_FORMAT, shown)
    assert character['illustrations'] == shown


async def test_defaults_make_a_collectible_without_a_scene(client: AsyncClient, operator: dict, picture: str):
    bare = {key: value for key, value in illustration(picture).items() if key not in ('scene', 'collectible')}

    character = await create(client, operator, illustrations=[bare])

    assert (character['illustrations'][0]['scene'], character['illustrations'][0]['collectible']) == ('', True)


async def test_illustrations_can_be_cleared(client: AsyncClient, operator: dict, picture: str):
    character = await create(client, operator, illustrations=[illustration(picture)])

    cleared = await patch(client, operator, character, {'illustrations': []})

    assert cleared.json()['illustrations'] == []


# --- 칸의 검사 ---


@pytest.mark.parametrize(
    'change',
    [
        {'id': '첫 데이트'},
        {'title': ' '},
        {'title': 'x' * 31},
        {'image_id': None},
        {'scene': 'x' * 301},
        {'when': {'kind': 'say_word', 'target': 'cafe'}},
        {'when': {'kind': 'reach_place', 'target': ''}},
        {'when': {'kind': 'reach_place'}},
        {'secret': 1},
    ],
)
async def test_a_bad_illustration_is_refused(client: AsyncClient, operator: dict, picture: str, change: dict):
    character = await create(client, operator)

    response = await patch(client, operator, character, {'illustrations': [illustration(picture, **change)]})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_repeated_ids_and_too_many_are_refused(client: AsyncClient, operator: dict, picture: str):
    character = await create(client, operator)

    twice = await patch(client, operator, character, {'illustrations': [illustration(picture)] * 2})
    many = [illustration(picture, id=f'i{number}') for number in range(CHARACTER_MAX_ILLUSTRATIONS + 1)]
    too_many = await patch(client, operator, character, {'illustrations': many})

    assert (twice.status_code, too_many.status_code) == (status.HTTP_422_UNPROCESSABLE_CONTENT,) * 2


async def test_null_does_not_clear_illustrations(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    response = await patch(client, operator, character, {'illustrations': None})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 게시를 막는 것 ---


@pytest.mark.parametrize(
    ('when', 'fields'),
    [
        ({'kind': 'reach_place', 'target': 'library'}, {}),
        ({'kind': 'give_item', 'target': 'ring'}, {}),
        ({'kind': 'give_item', 'target': 'cafe'}, {}),
        ({'kind': 'affection_stage', 'target': '친구'}, {}),
        ({'kind': 'affection_stage', 'target': '연인'}, {'affection': None}),
    ],
    ids=['no_place', 'no_item', 'place_as_item', 'no_stage', 'no_affection'],
)
async def test_a_condition_pointing_at_nothing_blocks_publishing(
    client: AsyncClient, operator: dict, picture: str, when: dict, fields: dict
):
    character = await create(client, operator)
    saved = await patch(client, operator, character, {'illustrations': [illustration(picture, when=when)], **fields})

    refused = await publish(client, operator, character)

    assert saved.status_code == status.HTTP_200_OK
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['problems'] == ['illustration_target_missing']


# --- 그림 ---


async def test_illustration_images_must_be_mine(client: AsyncClient, operator: dict, session: AsyncSession):
    theirs = await own_image(session, OTHER)
    character = await create(client, operator)

    response = await patch(client, operator, character, {'illustrations': [illustration(theirs)]})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'image_not_owned'


async def test_publishing_records_illustration_images(
    client: AsyncClient, operator: dict, session: AsyncSession, picture: str
):
    character = await create(client, operator, illustrations=[illustration(picture)])

    await publish(client, operator, character)

    used = [str(image) for image in (await session.scalars(select(ImageUse.image_id))).all()]
    assert used == [picture]


# --- 형식 4 ---


async def test_a_format_four_version_has_no_illustrations(
    client: AsyncClient, operator: dict, session: AsyncSession, picture: str
):
    character = await create(client, operator, illustrations=[illustration(picture)])
    published = (await publish(client, operator, character)).json()
    version = await session.get(CharacterVersion, uuid.UUID(published['id']))
    version.document = {key: value for key, value in version.document.items() if key != 'illustrations'} | {'format': 4}
    await session.commit()

    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/versions/1', headers=operator)

    assert response.status_code == status.HTTP_200_OK
    assert (response.json()['document']['format'], response.json()['document']['illustrations']) == (4, [])
