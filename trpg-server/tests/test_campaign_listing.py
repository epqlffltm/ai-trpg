# trpg-server/tests/test_campaign_listing.py

"""
캠페인의 플레이를 찾는 API(#481 B, app/campaigns/listing.py)를 검증한다.

판: 두 편짜리 캠페인 추격전(tests/test_campaign_next.py 의 판). 나(방장)와 친구가 1편에 앉는다.

보는 것.
  - 내 플레이(GET /campaign-runs): 연 사람과 앉은 사람에게 보이고 남에게는 보이지 않는다.
    지금 편, 편의 수, 지금 편의 이름과 테이블을 싣는다. 다음 편을 열면 그 편으로 바뀐다.
    넘긴 것만 있어도 보인다. 한 쪽씩 읽는다.
  - 테이블의 플레이(GET /campaign-runs/of-table/{id}): 그 플레이의 사람에게는 플레이를,
    남과 캠페인이 아닌 테이블에는 null 을 준다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_campaign_next import episode_one_done, first_episode, next_episode
from tests.test_campaign_runs import RUNS_URL
from tests.test_lobby_api import FRIEND, ME, THIRD, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, THIRD)


async def my_runs(client: AsyncClient, headers: dict, **query) -> dict:
    response = await client.get(RUNS_URL, params=query, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def run_of(client: AsyncClient, headers: dict, table_id: str):
    response = await client.get(f'{RUNS_URL}/of-table/{table_id}', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 내 플레이 ---


async def test_the_people_of_the_run_see_it(client: AsyncClient, me: dict, friend: dict, stranger: dict):
    run, table, _, _ = await first_episode(client, me, friend)

    mine = await my_runs(client, me)
    theirs = await my_runs(client, friend)

    assert mine['total'] == 1
    item = mine['items'][0]
    assert (item['id'], item['title'], item['position'], item['episode_count']) == (run['id'], '추격전', 0, 2)
    assert (item['episode_title'], item['table_id'], item['status']) == ('1편', table['id'], 'playing')
    assert [one['id'] for one in theirs['items']] == [run['id']]
    assert await my_runs(client, stranger) == {'items': [], 'total': 0}


async def test_the_list_follows_the_next_episode(client: AsyncClient, me: dict, friend: dict, session: AsyncSession):
    run, _ = await episode_one_done(client, me, friend, session)
    opened = (await next_episode(client, me, run)).json()

    # 친구는 2편에 아직 앉지 않았고 1편의 자리도 없다(내보내졌다). 그래도 1편에서 넘긴 것이 있어 보인다
    await session.execute(text('DELETE FROM table_members WHERE user_id = :user_id'), {'user_id': FRIEND})
    await session.commit()

    item = (await my_runs(client, me))['items'][0]
    friends = await my_runs(client, friend)

    assert (item['position'], item['episode_title'], item['table_id']) == (1, '2편', opened['episodes'][1]['table_id'])
    assert friends['total'] == 1


async def test_the_list_is_paged(client: AsyncClient, me: dict, friend: dict):
    await first_episode(client, me, friend)

    page = await my_runs(client, me, limit=1, offset=1)

    assert page == {'items': [], 'total': 1}


# --- 테이블의 플레이 ---


async def test_the_run_of_a_table(client: AsyncClient, me: dict, friend: dict, stranger: dict):
    run, table, _, _ = await first_episode(client, me, friend)

    found = await run_of(client, friend, table['id'])

    assert (found['id'], found['position'], found['episodes'][0]['table_id']) == (run['id'], 0, table['id'])
    # 남에게는 있다는 것을 드러내지 않고, 캠페인의 테이블이 아니면 null 이다
    assert await run_of(client, stranger, table['id']) is None
    assert await run_of(client, me, str(uuid.uuid4())) is None
