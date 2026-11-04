# trpg-server/tests/test_listing_exclusions.py

"""
보는 사람이 막은 제작자와 태그(app/listings/exclusions.py, #988)를 검증한다. 실제 DB(game_test)에서 돈다.

  - 공개 목록, 검색, 랭킹, 배너에서 막은 제작자의 것과 막은 태그가 하나라도 붙은 것을 뺀다
  - 제작자는 쉼표로 잇고(exclude_creators), 태그는 이름을 되풀이한다(exclude_tag). 쉼표가 든 태그도 뺀다
  - 소개 하나를 여는 주소는 그대로 열린다(막은 값을 싣지 않는다)
  - 제작자 100명, 태그 30개까지다. 넘거나 공개 ID 가 아니면 422 다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from app.listings.exclusions import MAX_EXCLUDED_CREATORS, MAX_EXCLUDED_TAGS
from app.main import API_PREFIX
from tests import test_listings_api as listing_tests
from tests.test_banners import hang, shown
from tests.test_listings_api import ME, SOMEONE_ELSE, make_public
from tests.test_rankings import open_tables, ranked

pytestmark = pytest.mark.usefixtures('clean_tables')

my_headers = listing_tests.my_headers
their_headers = listing_tests.their_headers
operator_headers = listing_tests.operator_headers

LISTINGS_URL = f'{API_PREFIX}/listings'


async def titles(client: AsyncClient, params: dict | list) -> list[str]:
    response = await client.get(LISTINGS_URL, params=params)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [item['title'] for item in response.json()['items']]


async def test_the_list_drops_blocked_creators_and_tags(client: AsyncClient, my_headers: dict, their_headers: dict):
    await make_public(client, my_headers, title='내 공포', tags=['공포'])
    await make_public(client, my_headers, title='내 쉼표', tags=['가,나'])
    await make_public(client, my_headers, title='내 일상', tags=['일상'])
    await make_public(client, their_headers, title='남의 일상', tags=['일상'])

    assert await titles(client, {'exclude_creators': str(SOMEONE_ELSE)}) == ['내 일상', '내 쉼표', '내 공포']
    assert await titles(client, [('exclude_tag', '공포'), ('exclude_tag', '가,나')]) == ['남의 일상', '내 일상']
    both = [('exclude_creators', f'{ME}, {SOMEONE_ELSE}'), ('exclude_tag', '없는 태그')]
    assert await titles(client, both) == []
    # 검색과 함께여도 뺀다
    assert await titles(client, {'q': '일상', 'exclude_creators': str(ME)}) == ['남의 일상']


async def test_the_detail_still_opens(client: AsyncClient, my_headers: dict):
    scenario = await make_public(client, my_headers, title='내 공포', tags=['공포'])

    response = await client.get(f'{LISTINGS_URL}/{scenario["id"]}', params={'exclude_tag': '공포'})

    assert response.status_code == status.HTTP_200_OK


async def test_rankings_and_banners_drop_them(
    client: AsyncClient, my_headers: dict, their_headers: dict, operator_headers: dict
):
    mine = await make_public(client, my_headers, title='내 것', tags=['공포'])
    theirs = await make_public(client, their_headers, title='남의 것')
    await open_tables(client, my_headers, mine, 2)
    await open_tables(client, their_headers, theirs, 1)
    await hang(client, operator_headers, mine)
    await hang(client, operator_headers, theirs)

    assert await ranked(client, exclude_tag='공포') == [(1, '남의 것', 1)]
    assert await ranked(client, exclude_creators=str(SOMEONE_ELSE)) == [(1, '내 것', 2)]
    assert await shown(client, params={'exclude_creators': str(ME)}) == ['남의 것']
    assert await shown(client, params={'exclude_tag': '공포'}) == ['남의 것']


@pytest.mark.parametrize(
    'params',
    [
        {'exclude_creators': 'not-a-uuid'},
        {'exclude_creators': ','.join(str(uuid.uuid4()) for _ in range(MAX_EXCLUDED_CREATORS + 1))},
        [('exclude_tag', f'태그{index}') for index in range(MAX_EXCLUDED_TAGS + 1)],
        {'exclude_tag': 'ㄱ' * 21},
        {'exclude_tag': ' '},
    ],
)
async def test_rejects_bad_exclusions(client: AsyncClient, params: dict | list):
    response = await client.get(LISTINGS_URL, params=params)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_takes_the_most_exclusions_allowed(client: AsyncClient, my_headers: dict):
    await make_public(client, my_headers, title='내 것')
    creators = ','.join(str(uuid.uuid4()) for _ in range(MAX_EXCLUDED_CREATORS))
    # 가장 긴 태그(20자) 30개. 주소가 가장 길어지는 경우다
    tags = [('exclude_tag', f'{index:02d}' + '가' * 18) for index in range(MAX_EXCLUDED_TAGS)]

    assert await titles(client, [('exclude_creators', creators), *tags]) == ['내 것']
