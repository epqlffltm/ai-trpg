# notification-server/tests/test_follows.py

"""
제작자 팔로우(#989)를 검증한다. 실제 DB(notification_test)에서 돈다.

  - 팔로우하면 내가 팔로우하는 것으로 보이고 팔로워의 수가 는다. 두 번 하거나 두 번 끊어도 수가 어긋나지 않는다
  - 팔로워의 수는 로그인하지 않아도 본다. 내 팔로잉은 최근에 한 것부터, 나만 본다
  - 자기 자신은 422(follow_self), 상한을 넘으면 409(follow_limit)다. 이미 팔로우하는 제작자는 상한에 걸리지 않는다
  - 로그인해야 한다. 탈퇴하면 그 사람이 한 팔로우와 받은 팔로우를 지운다
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token

from app.main import API_PREFIX
from tests.signing import signed_withdrawal

pytestmark = pytest.mark.usefixtures('clean_tables')

FOLLOWS_URL = f'{API_PREFIX}/me/follows'
ME = uuid.UUID('0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
OTHER = uuid.UUID('b1c2d3e4-f5a6-4b7c-8d9e-0f1a2b3c4d5e')
CREATOR = uuid.UUID('c0c0c0c0-0000-4000-8000-00000000c0c0')
WITHDRAWN = {'withdrawn_at': '2026-11-04T03:00:00+00:00'}


def headers_of(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    return {'Authorization': f'Bearer {make_token(signing_key, make_access_claims(sub=str(user_id)))}'}


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return headers_of(signing_key, ME)


@pytest.fixture
def theirs(signing_key: SigningKey) -> dict[str, str]:
    return headers_of(signing_key, OTHER)


def follow_url(creator_id: uuid.UUID) -> str:
    return f'{FOLLOWS_URL}/{creator_id}'


def followers_url(creator_id: uuid.UUID) -> str:
    return f'{API_PREFIX}/creators/{creator_id}/followers'


async def test_follows_count_once_per_person(client: AsyncClient, mine: dict, theirs: dict):
    first = await client.put(follow_url(CREATOR), headers=mine)
    again = await client.put(follow_url(CREATOR), headers=mine)
    other = await client.put(follow_url(CREATOR), headers=theirs)

    assert first.status_code == status.HTTP_200_OK, first.text
    assert first.json() == again.json() == {'following': True, 'follower_count': 1}
    assert other.json() == {'following': True, 'follower_count': 2}
    # 팔로워의 수는 누구나 본다
    assert (await client.get(followers_url(CREATOR))).json() == {'follower_count': 2}

    left = await client.delete(follow_url(CREATOR), headers=mine)
    left_again = await client.delete(follow_url(CREATOR), headers=mine)
    read = await client.get(follow_url(CREATOR), headers=mine)

    assert left.json() == left_again.json() == read.json() == {'following': False, 'follower_count': 1}
    assert (await client.get(follow_url(CREATOR), headers=theirs)).json() == {'following': True, 'follower_count': 1}


async def test_my_following_is_newest_first_and_mine_only(client: AsyncClient, mine: dict, theirs: dict):
    creators = [uuid.uuid4() for _ in range(3)]
    for creator_id in creators:
        await client.put(follow_url(creator_id), headers=mine)
    await client.put(follow_url(creators[0]), headers=theirs)

    page = (await client.get(FOLLOWS_URL, headers=mine)).json()
    limited = (await client.get(FOLLOWS_URL, params={'limit': 1, 'offset': 1}, headers=mine)).json()
    other = (await client.get(FOLLOWS_URL, headers=theirs)).json()

    assert [item['creator_id'] for item in page['items']] == [str(c) for c in reversed(creators)]
    assert page['total'] == 3
    assert [item['creator_id'] for item in limited['items']] == [str(creators[1])]
    assert ([item['creator_id'] for item in other['items']], other['total']) == ([str(creators[0])], 1)


async def test_cannot_follow_oneself(client: AsyncClient, mine: dict):
    response = await client.put(follow_url(ME), headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail']['code'] == 'follow_self'


async def test_the_follow_limit(app: FastAPI, client: AsyncClient, mine: dict):
    app.state.settings.follow_max_per_user = 2
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await client.put(follow_url(first), headers=mine)
    await client.put(follow_url(second), headers=mine)

    over = await client.put(follow_url(third), headers=mine)
    again = await client.put(follow_url(second), headers=mine)

    assert over.status_code == status.HTTP_409_CONFLICT
    assert over.json()['detail']['code'] == 'follow_limit'
    # 이미 팔로우하는 제작자는 상한에 걸리지 않는다. 하나를 끊으면 다시 된다
    assert again.status_code == status.HTTP_200_OK
    await client.delete(follow_url(first), headers=mine)
    assert (await client.put(follow_url(third), headers=mine)).status_code == status.HTTP_200_OK


async def test_follows_need_login(client: AsyncClient):
    for method in ('GET', 'PUT', 'DELETE'):
        response = await client.request(method, follow_url(CREATOR))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert (await client.get(FOLLOWS_URL)).status_code == status.HTTP_401_UNAUTHORIZED


async def test_withdrawal_erases_follows_both_ways(client: AsyncClient, mine: dict, theirs: dict):
    await client.put(follow_url(CREATOR), headers=mine)
    await client.put(follow_url(ME), headers=theirs)
    await client.put(follow_url(CREATOR), headers=theirs)

    response = await signed_withdrawal(client, str(ME), WITHDRAWN)

    assert response.status_code == status.HTTP_200_OK, response.text
    # 내가 한 팔로우와 나를 팔로우한 것이 사라진다. 남의 팔로우는 남는다
    assert (await client.get(followers_url(CREATOR))).json() == {'follower_count': 1}
    assert (await client.get(followers_url(ME))).json() == {'follower_count': 0}
    assert (await client.get(FOLLOWS_URL, headers=theirs)).json()['total'] == 1
