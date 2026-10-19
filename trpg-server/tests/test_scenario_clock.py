# trpg-server/tests/test_scenario_clock.py

"""
시나리오의 시계(달력 1단계, 판의 형식 24)를 검증한다.

시계는 테이블이 시작할 때의 시각(며칠째, 몇 시)과 라운드 하나에 흐르는 기본 시간(분)이다.
  - 만들고 고치기: 안 보내면 1일째 8시, 10분이다. 셋을 함께 보내고, 보낸 것으로 통째로 바꾼다. 범위 밖은 422 다.
  - 판: 게시하면 판에 굳는다. 시계가 없던 옛 판(형식 23)은 기본값으로 읽는다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_23
from tests import test_versions_api as versions
from tests.narration_model import with_model
from tests.test_scenarios_api import SCENARIOS_URL, create
from tests.test_versions_api import create_ready_scenario, publish

pytestmark = pytest.mark.usefixtures('clean_tables')

# 판의 테스트의 픽스처를 그대로 쓴다. 내 토큰이 실린 머리말
my_headers = versions.my_headers

DEFAULT = {'start_day': 1, 'start_hour': 8, 'round_minutes': 10}
NIGHT_MARCH = {'start_day': 3, 'start_hour': 22, 'round_minutes': 60}


# --- 만들고 고치기 ---


async def test_a_scenario_starts_on_the_first_morning_by_default(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers)

    assert scenario['clock'] == DEFAULT


async def test_the_clock_is_set_and_replaced_as_a_whole(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create(client, SCENARIOS_URL, my_headers, clock=NIGHT_MARCH)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    changed = await client.patch(url, json={'clock': DEFAULT}, headers=my_headers)
    untouched = await client.patch(url, json={'title': '다른 이름'}, headers=my_headers)

    assert scenario['clock'] == NIGHT_MARCH
    assert changed.json()['clock'] == DEFAULT
    assert untouched.json()['clock'] == DEFAULT


@pytest.mark.parametrize(
    'clock',
    [
        {**DEFAULT, 'start_day': 0},
        {**DEFAULT, 'start_day': 1000},
        {**DEFAULT, 'start_hour': -1},
        {**DEFAULT, 'start_hour': 24},
        {**DEFAULT, 'round_minutes': 0},
        {**DEFAULT, 'round_minutes': 7 * 24 * 60 + 1},
        {'start_day': 1, 'start_hour': 8},
        {**DEFAULT, 'minute': 30},
    ],
    ids=['day-zero', 'day-too-late', 'hour-negative', 'hour-24', 'no-time', 'over-a-week', 'missing', 'unknown-field'],
)
async def test_rejects_a_bad_clock(client: AsyncClient, my_headers: dict[str, str], clock: dict):
    response = await client.post(
        SCENARIOS_URL, json=with_model({'title': '시나리오', 'clock': clock}), headers=my_headers
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 판 ---


async def test_the_clock_is_frozen_into_the_version(client: AsyncClient, my_headers: dict[str, str]):
    scenario = await create_ready_scenario(client, my_headers, clock=NIGHT_MARCH)

    version = await publish(client, my_headers, scenario)

    assert version['snapshot']['format'] == SNAPSHOT_FORMAT >= 24
    assert version['snapshot']['clock'] == NIGHT_MARCH


def test_an_old_version_without_a_clock_reads_as_the_default():
    old = {'format': 23, 'title': '옛 판'}

    upgraded = upgrade_from_23(old)

    assert upgraded['clock'] == DEFAULT
    assert upgraded['format'] == 24
    # 받은 문서는 고치지 않는다
    assert 'clock' not in old
    # 형식 23 의 판을 읽으면 이 함수를 거친다
    assert UPGRADES[23] is upgrade_from_23
