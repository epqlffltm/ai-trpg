# trpg-server/tests/test_past_tables.py

"""
떠난 사람이 떠난 테이블의 기록을 읽는 것(#428, GET /tables/past, GET /tables/past/{id}/events)을 검증한다.

자리는 떠날 때 지워져서, 나간 사람과 내보내진 사람은 그 판의 기록을 더 읽지 못했다.
픽스처와 도우미는 tests/test_events_api.py 의 것이다. 크레딧이 모자라 빠지는 길은 tests/test_credit_waits.py 의 것이다.

보는 것.
  - 시작한 테이블에서 나가거나, 내보내지거나, 크레딧이 모자라 빠지면 목록에 남는다. 최근에 떠난 것부터다.
  - 떠났다는 이벤트까지만 읽는다. 떠난 뒤에 적힌 이벤트는 오지 않는다. 앉은 사람이 읽는 것과 앞부분이 같다.
  - 끝난 테이블에서 나가도 남는다.
  - 모집 중에 나간 사람, 앉은 적 없는 사람, 지금 앉아 있는 사람에게는 404 다.
"""

from datetime import timedelta

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.tables.models import DEFAULT_CREDIT_WAIT
from tests import test_credit_waits as credit_tests
from tests import test_events_api as event_tests
from tests.test_credit_waits import PAST, stall
from tests.test_events_api import FRIEND, TABLES_URL, join, open_table, read_events, start_duo, table_url, types
from tests.test_round_time_limit import clock_at

pytestmark = pytest.mark.usefixtures('clean_tables')

# 이벤트 테스트의 픽스처를 그대로 쓴다. 나(방장), 친구(떠나는 사람), 앉지 않는 사람
me = event_tests.me
friend = event_tests.friend
stranger = event_tests.stranger

PAST_URL = f'{TABLES_URL}/past'


def past_events_url(table: dict) -> str:
    return f'{PAST_URL}/{table["id"]}/events'


async def leave(client: AsyncClient, headers: dict, table: dict) -> None:
    response = await client.delete(table_url(table, '/members/me'), headers=headers)
    assert response.status_code == status.HTTP_204_NO_CONTENT, response.text


async def kick(client: AsyncClient, host: dict, table: dict) -> None:
    response = await client.delete(table_url(table, f'/members/{FRIEND}'), headers=host)
    assert response.status_code == status.HTTP_200_OK, response.text


async def move_on(client: AsyncClient, host: dict, table: dict) -> None:
    """남은 방장이 테이블을 이어 간다. 이벤트가 하나 더 적힌다(narration_style_changed)."""
    body = {'narration_style': 'literary'}
    response = await client.put(table_url(table, '/narration-style'), json=body, headers=host)
    assert response.status_code == status.HTTP_200_OK, response.text


async def past_tables(client: AsyncClient, headers: dict) -> dict:
    response = await client.get(PAST_URL, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def past_events(client: AsyncClient, headers: dict, table: dict, **params) -> dict:
    response = await client.get(past_events_url(table), params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def test_one_who_left_reads_up_to_leaving(client: AsyncClient, me: dict, friend: dict):
    table = await start_duo(client, me, friend)
    await leave(client, friend, table)
    await move_on(client, me, table)

    (listed,) = (await past_tables(client, friend))['items']
    page = await past_events(client, friend, table)
    everything = await read_events(client, me, table)

    assert listed['table_id'] == table['id']
    assert (listed['title'], listed['character_name'], listed['kind']) == (table['title'], '영애', 'left')
    assert listed['scenario_id'] == table['scenario_id']
    # 떠났다는 이벤트가 끝이다. 앉은 사람의 기록과 거기까지 같다. 그 뒤에 남은 사람이 한 일은 오지 않는다
    assert types(page['items'])[-1] == 'member_left'
    assert page['last_sequence'] == listed['last_sequence'] == page['items'][-1]['sequence']
    assert page['items'] == everything[: len(page['items'])]
    assert 'narration_style_changed' in types(everything)
    assert 'narration_style_changed' not in types(page['items'])


async def test_one_who_was_kicked_reads_up_to_the_kick(client: AsyncClient, me: dict, friend: dict):
    table = await start_duo(client, me, friend)
    await kick(client, me, table)
    await move_on(client, me, table)

    (listed,) = (await past_tables(client, friend))['items']
    page = await past_events(client, friend, table)

    assert listed['kind'] == 'kicked'
    assert types(page['items'])[-1] == 'member_kicked'
    assert page['last_sequence'] == page['items'][-1]['sequence']


async def test_the_reading_is_paged_and_stops_at_leaving(client: AsyncClient, me: dict, friend: dict):
    table = await start_duo(client, me, friend)
    await leave(client, friend, table)
    await move_on(client, me, table)
    last = (await past_events(client, friend, table))['last_sequence']

    first = await past_events(client, friend, table, limit=2)
    tail = await past_events(client, friend, table, after=last - 1)
    beyond = await past_events(client, friend, table, after=last)

    assert [event['sequence'] for event in first['items']] == [1, 2]
    # 쪽마다 끝 번호가 같다. 받은 것의 마지막이 이보다 작으면 더 읽는다
    assert first['last_sequence'] == beyond['last_sequence'] == last
    assert types(tail['items']) == ['member_left']
    assert beyond['items'] == []


async def test_leaving_an_ended_table_is_kept(client: AsyncClient, me: dict, friend: dict):
    table = await start_duo(client, me, friend)
    ended = await client.post(table_url(table, '/end'), headers=me)
    assert ended.status_code == status.HTTP_200_OK, ended.text

    await leave(client, friend, table)

    (listed,) = (await past_tables(client, friend))['items']
    assert listed['kind'] == 'left'
    assert types((await past_events(client, friend, table))['items'])[-1] == 'member_left'


async def test_the_most_recent_departure_comes_first(client: AsyncClient, me: dict, friend: dict):
    older = await start_duo(client, me, friend)
    await leave(client, friend, older)
    newer = await start_duo(client, me, friend)
    await leave(client, friend, newer)

    page = await past_tables(client, friend)

    assert [item['table_id'] for item in page['items']] == [newer['id'], older['id']]
    assert page['total'] == 2


async def test_leaving_before_the_start_leaves_nothing(client: AsyncClient, me: dict, friend: dict):
    table = await open_table(client, me)
    await join(client, friend, table)

    await leave(client, friend, table)

    assert await past_tables(client, friend) == {'items': [], 'total': 0}
    response = await client.get(past_events_url(table), headers=friend)
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_only_those_who_left_read_this_way(client: AsyncClient, me: dict, friend: dict, stranger: dict):
    table = await start_duo(client, me, friend)
    await leave(client, friend, table)

    # 앉은 적 없는 사람과 지금 앉아 있는 사람(앉은 사람의 길로 읽는다)
    for headers in (stranger, me):
        response = await client.get(past_events_url(table), headers=headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
    assert (await past_tables(client, me))['items'] == []
    unknown = await client.get(past_events_url({'id': event_tests.NO_SUCH_ID}), headers=friend)
    assert unknown.status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(PAST_URL)).status_code == status.HTTP_401_UNAUTHORIZED


# --- 크레딧이 모자라 빠지기 ---

# 크레딧 테스트의 픽스처. 사람은 위의 나와 친구와 같다(같은 id)
billing = credit_tests.billing
narrator = credit_tests.narrator


async def test_one_who_was_dropped_reads_up_to_the_drop(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, billing, narrator, narrated
):
    table, failed_at = await stall(client, app, me, friend, billing, narrated)

    await clock_at(app, failed_at + timedelta(seconds=DEFAULT_CREDIT_WAIT) + PAST).tick()
    await narrated()

    (listed,) = (await past_tables(client, friend))['items']
    page = await past_events(client, friend, table)
    everything = await read_events(client, me, table)
    assert listed['kind'] == 'dropped'
    assert types(page['items'])[-1] == 'member_dropped'
    # 빠진 뒤에 나머지로 다시 서술했다. 그 서술은 오지 않는다
    assert len(everything) > len(page['items'])
