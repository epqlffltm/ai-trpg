# asset-server/tests/test_hearts.py

"""
캐릭터와 세계관의 관심(하트, #989)을 검증한다. 실제 DB(asset_test)에서 돈다.

  - 두면 내가 둔 것으로 보이고 관심의 수가 하나 는다. 두 번 두거나 두 번 거둬도 수가 어긋나지 않는다
  - 공개 목록과 소개에 관심의 수가 실린다
  - 둘 수 있는 것은 주소로 열 수 있는 것이다(비공개, 볼 수 없는 등급은 404). 거두는 것은 비공개로 돌린 뒤에도 된다
  - 내 관심 작품은 최근에 둔 것부터, 지금 열 수 있는 것만이다
  - 로그인해야 한다. 탈퇴하면 그 사람의 관심을 거두고 수도 뺀다. 작품을 지우면 관심도 지워진다
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from tests import test_characters_api as character_tests
from tests.signing import signed_withdrawal
from tests.test_characters_api import CHARACTERS_URL, LISTINGS_URL, PLAYER, make_public
from tests.test_world_listings import LISTINGS_URL as WORLD_LISTINGS_URL
from tests.test_world_listings import published
from tests.worlds import OWNER, WORLDS_URL, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

operator = character_tests.operator
player = character_tests.player
adult = character_tests.adult


def heart_url(base: str, work: dict) -> str:
    return f'{base}/{work["id"]}/heart'


async def test_character_hearts_count_once_per_person(client: AsyncClient, operator: dict, player: dict):
    character = await make_public(client, operator, name='세라')
    url = heart_url(LISTINGS_URL, character)

    first = await client.put(url, headers=player)
    again = await client.put(url, headers=player)
    mine = await client.put(url, headers=operator)

    assert first.status_code == status.HTTP_200_OK, first.text
    assert first.json() == again.json() == {'hearted': True, 'heart_count': 1}
    assert mine.json() == {'hearted': True, 'heart_count': 2}
    # 목록과 소개에 실린다
    assert (await client.get(LISTINGS_URL)).json()['items'][0]['heart_count'] == 2
    assert (await client.get(f'{LISTINGS_URL}/{character["id"]}')).json()['heart_count'] == 2

    taken = await client.delete(url, headers=player)
    taken_again = await client.delete(url, headers=player)
    read = await client.get(url, headers=player)

    assert taken.json() == taken_again.json() == read.json() == {'hearted': False, 'heart_count': 1}


async def test_only_opened_characters_take_hearts(client: AsyncClient, operator: dict, player: dict, adult: dict):
    night = await make_public(client, operator, name='밤', rating='adult')
    later = await make_public(client, operator, name='돌릴 것')
    await client.put(heart_url(LISTINGS_URL, later), headers=player)
    await client.patch(f'{CHARACTERS_URL}/{later["id"]}', json={'visibility': 'private'}, headers=operator)

    # 볼 수 없는 등급과 비공개는 없는 것이다. 성인은 둔다
    assert (await client.put(heart_url(LISTINGS_URL, night), headers=player)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.put(heart_url(LISTINGS_URL, later), headers=adult)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(heart_url(LISTINGS_URL, later), headers=player)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.put(heart_url(LISTINGS_URL, night), headers=adult)).json()['heart_count'] == 1
    # 비공개로 돌린 뒤에도 거둔다
    taken = await client.delete(heart_url(LISTINGS_URL, later), headers=player)
    assert taken.json() == {'hearted': False, 'heart_count': 0}


async def test_my_hearted_characters(client: AsyncClient, operator: dict, player: dict):
    first = await make_public(client, operator, name='먼저')
    second = await make_public(client, operator, name='나중')
    gone = await make_public(client, operator, name='돌림')
    for character in (first, gone, second):
        await client.put(heart_url(LISTINGS_URL, character), headers=player)
    await client.patch(f'{CHARACTERS_URL}/{gone["id"]}', json={'visibility': 'private'}, headers=operator)

    page = (await client.get(f'{LISTINGS_URL}/hearted', headers=player)).json()
    limited = (await client.get(f'{LISTINGS_URL}/hearted', params={'limit': 1, 'offset': 1}, headers=player)).json()

    # 최근에 둔 것부터, 지금 열 수 있는 것만이다
    assert ([item['name'] for item in page['items']], page['total']) == (['나중', '먼저'], 2)
    assert [item['name'] for item in limited['items']] == ['먼저']
    assert (await client.get(f'{LISTINGS_URL}/hearted', headers=operator)).json() == {'items': [], 'total': 0}


async def test_world_hearts(client: AsyncClient, signing_key: SigningKey):
    owner = bearer(signing_key, OWNER)
    viewer = bearer(signing_key, PLAYER, operator=False)
    summer = await published(client, owner, name='여름')
    url = heart_url(WORLD_LISTINGS_URL, summer)

    assert (await client.put(url, headers=viewer)).json() == {'hearted': True, 'heart_count': 1}
    assert (await client.get(f'{WORLD_LISTINGS_URL}/{summer["id"]}')).json()['heart_count'] == 1
    assert (await client.get(WORLD_LISTINGS_URL)).json()['items'][0]['heart_count'] == 1
    hearted = (await client.get(f'{WORLD_LISTINGS_URL}/hearted', headers=viewer)).json()
    assert [item['name'] for item in hearted['items']] == ['여름']

    # 비공개로 돌리면 둘 수 없고 목록에서 빠진다. 거두는 것은 된다
    await client.patch(f'{WORLDS_URL}/{summer["id"]}', json={'visibility': 'private'}, headers=owner)
    assert (await client.put(url, headers=owner)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(f'{WORLD_LISTINGS_URL}/hearted', headers=viewer)).json()['total'] == 0
    assert (await client.delete(url, headers=viewer)).json() == {'hearted': False, 'heart_count': 0}


async def test_hearts_need_login(client: AsyncClient, operator: dict):
    character = await make_public(client, operator)

    for method in ('GET', 'PUT', 'DELETE'):
        response = await client.request(method, heart_url(LISTINGS_URL, character))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert (await client.get(f'{LISTINGS_URL}/hearted')).status_code == status.HTTP_401_UNAUTHORIZED
    assert (await client.get(f'{WORLD_LISTINGS_URL}/hearted')).status_code == status.HTTP_401_UNAUTHORIZED


async def test_withdrawal_takes_back_the_hearts(client: AsyncClient, operator: dict, player: dict):
    character = await make_public(client, operator)
    url = heart_url(LISTINGS_URL, character)
    await client.put(url, headers=player)
    await client.put(url, headers=operator)

    response = await signed_withdrawal(client, str(PLAYER))

    assert response.status_code == status.HTTP_200_OK, response.text
    assert (await client.get(url, headers=operator)).json() == {'hearted': True, 'heart_count': 1}


async def test_deleting_a_character_deletes_its_hearts(client: AsyncClient, operator: dict, player: dict):
    character = await make_public(client, operator)
    await client.put(heart_url(LISTINGS_URL, character), headers=player)

    deleted = await client.delete(f'{CHARACTERS_URL}/{character["id"]}', headers=operator)

    assert deleted.status_code == status.HTTP_204_NO_CONTENT, deleted.text
    assert (await client.get(f'{LISTINGS_URL}/hearted', headers=player)).json() == {'items': [], 'total': 0}
