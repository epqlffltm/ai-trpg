# game-server/tests/test_worlds_api.py

"""
세계관 API 를 검증한다. 요청이 서비스까지 이어지고, 결과가 올바른 HTTP 응답으로 나오는가.

만들고 고치는 규칙 자체는 test_world_service.py 가 검증한다. 여기서는 API 의 약속을 본다.
로그인을 요구하는가, 누구의 요청인지가 토큰에서 오는가, 상태 코드와 응답의 모양이 맞는가.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import API_PREFIX
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

WORLDS_URL = f'{API_PREFIX}/worlds'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
SOMEONE_ELSE = uuid.UUID('99999999-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시 세계관. 내용은 아무 뜻이 없다
TITLE = '악역영애와 엘프 폭주족'
SETTING = (
    '실연당한 악역영애가, 17개 행성에서 사형선고를 받은 모히칸 엘프 폭주족의 바이크 뒷자리에 탔다. '
    '둘은 행성마다 TS 약물을 뿌리는 테러를 벌인다.'
)
GM_NOTES = '둘을 쫓는 추격자는 마법소년 매지컬 스미스. 드워프다.'


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


async def create_world(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """API 로 세계관 하나를 만들고 응답의 본문을 돌려준다."""
    body = {'title': TITLE}
    body.update(fields)
    response = await client.post(WORLDS_URL, json=body, headers=headers)
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
    response = await client.request(method, f'{WORLDS_URL}{path}', json={'title': '세계'})

    # 로그인 없이 열리는 주소가 하나도 없다
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 만들기 ---


async def test_creates_a_world(client: AsyncClient, my_headers: dict[str, str]):
    response = await client.post(
        WORLDS_URL,
        json={
            'title': TITLE,
            'setting': SETTING,
            'gm_notes': GM_NOTES,
        },
        headers=my_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body['title'] == TITLE
    assert body['setting'] == SETTING
    assert body['gm_notes'] == GM_NOTES
    assert body['visibility'] == 'private'
    assert uuid.UUID(body['id'])
    assert body['created_at']


async def test_the_response_does_not_carry_internal_fields(client: AsyncClient, my_headers: dict[str, str]):
    body = await create_world(client, my_headers)

    # 응답의 칸은 정해 둔 것뿐이다. 모델에 컬럼을 추가해도 저절로 새어 나가지 않는다
    assert set(body) == {
        'id',
        'title',
        'description',
        'visibility',
        'created_at',
        'updated_at',
        'setting',
        'gm_notes',
    }


async def test_the_owner_comes_from_the_token_not_the_body(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    response = await client.post(WORLDS_URL, json={'title': '세계', 'owner_id': str(SOMEONE_ELSE)}, headers=my_headers)

    # 남의 이름으로 자산을 만들 수 없다. 조용히 무시하지 않고 거부한다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    listed = await client.get(WORLDS_URL, headers=their_headers)
    assert listed.json()['total'] == 0


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'title': ''},
        {'title': '   '},
        {'title': 'x' * 101},
        # 등급은 시나리오에서만 정한다. 맞는 값이어도 재료에는 받지 않는다
        {'title': '세계', 'rating': 'adult'},
        {'title': '세계', 'setting': '가' * 8001},
        {'title': '세계', 'gm_notes': '가' * 4001},
        {'title': '세계', 'description': '가' * 1001},
    ],
)
async def test_rejects_bad_input(client: AsyncClient, my_headers: dict[str, str], body: dict):
    response = await client.post(WORLDS_URL, json=body, headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 목록 ---


async def test_lists_only_my_worlds(client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]):
    mine = await create_world(client, my_headers, title='내 세계')
    await create_world(client, their_headers, title='남의 세계')

    response = await client.get(WORLDS_URL, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['total'] == 1
    assert [item['id'] for item in body['items']] == [mine['id']]


async def test_the_list_does_not_carry_the_long_text(client: AsyncClient, my_headers: dict[str, str]):
    await create_world(client, my_headers, setting='긴 설정', gm_notes='비밀')

    response = await client.get(WORLDS_URL, headers=my_headers)

    item = response.json()['items'][0]
    assert 'setting' not in item
    assert 'gm_notes' not in item


async def test_the_list_is_paged(client: AsyncClient, my_headers: dict[str, str]):
    for number in range(3):
        await create_world(client, my_headers, title=f'세계 {number}')

    response = await client.get(WORLDS_URL, params={'limit': 2, 'offset': 2}, headers=my_headers)

    body = response.json()
    assert body['total'] == 3
    assert len(body['items']) == 1


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 101}, {'limit': -1}, {'offset': -1}, {'limit': 'many'}])
async def test_rejects_a_bad_page_request(client: AsyncClient, my_headers: dict[str, str], params: dict):
    response = await client.get(WORLDS_URL, params=params, headers=my_headers)

    # 한 번에 전부 달라는 요청을 받지 않는다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 하나 읽기 ---


async def test_reads_my_world_with_the_gm_notes(client: AsyncClient, my_headers: dict[str, str]):
    created = await create_world(client, my_headers, gm_notes='비밀')

    response = await client.get(f'{WORLDS_URL}/{created["id"]}', headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['gm_notes'] == '비밀'


async def test_someone_elses_world_looks_like_it_does_not_exist(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_world(client, their_headers, gm_notes='비밀')

    someone_elses = await client.get(f'{WORLDS_URL}/{theirs["id"]}', headers=my_headers)
    missing = await client.get(f'{WORLDS_URL}/{uuid.uuid4()}', headers=my_headers)

    assert someone_elses.status_code == status.HTTP_404_NOT_FOUND
    # 남의 것과 없는 것의 응답이 같다. 그 ID 의 자산이 있는지 알 수 없다
    assert someone_elses.json() == missing.json()
    assert '비밀' not in someone_elses.text


async def test_rejects_an_id_that_is_not_a_uuid(client: AsyncClient, my_headers: dict[str, str]):
    response = await client.get(f'{WORLDS_URL}/1', headers=my_headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 고치기 ---


async def test_updates_only_what_was_sent(client: AsyncClient, my_headers: dict[str, str]):
    created = await create_world(client, my_headers, setting='옛 설정', gm_notes='비밀')

    response = await client.patch(f'{WORLDS_URL}/{created["id"]}', json={'setting': '새 설정'}, headers=my_headers)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body['setting'] == '새 설정'
    assert body['gm_notes'] == '비밀'
    assert body['title'] == TITLE
    assert body['updated_at'] > created['updated_at']


async def test_cannot_change_the_owner_or_visibility(client: AsyncClient, my_headers: dict[str, str]):
    created = await create_world(client, my_headers)
    url = f'{WORLDS_URL}/{created["id"]}'

    owner = await client.patch(url, json={'owner_id': str(SOMEONE_ELSE)}, headers=my_headers)
    visibility = await client.patch(url, json={'visibility': 'public'}, headers=my_headers)

    assert owner.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert visibility.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_cannot_update_someone_elses_world(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_world(client, their_headers)
    url = f'{WORLDS_URL}/{theirs["id"]}'

    response = await client.patch(url, json={'title': '빼앗음'}, headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    untouched = await client.get(url, headers=their_headers)
    assert untouched.json()['title'] == TITLE


# --- 지우기 ---


async def test_deletes_my_world(client: AsyncClient, my_headers: dict[str, str]):
    created = await create_world(client, my_headers)
    url = f'{WORLDS_URL}/{created["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b''
    assert (await client.get(url, headers=my_headers)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(WORLDS_URL, headers=my_headers)).json()['total'] == 0


async def test_cannot_delete_someone_elses_world(
    client: AsyncClient, my_headers: dict[str, str], their_headers: dict[str, str]
):
    theirs = await create_world(client, their_headers)
    url = f'{WORLDS_URL}/{theirs["id"]}'

    response = await client.delete(url, headers=my_headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(url, headers=their_headers)).status_code == status.HTTP_200_OK
