# trpg-server/tests/test_table_scenario.py

"""
테이블이 자기 시나리오를 알려 주는 것(#428, game_tables.scenario_id)을 검증한다.

화면은 테이블에서 시나리오 소개(GET /listings/{scenario_id})로 돌아가야 한다. 그 값이 테이블의 응답에 없었다.
픽스처와 도우미는 tests/test_lobby_api.py 의 것이다.

보는 것.
  - 테이블을 열면 그 시나리오의 id 가 테이블에 적힌다.
  - 응답의 세 곳(테이블 하나, 내 테이블 목록, 로비)에 같은 값이 실린다.
  - DB 는 시나리오를 비운 테이블과 없는 시나리오를 가리키는 테이블을 받지 않는다.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.tables.models import GameTable
from tests import test_lobby_api as lobby_tests
from tests.test_lobby_api import TABLES_URL, lobby, open_table, publish_scenario
from tests.test_tables_api import make_table

pytestmark = pytest.mark.usefixtures('clean_tables')

# 로비 테스트의 픽스처를 그대로 쓴다. 나(방장)와 로비에서 보는 친구
me = lobby_tests.me
friend = lobby_tests.friend


async def stored_scenario(session: AsyncSession, table: dict) -> uuid.UUID:
    query = select(GameTable.scenario_id).where(GameTable.id == uuid.UUID(table['id']))
    return await session.scalar(query.execution_options(populate_existing=True))


async def test_a_table_knows_its_scenario(client: AsyncClient, me: dict, session: AsyncSession):
    scenario = await publish_scenario(client, me)

    table = await open_table(client, me, scenario)

    assert table['scenario_id'] == scenario['id']
    assert str(await stored_scenario(session, table)) == scenario['id']


async def test_every_table_response_carries_the_scenario(client: AsyncClient, me: dict, friend: dict):
    scenario = await publish_scenario(client, me)
    table = await open_table(client, me, scenario)

    detail = (await client.get(f'{TABLES_URL}/{table["id"]}', headers=me)).json()
    (mine,) = (await client.get(TABLES_URL, headers=me)).json()['items']
    (listed,) = (await lobby(client, friend))['items']

    assert detail['scenario_id'] == mine['scenario_id'] == listed['scenario_id'] == scenario['id']


async def test_the_database_requires_a_known_scenario(session: AsyncSession):
    table = await make_table(session)
    await session.commit()

    table.scenario_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_requires_a_scenario(session: AsyncSession):
    await make_table(session, scenario_id=None)

    with pytest.raises(IntegrityError):
        await session.commit()
