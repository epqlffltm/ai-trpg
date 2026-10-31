# asset-server/tests/test_character_gifts.py

"""
모델의 제안에 쓰는 칸(#676, 판의 형식 7)을 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 물건의 giftable(상대가 사용자에게 줄 수 있다)은 초안과 판에 남는다. 적지 않으면 거짓이다
  - 호감도의 model_step(모델이 답 하나에 바꿀 수 있는 크기)은 초안과 판에 남는다. 적지 않으면 기본값이다. 0~20 만 받는다
  - 형식 6 의 판(두 칸이 없다)은 줄 수 있는 물건이 없고 model_step 이 기본값인 것으로 읽힌다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.documents import DOCUMENT_FORMAT
from app.characters.models import AFFECTION_MAX_CHANGE, AFFECTION_MODEL_STEP_DEFAULT, CharacterVersion
from app.main import API_PREFIX

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}
ROSE = {'id': 'rose', 'name': '장미', 'giftable': True}
STONE = {'id': 'stone', 'name': '돌'}
AFFECTION = {'stages': [{'name': '보통', 'at': 0}]}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    claims = make_access_claims(sub=str(OPERATOR))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    body = {
        'genre': 'romance',
        'name': '세라',
        'starts': [START],
        'items': [ROSE, STONE],
        'affection': AFFECTION,
        **fields,
    }
    response = await client.post(CHARACTERS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def patch(client: AsyncClient, headers: dict, character: dict, body: dict):
    return await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json=body, headers=headers)


async def publish(client: AsyncClient, headers: dict, character: dict) -> dict:
    response = await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def giftable(items: list[dict]) -> list[tuple[str, bool]]:
    return [(item['id'], item['giftable']) for item in items]


# --- 줄 수 있는 물건 ---


async def test_giftable_is_kept_and_frozen(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    document = (await publish(client, operator, character))['document']

    assert giftable(character['items']) == [('rose', True), ('stone', False)]
    assert (document['format'], giftable(document['items'])) == (DOCUMENT_FORMAT, [('rose', True), ('stone', False)])


# --- 모델이 바꾸는 크기 ---


async def test_the_model_step_is_kept_and_frozen(client: AsyncClient, operator: dict):
    character = await create(client, operator, affection={**AFFECTION, 'model_step': 7})

    document = (await publish(client, operator, character))['document']

    assert character['affection']['model_step'] == document['affection']['model_step'] == 7


async def test_without_a_model_step_the_default_is_used(client: AsyncClient, operator: dict):
    character = await create(client, operator)

    assert character['affection']['model_step'] == AFFECTION_MODEL_STEP_DEFAULT == 3


@pytest.mark.parametrize('step', [0, AFFECTION_MAX_CHANGE])
async def test_zero_and_the_largest_step_are_accepted(client: AsyncClient, operator: dict, step: int):
    character = await create(client, operator, affection={**AFFECTION, 'model_step': step})

    assert character['affection']['model_step'] == step


@pytest.mark.parametrize('step', [-1, AFFECTION_MAX_CHANGE + 1, 1.5, '크게', None])
async def test_a_bad_model_step_is_refused(client: AsyncClient, operator: dict, step):
    character = await create(client, operator)

    response = await patch(client, operator, character, {'affection': {**AFFECTION, 'model_step': step}})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 형식 6 ---


async def test_a_format_six_version_is_still_read(client: AsyncClient, operator: dict, session: AsyncSession):
    character = await create(client, operator)
    published = await publish(client, operator, character)
    version = await session.get(CharacterVersion, uuid.UUID(published['id']))
    old = version.document
    items = [{key: value for key, value in item.items() if key != 'giftable'} for item in old['items']]
    affection = {key: value for key, value in old['affection'].items() if key != 'model_step'}
    version.document = {**old, 'format': 6, 'items': items, 'affection': affection}
    await session.commit()

    response = await client.get(f'{CHARACTERS_URL}/{character["id"]}/versions/1', headers=operator)

    assert response.status_code == status.HTTP_200_OK
    document = response.json()['document']
    assert document['format'] == 6
    assert giftable(document['items']) == [('rose', False), ('stone', False)]
    assert document['affection']['model_step'] == AFFECTION_MODEL_STEP_DEFAULT
