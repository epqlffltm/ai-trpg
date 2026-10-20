# trpg-server/tests/test_listing_play_info.py

"""
공개된 시나리오 하나에서 테이블을 만들기 전에 고를 것들을 읽는 것(#428, GET /listings/{scenario_id})을 검증한다.

남의 시나리오는 판을 읽을 수 없어서, 테이블을 만들 때 고르는 스타팅의 순번, 캐릭터 방식, 서술 모델을
보고 고를 길이 없었다.
픽스처와 도우미는 tests/test_listings_api.py 의 것이다.

보는 것.
  - 하나를 볼 때 스타팅, 캐릭터 방식, 프리젠(이름, 설명, 숫자), 능력치의 이름, 추천 서술 모델이 실린다.
  - 공개 중인 판의 것이다. 그 뒤에 초안을 고치거나 새 판을 내도 공개를 바꾸기 전에는 그대로다.
  - 프리젠이 함께 받는 소지품과 GM 전용 글은 싣지 않는다. 목록에는 고를 것들을 싣지 않는다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from tests import test_listings_api as listing_tests
from tests.sheets import SHEET, make_sheet
from tests.test_listings_api import (
    LISTINGS_URL,
    SCENARIOS_URL,
    listing_url,
    make_public,
    publish_version,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

# 공개 정보 테스트의 픽스처를 그대로 쓴다. 나(제작자)와 다른 사용자
my_headers = listing_tests.my_headers
their_headers = listing_tests.their_headers

KNIGHT = {'name': '기사', 'description': '방패를 든 기사', 'sheet': make_sheet(str=16, max_hp=12)}
SECOND_OPENING = '두 번째 스타팅. 톨게이트의 차단기가 내려온다.'


async def public_detail(client: AsyncClient, headers: dict, scenario: dict) -> dict:
    response = await client.get(f'{LISTINGS_URL}/{scenario["id"]}', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_the_choices_for_a_new_table_are_shown(client: AsyncClient, my_headers: dict, their_headers: dict):
    scenario = await make_public(client, my_headers, pregens=[KNIGHT], character_modes=['pregen'], default_sheet=SHEET)

    public = await public_detail(client, their_headers, scenario)

    assert public['character_modes'] == ['pregen']
    assert public['pregens'] == [KNIGHT]
    assert [ability['key'] for ability in public['abilities']] == ['str', 'dex', 'con', 'int', 'wis', 'cha']


async def test_the_pregens_items_are_not_shown(client: AsyncClient, my_headers: dict, their_headers: dict):
    scenario = await make_public(client, my_headers, pregens=[KNIGHT])

    public = await public_detail(client, their_headers, scenario)

    assert set(public['pregens'][0]) == {'name', 'description', 'sheet'}


async def test_it_shows_the_listed_version_not_the_draft(client: AsyncClient, my_headers: dict, their_headers: dict):
    scenario = await make_public(client, my_headers)
    # 초안에 스타팅을 더하고 새 판을 냈지만, 공개는 1번 판 그대로다
    url = f'{SCENARIOS_URL}/{scenario["id"]}'
    draft = (await client.get(url, headers=my_headers)).json()
    patched = await client.patch(url, json={'openings': [*draft['openings'], SECOND_OPENING]}, headers=my_headers)
    assert patched.status_code == status.HTTP_200_OK, patched.text
    second = await publish_version(client, my_headers, scenario)

    before = await public_detail(client, their_headers, scenario)
    switched = await client.put(f'{listing_url(scenario)}/publication', json={'version': second}, headers=my_headers)
    assert switched.status_code == status.HTTP_200_OK, switched.text
    after = await public_detail(client, their_headers, scenario)

    assert SECOND_OPENING not in before['openings']
    assert after['openings'][-1] == SECOND_OPENING


async def test_the_list_carries_no_choices(client: AsyncClient, my_headers: dict, their_headers: dict):
    await make_public(client, my_headers, pregens=[KNIGHT])

    (item,) = (await client.get(LISTINGS_URL, headers=their_headers)).json()['items']

    assert not {'openings', 'character_modes', 'pregens', 'abilities', 'recommended_narration_model'} & set(item)
