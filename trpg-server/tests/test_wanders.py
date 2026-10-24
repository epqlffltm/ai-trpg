# trpg-server/tests/test_wanders.py

"""
무작위 조우 표(#283)를 시나리오에 적고 판에 굳히는 것을 검증한다. 굴리는 것은 테이블의 일이라 여기서 보지 않는다.

맵과 몬스터는 tests/test_encounters.py 의 것이다. 수로 입구에서 시작해 깊은 수로로 가는 길이 있다.
쥐와 해골은 시트가 있고, 골렘은 도감에만 있다. 수문지기는 인물이다.

보는 것.
  - 시나리오: 표를 적고 읽고 고친다. 확률과 몬스터가 어긋나거나, 같은 장소의 표가 같은 때를 쓰거나,
    한 표에 같은 몬스터나 같은 때가 두 번이면 422 다.
  - 게시: 표의 장소는 맵의 장소여야 하고(wander_off_map, 기본 표는 맵이 있어야), 몬스터는 시트가 있어야 한다
    (wander_monster_missing).
  - 판: 형식 57 에 실린다. 옛 판은 표 없이 읽는다. 판의 계약이 엉뚱한 표를 거부한다.
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError

from app.assets.models import ENCOUNTER_MAX_COUNT, SCENARIO_MAX_WANDERS, WANDER_MAX_MONSTERS, WANDER_MAX_WEIGHT
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, Snapshot, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_56
from tests import test_encounters as encounters
from tests.narration_model import with_model

pytestmark = pytest.mark.usefixtures('clean_tables')

me = encounters.me
world = encounters.world
SCENARIOS_URL = encounters.SCENARIOS_URL
NO_SUCH_ID = encounters.NO_SUCH_ID


def line(monster: dict, count: int = 1, weight: int = 1, surprise: str = 'none') -> dict:
    return {'monster_id': monster['id'], 'count': count, 'weight': weight, 'surprise': surprise}


def table(place: dict | None, chance: int, *lines: dict, times: list[str] | None = None) -> dict:
    return {
        'place_id': None if place is None else place['id'],
        'times': times or [],
        'chance': chance,
        'monsters': list(lines),
    }


def the_wanders(world: dict) -> list[dict]:
    """깊은 수로의 밤의 표, 깊은 수로의 낮의 표, 판의 기본 표, 수로 입구의 안전한 표."""
    return [
        table(world['deep'], 40, line(world['rat'], 3, 2), line(world['skeleton'], 1, 1, 'monsters'), times=['night']),
        table(world['deep'], 10, line(world['rat']), times=['dawn', 'morning', 'day', 'evening']),
        table(None, 20, line(world['rat'], 2)),
        table(world['gate'], 0),
    ]


async def create(client: AsyncClient, me: dict, world: dict, **fields) -> dict:
    return await encounters.create_scenario(client, me, **encounters.with_map(world, **fields))


async def try_create(client: AsyncClient, me: dict, wanders: list[dict]):
    return await client.post(SCENARIOS_URL, json=with_model({'title': '지하 수로', 'wanders': wanders}), headers=me)


# --- 시나리오 ---


async def test_wanders_are_saved_and_read_back(client: AsyncClient, me: dict, world: dict):
    scenario = await create(client, me, world, wanders=the_wanders(world))

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert read['wanders'] == the_wanders(world)


async def test_a_scenario_starts_without_wanders(client: AsyncClient, me: dict):
    scenario = await encounters.create_scenario(client, me)

    assert scenario['wanders'] == []


async def test_left_out_fields_take_their_defaults(client: AsyncClient, me: dict, world: dict):
    wanders = [{'chance': 5, 'monsters': [{'monster_id': world['rat']['id']}]}]

    scenario = await create(client, me, world, wanders=wanders)

    assert scenario['wanders'] == [table(None, 5, line(world['rat']))]


def misshaped(world: dict) -> dict[str, list[dict]]:
    """모양이 틀린 표들. 하나하나가 422 다."""
    rat = line(world['rat'])
    return {
        'chance-without-monsters': [table(world['deep'], 10)],
        'monsters-without-chance': [table(world['deep'], 0, rat)],
        'chance-over-100': [table(world['deep'], 101, rat)],
        'chance-below-0': [table(world['deep'], -1, rat)],
        'count-0': [table(world['deep'], 10, line(world['rat'], 0))],
        'count-over-max': [table(world['deep'], 10, line(world['rat'], ENCOUNTER_MAX_COUNT + 1))],
        'weight-0': [table(world['deep'], 10, line(world['rat'], 1, 0))],
        'weight-over-max': [table(world['deep'], 10, line(world['rat'], 1, WANDER_MAX_WEIGHT + 1))],
        'same-monster-twice': [table(world['deep'], 10, rat, line(world['rat'], 2))],
        'too-many-monsters': [
            table(
                world['deep'],
                10,
                *(
                    {**rat, 'monster_id': f'{n:08d}-0000-4000-8000-000000000000'}
                    for n in range(WANDER_MAX_MONSTERS + 1)
                ),
            )
        ],
        'same-time-twice': [table(world['deep'], 10, rat, times=['night', 'night'])],
        'unknown-time': [table(world['deep'], 10, rat, times=['midnight'])],
        'unknown-field': [{**table(world['deep'], 10, rat), 'noise': 1}],
        'overlapping-times': [
            table(world['deep'], 10, rat, times=['night', 'dawn']),
            table(world['deep'], 10, rat, times=['dawn']),
        ],
        'always-and-a-time': [table(world['deep'], 10, rat), table(world['deep'], 10, rat, times=['night'])],
        'two-defaults': [table(None, 10, rat), table(None, 20, rat)],
        'too-many-tables': [
            table({'id': f'{n:08d}-0000-4000-8000-000000000000'}, 0) for n in range(SCENARIO_MAX_WANDERS + 1)
        ],
    }


@pytest.mark.parametrize('case', list(misshaped({'deep': {'id': NO_SUCH_ID}, 'rat': {'id': NO_SUCH_ID}})))
async def test_rejects_misshaped_wanders(client: AsyncClient, me: dict, world: dict, case: str):
    response = await try_create(client, me, misshaped(world)[case])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


async def test_tables_of_one_place_may_split_the_day(client: AsyncClient, me: dict, world: dict):
    rat = line(world['rat'])
    wanders = [
        table(world['deep'], 10, rat, times=['night']),
        table(world['deep'], 20, rat, times=['day']),
        table(world['gate'], 30, rat),
        table(None, 0),
    ]

    scenario = await create(client, me, world, wanders=wanders)

    assert scenario['wanders'] == wanders


async def test_up_to_the_most_monsters_fit_in_one_table(client: AsyncClient, me: dict, world: dict):
    ids = [f'{n:08d}-0000-4000-8000-000000000000' for n in range(WANDER_MAX_MONSTERS)]
    wanders = [table(world['deep'], 10, *(line({'id': monster_id}) for monster_id in ids))]

    response = await try_create(client, me, wanders)

    assert response.status_code == status.HTTP_201_CREATED, response.text


async def test_updating_replaces_or_keeps_the_wanders(client: AsyncClient, me: dict, world: dict):
    scenario = await create(client, me, world, wanders=the_wanders(world))
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    kept = await client.patch(url, json={'title': '새 제목'}, headers=me)
    changed = await client.patch(url, json={'wanders': [table(None, 5, line(world['skeleton']))]}, headers=me)
    cleared = await client.patch(url, json={'wanders': []}, headers=me)

    assert kept.json()['wanders'] == the_wanders(world)
    assert changed.json()['wanders'] == [table(None, 5, line(world['skeleton']))]
    assert cleared.json()['wanders'] == []


# --- 게시 ---


async def test_wanders_are_frozen_into_the_version(client: AsyncClient, me: dict, world: dict):
    scenario = await create(client, me, world, wanders=the_wanders(world))

    document = await encounters.published(client, me, scenario)

    assert document['format'] == SNAPSHOT_FORMAT == 57
    assert document['wanders'] == the_wanders(world)
    night, _, default, safe = read_snapshot(document).wanders
    assert (night.times, night.monsters[1].surprise, default.place_id, safe.chance) == (['night'], 'monsters', None, 0)


@pytest.mark.parametrize(
    ('case', 'problems'),
    [
        ('off-map', ['wander_off_map']),
        ('default-without-map', ['wander_off_map']),
        ('safe-place-without-map', ['wander_off_map']),
        ('monster-without-sheet', ['wander_monster_missing']),
        ('both', ['wander_off_map', 'wander_monster_missing']),
    ],
)
async def test_a_wander_must_fit_the_map_and_the_monsters(
    client: AsyncClient, me: dict, world: dict, case: str, problems: list[str]
):
    no_map = {'start_place': None, 'routes': []}
    fields = {
        # 수문지기는 맵의 장소가 아니다(시작 장소도, 길의 끝도, 명소도 아니다)
        'off-map': {'wanders': [table(world['keeper'], 10, line(world['rat']))]},
        'default-without-map': {'wanders': [table(None, 10, line(world['rat']))], **no_map},
        'safe-place-without-map': {'wanders': [table(world['gate'], 0)], **no_map},
        # 골렘은 도감에 있지만 시트가 없다. 이 시나리오가 쓰지 않는 몬스터라 숫자가 없다
        'monster-without-sheet': {'wanders': [table(world['deep'], 10, line(world['golem']))]},
        'both': {'wanders': [table(world['keeper'], 10, line(world['golem']))]},
    }[case]
    scenario = await create(client, me, world, **fields)

    assert await encounters.refused(client, me, scenario) == problems


async def test_a_wander_may_use_a_landmark(client: AsyncClient, me: dict, world: dict):
    fields = {'landmarks': [world['keeper']['id']], 'wanders': [table(world['keeper'], 10, line(world['rat']))]}
    scenario = await create(client, me, world, **fields)

    # 명소는 맵의 장소다. 인물 항목을 명소로 적은 것은 맵의 문제로 따로 막는다
    assert 'wander_off_map' not in await encounters.refused(client, me, scenario)


# --- 판: 계약과 옛 판 ---


@pytest.mark.parametrize('case', ['not-a-place', 'unknown-monster', 'no-map'])
async def test_the_snapshot_refuses_wanders_that_point_at_nothing(
    client: AsyncClient, me: dict, world: dict, case: str
):
    scenario = await create(client, me, world, wanders=the_wanders(world))
    document = await encounters.published(client, me, scenario)
    broken = {
        'not-a-place': {'wanders': [table(world['keeper'], 10, line(world['rat']))]},
        'unknown-monster': {'wanders': [table(world['deep'], 10, line(world['golem']))]},
        'no-map': {'start_place': None, 'routes': [], 'encounters': []},
    }[case]

    with pytest.raises(ValidationError):
        Snapshot.model_validate({**document, **broken})
    Snapshot.model_validate(document)


def test_an_old_snapshot_reads_as_no_wanders():
    document = {'format': 56, 'covers': []}

    upgraded = upgrade_from_56(document)

    assert (upgraded['format'], upgraded['wanders']) == (57, [])
    assert 'wanders' not in document
    assert UPGRADES[56] is upgrade_from_56
