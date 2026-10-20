# trpg-server/tests/test_table_detail_clock.py

"""
테이블 하나의 응답(TableDetail)에 시계가 실리는 것(#428, B7)을 검증한다.

지금 시각은 GET /tables/{id}/clock 으로만 읽었다. 상태 패널을 그리려면 테이블과 시계를 두 번 읽어야 했다.
픽스처와 도우미는 tests/test_table_clock.py 의 것이다.

보는 것.
  - 테이블을 만든 응답과 테이블 하나를 읽은 응답에 시계가 있고, GET .../clock 과 같다(시작 전에는 판의 시작 시각).
  - 방장이 다음 라운드에 흐를 시간을 정하면 테이블의 응답에도 보인다.
  - 라운드가 열려 시간이 흐르면 테이블의 응답의 시각도 흐른다.
  - 내 테이블 목록과 로비의 한 줄(TableSummary)에는 싣지 않는다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from tests import test_table_clock as clock_tests
from tests.test_rounds_api import TABLES_URL
from tests.test_table_clock import NIGHT_MARCH, next_round, open_solo, read_clock, set_step, start_solo, when

pytestmark = pytest.mark.usefixtures('clean_tables')

# 시계 테스트의 픽스처를 그대로 쓴다
me = clock_tests.me


async def read_table(client: AsyncClient, headers: dict, table: dict) -> dict:
    response = await client.get(f'{TABLES_URL}/{table["id"]}', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_the_table_carries_its_clock_from_the_start(client: AsyncClient, me: dict):
    created = await open_solo(client, me, NIGHT_MARCH)

    detail = await read_table(client, me, created)

    assert when(created['clock']) == (3, 22, 0, 'night')
    assert detail['clock'] == created['clock'] == await read_clock(client, me, created)


async def test_the_host_s_step_shows_on_the_table(client: AsyncClient, me: dict):
    table = await start_solo(client, me, NIGHT_MARCH)

    await set_step(client, me, table, 8 * 60)
    detail = await read_table(client, me, table)

    assert (detail['clock']['next_step_minutes'], detail['clock']['step_changed']) == (480, True)
    assert detail['clock']['default_step_minutes'] == 180
    assert detail['clock'] == await read_clock(client, me, table)


async def test_the_table_s_clock_moves_with_the_rounds(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me, NIGHT_MARCH)

    await next_round(client, me, table, narrated)
    detail = await read_table(client, me, table)

    assert when(detail['clock']) == (4, 1, 0, 'night')
    assert detail['clock'] == await read_clock(client, me, table)


async def test_the_one_line_summaries_leave_the_clock_out(client: AsyncClient, me: dict):
    await open_solo(client, me, NIGHT_MARCH)

    (mine,) = (await client.get(TABLES_URL, headers=me)).json()['items']

    assert 'clock' not in mine
