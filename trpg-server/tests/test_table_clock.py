# trpg-server/tests/test_table_clock.py

"""
테이블의 시계(달력 2단계)를 검증한다.

다섯을 본다.
  - 셈: 1일째 0시부터 흐른 분을 며칠째, 몇 시, 몇 분, 하루의 어느 때로 푼다. 자정을 넘으면 날이 바뀐다.
  - 달기: 테이블을 만들면 판의 시작 시각을 가리키는 시계가 달린다. 첫 라운드는 그 시각에 열린다.
  - 흐르기: 새 라운드가 열릴 때 판의 기본 시간만큼 흐른다. 열린 이벤트에 그때의 시각과 흐른 시간이 있다.
  - 기다리기(#367, app/rounds/waits.py): 모두 기다리면 가장 짧게 부른 시간만큼 건너뛴다. 한 번 쓰고 판의 기본으로.
    한 사람이라도 다른 일을 하거나 내지 않으면 흐르지 않는다. 1분에서 일주일까지.
  - 막기: 사람(방장)이 흐를 시간을 정하는 길은 없다. 앉지 않은 사람에게는 테이블이 없다.
기다리는 중에 맞으면 깨지는 것은 tests/test_waits.py 가 본다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.calendar.clock import ClockTime, TimeOfDay, read_time, start_minutes, time_of_day
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.test_rounds_api import (
    FRIEND,
    ME,
    MY_ACTION,
    NO_SUCH_ID,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    STRANGER,
    TABLES_URL,
    bearer,
    declare,
    start_duo,
)
from tests.test_table_items import events_of

pytestmark = pytest.mark.usefixtures('clean_tables')

# 3일째 밤 10시에 시작하고, 라운드 하나에 3시간이 흐르는 판
NIGHT_MARCH = {'start_day': 3, 'start_hour': 22, 'round_minutes': 180}
WEEK = 7 * 24 * 60


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장의 머리말. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """함께 앉는 사람의 머리말. 캐릭터는 '영애'다."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def clock_url(table: dict, path: str = '') -> str:
    """테이블의 시계 주소."""
    return f'{TABLES_URL}/{table["id"]}/clock{path}'


async def open_solo(client: AsyncClient, me: dict[str, str], clock: dict | None = None) -> dict:
    """시계를 정한 판으로 나 혼자 앉은 테이블을 연다. 시작하지 않았다. clock 이 없으면 판의 기본 시계다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {
        'title': '야간 행군',
        'rulebook_id': rulebook.json()['id'],
        'openings': ['출발한다.'],
        'default_sheet': SHEET,
    }
    if clock is not None:
        body['clock'] = clock
    scenario = (await client.post(SCENARIOS_URL, json=with_model(body), headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1}
    table = await client.post(TABLES_URL, json=body, headers=me)
    assert table.status_code == status.HTTP_201_CREATED, table.text
    await client.put(f'{TABLES_URL}/{table.json()["id"]}/character', json={'name': '엘프'}, headers=me)
    return table.json()


async def start_solo(client: AsyncClient, me: dict[str, str], clock: dict | None = None) -> dict:
    """시계를 정한 판으로 나 혼자 앉은 테이블을 시작한다."""
    table = await open_solo(client, me, clock)
    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def next_round(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """혼자 선언해 라운드를 닫고, 서술이 끝나 다음 라운드가 열릴 때까지 기다린다."""
    await declare(client, me, table, MY_ACTION)
    await narrated()


async def read_clock(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """테이블의 시계를 읽는다."""
    response = await client.get(clock_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def wait(minutes: int) -> dict:
    """minutes 분을 기다리는 행동."""
    return {'kind': 'wait', 'minutes': minutes}


async def declare_wait(client: AsyncClient, headers: dict[str, str], table: dict, minutes: int):
    """기다리기를 선언하는 요청. 응답을 그대로 돌려준다."""
    body = {'content': '기다린다.', 'action': wait(minutes)}
    return await client.put(f'{TABLES_URL}/{table["id"]}/rounds/current/declaration', json=body, headers=headers)


async def wait_round(client: AsyncClient, headers: dict[str, str], table: dict, minutes: int, narrated) -> None:
    """혼자 기다리기를 선언해 라운드를 닫고, 다음 라운드가 열릴 때까지 기다린다."""
    response = await declare_wait(client, headers, table, minutes)
    assert response.status_code == status.HTTP_200_OK, response.text
    await narrated()


async def wait_outcome(client: AsyncClient, headers: dict[str, str], table: dict, number: int) -> dict:
    """그 라운드에서 나의(ME) 기다리기의 결과."""
    response = await client.get(f'{TABLES_URL}/{table["id"]}/rounds/{number}', headers=headers)
    mine = next(item for item in response.json()['declarations'] if item['user_id'] == str(ME))
    return mine['outcome']['wait']


def when(clock: dict) -> tuple[int, int, int, str]:
    """시계나 이벤트의 시각을 (며칠째, 시, 분, 하루의 어느 때)로."""
    return clock['day'], clock['hour'], clock['minute'], clock['time_of_day']


# --- 셈 ---


def test_the_start_is_counted_from_the_first_midnight():
    assert start_minutes(1, 0) == 0
    assert start_minutes(1, 8) == 8 * 60
    assert start_minutes(3, 22) == (2 * 24 + 22) * 60


@pytest.mark.parametrize(
    ('minutes', 'expected'),
    [
        (0, ClockTime(day=1, hour=0, minute=0, time_of_day=TimeOfDay.NIGHT)),
        (8 * 60 + 30, ClockTime(day=1, hour=8, minute=30, time_of_day=TimeOfDay.MORNING)),
        (24 * 60 - 1, ClockTime(day=1, hour=23, minute=59, time_of_day=TimeOfDay.NIGHT)),
        # 자정을 넘으면 날이 바뀐다
        (24 * 60, ClockTime(day=2, hour=0, minute=0, time_of_day=TimeOfDay.NIGHT)),
        # 시작은 999일째까지지만, 흐르는 시계는 그 뒤로도 간다
        (start_minutes(999, 23) + 120, ClockTime(day=1000, hour=1, minute=0, time_of_day=TimeOfDay.NIGHT)),
    ],
)
def test_minutes_are_read_as_day_hour_and_minute(minutes: int, expected: ClockTime):
    assert read_time(minutes) == expected


@pytest.mark.parametrize(
    ('hour', 'part'),
    [
        (0, TimeOfDay.NIGHT),
        (3, TimeOfDay.NIGHT),
        (4, TimeOfDay.DAWN),
        (6, TimeOfDay.DAWN),
        (7, TimeOfDay.MORNING),
        (10, TimeOfDay.MORNING),
        (11, TimeOfDay.DAY),
        (16, TimeOfDay.DAY),
        (17, TimeOfDay.EVENING),
        (20, TimeOfDay.EVENING),
        (21, TimeOfDay.NIGHT),
        (23, TimeOfDay.NIGHT),
    ],
)
def test_each_hour_belongs_to_a_part_of_the_day(hour: int, part: TimeOfDay):
    assert time_of_day(hour) == part


# --- 달기 ---


async def test_a_new_table_shows_the_start_of_its_version(client: AsyncClient, me: dict):
    table = await open_solo(client, me, NIGHT_MARCH)

    clock = await read_clock(client, me, table)

    assert when(clock) == (3, 22, 0, 'night')
    assert (clock['next_step_minutes'], clock['default_step_minutes'], clock['step_changed']) == (180, 180, False)


async def test_a_version_without_a_set_clock_starts_on_the_first_morning(client: AsyncClient, me: dict):
    table = await open_solo(client, me)

    clock = await read_clock(client, me, table)

    assert when(clock) == (1, 8, 0, 'morning')
    assert clock['next_step_minutes'] == 10


async def test_the_first_round_opens_at_the_start(client: AsyncClient, me: dict):
    table = await start_solo(client, me, NIGHT_MARCH)

    [opened] = await events_of(client, me, table, 'round_opened')

    assert when(opened['payload']['clock']) == (3, 22, 0, 'night')
    assert opened['payload']['passed_minutes'] == 0
    assert when(await read_clock(client, me, table)) == (3, 22, 0, 'night')


# --- 흐르기 ---


async def test_time_passes_when_the_next_round_opens(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me, NIGHT_MARCH)

    await next_round(client, me, table, narrated)
    await next_round(client, me, table, narrated)

    first, second, third = await events_of(client, me, table, 'round_opened')
    # 3시간씩 흐른다. 자정을 넘으면 날이 바뀌고, 새벽이 된다
    assert [event['payload']['passed_minutes'] for event in (first, second, third)] == [0, 180, 180]
    assert when(second['payload']['clock']) == (4, 1, 0, 'night')
    assert when(third['payload']['clock']) == (4, 4, 0, 'dawn')
    assert when(await read_clock(client, me, table)) == (4, 4, 0, 'dawn')


# --- 기다리기 ---


async def test_waiting_skips_the_time_once(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me, NIGHT_MARCH)

    await wait_round(client, me, table, 8 * 60, narrated)
    after = await read_clock(client, me, table)
    await next_round(client, me, table, narrated)

    # 하룻밤 기다렸다. 늘린 걸음은 한 번 쓰고 판의 기본으로 돌아간다
    _, waited, then = await events_of(client, me, table, 'round_opened')
    assert (waited['payload']['passed_minutes'], when(waited['payload']['clock'])) == (480, (4, 6, 0, 'dawn'))
    assert (after['next_step_minutes'], after['step_changed']) == (180, False)
    assert (then['payload']['passed_minutes'], when(then['payload']['clock'])) == (180, (4, 9, 0, 'morning'))
    assert await wait_outcome(client, me, table, 1) == {'minutes': 480, 'waited': True, 'reason': None}


async def test_a_wait_shorter_than_a_round_does_not_shorten_it(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me, NIGHT_MARCH)

    await wait_round(client, me, table, 30, narrated)

    # 판의 기본(3시간)보다 짧게 기다려도 라운드는 판의 기본만큼 흐른다
    _, opened = await events_of(client, me, table, 'round_opened')
    assert opened['payload']['passed_minutes'] == 180


async def test_the_shortest_wait_is_kept(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)

    for headers, minutes in ((me, 3 * 24 * 60), (friend, 24 * 60)):
        response = await declare_wait(client, headers, table, minutes)
        assert response.status_code == status.HTTP_200_OK, response.text
    await narrated()

    # 사흘을 부른 사람도 하루는 기다리겠다고 한 것이다
    _, opened = await events_of(client, me, table, 'round_opened')
    assert opened['payload']['passed_minutes'] == 24 * 60


async def test_one_who_does_something_else_stops_the_wait(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)

    await declare_wait(client, me, table, 3 * 24 * 60)
    await declare(client, friend, table, MY_ACTION)
    await narrated()

    # 방장 혼자 사흘을 흘려 다른 사람의 기한을 넘기지 못한다
    _, opened = await events_of(client, me, table, 'round_opened')
    assert opened['payload']['passed_minutes'] == 10
    assert await wait_outcome(client, me, table, 1) == {'minutes': 3 * 24 * 60, 'waited': False, 'reason': 'not_all'}


async def test_one_who_did_not_declare_stops_the_wait(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)

    await declare_wait(client, me, table, 8 * 60)
    closed = await client.post(f'{TABLES_URL}/{table["id"]}/rounds/current/close', headers=me)
    assert closed.status_code == status.HTTP_202_ACCEPTED, closed.text
    await narrated()

    _, opened = await events_of(client, me, table, 'round_opened')
    assert opened['payload']['passed_minutes'] == 10
    assert (await wait_outcome(client, me, table, 1))['reason'] == 'not_all'


@pytest.mark.parametrize('minutes', [0, -1, WEEK + 1, '사흘'])
async def test_rejects_a_bad_wait(client: AsyncClient, me: dict, minutes):
    table = await start_solo(client, me)

    response = await declare_wait(client, me, table, minutes)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_week_is_the_longest_wait(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me)

    await wait_round(client, me, table, WEEK, narrated)

    _, opened = await events_of(client, me, table, 'round_opened')
    assert opened['payload']['passed_minutes'] == WEEK


# --- 막기 ---


@pytest.mark.parametrize('body', [{'minutes': 480}, {'minutes': None}])
async def test_no_one_sets_the_step(client: AsyncClient, me: dict, body: dict):
    table = await start_solo(client, me, NIGHT_MARCH)

    response = await client.put(clock_url(table, '/step'), json=body, headers=me)

    # 방장이 흐를 시간을 정하던 길(#367)은 없다. 시간을 건너뛰려면 모두 기다린다
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert (await read_clock(client, me, table))['step_changed'] is False


async def test_only_those_seated_see_the_clock(client: AsyncClient, me: dict, stranger: dict):
    table = await open_solo(client, me)

    seen = await client.get(clock_url(table), headers=stranger)
    missing = await client.get(f'{TABLES_URL}/{NO_SUCH_ID}/clock', headers=me)

    assert seen.status_code == missing.status_code == status.HTTP_404_NOT_FOUND


async def test_the_clock_requires_login(client: AsyncClient):
    response = await client.get(f'{TABLES_URL}/{NO_SUCH_ID}/clock')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
