# game-server/tests/test_rulebooks_api.py

"""
룰북 API 를 검증한다.

모든 자산에 공통인 규칙(소유자 검사, 지우기, 쪽 나누기)은 세계관의 테스트가 이미 검증한다. 같은 것을 다시 쓰지 않는다.
여기서는 두 가지를 본다. 공통 규칙이 룰북에도 이어져 있는가, 그리고 룰북만의 것(진행 지침, 다른 종류와 섞이지 않는가).
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import RULEBOOK_GM_GUIDE_MAX_LENGTH, Asset, AssetType, Rulebook
from app.main import API_PREFIX
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
WORLDS_URL = f'{API_PREFIX}/worlds'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시 룰북. 내용은 아무 뜻이 없다
TITLE = '폭주족 추격전 룰'
GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다. 악역영애의 대사는 항상 존댓말로 쓴다.'


@pytest.fixture
def my_headers(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말."""
    return bearer(signing_key, ME)


@pytest.fixture
def their_headers(signing_key: SigningKey) -> dict[str, str]:
    """다른 사람의 토큰이 실린 머리말."""
    return bearer(signing_key, SOMEONE_ELSE)


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


async def create_rulebook(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """API 로 룰북 하나를 만들고 응답의 본문을 돌려준다."""
    body = {'title': TITLE}
    body.update(fields)
    response = await client.post(RULEBOOKS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('POST', ''),
        ('GET', ''),
        ('GET', '/11111111-2222-4333-8444-555555555555'),
        ('PATCH', '/11111111-2222-4333-8444-555555555555'),
        ('DELETE', '/11111111-2222-4333-8444-555555555555'),
    ],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{RULEBOOKS_URL}{path}', json={'title': '룰'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 룰북만의 것 ---


async def test_creates_a_rulebook_with_a_gm_guide(client: AsyncClient, my_headers: dict[str, str]):
    response = await client.post(RULEBOOKS_URL, json={'title': TITLE, 'gm_guide': GM_GUIDE}, headers=my_headers)

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body['title'] == TITLE
    assert body['gm_guide'] == GM_GUIDE
    assert body['visibility'] == 'private'


async def test_the_response_carries_only_the_listed_fields(client: AsyncClient, my_headers: dict[str, str]):
    body = await create_rulebook(client, my_headers)

    assert set(body) == {
        'id',
        'title',
        'description',
        'visibility',
        'created_at',
        'updated_at',
        'gm_guide',
    }


async def test_a_rulebook_is_saved_as_the_rulebook_type(
    client: AsyncClient, my_headers: dict[str, str], session: AsyncSession
):
    created = await create_rulebook(client, my_headers)

    saved_type = await session.scalar(text('SELECT type FROM assets WHERE id = :id'), {'id': created['id']})

    assert saved_type == AssetType.RULEBOOK


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'title': '   '},
        {'title': '룰', 'gm_guide': '가' * (RULEBOOK_GM_GUIDE_MAX_LENGTH + 1)},
        # 세계관의 칸이다. 룰북에는 없다
        {'title': '룰', 'setting': '설정'},
        # 등급은 시나리오에서만 정한다
        {'title': '룰', 'rating': 'adult'},
        {'title': '룰', 'owner_id': str(SOMEONE_ELSE)},
    ],
)
async def test_rejects_bad_input(client: AsyncClient, my_headers: dict[str, str], body: dict):
    response = await client.post(RULEBOOKS_URL, json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_updates_the_gm_guide_only(client: AsyncClient, my_headers: dict[str, str]):
    created = await create_rulebook(client, my_headers, description='소개', gm_guide='옛 지침')

    response = await client.patch(f'{RULEBOOKS_URL}/{created["id"]}', json={'gm_guide': GM_GUIDE}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['gm_guide'] == GM_GUIDE
    assert body['title'] == TITLE
    assert body['description'] == '소개'
    assert body['updated_at'] > created['updated_at']


async def test_the_list_does_not_carry_the_gm_guide(client: AsyncClient, my_headers: dict[str, str]):
    await create_rulebook(client, my_headers, gm_guide=GM_GUIDE)

    response = await client.get(RULEBOOKS_URL, headers=my_headers)

    body = response.json()
    assert body['total'] == 1
    assert 'gm_guide' not in body['items'][0]


# --- 다른 종류와 섞이지 않는다 ---


async def test_lists_do_not_mix_asset_types(client: AsyncClient, my_headers: dict[str, str]):
    rulebook = await create_rulebook(client, my_headers)
    world = (await client.post(WORLDS_URL, json={'title': '세계'}, headers=my_headers)).json()

    rulebooks = (await client.get(RULEBOOKS_URL, headers=my_headers)).json()
    worlds = (await client.get(WORLDS_URL, headers=my_headers)).json()

    # 같은 사람의 자산이어도 종류별 목록에는 그 종류만 나온다
    assert [item['id'] for item in rulebooks['items']] == [rulebook['id']]
    assert [item['id'] for item in worlds['items']] == [world['id']]
    assert rulebooks['total'] == 1
    assert worlds['total'] == 1


async def test_a_world_cannot_be_reached_through_the_rulebook_address(client: AsyncClient, my_headers: dict[str, str]):
    world = (await client.post(WORLDS_URL, json={'title': '세계'}, headers=my_headers)).json()
    url = f'{RULEBOOKS_URL}/{world["id"]}'

    read = await client.get(url, headers=my_headers)
    update = await client.patch(url, json={'title': '바꿈'}, headers=my_headers)
    delete = await client.delete(url, headers=my_headers)

    # 내 자산의 ID 여도, 종류가 다르면 없는 것이다
    assert read.status_code == status.HTTP_404_NOT_FOUND
    assert update.status_code == status.HTTP_404_NOT_FOUND
    assert delete.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(f'{WORLDS_URL}/{world["id"]}', headers=my_headers)).json()['title'] == '세계'


# --- 공통 규칙이 룰북에도 이어져 있다 ---


async def test_someone_elses_rulebook_looks_like_it_does_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_rulebook(client, their_headers, gm_guide=GM_GUIDE)
    url = f'{RULEBOOKS_URL}/{theirs["id"]}'

    read = await client.get(url, headers=my_headers)
    update = await client.patch(url, json={'title': '빼앗음'}, headers=my_headers)
    delete = await client.delete(url, headers=my_headers)

    assert read.status_code == status.HTTP_404_NOT_FOUND
    assert update.status_code == status.HTTP_404_NOT_FOUND
    assert delete.status_code == status.HTTP_404_NOT_FOUND
    assert GM_GUIDE not in read.text
    assert (await client.get(url, headers=their_headers)).json()['title'] == TITLE


async def test_deletes_my_rulebook(client: AsyncClient, my_headers: dict[str, str]):
    created = await create_rulebook(client, my_headers)
    url = f'{RULEBOOKS_URL}/{created["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert (await client.get(url, headers=my_headers)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(RULEBOOKS_URL, headers=my_headers)).json()['total'] == 0


# --- DB 의 마지막 방어선 ---


async def test_the_database_rejects_a_gm_guide_that_is_too_long(session: AsyncSession):
    asset = Asset(owner_id=ME, type=AssetType.RULEBOOK, title='룰')
    session.add(Rulebook(asset=asset, gm_guide='가' * (RULEBOOK_GM_GUIDE_MAX_LENGTH + 1)))

    with pytest.raises(IntegrityError):
        await session.commit()
