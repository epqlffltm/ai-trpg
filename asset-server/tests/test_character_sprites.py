# asset-server/tests/test_character_sprites.py

"""
캐릭터 그림(sprites, 판의 형식 6)을 검증한다. 실제 DB(asset_test)에서 돈다.

그림은 셋이다(2026-10-23 유저 결정): 캐릭터 그림, 배경, 이벤트 씬. 캐릭터 그림은 배경이 투명한 서 있는 그림이고
표정과 차림마다 여럿을 둔다. 대표 그림(image_id)은 목록과 프로필에 쓰는 그림으로 따로 남는다.

보는 것.
  - 캐릭터 그림은 초안과 판에 남는다. 표정은 비우면 기본, 차림은 비우면 처음 차림이다
  - 칸의 검사: id 의 모양과 같은 id, 같은 표정과 차림(대소문자만 다른 표정도), 표정의 길이, 그림이 없음, 개수
  - 게시를 막는 것: 차림이 없는 물건이나 옷이 아닌 물건을 가리킨다. 초안에는 둘 수 있다
  - 그림: 캐릭터 그림도 자기 그림만 붙인다. 게시하면 판에 쓰인 그림으로 적힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import CHARACTER_MAX_SPRITES
from app.images.models import ImageUse
from app.main import API_PREFIX
from tests.images import own_image

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
OTHER = uuid.UUID('99999999-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.', 'hour': 21}
SCARF = {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'consumable': False, 'image_id': None}
COOKIE = {'id': 'cookie', 'name': '쿠키', 'description': '', 'kind': 'thing', 'consumable': True, 'image_id': None}


def sprite(picture: str, **fields) -> dict:
    return {'id': 'base', 'image_id': picture, 'expression': '', 'outfit': None, **fields}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
async def picture(session: AsyncSession) -> str:
    return await own_image(session, OPERATOR)


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {'genre': 'romance', 'name': '세라', 'starts': [START], 'items': [SCARF, COOKIE], **fields}
    response = await client.post(CHARACTERS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def patch(client: AsyncClient, headers: dict, character: dict, body: dict):
    return await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json=body, headers=headers)


async def publish(client: AsyncClient, headers: dict, character: dict):
    return await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)


# --- 만들고 게시하기 ---


async def test_sprites_are_kept_and_frozen(client: AsyncClient, operator: dict, picture: str):
    sprites = [
        sprite(picture),
        sprite(picture, id='smile', expression='웃음'),
        sprite(picture, id='scarf-base', outfit='scarf'),
        sprite(picture, id='scarf-smile', expression='웃음', outfit='scarf'),
    ]
    character = await create(client, operator, sprites=sprites)

    response = await publish(client, operator, character)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    document = response.json()['document']
    assert (document['format'], document['sprites']) == (DOCUMENT_FORMAT, sprites)
    assert character['sprites'] == sprites


async def test_defaults_are_the_base_expression_and_the_first_outfit(client: AsyncClient, operator: dict, picture: str):
    character = await create(client, operator, sprites=[{'id': 'base', 'image_id': picture}])

    assert character['sprites'] == [sprite(picture)]


async def test_sprites_can_be_cleared(client: AsyncClient, operator: dict, picture: str):
    character = await create(client, operator, sprites=[sprite(picture)])

    cleared = await patch(client, operator, character, {'sprites': []})

    assert cleared.json()['sprites'] == []


# --- 칸의 검사 ---


@pytest.mark.parametrize(
    'sprites',
    [
        [{'id': '기본', 'image_id': 'PICTURE'}],
        [{'id': 'base', 'image_id': None}],
        [{'id': 'base', 'image_id': 'PICTURE', 'expression': 'x' * 21}],
        [{'id': 'base', 'image_id': 'PICTURE', 'outfit': '목도리'}],
        [{'id': 'base', 'image_id': 'PICTURE'}, {'id': 'base', 'image_id': 'PICTURE', 'expression': '웃음'}],
        [{'id': 'a', 'image_id': 'PICTURE'}, {'id': 'b', 'image_id': 'PICTURE'}],
        [
            {'id': 'a', 'image_id': 'PICTURE', 'expression': 'Smile'},
            {'id': 'b', 'image_id': 'PICTURE', 'expression': 'smile'},
        ],
        [{'id': 'base', 'image_id': 'PICTURE', 'pose': 'sit'}],
    ],
    ids=['bad_id', 'no_image', 'long_expression', 'bad_outfit', 'same_id', 'same_pair', 'same_pair_case', 'extra'],
)
async def test_bad_sprites_are_refused(client: AsyncClient, operator: dict, picture: str, sprites: list):
    character = await create(client, operator)
    sent = [{key: picture if value == 'PICTURE' else value for key, value in item.items()} for item in sprites]

    response = await patch(client, operator, character, {'sprites': sent})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_too_many_sprites_are_refused(client: AsyncClient, operator: dict, picture: str):
    character = await create(client, operator)
    many = [sprite(picture, id=f's{number}', expression=f'e{number}') for number in range(CHARACTER_MAX_SPRITES + 1)]

    response = await patch(client, operator, character, {'sprites': many})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 게시를 막는 것 ---


@pytest.mark.parametrize('outfit', ['ring', 'cookie'], ids=['no_item', 'not_clothing'])
async def test_an_outfit_that_is_not_a_garment_blocks_publishing(
    client: AsyncClient, operator: dict, picture: str, outfit: str
):
    character = await create(client, operator)
    saved = await patch(client, operator, character, {'sprites': [sprite(picture, outfit=outfit)]})

    refused = await publish(client, operator, character)

    assert saved.status_code == status.HTTP_200_OK
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['problems'] == ['sprite_outfit_missing']


# --- 그림 ---


async def test_sprite_images_must_be_mine(client: AsyncClient, operator: dict, session: AsyncSession):
    theirs = await own_image(session, OTHER)
    character = await create(client, operator)

    response = await patch(client, operator, character, {'sprites': [sprite(theirs)]})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['code'] == 'image_not_owned'


async def test_publishing_records_sprite_images(
    client: AsyncClient, operator: dict, session: AsyncSession, picture: str
):
    portrait = await own_image(session, OPERATOR)
    character = await create(client, operator, image_id=portrait, sprites=[sprite(picture)])

    await publish(client, operator, character)

    used = sorted(str(image) for image in (await session.scalars(select(ImageUse.image_id))).all())
    assert used == sorted([portrait, picture])
