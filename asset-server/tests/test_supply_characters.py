# asset-server/tests/test_supply_characters.py

"""
게시한 판을 다른 서버에 내주는 주소(app/characters/supply.py)를 검증한다. 서명은 tests/test_service_auth.py 가 본다.

보는 것.
  - 마지막 판의 번호와 문서를 내준다. 초안을 고쳐도 판은 그대로이고, 새로 게시하면 번호가 오른다
  - 쓸 수 있는 사람: 주인(비공개여도), 그리고 공개 캐릭터를 볼 수 있는 사람. 등급은 판의 것으로 본다
  - 쓸 수 없으면 404 다(남의 비공개, 볼 수 없는 등급, 게시한 적이 없는 것, 없는 것, 지운 것)
  - 주인인데 등급을 쓸 수 없으면(성인 확인을 잃었다) 403 adult_content_required 다
  - 번호만 묻는 길도 같은 규칙이다
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import API_PREFIX, create_app
from tests.conftest import make_client, make_test_settings
from tests.signing import signed_get

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
OPERATOR = uuid.UUID('11111111-2222-4333-8444-555555555555')
PLAYER = uuid.UUID('99999999-2222-4333-8444-555555555555')
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'
FULL = {
    'name': '세라',
    'intro_html': '<p>도서관의 <strong>사서</strong>.</p><script>alert(1)</script>',
    'greeting': '어서 와요. 찾는 책이 있나요?',
    'speech_examples': '"조용히 해 주세요."',
    'age': '스물넷',
    'gender': '여성',
    'tags': ['사서', '조용함'],
    'starts': [{'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}],
    'rating': 'all',
}
BOTH_PATHS = ['/latest', '/latest/number']


def bearer(signing_key: SigningKey, user_id: uuid.UUID, operator: bool = False, adult: bool = False) -> dict:
    claims = make_access_claims(sub=str(user_id))
    if operator:
        claims['roles'] = ['operator']
    if adult:
        claims['adult_content'] = True
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def operator(signing_key: SigningKey) -> dict:
    return bearer(signing_key, OPERATOR, operator=True)


@pytest.fixture
def player(signing_key: SigningKey) -> dict:
    return bearer(signing_key, PLAYER)


@pytest.fixture
def adult(signing_key: SigningKey) -> dict:
    return bearer(signing_key, PLAYER, adult=True)


@pytest.fixture
async def open_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """누구나 캐릭터를 만드는 앱(3단계). 운영자가 아닌 주인을 만들 때 쓴다."""
    app = create_app(
        make_test_settings(characters_for_everyone=True), http_client=auth_server.make_client(), engine=engine
    )
    yield app
    await app.state.http_client.aclose()


async def create(client: AsyncClient, headers: dict, **fields) -> dict:
    response = await client.post(CHARACTERS_URL, json={**FULL, **fields}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish(client: AsyncClient, headers: dict, character: dict) -> dict:
    response = await client.post(f'{CHARACTERS_URL}/{character["id"]}/versions', json={}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def set_visibility(client: AsyncClient, headers: dict, character: dict, visibility: str) -> None:
    response = await client.patch(
        f'{CHARACTERS_URL}/{character["id"]}', json={'visibility': visibility}, headers=headers
    )
    assert response.status_code == status.HTTP_200_OK, response.text


async def make_public(client: AsyncClient, headers: dict, **fields) -> dict:
    """공개로 두고 게시한 캐릭터."""
    character = await create(client, headers, **fields)
    await set_visibility(client, headers, character, 'public')
    await publish(client, headers, character)
    return character


async def latest(client: AsyncClient, headers: dict, character: dict | str, suffix: str = '/latest'):
    character_id = character['id'] if isinstance(character, dict) else character
    return await signed_get(client, f'/characters/{character_id}{suffix}', headers)


# --- 내주는 것 ---


async def test_gives_the_latest_version_and_its_document(client: AsyncClient, operator: dict):
    character = await create(client, operator)
    published = await publish(client, operator, character)

    response = await latest(client, operator, character)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert (body['id'], body['version'], body['rating']) == (character['id'], 1, 'all')
    assert body['document'] == published['document']
    # 소개는 거른 것이다(판의 문서)
    assert body['document']['intro_html'] == '<p>도서관의 <strong>사서</strong>.</p>'
    assert body['published_at'] == published['created_at']


async def test_the_version_stays_until_published_again(client: AsyncClient, operator: dict):
    character = await create(client, operator)
    await publish(client, operator, character)
    await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'greeting': '안녕.'}, headers=operator)

    before = await latest(client, operator, character)
    number_before = await latest(client, operator, character, '/latest/number')
    await publish(client, operator, character)
    after = await latest(client, operator, character)
    number_after = await latest(client, operator, character, '/latest/number')

    assert (before.json()['version'], before.json()['document']['greeting']) == (1, FULL['greeting'])
    assert (after.json()['version'], after.json()['document']['greeting']) == (2, '안녕.')
    assert number_before.json() == {'id': character['id'], 'version': 1}
    assert number_after.json() == {'id': character['id'], 'version': 2}


# --- 쓸 수 있는 사람 ---


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_the_owner_uses_a_private_one(client: AsyncClient, operator: dict, suffix: str):
    character = await create(client, operator)
    await publish(client, operator, character)

    response = await latest(client, operator, character, suffix)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['version'] == 1


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_others_cannot_use_a_private_one(client: AsyncClient, operator: dict, player: dict, suffix: str):
    character = await create(client, operator)
    await publish(client, operator, character)

    response = await latest(client, player, character, suffix)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': '찾을 수 없습니다.'}


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_others_use_a_public_one(client: AsyncClient, operator: dict, player: dict, suffix: str):
    character = await make_public(client, operator)

    response = await latest(client, player, character, suffix)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['version'] == 1


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_made_private_again_it_is_gone_for_others(client: AsyncClient, operator: dict, player: dict, suffix: str):
    character = await make_public(client, operator)
    await set_visibility(client, operator, character, 'private')

    theirs = await latest(client, player, character, suffix)
    owners = await latest(client, operator, character, suffix)

    assert theirs.status_code == status.HTTP_404_NOT_FOUND
    assert owners.status_code == status.HTTP_200_OK


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_a_public_adult_one_is_only_for_adults(
    client: AsyncClient, operator: dict, player: dict, adult: dict, suffix: str
):
    character = await make_public(client, operator, rating='adult')

    refused = await latest(client, player, character, suffix)
    allowed = await latest(client, adult, character, suffix)

    # 볼 수 없는 사람에게는 없는 것이다(공개 목록과 같다)
    assert (refused.status_code, refused.json()) == (status.HTTP_404_NOT_FOUND, {'detail': '찾을 수 없습니다.'})
    assert allowed.status_code == status.HTTP_200_OK


async def test_the_rating_is_the_published_versions(client: AsyncClient, operator: dict, player: dict):
    character = await make_public(client, operator)
    # 초안만 성인으로 바꿨다. 게시한 판은 전체 이용가다
    await client.patch(f'{CHARACTERS_URL}/{character["id"]}', json={'rating': 'adult'}, headers=operator)

    response = await latest(client, player, character)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['rating'] == 'all'


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_an_owner_who_lost_adult_content_is_told_why(open_app: FastAPI, player: dict, adult: dict, suffix: str):
    async with make_client(open_app) as client:
        character = await create(client, adult, rating='adult')
        await publish(client, adult, character)

        response = await latest(client, player, character, suffix)

    # 자기 캐릭터라 있는 것을 안다. 화면이 본인인증으로 안내한다
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()['code'] == 'adult_content_required'


# --- 없는 것 ---


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_never_published_is_404_even_for_the_owner(client: AsyncClient, operator: dict, suffix: str):
    character = await create(client, operator)
    await set_visibility(client, operator, character, 'public')

    response = await latest(client, operator, character, suffix)

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize('suffix', BOTH_PATHS)
async def test_missing_and_deleted_are_404(client: AsyncClient, operator: dict, suffix: str):
    character = await make_public(client, operator)
    await client.delete(f'{CHARACTERS_URL}/{character["id"]}', headers=operator)

    deleted = await latest(client, operator, character, suffix)
    missing = await latest(client, operator, NO_SUCH_ID, suffix)

    assert (deleted.status_code, missing.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


async def test_needs_the_users_token(client: AsyncClient, operator: dict):
    character = await make_public(client, operator)

    response = await latest(client, {}, character)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
