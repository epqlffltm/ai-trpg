# trpg-server/tests/test_travel_time.py

"""
길에 걸리는 시간(달력 2단계, 판 형식 26)을 검증한다.

넷을 본다.
  - 판: 길에 한 칸 가는 시간(travel_minutes)을 적는다. 1분부터 일주일까지다. 옛 판은 비어 있는 것으로 읽는다.
  - 흐르기: 그 길로 가면 다음 라운드가 열릴 때 적어도 그만큼 흐른다. 여럿이면 가장 긴 길을 따른다.
    방장이 더 길게 정한 걸음은 줄지 않는다. 시간을 적지 않은 길은 라운드의 걸음 안에서 간다(전과 같다).
  - 보이기: 결과, 이벤트, 테이블의 아는 맵에 그 시간이 실린다.
  - 서술: 가기의 줄에 걸린 시간이 붙고, [시각]의 흐르는 시간도 그만큼이다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_25
from app.rounds import move_lines
from app.rounds.narrator import TravelNote
from tests import test_table_map as map_tables
from tests.test_map_actions import going, outcome_of, play
from tests.test_table_clock import wait
from tests.test_table_items import ME, events_of, read_table, table_url
from tests.test_table_map import route, start_duo
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')

# 지도 테스트의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 장소 여섯이 든 로어북
me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore

HOUR = 60
WEEK = 7 * 24 * HOUR


def far_map(lore: dict) -> dict:
    """
    성문에서 시작한다. 성문-광장은 옆길(시간 없음), 성문-숲은 3시간, 성문-탑은 하룻길(12시간)이다.
    """
    return {
        'start_place': lore['gate']['id'],
        'routes': [
            route(lore['gate'], lore['square']),
            route(lore['gate'], lore['forest'], travel_minutes=3 * HOUR),
            route(lore['gate'], lore['tower'], travel_minutes=12 * HOUR),
        ],
    }


async def clock_of(client: AsyncClient, headers: dict, table: dict) -> dict:
    response = await client.get(table_url(table, '/clock'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def opened(client: AsyncClient, headers: dict, table: dict) -> list[dict]:
    """열린 라운드들의 이벤트 payload. 차례대로다."""
    return [event['payload'] for event in await events_of(client, headers, table, 'round_opened')]


# --- 판 ---


@pytest.mark.parametrize('minutes', [0, -1, WEEK + 1, '세 시간'])
async def test_rejects_a_bad_travel_time(client: AsyncClient, me: dict, friend: dict, lore: dict, minutes):
    body = {'title': '먼 길', 'start_place': lore['gate']['id']}
    body['routes'] = [route(lore['gate'], lore['forest'], travel_minutes=minutes)]

    response = await client.post(map_tables.SCENARIOS_URL, json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_an_old_version_reads_every_route_as_taking_no_time():
    old = {'format': 25, 'routes': [{'from_place': 'a', 'to_place': 'b'}]}

    upgraded = upgrade_from_25(old)

    assert upgraded['routes'] == [{'from_place': 'a', 'to_place': 'b', 'travel_minutes': None}]
    assert upgraded['format'] == 26
    assert 'travel_minutes' not in old['routes'][0]
    assert UPGRADES[25] is upgrade_from_25


# --- 흐르기 ---


async def test_a_long_road_makes_the_next_round_open_later(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore, **far_map(lore))

    await play(client, me, friend, table, narrated, mine=going(lore['forest']))

    # 1일째 8시에 열려 3시간 뒤인 11시에 다음 라운드가 열렸다
    first, second = await opened(client, me, table)
    assert second['passed_minutes'] == 3 * HOUR
    assert (second['clock']['day'], second['clock']['hour']) == (1, 11)
    # 늘린 걸음은 한 번 쓰고 판의 기본으로 돌아간다
    assert (await clock_of(client, me, table))['next_step_minutes'] == 10


async def test_the_longest_road_sets_the_pace(client: AsyncClient, me: dict, friend: dict, lore: dict, narrated):
    table = await start_duo(client, me, friend, lore, **far_map(lore))

    await play(client, me, friend, table, narrated, mine=going(lore['forest']), theirs=going(lore['tower']))

    _, second = await opened(client, me, table)
    assert second['passed_minutes'] == 12 * HOUR


async def test_one_on_the_road_stops_the_others_wait(client: AsyncClient, me: dict, friend: dict, lore: dict, narrated):
    table = await start_duo(client, me, friend, lore, **far_map(lore))

    await play(client, me, friend, table, narrated, mine=going(lore['tower']), theirs=wait(16 * HOUR))

    # 길을 간 사람이 있어 모두 기다린 것이 아니다. 기다림은 깨지고 길의 시간만 흐른다(app/rounds/waits.py)
    _, second = await opened(client, me, table)
    assert second['passed_minutes'] == 12 * HOUR


async def test_a_road_without_a_time_takes_only_the_round(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore, **far_map(lore))

    await play(client, me, friend, table, narrated, mine=going(lore['square']))

    _, second = await opened(client, me, table)
    assert second['passed_minutes'] == 10
    assert (await outcome_of(client, me, table, 1, ME))['move']['travel_minutes'] is None


async def test_a_move_that_fails_takes_no_time(client: AsyncClient, me: dict, friend: dict, lore: dict, narrated):
    table = await start_duo(client, me, friend, lore, **far_map(lore))
    # 받은 뒤에 방장이 광장으로 옮겼다. 광장에서 숲으로 가는 길은 없다
    declared = await client.put(
        table_url(table, '/rounds/current/declaration'),
        json={'content': '숲으로 간다.', 'action': going(lore['forest'])},
        headers=me,
    )
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await map_tables.move(client, me, table, ME, lore['square'])
    await play_friend_only(client, friend, table, narrated)

    result = (await outcome_of(client, me, table, 1, ME))['move']
    assert (result['moved'], result['travel_minutes']) == (False, None)
    _, second = await opened(client, me, table)
    assert second['passed_minutes'] == 10


async def play_friend_only(client: AsyncClient, friend: dict, table: dict, narrated) -> None:
    """친구만 글로 선언해 라운드를 닫는다(나는 이미 냈다)."""
    url = table_url(table, '/rounds/current/declaration')
    declared = await client.put(url, json={'content': '기다린다.'}, headers=friend)
    assert declared.status_code == status.HTTP_200_OK, declared.text
    await narrated()


# --- 보이기 ---


async def test_the_time_is_shown_in_the_result_the_event_and_the_map(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore, **far_map(lore))

    await play(client, me, friend, table, narrated, mine=going(lore['forest']))

    assert (await outcome_of(client, me, table, 1, ME))['move']['travel_minutes'] == 3 * HOUR
    (moved,) = await events_of(client, friend, table, 'character_moved')
    assert moved['payload']['travel_minutes'] == 3 * HOUR
    routes = (await read_table(client, friend, table))['map']['routes']
    assert [item['travel_minutes'] for item in routes] == [None, 3 * HOUR, 12 * HOUR]


async def test_a_host_move_takes_no_time(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore, **far_map(lore))

    # 방장이 옮기는 것은 이야기가 건너뛴 이동이다. 시간은 방장이 걸음으로 정한다
    await map_tables.move(client, me, table, ME, lore['tower'])

    (moved,) = await events_of(client, friend, table, 'character_moved')
    assert 'travel_minutes' not in moved['payload']
    assert (await clock_of(client, me, table))['next_step_minutes'] == 10


# --- 서술 ---


async def test_the_narrator_hears_how_long_the_road_took(
    client: AsyncClient, app, me: dict, friend: dict, lore: dict, narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start_duo(client, me, friend, lore, **far_map(lore))

    await play(client, me, friend, table, narrated, mine=going(lore['forest']))

    (request,) = narrator.requests
    mine = next(move for move in request.moves if move.character_name == '기사')
    assert mine.travel == TravelNote(from_place='성문', to_place='숲', moved=True, travel_minutes=3 * HOUR)
    assert request.clock.passes_minutes == 3 * HOUR


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (TravelNote('성문', '숲', True, travel_minutes=3 * HOUR), '(간 곳: 성문 → 숲, 3시간 걸림)'),
        (TravelNote('성문', '탑', True, travel_minutes=90), '(간 곳: 성문 → 탑, 1시간 30분 걸림)'),
        (TravelNote('성문', '광장', True), '(간 곳: 성문 → 광장)'),
    ],
)
def test_the_road_time_is_told_in_the_move_line(note: TravelNote, line: str):
    assert move_lines.describe_travel(note) == line
