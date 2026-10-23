# asset-server/tests/test_withdrawal.py

"""
인증 서버가 탈퇴를 알리는 주소(app/withdrawal/)를 검증한다. 실제 DB(asset_test)에서 돈다.

보는 것.
  - 그 사람의 페르소나와 비공개 캐릭터(판까지)를 지운다. 공개 캐릭터와 남의 것은 남는다
  - 그 사람의 로어북(판까지)을 지운다. 남의 로어북은 남는다
  - 같은 알림이 다시 와도, 이 서버에 그 사람의 것이 없어도 200 processed 다
  - 인증 서버의 서명이 아니면(없음, 틀림, chat 의 비밀, 비밀이 빔) 401 이고 아무것도 지우지 않는다
  - 본문의 모양이 틀리면 422 이고 아무것도 지우지 않는다. 모르는 칸은 버린다
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.service_auth.signing import SIGNATURE_HEADER
from server_core.testing.tokens import FakeAuthServer, SigningKey, make_access_claims, make_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.characters.models import Character, CharacterVersion
from app.lorebooks.models import Lorebook, LorebookVersion
from app.main import API_PREFIX, create_app
from app.personas.models import Persona
from tests.conftest import make_client, make_test_settings
from tests.signing import TEST_SECRETS, signed_withdrawal, withdrawal_path

pytestmark = pytest.mark.usefixtures('clean_tables')

LEAVER = uuid.UUID('11111111-2222-4333-8444-555555555555')
STAYER = uuid.UUID('99999999-2222-4333-8444-555555555555')
PROCESSED = {'status': 'processed'}
CHARACTER = {
    'name': '세라',
    'starts': [{'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}],
}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict:
    # 1~2단계에는 운영자만 캐릭터를 만든다. 두 사람 모두 운영자로 둔다
    claims = make_access_claims(sub=str(user_id))
    claims['roles'] = ['operator']
    return {'Authorization': f'Bearer {make_token(signing_key, claims)}'}


@pytest.fixture
def leaver(signing_key: SigningKey) -> dict:
    return bearer(signing_key, LEAVER)


@pytest.fixture
def stayer(signing_key: SigningKey) -> dict:
    return bearer(signing_key, STAYER)


async def make_persona(client: AsyncClient, headers: dict) -> None:
    response = await client.post(f'{API_PREFIX}/personas', json={'name': '나'}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text


async def make_character(client: AsyncClient, headers: dict, public: bool = False) -> dict:
    response = await client.post(f'{API_PREFIX}/characters', json=CHARACTER, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    character = response.json()
    url = f'{API_PREFIX}/characters/{character["id"]}'
    if public:
        await client.patch(url, json={'visibility': 'public'}, headers=headers)
    published = await client.post(f'{url}/versions', json={}, headers=headers)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    return character


@pytest.fixture
async def belongings(client: AsyncClient, leaver: dict, stayer: dict) -> dict:
    """떠나는 사람과 남는 사람이 각각 페르소나 둘, 비공개 캐릭터 하나, 공개 캐릭터 하나를 갖는다."""
    made = {}
    for name, headers in (('leaver', leaver), ('stayer', stayer)):
        await make_persona(client, headers)
        await make_persona(client, headers)
        made[name] = {
            'private': await make_character(client, headers),
            'public': await make_character(client, headers, public=True),
        }
    return made


async def personas_of(session: AsyncSession, owner_id: uuid.UUID) -> int:
    return await session.scalar(select(func.count()).select_from(Persona).where(Persona.owner_id == owner_id))


async def character_ids_of(session: AsyncSession, owner_id: uuid.UUID) -> set[str]:
    return {str(found) for found in await session.scalars(select(Character.id).where(Character.owner_id == owner_id))}


async def versions_of(session: AsyncSession, character_id: str) -> int:
    query = select(func.count()).select_from(CharacterVersion).where(CharacterVersion.character_id == character_id)
    return await session.scalar(query)


async def test_erases_personas_and_private_characters(client: AsyncClient, session: AsyncSession, belongings: dict):
    response = await signed_withdrawal(client, str(LEAVER))

    assert (response.status_code, response.json()) == (status.HTTP_200_OK, PROCESSED)
    assert await personas_of(session, LEAVER) == 0
    # 비공개 캐릭터는 판과 함께 지워진다. 공개 캐릭터는 남이 쓰는 것이라 남는다
    assert await character_ids_of(session, LEAVER) == {belongings['leaver']['public']['id']}
    assert await versions_of(session, belongings['leaver']['private']['id']) == 0
    assert await versions_of(session, belongings['leaver']['public']['id']) == 1


async def test_leaves_everyone_elses_things(client: AsyncClient, session: AsyncSession, belongings: dict):
    await signed_withdrawal(client, str(LEAVER))

    assert await personas_of(session, STAYER) == 2
    assert await character_ids_of(session, STAYER) == {
        belongings['stayer']['private']['id'],
        belongings['stayer']['public']['id'],
    }


async def test_the_same_notice_again_is_processed(client: AsyncClient, session: AsyncSession, belongings: dict):
    first = await signed_withdrawal(client, str(LEAVER))
    again = await signed_withdrawal(client, str(LEAVER))

    assert (first.json(), again.json()) == (PROCESSED, PROCESSED)
    assert again.status_code == status.HTTP_200_OK
    assert await character_ids_of(session, LEAVER) == {belongings['leaver']['public']['id']}


async def make_lorebook(client: AsyncClient, headers: dict) -> None:
    response = await client.post(f'{API_PREFIX}/lorebooks', json={'name': '설정'}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    published = await client.post(f'{API_PREFIX}/lorebooks/{response.json()["id"]}/versions', json={}, headers=headers)
    assert published.status_code == status.HTTP_201_CREATED, published.text


async def test_erases_lorebooks(client: AsyncClient, session: AsyncSession, leaver: dict, stayer: dict):
    await make_lorebook(client, leaver)
    await make_lorebook(client, stayer)

    await signed_withdrawal(client, str(LEAVER))

    owners = list(await session.scalars(select(Lorebook.owner_id)))
    assert owners == [STAYER]
    assert await session.scalar(select(func.count()).select_from(LorebookVersion)) == 1


async def test_someone_with_nothing_here_is_processed(client: AsyncClient):
    response = await signed_withdrawal(client, str(uuid.uuid4()))

    assert (response.status_code, response.json()) == (status.HTTP_200_OK, PROCESSED)


async def test_unknown_fields_in_the_body_are_ignored(client: AsyncClient, session: AsyncSession, belongings: dict):
    body = b'{"withdrawn_at": "2026-10-28T03:00:00Z", "reason": "later field"}'

    response = await signed_withdrawal(client, str(LEAVER), body)

    assert response.status_code == status.HTTP_200_OK
    assert await personas_of(session, LEAVER) == 0


@pytest.mark.parametrize(
    'body', [b'{}', b'{"withdrawn_at": "not a time"}', b'not json'], ids=['missing', 'bad', 'junk']
)
async def test_a_bad_body_is_422_and_erases_nothing(
    client: AsyncClient, session: AsyncSession, belongings: dict, body: bytes
):
    response = await signed_withdrawal(client, str(LEAVER), body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await personas_of(session, LEAVER) == 2


@pytest.mark.parametrize(
    'secret',
    ['a-different-secret-0123456789abcdef', TEST_SECRETS['chat']],
    ids=['wrong-secret', 'chat-secret'],
)
async def test_only_the_auth_servers_signature_is_accepted(
    client: AsyncClient, session: AsyncSession, belongings: dict, secret: str
):
    response = await signed_withdrawal(client, str(LEAVER), secret=secret)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await personas_of(session, LEAVER) == 2


async def test_without_a_signature_it_is_401(client: AsyncClient, session: AsyncSession, belongings: dict):
    response = await client.post(withdrawal_path(str(LEAVER)), json={'withdrawn_at': '2026-10-28T03:00:00Z'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert SIGNATURE_HEADER not in response.headers
    assert await personas_of(session, LEAVER) == 2


@pytest.fixture
async def closed_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """인증 서버의 비밀을 적지 않은 앱."""
    app = create_app(make_test_settings(auth_server_secret=''), http_client=auth_server.make_client(), engine=engine)
    yield app
    await app.state.http_client.aclose()


async def test_an_empty_auth_secret_accepts_nothing(closed_app: FastAPI):
    async with make_client(closed_app) as client:
        response = await signed_withdrawal(client, str(LEAVER), secret='')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
