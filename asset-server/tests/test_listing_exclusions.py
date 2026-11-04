# asset-server/tests/test_listing_exclusions.py

"""
보는 사람이 막은 제작자와 태그(app/exclusions.py, #988)를 검증한다. 실제 DB(asset_test)에서 돈다.

  - 캐릭터와 세계관의 공개 목록, 검색, 랭킹, 배너에서 막은 제작자의 것과 막은 태그가 하나라도 붙은 것을 뺀다
  - 태그는 마지막 판의 것을 본다. 제작자는 쉼표로 잇고(exclude_creators), 태그는 이름을 되풀이한다(exclude_tag)
  - 소개 하나를 여는 주소는 그대로 열린다
  - 제작자 100명, 태그 30개까지다. 넘거나 공개 ID 가 아니면 422 다
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.exclusions import MAX_EXCLUDED_CREATORS, MAX_EXCLUDED_TAGS
from app.main import API_PREFIX
from app.stats.models import WorkKind
from tests import test_characters_api as character_tests
from tests.test_characters_api import OPERATOR, make_public
from tests.test_rankings import ranked, seed
from tests.test_world_listings import published
from tests.worlds import OTHER, OWNER, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

operator = character_tests.operator

CHARACTERS = f'{API_PREFIX}/listings/characters'
WORLDS = f'{API_PREFIX}/listings/worlds'
BANNERS = f'{API_PREFIX}/banners'
ADMIN_BANNERS = f'{API_PREFIX}/admin/banners'


async def names(client: AsyncClient, url: str, params: dict | list) -> list[str]:
    response = await client.get(url, params=params)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [item['name'] for item in response.json()['items']]


async def test_characters_drop_blocked_tags_and_creators(client: AsyncClient, operator: dict):
    await make_public(client, operator, name='공포', tags=['공포'])
    await make_public(client, operator, name='일상', tags=['일상', '가,나'])

    assert await names(client, CHARACTERS, {'exclude_tag': '공포'}) == ['일상']
    assert await names(client, CHARACTERS, [('exclude_tag', '가,나')]) == ['공포']
    assert await names(client, CHARACTERS, {'exclude_creators': f'{uuid.uuid4()},{OPERATOR}'}) == []
    assert await names(client, CHARACTERS, {'q': '#일상', 'exclude_tag': '없음'}) == ['일상']


async def test_worlds_drop_blocked_creators(client: AsyncClient, signing_key: SigningKey):
    await published(client, bearer(signing_key, OWNER), name='내 여름')
    theirs = await published(client, bearer(signing_key, OTHER), name='남의 여름', tags=['공포'])

    assert await names(client, WORLDS, {'exclude_creators': str(OWNER)}) == ['남의 여름']
    assert await names(client, WORLDS, {'exclude_tag': '공포'}) == ['내 여름']
    detail = await client.get(f'{WORLDS}/{theirs["id"]}', params={'exclude_tag': '공포'})
    assert detail.status_code == status.HTTP_200_OK


async def test_rankings_and_banners_drop_them(client: AsyncClient, session: AsyncSession, operator: dict):
    busy = await make_public(client, operator, name='바쁜', tags=['공포'])
    calm = await make_public(client, operator, name='조용한')
    await seed(session, WorkKind.CHARACTER, (busy['id'], 5, 5), (calm['id'], 1, 1))
    for character in (busy, calm):
        response = await client.post(
            ADMIN_BANNERS, json={'kind': 'character', 'target_id': character['id']}, headers=operator
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text

    assert await ranked(client, 'characters', exclude_tag='공포') == [(1, '조용한', 1)]
    assert await ranked(client, 'characters', exclude_creators=str(OPERATOR)) == []
    banners = await client.get(BANNERS, params={'exclude_tag': '공포'})
    assert [item['character']['name'] for item in banners.json()['items']] == ['조용한']


@pytest.mark.parametrize(
    'params',
    [
        {'exclude_creators': 'not-a-uuid'},
        {'exclude_creators': ','.join(str(uuid.uuid4()) for _ in range(MAX_EXCLUDED_CREATORS + 1))},
        [('exclude_tag', f'태그{index}') for index in range(MAX_EXCLUDED_TAGS + 1)],
        {'exclude_tag': 'ㄱ' * 21},
    ],
)
async def test_rejects_bad_exclusions(client: AsyncClient, params: dict | list):
    for url in (CHARACTERS, WORLDS, f'{API_PREFIX}/rankings/characters', BANNERS):
        response = await client.get(url, params=params)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, url
