# asset-server/tests/test_supply_personas.py

"""
페르소나를 다른 서버에 내주는 주소(app/personas/supply.py)를 검증한다. 서명은 tests/test_service_auth.py 가 본다.

보는 것.
  - 사본: 모델에 넣을 내용과 revision 이다. 기본인지와 시각은 싣지 않는다
  - 토큰의 주인의 것만. 남의 것과 없는 것과 지운 것은 404 다
  - revision 만 묻는 길: 내용을 고치면 오르고, 기본으로 두는 것으로는 오르지 않는다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import TEST_USER_ID, SigningKey, make_access_claims, make_token

from app.main import API_PREFIX
from tests.signing import signed_get

pytestmark = pytest.mark.usefixtures('clean_tables')

PERSONAS_URL = f'{API_PREFIX}/personas'
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'
FULL = {
    'name': '한서윤',
    'description': '서울의 작은 출판사에서 일한다.',
    'age': '스물일곱',
    'gender': '여성',
    'form_of_address': '선배',
    'speech_examples': '"그거 진짜야? 말도 안 돼."',
    'personality': '호기심이 많고 말이 빠르다.',
}


def bearer(signing_key: SigningKey, user_id: uuid.UUID = TEST_USER_ID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, SOMEONE_ELSE)


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    response = await client.post(PERSONAS_URL, json={**FULL, **fields}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def revision_of(client: AsyncClient, headers: dict, persona: dict) -> int:
    response = await signed_get(client, f'/personas/{persona["id"]}/revision', headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['id'] == persona['id']
    return response.json()['revision']


async def test_the_copy_is_the_content_and_the_revision(client: AsyncClient, mine: dict):
    persona = await create(client, mine)

    response = await signed_get(client, f'/personas/{persona["id"]}', mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'id': persona['id'], 'revision': 1, 'image_id': None, **FULL}


async def test_the_copy_follows_the_latest_content(client: AsyncClient, mine: dict):
    persona = await create(client, mine)
    await client.patch(f'{PERSONAS_URL}/{persona["id"]}', json={'personality': '조용하다.'}, headers=mine)

    response = await signed_get(client, f'/personas/{persona["id"]}', mine)

    assert (response.json()['personality'], response.json()['revision']) == ('조용하다.', 2)


@pytest.mark.parametrize('suffix', ['', '/revision'])
async def test_only_the_owner_gets_it(client: AsyncClient, mine: dict, theirs: dict, suffix: str):
    persona = await create(client, mine)

    response = await signed_get(client, f'/personas/{persona["id"]}{suffix}', theirs)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': '찾을 수 없습니다.'}


@pytest.mark.parametrize('suffix', ['', '/revision'])
async def test_missing_and_deleted_are_404(client: AsyncClient, mine: dict, suffix: str):
    persona = await create(client, mine)
    await client.delete(f'{PERSONAS_URL}/{persona["id"]}', headers=mine)

    deleted = await signed_get(client, f'/personas/{persona["id"]}{suffix}', mine)
    missing = await signed_get(client, f'/personas/{NO_SUCH_ID}{suffix}', mine)

    assert (deleted.status_code, missing.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


async def test_the_revision_rises_with_content_only(client: AsyncClient, mine: dict):
    persona = await create(client, mine)
    other = await create(client, mine, name='둘째')
    first = await revision_of(client, mine, persona)

    await client.put(f'{PERSONAS_URL}/{other["id"]}/default', headers=mine)
    await client.put(f'{PERSONAS_URL}/{persona["id"]}/default', headers=mine)
    after_default = await revision_of(client, mine, persona)
    await client.patch(f'{PERSONAS_URL}/{persona["id"]}', json={'name': '서윤'}, headers=mine)
    after_edit = await revision_of(client, mine, persona)

    assert (first, after_default, after_edit) == (1, 1, 2)
