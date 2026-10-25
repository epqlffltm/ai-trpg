# asset-server/tests/test_character_reports.py

"""
공개 캐릭터의 신고(app/reports/, #678)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 볼 수 있는 공개 캐릭터를 신고한다. 본 판의 번호와 사유, 설명이 남는다
  - 사유 기타(other)는 설명이 있어야 한다. 모르는 사유, 긴 설명은 422 다
  - 자기 캐릭터는 403 own_character, 같은 캐릭터를 두 번이면 409 already_reported(처리된 뒤에도)
  - 볼 수 없는 것(비공개, 게시 전, 숨김, 볼 수 없는 등급)은 404, 로그인하지 않으면 401 이다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character
from app.main import API_PREFIX
from app.reports.models import DESCRIPTION_MAX_LENGTH, CharacterReport

pytestmark = pytest.mark.usefixtures('clean_tables')

CHARACTERS_URL = f'{API_PREFIX}/characters'
LISTINGS_URL = f'{API_PREFIX}/listings/characters'
OWNER = uuid.UUID('11111111-2222-4333-8444-555555555555')
READER = uuid.UUID('99999999-2222-4333-8444-555555555555')
START = {'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}


def headers_for(signing_key: SigningKey, user_id: uuid.UUID, operator: bool = False) -> dict:
    claims = make_access_claims(sub=str(user_id))
    if operator:
        claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def owner(signing_key: SigningKey) -> dict:
    # 1~2단계에는 운영자만 캐릭터를 만들고 공개한다
    return headers_for(signing_key, OWNER, operator=True)


@pytest.fixture
def reader(signing_key: SigningKey) -> dict:
    return headers_for(signing_key, READER)


async def character(
    client: AsyncClient, headers: dict, public: bool = True, published: bool = True, rating: str = 'all'
) -> dict:
    response = await client.post(
        CHARACTERS_URL, json={'name': '세라', 'starts': [START], 'rating': rating}, headers=headers
    )
    made = response.json()
    if public:
        await client.patch(f'{CHARACTERS_URL}/{made["id"]}', json={'visibility': 'public'}, headers=headers)
    if published:
        await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=headers)
    return made


async def report(client: AsyncClient, headers: dict, made: dict, body: dict | None = None):
    body = body if body is not None else {'reason': 'minor', 'description': '어린 인물을 성적으로 다룬다'}
    return await client.post(f'{LISTINGS_URL}/{made["id"]}/reports', json=body, headers=headers)


async def test_a_public_character_is_reported(client: AsyncClient, session: AsyncSession, owner: dict, reader: dict):
    made = await character(client, owner)
    await client.post(f'{CHARACTERS_URL}/{made["id"]}/versions', json={}, headers=owner)

    response = await report(client, reader, made)

    assert response.status_code == status.HTTP_201_CREATED
    stored = await session.scalar(select(CharacterReport))
    assert (stored.reporter_id, stored.version, stored.reason, stored.handled_at) == (READER, 2, 'minor', None)
    assert str(stored.id) == response.json()['id']


@pytest.mark.parametrize(
    'body',
    [
        {'reason': 'other'},
        {'reason': 'other', 'description': '   '},
        {'reason': 'boring'},
        {'reason': 'spam', 'description': 'x' * (DESCRIPTION_MAX_LENGTH + 1)},
        {'reason': 'spam', 'extra': 1},
    ],
)
async def test_bad_reports_are_refused(client: AsyncClient, owner: dict, reader: dict, body: dict):
    made = await character(client, owner)

    response = await report(client, reader, made, body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # 칸이 틀린 요청은 서버들이 함께 쓰는 본문이다(server_core/input_errors.py)
    assert set(response.json()) == {'detail', 'errors'}


async def test_a_reason_without_a_description_is_fine(client: AsyncClient, owner: dict, reader: dict):
    made = await character(client, owner)

    assert (await report(client, reader, made, {'reason': 'spam'})).status_code == status.HTTP_201_CREATED


async def test_my_own_character_is_403(client: AsyncClient, owner: dict):
    made = await character(client, owner)

    response = await report(client, owner, made)

    assert (response.status_code, response.json()['code']) == (status.HTTP_403_FORBIDDEN, 'own_character')


async def test_reporting_twice_is_409_even_after_handling(
    client: AsyncClient, session: AsyncSession, owner: dict, reader: dict
):
    made = await character(client, owner)
    await report(client, reader, made)
    await session.execute(
        update(CharacterReport).values(handled_at=CharacterReport.created_at, handled_by=OWNER, outcome='dismissed')
    )
    await session.commit()

    again = await report(client, reader, made)

    assert (again.status_code, again.json()['code']) == (status.HTTP_409_CONFLICT, 'already_reported')


async def test_what_i_cannot_see_is_404(client: AsyncClient, session: AsyncSession, owner: dict, reader: dict):
    private = await character(client, owner, public=False)
    unpublished = await character(client, owner, published=False)
    adult = await character(client, owner, rating='adult')
    hidden = await character(client, owner)
    await session.execute(
        update(Character).where(Character.id == uuid.UUID(hidden['id'])).values(hidden_at=Character.created_at)
    )
    await session.commit()

    codes = {(await report(client, reader, made)).status_code for made in (private, unpublished, adult, hidden)}

    assert codes == {status.HTTP_404_NOT_FOUND}


async def test_reporting_needs_a_token(client: AsyncClient, owner: dict):
    made = await character(client, owner)

    assert (await report(client, {}, made)).status_code == status.HTTP_401_UNAUTHORIZED
