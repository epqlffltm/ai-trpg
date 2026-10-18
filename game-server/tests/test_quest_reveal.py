# game-server/tests/test_quest_reveal.py

"""
숨긴 퀘스트가 드러나는 것(#367, app/rounds/quest_goals.py 의 reveal_quests, settle_quests)을 검증한다.

맵과 판은 test_quest_goals.py 의 것이다. 성문(시작)과 숲, 들쥐 둘, 악역영애. 사건은 왕녀 구출과 숨은 비밀이다.

보는 것.
  - 시나리오: 드러나는 조건(reveal, reveal_match)을 적고 판에 굳힌다. 퀘스트 잇기(quest_succeeded, quest_failed)는
    드러나는 조건에만, 드러나는 조건은 숨긴 채 시작하는 퀘스트에만, 자기 자신은 안 된다.
    게시할 때 잇기가 사건 항목을 가리키는지, 기다리는 성공이 올 수 있는지, 돌고 돌지 않는지 본다.
    옛 판은 드러나는 조건이 없는 것으로 읽는다.
  - 라운드: 조건을 채우면 드러난다(까닭 conditions_met, 행한 사람 없음, 기한은 그때부터).
    드러나고 바로 이루면 두 번 바뀐다. 다른 퀘스트의 성공과 기한의 실패로 같은 라운드에 드러난다(잇기).
  - 사람: 방장은 드러내지 못하고(409 quest_reveal_by_engine), 숨긴 퀘스트를 보지도, 끝내지도 못한다(422).
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_30
from tests.narration_model import asset_body
from tests.test_quest_deadline import EIGHT, clock_at
from tests.test_quest_goals import (
    SCENARIOS_URL,
    declare,
    goal,
    make_scenario,
    make_world,
    move,
    publish,
    quest,
    start,
    status_of,
)
from tests.test_table_items import ME, bearer, events_of, read_table, table_url

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


def secret(world: dict, *reveal: dict, conditions: list | None = None, reveal_match: str = 'all', **fields) -> dict:
    """두 번째 사건(숨은 비밀)의 퀘스트 규칙. 숨긴 채로 시작한다."""
    rule = {'entry_id': world['secret']['id'], 'start': 'hidden', 'reveal': list(reveal), 'reveal_match': reveal_match}
    return {**rule, 'conditions': conditions or [], **fields}


def link(kind: str, quest_entry: dict) -> dict:
    """퀘스트 잇기 조건 하나."""
    return {'kind': kind, 'target': quest_entry['id']}


def names(table: dict) -> list[str]:
    return [shown['name'] for shown in table['quests']]


async def quest_changes(client: AsyncClient, me: dict, table: dict) -> list[tuple[str, str, str]]:
    """퀘스트가 바뀐 이벤트들. (이름, 앞, 뒤) 차례다."""
    events = await events_of(client, me, table, 'quest_changed')
    return [(event['payload']['name'], event['payload']['previous'], event['payload']['status']) for event in events]


# --- 시나리오 ---


async def test_reveal_conditions_are_saved_and_published(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    rule = secret(
        world, goal('reach_place', world['forest']), link('quest_failed', world['rescue']), reveal_match='any'
    )
    scenario = await make_scenario(client, me, world, [quest(world, goal('reach_place', world['forest'])), rule])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    published = read_snapshot(response.json()['snapshot']).quests[1]
    assert published.reveal_match == 'any'
    assert [(item.kind, str(item.target)) for item in published.reveal] == [
        ('reach_place', world['forest']['id']),
        ('quest_failed', world['rescue']['id']),
    ]


@pytest.mark.parametrize('case', ['link-in-conditions', 'reveal-on-active', 'reveal-on-itself'])
async def test_a_misplaced_reveal_is_refused(client: AsyncClient, me: dict[str, str], case: str):
    world = await make_world(client, me)
    rules = {
        # 이루는 것은 이 퀘스트의 일이다. 잇기는 드러나는 조건에만 쓴다
        'link-in-conditions': secret(world, conditions=[link('quest_succeeded', world['rescue'])]),
        # 처음부터 진행 중이면 드러날 일이 없다
        'reveal-on-active': {**secret(world, goal('reach_place', world['forest'])), 'start': 'active'},
        'reveal-on-itself': secret(world, link('quest_succeeded', world['secret'])),
    }
    body = {'title': '성문', 'quests': [rules[case]]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('kind', 'target', 'problem'),
    [
        ('quest_succeeded', 'gone', 'quest_condition_missing'),
        ('quest_failed', 'forest', 'quest_condition_invalid'),
        ('reach_place', 'island', 'quest_condition_impossible'),
    ],
    ids=['no-quest', 'place-as-quest', 'off-map'],
)
async def test_a_reveal_condition_must_point_at_something_possible(
    client: AsyncClient, me: dict[str, str], kind: str, target: str, problem: str
):
    world = await make_world(client, me)
    pointed = world[target] if target in world else {'id': str(uuid.uuid4())}
    scenario = await make_scenario(client, me, world, [secret(world, {'kind': kind, 'target': pointed['id']})])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


async def test_waiting_for_a_success_that_cannot_come_is_refused(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    # 왕녀 구출에는 이루는 조건이 없다. 성공하지 않으니 숨은 비밀은 그 성공으로 드러나지 않는다
    rules = [quest(world), secret(world, link('quest_succeeded', world['rescue']))]
    scenario = await make_scenario(client, me, world, rules)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['quest_condition_impossible']


async def test_reveals_that_wait_for_each_other_are_refused(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    forest = [goal('reach_place', world['forest'])]
    rules = [
        {**secret(world, link('quest_succeeded', world['rescue']), conditions=forest)},
        {
            'entry_id': world['rescue']['id'],
            'start': 'hidden',
            'conditions': forest,
            'reveal': [link('quest_succeeded', world['secret'])],
        },
    ]
    scenario = await make_scenario(client, me, world, rules)

    response = await publish(client, me, scenario)

    # 서로가 끝나야 드러난다. 숨긴 채로 이룰 수는 있어 막히지 않지만 만든 사람의 실수다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['quest_reveal_cycle']


def test_an_old_snapshot_reads_as_no_reveal_conditions():
    document = {'format': 30, 'quests': [{'entry_id': str(uuid.uuid4()), 'start': 'hidden'}]}

    upgraded = upgrade_from_30(document)

    assert upgraded['format'] == 31
    assert (upgraded['quests'][0]['reveal'], upgraded['quests'][0]['reveal_match']) == ([], 'all')
    assert 'reveal' not in document['quests'][0]


# --- 라운드 ---


async def test_reaching_the_place_reveals_the_quest(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rule = secret(world, goal('reach_place', world['forest']), time_limit_minutes=30)
    table = await start(client, me, world, [rule])
    hidden = await read_table(client, me, table)

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 방장에게도 숨겨져 있었다. 드러난 뒤에는 모두 본다. 기한은 드러난 라운드가 열린 시각부터 센다
    seen = await read_table(client, me, table)
    assert names(hidden) == []
    assert status_of(seen, '숨은 비밀') == 'active'
    (changed,) = await events_of(client, me, table, 'quest_changed')
    assert changed['actor_id'] is None
    assert changed['payload']['reason'] == 'conditions_met'
    assert (changed['payload']['previous'], changed['payload']['status']) == ('hidden', 'active')
    assert changed['payload']['due_at'] == clock_at(EIGHT + 30)


async def test_without_the_condition_the_quest_stays_hidden(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    table = await start(client, me, world, [secret(world, goal('reach_place', world['forest']))])

    await declare(client, me, table)
    await narrated()

    assert names(await read_table(client, me, table)) == []
    assert await events_of(client, me, table, 'quest_changed') == []


async def test_a_quest_revealed_and_achieved_at_once_changes_twice(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    forest = goal('reach_place', world['forest'])
    table = await start(client, me, world, [secret(world, forest, conditions=[forest])])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 드러내기를 먼저 본다. 그 라운드에 드러난 것도 그 라운드에 이룬다
    assert await quest_changes(client, me, table) == [
        ('숨은 비밀', 'hidden', 'active'),
        ('숨은 비밀', 'active', 'succeeded'),
    ]


async def test_a_success_reveals_the_linked_quest_in_the_same_round(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rules = [
        quest(world, goal('reach_place', world['forest'])),
        secret(world, link('quest_succeeded', world['rescue'])),
    ]
    table = await start(client, me, world, rules)

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    seen = await read_table(client, me, table)
    assert (status_of(seen, '왕녀 구출'), status_of(seen, '숨은 비밀')) == ('succeeded', 'active')
    assert await quest_changes(client, me, table) == [
        ('왕녀 구출', 'active', 'succeeded'),
        ('숨은 비밀', 'hidden', 'active'),
    ]


async def test_a_missed_deadline_reveals_the_linked_quest(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rules = [
        {**quest(world, goal('reach_place', world['forest'])), 'time_limit_minutes': 10},
        secret(world, link('quest_failed', world['rescue'])),
    ]
    table = await start(client, me, world, rules)

    for _ in range(2):
        await declare(client, me, table)
        await narrated()

    # 2 라운드가 기한(8시 10분)에 열렸다. 그 라운드가 닫힐 때 실패하고, 실패를 적은 뒤에 한 번 더 보아 드러난다
    assert await quest_changes(client, me, table) == [
        ('왕녀 구출', 'active', 'failed'),
        ('숨은 비밀', 'hidden', 'active'),
    ]


# --- 사람 ---


@pytest.mark.parametrize('which', ['rescue', 'secret'])
async def test_the_host_cannot_reveal(client: AsyncClient, me: dict[str, str], which: str):
    world = await make_world(client, me)
    rules = [quest(world, goal('reach_place', world['forest'])), secret(world)]
    table = await start(client, me, world, rules)

    response = await client.put(
        table_url(table, f'/quests/{world[which]["id"]}'), json={'status': 'active'}, headers=me
    )

    # 진행 중이든 숨겼든 같은 답이다. 숨긴 퀘스트가 있는지 새지 않는다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'quest_reveal_by_engine'


async def test_the_host_cannot_end_a_hidden_quest(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    table = await start(client, me, world, [secret(world)])

    response = await client.put(
        table_url(table, f'/quests/{world["secret"]["id"]}'), json={'status': 'failed'}, headers=me
    )

    # 없는 퀘스트와 같은 답이다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert names(await read_table(client, me, table)) == []
