# trpg-server/tests/test_quest_failure.py

"""
퀘스트가 판의 실패하는 조건으로 실패하는 것(#367, app/rounds/quest_goals.py 의 fail_quests, settle_quests)을 검증한다.

맵과 판은 test_quest_goals.py 의 것이다. 성문(시작)과 숲, 들쥐 둘, 악역영애(인물, 최대 HP 4), 치유 물약.
사건은 왕녀 구출(진행 중)과 숨은 비밀이다.

보는 것.
  - 시나리오: 실패하는 조건(fail, fail_match)을 적고 판에 굳힌다. 물건을 잃는 것(lose_item)은 실패하는 조건에만,
    가져가기(consume)는 이루는 조건에만, 자기 자신은 안 된다. 인물이 죽음(npc_dead)은 세지 않는다.
    게시할 때 가리키는 것이 맞는 종류인지 본다. 실패를 기다리는 잇기는 그 퀘스트가 실패할 수 있어야 한다.
    옛 판은 실패하는 조건이 없는 것으로 읽는다.
  - 라운드: 지킬 인물이 죽으면(쓰러짐은 아니다), 지킬 물건을 잃으면, 가지 말아야 할 곳에 가면, 다른 퀘스트가 이루면
    실패한다(까닭 conditions_met, 행한 사람 없음, 보상 없음). 모두(all)와 하나라도(any).
    같은 라운드에 이루는 조건도 채워졌으면 성공이다. 숨긴 퀘스트는 숨긴 채로 실패하지 않는다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.assets.models import QuestConditionKind, QuestMatch
from app.assets.scenarios.snapshot import QuestConditionSnapshot, read_snapshot
from app.assets.scenarios.upgrades import upgrade_from_42
from app.rounds.quest_goals import is_failing, npc_dead
from app.tables.models import NpcStatus
from app.tables.quests import CatalogQuest
from tests.narration_model import asset_body
from tests.test_quest_goals import (
    DOWN,
    PASS,
    SCENARIOS_URL,
    declare,
    goal,
    load_dice,
    make_scenario,
    make_world,
    move,
    person,
    publish,
    quest,
    start,
    status_of,
    strike,
)
from tests.test_quest_reveal import link, quest_changes, secret
from tests.test_table_items import ME, bearer, events_of, read_table

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


def failing(rule: dict, *fail: dict, fail_match: str = 'all') -> dict:
    """그 퀘스트 규칙에 실패하는 조건을 붙인다."""
    return {**rule, 'fail': list(fail), 'fail_match': fail_match}


def spared(**target) -> dict:
    """죽이지 않고 쓰러뜨리려고 친다."""
    return {**strike(**target), 'lethal': False}


def put_down(world: dict, item: str, count: int = 1) -> dict:
    return {'kind': 'put_down', 'item': world[item]['id'], 'count': count}


# --- 시나리오 ---


async def test_fail_conditions_are_saved_and_published(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    rule = failing(
        quest(world, goal('reach_place', world['forest'])),
        goal('npc_dead', world['lady']),
        goal('lose_item', world['potion'], 2),
        fail_match='any',
    )
    scenario = await make_scenario(client, me, world, [rule])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    (published,) = read_snapshot(response.json()['snapshot']).quests
    assert published.fail_match == QuestMatch.ANY
    assert [(item.kind, str(item.target), item.count) for item in published.fail] == [
        (QuestConditionKind.NPC_DEAD, world['lady']['id'], 1),
        (QuestConditionKind.LOSE_ITEM, world['potion']['id'], 2),
    ]


@pytest.mark.parametrize(
    'case', ['lose-in-conditions', 'lose-in-reveal', 'consume-in-fail', 'fail-on-itself', 'count-on-npc-dead']
)
async def test_a_misplaced_fail_condition_is_refused(client: AsyncClient, me: dict[str, str], case: str):
    world = await make_world(client, me)
    lose = goal('lose_item', world['potion'])
    rules = {
        # 잃어서 이루거나 드러나는 퀘스트는 없다
        'lose-in-conditions': quest(world, lose),
        'lose-in-reveal': secret(world, lose),
        # 실패할 때는 아무것도 가져가지 않는다
        'consume-in-fail': failing(quest(world), {**goal('hold_item', world['potion']), 'consume': True}),
        'fail-on-itself': failing(quest(world), link('quest_succeeded', world['rescue'])),
        'count-on-npc-dead': failing(quest(world), goal('npc_dead', world['lady'], 2)),
    }
    body = {'title': '성문', 'quests': [rules[case]]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('kind', 'target', 'problem'),
    [
        ('npc_dead', 'potion', 'quest_condition_invalid'),
        ('lose_item', 'lady', 'quest_condition_invalid'),
        ('quest_succeeded', 'gone', 'quest_condition_missing'),
        ('reach_place', 'island', 'quest_condition_impossible'),
    ],
    ids=['item-as-person', 'person-as-item', 'no-quest', 'off-map'],
)
async def test_a_fail_condition_must_point_at_something_possible(
    client: AsyncClient, me: dict[str, str], kind: str, target: str, problem: str
):
    world = await make_world(client, me)
    pointed = world[target] if target in world else {'id': str(uuid.uuid4())}
    rule = failing(quest(world), {'kind': kind, 'target': pointed['id']})
    scenario = await make_scenario(client, me, world, [rule])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


async def test_waiting_for_a_failure_that_cannot_come_is_refused(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    # 왕녀 구출에는 기한도 실패하는 조건도 없다. 사람이 실패시키는 길도 없다(#367).
    # 실패하지 않으니 비밀은 드러나지 않는다
    rules = [quest(world, goal('reach_place', world['forest'])), secret(world, link('quest_failed', world['rescue']))]
    scenario = await make_scenario(client, me, world, rules)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['quest_condition_impossible']


async def test_a_failure_by_conditions_can_be_waited_for(client: AsyncClient, me: dict[str, str]):
    world = await make_world(client, me)
    rescue = failing(quest(world, goal('reach_place', world['forest'])), goal('npc_dead', world['lady']))
    rules = [rescue, secret(world, link('quest_failed', world['rescue']))]
    scenario = await make_scenario(client, me, world, rules)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text


def test_an_old_snapshot_reads_as_no_fail_conditions():
    document = {'format': 42, 'quests': [{'entry_id': str(uuid.uuid4()), 'start': 'active'}]}

    upgraded = upgrade_from_42(document)

    assert upgraded['format'] == 43
    assert (upgraded['quests'][0]['fail'], upgraded['quests'][0]['fail_match']) == ([], 'all')
    assert 'fail' not in document['quests'][0]


# --- 라운드 ---


async def test_the_quest_fails_when_the_person_to_protect_dies(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await make_world(client, me)
    rule = failing(quest(world, goal('reach_place', world['forest'])), goal('npc_dead', world['lady']))
    table = await start(client, me, world, [rule])

    load_dice(app, [PASS, DOWN])
    await declare(client, me, table, '영애를 벤다.', strike(npc=world['lady']['id']))
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'failed'
    (changed,) = await events_of(client, me, table, 'quest_changed')
    assert changed['actor_id'] is None
    payload = changed['payload']
    assert (payload['previous'], payload['status'], payload['reason']) == ('active', 'failed', 'conditions_met')
    assert (payload['rewards'], payload['consumed']) == ([], [])


async def test_a_downed_person_is_not_dead(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rule = failing(quest(world, goal('reach_place', world['forest'])), goal('npc_dead', world['lady']))
    table = await start(client, me, world, [rule])

    # 죽이지 않는 큰 피해는 부상 표를 한 번 더 굴린다
    load_dice(app, [PASS, DOWN, 1])
    await declare(client, me, table, '영애를 때려 눕힌다.', spared(npc=world['lady']['id']))
    await narrated()

    # 쓰러진 인물은 회복을 받으면 일어난다. 아직 지킬 수 있다
    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'active'


async def test_the_quest_fails_when_the_item_to_keep_is_lost(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rule = failing(quest(world, goal('reach_place', world['forest'])), goal('lose_item', world['potion'], 2))
    starting = [{'entry_id': world['potion']['id'], 'count': 2}]
    table = await start(client, me, world, [rule], starting_items=starting)

    await declare(client, me, table)
    await narrated()
    kept = status_of(await read_table(client, me, table), '왕녀 구출')
    await declare(client, me, table, '물약 하나를 내려놓는다.', put_down(world, 'potion'))
    await narrated()

    # 둘을 지키는 동안은 그대로다. 하나라도 잃으면 둘보다 적다
    assert kept == 'active'
    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'failed'


async def test_the_quest_fails_when_the_party_goes_where_it_must_not(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rule = failing(quest(world, goal('defeat_npc', world['lady'])), goal('reach_place', world['forest']))
    table = await start(client, me, world, [rule])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == 'failed'


async def test_success_comes_first_in_the_same_round(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    forest = goal('reach_place', world['forest'])
    reward = [{'entry_id': world['potion']['id'], 'count': 1}]
    table = await start(client, me, world, [failing(quest(world, forest, reward=reward), forest)])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 이루는 조건과 실패하는 조건이 함께 채워졌다. 마지막 순간에 이룬 것은 이룬 것이다(기한과 같다)
    assert await quest_changes(client, me, table) == [('왕녀 구출', 'active', 'succeeded')]


@pytest.mark.parametrize(('fail_match', 'expected'), [('any', 'failed'), ('all', 'active')])
async def test_all_or_any(client: AsyncClient, me: dict[str, str], narrated, fail_match: str, expected: str):
    world = await make_world(client, me)
    rule = failing(
        quest(world, goal('defeat_npc', world['lady'])),
        goal('reach_place', world['forest']),
        goal('npc_dead', world['lady']),
        fail_match=fail_match,
    )
    table = await start(client, me, world, [rule])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    assert status_of(await read_table(client, me, table), '왕녀 구출') == expected


async def test_a_rival_success_fails_the_quest_in_the_same_round(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rules = [
        quest(world, goal('reach_place', world['forest'])),
        {
            'entry_id': world['secret']['id'],
            'start': 'active',
            'conditions': [goal('defeat_npc', world['lady'])],
            'fail': [link('quest_succeeded', world['rescue'])],
        },
    ]
    table = await start(client, me, world, rules)

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 한 바퀴에 성공을 보고, 그 성공을 잇는 실패는 같은 바퀴의 실패에서 본다
    assert await quest_changes(client, me, table) == [
        ('왕녀 구출', 'active', 'succeeded'),
        ('숨은 비밀', 'active', 'failed'),
    ]


async def test_a_hidden_quest_does_not_fail_while_hidden(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    rule = failing(
        secret(world, goal('defeat_npc', world['lady']), conditions=[goal('hold_item', world['potion'])]),
        goal('reach_place', world['forest']),
    )
    table = await start(client, me, world, [rule])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 아무도 모르는 퀘스트는 실패하지 않는다. 드러난 뒤에 본다
    assert await events_of(client, me, table, 'quest_changed') == []


async def test_a_quest_revealed_with_its_failure_met_fails_at_once(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    forest = goal('reach_place', world['forest'])
    rule = failing(secret(world, forest, conditions=[goal('defeat_npc', world['lady'])]), forest)
    table = await start(client, me, world, [rule])

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    assert await quest_changes(client, me, table) == [
        ('숨은 비밀', 'hidden', 'active'),
        ('숨은 비밀', 'active', 'failed'),
    ]


# --- DB 를 쓰지 않는 작은 함수들 ---


def test_only_a_dead_person_is_dead():
    lady = uuid.uuid4()

    assert npc_dead([SimpleNamespace(entry_id=lady, status=NpcStatus.DEAD)], lady)
    assert not npc_dead([SimpleNamespace(entry_id=lady, status=NpcStatus.DOWNED)], lady)
    assert not npc_dead([SimpleNamespace(entry_id=uuid.uuid4(), status=NpcStatus.DEAD)], lady)
    assert not npc_dead([], lady)


@pytest.mark.parametrize(('held', 'expected'), [(3, False), (2, False), (1, True), (0, True)])
def test_losing_means_fewer_than_the_count(held: int, expected: bool):
    potion = uuid.uuid4()
    lose = (QuestConditionSnapshot(kind=QuestConditionKind.LOSE_ITEM, target=potion, count=2),)
    quest_ = CatalogQuest(entry_id=uuid.uuid4(), name='호위', start='active', reward=[], fail=lose)
    table = SimpleNamespace(members=[person(None, {potion: held})])

    assert is_failing(quest_, table, [], []) is expected


def test_no_fail_conditions_never_fail():
    quest_ = CatalogQuest(entry_id=uuid.uuid4(), name='구출', start='active', reward=[])

    assert not is_failing(quest_, SimpleNamespace(members=[]), [], [])
