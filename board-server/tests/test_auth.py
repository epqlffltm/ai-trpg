# board-server/tests/test_auth.py

"""
로그인이 필요한 API 의 사람(app/core/auth.py 의 Member)과 닉네임 적기를 검증한다.

  - 토큰의 닉네임을 그 사람의 닉네임으로 적는다. 같은 닉네임이면 다시 쓰지 않는다
  - 적을 수 없는 닉네임(보이지 않는 글자, 너무 긴 것)이면 적지 않고 토큰은 받는다
  - 인증 서버에서 키를 받은 적이 없고 지금 닿지 않으면 503 과 Retry-After 다(클라이언트의 잘못이 아니다)
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import FakeAuthServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authors.models import Author

ME = '/api/v1/board/me'

pytestmark = pytest.mark.usefixtures('clean_tables')

Headers = Callable[..., dict[str, str]]


async def nickname_of(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    session.expire_all()
    return await session.scalar(select(Author.nickname).where(Author.user_id == user_id))


async def test_the_owner_is_answered(client: AsyncClient, headers_for: Headers):
    user_id = uuid.uuid4()

    response = await client.get(ME, headers=headers_for(str(user_id), roles=['operator']))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {'user_id': str(user_id), 'is_operator': True}


async def test_the_nickname_in_the_token_is_stored(client: AsyncClient, headers_for: Headers, session: AsyncSession):
    user_id = uuid.uuid4()

    await client.get(ME, headers=headers_for(str(user_id), nickname='모험가'))
    await client.get(ME, headers=headers_for(str(user_id), nickname='새 이름'))

    assert await nickname_of(session, user_id) == '새 이름'


@pytest.mark.parametrize('nickname', ['', '   ', '이름​', '가' * 51, 42])
async def test_an_unacceptable_nickname_is_not_stored_but_the_token_is_accepted(
    client: AsyncClient, headers_for: Headers, session: AsyncSession, nickname: object
):
    user_id = uuid.uuid4()

    response = await client.get(ME, headers=headers_for(str(user_id), nickname=nickname))

    assert response.status_code == status.HTTP_200_OK
    assert await nickname_of(session, user_id) is None


async def test_without_a_token_it_is_401(client: AsyncClient):
    response = await client.get(ME)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {'detail': '인증이 필요합니다.'}
    assert response.headers['WWW-Authenticate'] == 'Bearer'


async def test_without_keys_from_a_dead_auth_server_it_is_503(
    client: AsyncClient, headers_for: Headers, auth_server: FakeAuthServer
):
    auth_server.down = True

    response = await client.get(ME, headers=headers_for(str(uuid.uuid4())))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers['Retry-After'] == '60'
    assert response.json() == {'detail': '지금은 인증을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.'}
