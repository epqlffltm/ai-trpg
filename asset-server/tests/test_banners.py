# asset-server/tests/test_banners.py

"""
홍보 배너(#994)를 검증한다. 운영자가 공개된 캐릭터와 세계관을 걸고, 누구나 지금 걸린 것을 차례대로 본다.

  - 비공개로 돌렸거나 숨긴 작품, 볼 수 없는 등급, 기간 밖의 배너는 보이지 않는다. 작품을 지우면 배너도 지워진다
  - 공개 목록처럼 보는 사람의 설정(성인 작품 숨김, 성향)으로 거른다
  - 운영자의 주소는 운영자가 아니면 404 다
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import API_PREFIX
from tests import test_characters_api as character_tests
from tests.test_characters_api import CHARACTERS_URL, create, make_public
from tests.worlds import WORLDS_URL, character, create_world, full_world, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

# 캐릭터 테스트의 픽스처를 그대로 쓴다(운영자, 성인 확인을 하지 않은 사람, 성인)
operator = character_tests.operator
player = character_tests.player
adult = character_tests.adult

BANNERS_URL = f'{API_PREFIX}/banners'
ADMIN_URL = f'{API_PREFIX}/admin/banners'


def iso(moment: datetime) -> str:
    return moment.isoformat()


async def hang(client: AsyncClient, headers: dict, kind: str, target: dict, **fields) -> dict:
    """배너를 건다."""
    body = {'kind': kind, 'target_id': target['id'], **fields}
    response = await client.post(ADMIN_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def public_world(client: AsyncClient, headers: dict, name: str, **fields) -> dict:
    """공개로 두고 게시한 세계관."""
    ari, beo = await character(client, headers, '아리'), await character(client, headers, '버')
    world = await create_world(client, headers, {**full_world(ari['id'], beo['id']), 'name': name, **fields})
    await client.patch(f'{WORLDS_URL}/{world["id"]}', json={'visibility': 'public'}, headers=headers)
    assert (await publish(client, headers, world)).status_code == status.HTTP_201_CREATED
    return world


async def shown(client: AsyncClient, headers: dict | None = None, params: dict | None = None) -> list[str]:
    """지금 보이는 배너의 작품 이름, 차례대로."""
    response = await client.get(BANNERS_URL, params=params or {}, headers=headers or {})
    assert response.status_code == status.HTTP_200_OK, response.text
    return [(item['character'] or item['world'])['name'] for item in response.json()['items']]


async def test_characters_and_worlds_are_shown_in_one_order(client: AsyncClient, operator: dict):
    seira = await make_public(client, operator, name='세라')
    summer = await public_world(client, operator, '여름 학교')
    await hang(client, operator, 'character', seira, position=2)
    await hang(client, operator, 'world', summer, position=1)

    response = (await client.get(BANNERS_URL)).json()['items']

    # 로그인하지 않아도 본다. 공개 목록의 한 줄과 같은 모양이다
    assert [(item['kind'], (item['character'] or item['world'])['name']) for item in response] == [
        ('world', '여름 학교'),
        ('character', '세라'),
    ]
    assert response[1]['character']['id'] == seira['id'] and response[1]['world'] is None


async def test_only_listed_works_can_be_hung(client: AsyncClient, operator: dict):
    private = await create(client, operator)
    missing = '00000000-0000-4000-8000-000000000000'

    refused = [
        await client.post(ADMIN_URL, json={'kind': 'character', 'target_id': private['id']}, headers=operator),
        await client.post(ADMIN_URL, json={'kind': 'world', 'target_id': missing}, headers=operator),
        # 캐릭터의 ID 를 세계관으로 걸 수 없다
        await client.post(ADMIN_URL, json={'kind': 'world', 'target_id': private['id']}, headers=operator),
    ]

    assert [response.status_code for response in refused] == [status.HTTP_409_CONFLICT] * 3
    assert refused[0].json()['code'] == 'not_published'


async def test_a_work_made_private_disappears_and_comes_back(client: AsyncClient, operator: dict):
    seira = await make_public(client, operator, name='세라')
    await hang(client, operator, 'character', seira)

    await client.patch(f'{CHARACTERS_URL}/{seira["id"]}', json={'visibility': 'private'}, headers=operator)
    hidden = await shown(client)
    listed = (await client.get(ADMIN_URL, headers=operator)).json()
    await client.patch(f'{CHARACTERS_URL}/{seira["id"]}', json={'visibility': 'public'}, headers=operator)

    assert hidden == []
    assert [(item['name'], item['kind'], item['shown']) for item in listed] == [('세라', 'character', False)]
    assert await shown(client) == ['세라']


async def test_deleting_a_work_deletes_its_banner(client: AsyncClient, operator: dict):
    seira = await make_public(client, operator, name='세라')
    await hang(client, operator, 'character', seira)

    await client.delete(f'{CHARACTERS_URL}/{seira["id"]}', headers=operator)

    assert await shown(client) == []
    assert (await client.get(ADMIN_URL, headers=operator)).json() == []


async def test_an_adult_banner_is_shown_only_to_adults(client: AsyncClient, operator: dict, player: dict, adult: dict):
    night = await make_public(client, operator, name='밤의 세라', rating='adult')
    await hang(client, operator, 'character', night)

    assert (await shown(client), await shown(client, player)) == ([], [])
    assert await shown(client, adult) == ['밤의 세라']


async def test_banners_follow_the_viewer_preferences(client: AsyncClient, operator: dict, adult: dict):
    night = await make_public(client, operator, name='밤의 세라', rating='adult', tags=['남성향'])
    day = await make_public(client, operator, name='낮의 세라', tags=['여성향'])
    summer = await public_world(client, operator, '여름 학원', tags=['여성향'])
    await hang(client, operator, 'character', night, position=1)
    await hang(client, operator, 'character', day, position=2)
    await hang(client, operator, 'world', summer, position=3)

    # 공개 목록처럼 성인 작품 숨김(#986)과 성향(#987)으로 거른다. 캐릭터와 세계관 모두다
    assert await shown(client, adult) == ['밤의 세라', '낮의 세라', '여름 학원']
    assert await shown(client, adult, {'hide_adult': 'true'}) == ['낮의 세라', '여름 학원']
    assert await shown(client, adult, {'orientation': 'female'}) == ['낮의 세라', '여름 학원']
    assert await shown(client, adult, {'orientation': 'male'}) == ['밤의 세라']


async def test_banners_show_only_within_their_period(client: AsyncClient, operator: dict):
    now = datetime.now(UTC)
    later = await make_public(client, operator, name='나중')
    over = await make_public(client, operator, name='지남')
    on = await make_public(client, operator, name='지금')
    await hang(client, operator, 'character', later, starts_at=iso(now + timedelta(days=1)))
    await hang(
        client,
        operator,
        'character',
        over,
        starts_at=iso(now - timedelta(days=2)),
        ends_at=iso(now - timedelta(days=1)),
    )
    await hang(client, operator, 'character', on, ends_at=iso(now + timedelta(days=1)))

    assert await shown(client) == ['지금']


async def test_the_operator_changes_order_and_period_and_takes_it_down(client: AsyncClient, operator: dict):
    a = await make_public(client, operator, name='가')
    b = await make_public(client, operator, name='나')
    first = await hang(client, operator, 'character', a, position=1)
    await hang(client, operator, 'character', b, position=2)

    moved = await client.patch(f'{ADMIN_URL}/{first["id"]}', json={'position': 3}, headers=operator)
    order = await shown(client)
    reversed_period = await client.patch(
        f'{ADMIN_URL}/{first["id"]}', json={'ends_at': iso(datetime.now(UTC) - timedelta(days=1))}, headers=operator
    )
    cleared = await client.patch(f'{ADMIN_URL}/{first["id"]}', json={'position': None}, headers=operator)
    removed = await client.delete(f'{ADMIN_URL}/{first["id"]}', headers=operator)
    again = await client.patch(f'{ADMIN_URL}/{first["id"]}', json={'position': 1}, headers=operator)

    assert moved.status_code == status.HTTP_200_OK and order == ['나', '가']
    assert (reversed_period.status_code, cleared.status_code) == (status.HTTP_422_UNPROCESSABLE_CONTENT,) * 2
    assert (removed.status_code, again.status_code) == (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND)
    assert await shown(client) == ['나']


@pytest.mark.parametrize(
    'body',
    [
        {'position': -1},
        {'position': 1000},
        {'kind': 'scenario'},
        {'starts_at': '2026-11-02T00:00:00Z', 'ends_at': '2026-11-01T00:00:00Z'},
        {'starts_at': '2026-11-02T00:00:00'},
        {'title': 'x'},
    ],
)
async def test_rejects_a_bad_banner(client: AsyncClient, operator: dict, body: dict):
    seira = await make_public(client, operator)

    response = await client.post(
        ADMIN_URL, json={'kind': 'character', 'target_id': seira['id'], **body}, headers=operator
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_admin_addresses_are_404_for_others(client: AsyncClient, operator: dict, player: dict):
    seira = await make_public(client, operator)
    banner = await hang(client, operator, 'character', seira)

    responses = [
        await client.get(ADMIN_URL, headers=player),
        await client.post(ADMIN_URL, json={'kind': 'character', 'target_id': seira['id']}, headers=player),
        await client.patch(f'{ADMIN_URL}/{banner["id"]}', json={'position': 1}, headers=player),
        await client.delete(f'{ADMIN_URL}/{banner["id"]}', headers=player),
    ]

    assert [response.status_code for response in responses] == [status.HTTP_404_NOT_FOUND] * 4
    assert (await client.get(ADMIN_URL)).status_code == status.HTTP_401_UNAUTHORIZED
