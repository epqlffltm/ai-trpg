# trpg-server/tests/test_quest_handover.py

"""
이룬 퀘스트가 물건을 가져가는 것(배달, #455, app/rounds/quest_handover.py)을 검증한다.

맵과 판은 test_quest_goals.py 의 것이다. 나(기사)와 약사가 성문에 선다. 물건은 치유 물약과 늑대 가죽이다.
소지품은 방장의 주기로 채운다. 퀘스트는 첫 사건(왕녀 구출)과 둘째 사건(숨은 비밀)이고 판의 순서도 그렇다.

보는 것.
  - 시나리오: consume 은 물건 갖기에만, 이루는 조건에만 적는다. 적지 않으면 가져가지 않는다. 옛 판은 가져가지 않는다.
  - 라운드: 이루면 그 개수를 뺀다. 여럿이 가졌으면 앉은 순서로 한 개씩 돌아가며 고르게 뺀다. 보상보다 먼저 뺀다.
    하나라도(any)로 이뤘으면 채운 조건의 물건만 가져간다. 같은 물건을 가져가는 퀘스트 둘은 판의 순서로 하나만 이룬다.
  - 이벤트: quest_changed 의 consumed 에 낸 사람과 물건이 있다.
  - 서술: 낸 사람의 한 일의 줄에 넘긴 물건이 붙는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.upgrades import upgrade_from_32
from app.rounds.move_lines import describe_handed_over, describe_move
from app.rounds.narrator import HandOverNote, Move
from app.rounds.quest_handover import split_evenly
from tests.narration_model import asset_body
from tests.test_quest_goals import (
    SCENARIOS_URL,
    declare,
    goal,
    make_world,
    move,
    quest,
    start,
    status_of,
)
from tests.test_table_items import FRIEND, ME, bearer, events_of, give, read_table
from tests.test_table_items import held as held_items
from tests.test_whispers import RecordingNarrator

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


def delivery(world: dict, item: str, count: int) -> dict:
    """이루면 그 물건을 가져가는 물건 갖기 조건."""
    return {**goal('hold_item', world[item], count), 'consume': True}


def second(rule: dict, world: dict) -> dict:
    """둘째 사건(숨은 비밀)의 퀘스트 규칙. 판의 순서로 첫 사건 뒤다."""
    return {**rule, 'entry_id': world['secret']['id']}


async def stock(session: AsyncSession, table: dict, user_id: uuid.UUID, entry: dict, count: int) -> None:
    """그 사람에게 물건을 준다. 테스트의 준비다."""
    await give(session, table, user_id, entry, count)


async def close_round(client: AsyncClient, table: dict, narrated, *seated: dict) -> None:
    """앉은 사람 모두가 그냥 둘러보고 라운드를 닫는다."""
    for headers in seated:
        await declare(client, headers, table)
    await narrated()


async def quest_change(client: AsyncClient, me: dict, table: dict, name: str = '왕녀 구출') -> dict:
    events = await events_of(client, me, table, 'quest_changed')
    return next(event['payload'] for event in events if event['payload']['name'] == name)


# --- 시나리오 ---


@pytest.mark.parametrize('where', ['not-an-item', 'reveal'])
async def test_consume_is_only_for_holding_an_item_on_success(client: AsyncClient, me: dict[str, str], where: str):
    world = await make_world(client, me)
    if where == 'not-an-item':
        rule = quest(world, {**goal('reach_place', world['forest']), 'consume': True})
    else:
        rule = {
            **quest(world, goal('reach_place', world['forest']), start='hidden'),
            'reveal': [delivery(world, 'potion', 1)],
        }
    body = {'title': '성문', 'quests': [rule]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'consume' in response.text


def test_an_old_snapshot_takes_nothing():
    condition = {'kind': 'hold_item', 'target': str(uuid.uuid4()), 'count': 2}
    document = {'format': 32, 'quests': [{'entry_id': 'q', 'conditions': [condition], 'reveal': [condition]}]}

    upgraded = upgrade_from_32(document)

    assert upgraded['format'] == 33
    (rule,) = upgraded['quests']
    assert [one['consume'] for one in [*rule['conditions'], *rule['reveal']]] == [False, False]
    # 받은 문서는 고치지 않는다
    assert 'consume' not in document['quests'][0]['conditions'][0]


# --- 라운드 ---


async def test_a_delivery_takes_the_items_evenly(
    client: AsyncClient,
    me: dict[str, str],
    friend: dict[str, str],
    narrated,
    session: AsyncSession,
):
    world = await make_world(client, me)
    reward = [{'entry_id': world['pelt']['id'], 'count': 1}]
    table = await start(client, me, world, [quest(world, delivery(world, 'potion', 3), reward=reward)], friend)
    await stock(session, table, ME, world['potion'], 2)
    await stock(session, table, FRIEND, world['potion'], 2)

    await close_round(client, table, narrated, me, friend)

    # 앉은 순서로 한 개씩: 기사 1, 약사 1, 기사 1. 보상은 빼고 나서 준다
    seen = await read_table(client, me, table)
    assert status_of(seen, '왕녀 구출') == 'succeeded'
    assert held_items(seen, ME) == [('늑대 가죽', 1)]
    assert held_items(seen, FRIEND) == [('치유 물약', 1), ('늑대 가죽', 1)]
    potion = {'entry_id': world['potion']['id'], 'name': '치유 물약'}
    assert (await quest_change(client, me, table))['consumed'] == [
        {'user_id': str(ME), 'character_name': '기사', 'items': [{**potion, 'count': 2, 'total': 0}]},
        {'user_id': str(FRIEND), 'character_name': '약사', 'items': [{**potion, 'count': 1, 'total': 1}]},
    ]


async def test_one_who_has_little_runs_out_first(
    client: AsyncClient,
    me: dict[str, str],
    friend: dict[str, str],
    narrated,
    session: AsyncSession,
):
    world = await make_world(client, me)
    table = await start(client, me, world, [quest(world, delivery(world, 'potion', 4))], friend)
    await stock(session, table, ME, world['potion'], 1)
    await stock(session, table, FRIEND, world['potion'], 5)

    await close_round(client, table, narrated, me, friend)

    # 기사는 하나뿐이라 하나를 내고, 남은 셋은 약사가 낸다
    seen = await read_table(client, me, table)
    assert (held_items(seen, ME), held_items(seen, FRIEND)) == ([], [('치유 물약', 2)])


async def test_it_takes_before_it_rewards(client: AsyncClient, me: dict[str, str], narrated, session: AsyncSession):
    world = await make_world(client, me)
    reward = [{'entry_id': world['potion']['id'], 'count': 1}]
    table = await start(client, me, world, [quest(world, delivery(world, 'potion', 2), reward=reward)])
    await stock(session, table, ME, world['potion'], 99)

    await close_round(client, table, narrated, me)

    # 먼저 둘을 내고 하나를 받는다. 받기를 먼저 했으면 가득 차서 받지 못했다
    assert held_items(await read_table(client, me, table), ME) == [('치유 물약', 98)]
    (rewarded,) = (await quest_change(client, me, table))['rewards']
    assert [(thing['count'], thing['capped']) for thing in rewarded['items']] == [(1, False)]


async def test_without_consume_the_items_stay(client: AsyncClient, me: dict[str, str], narrated, session: AsyncSession):
    world = await make_world(client, me)
    table = await start(client, me, world, [quest(world, goal('hold_item', world['potion'], 2))])
    await stock(session, table, ME, world['potion'], 2)

    await close_round(client, table, narrated, me)

    seen = await read_table(client, me, table)
    assert status_of(seen, '왕녀 구출') == 'succeeded'
    assert held_items(seen, ME) == [('치유 물약', 2)]
    assert (await quest_change(client, me, table))['consumed'] == []


async def test_any_takes_only_from_the_conditions_met(
    client: AsyncClient, me: dict[str, str], narrated, session: AsyncSession
):
    world = await make_world(client, me)
    conditions = [goal('reach_place', world['forest']), delivery(world, 'potion', 5)]
    table = await start(client, me, world, [quest(world, *conditions, match='any')])
    await stock(session, table, ME, world['potion'], 2)

    await declare(client, me, table, '숲으로 간다.', move(world['forest']))
    await narrated()

    # 숲에 닿아 이뤘다. 물약 다섯은 채우지 않았으므로 가져가지 않는다
    seen = await read_table(client, me, table)
    assert status_of(seen, '왕녀 구출') == 'succeeded'
    assert held_items(seen, ME) == [('치유 물약', 2)]


async def test_two_deliveries_of_the_same_thing_go_in_order(
    client: AsyncClient, me: dict[str, str], narrated, session: AsyncSession
):
    world = await make_world(client, me)
    rules = [quest(world, delivery(world, 'potion', 2)), second(quest(world, delivery(world, 'potion', 2)), world)]
    table = await start(client, me, world, rules)
    await stock(session, table, ME, world['potion'], 3)

    await close_round(client, table, narrated, me)

    # 셋으로는 둘 다 이룰 수 없다. 판의 순서로 앞 퀘스트가 가져가고 뒤 퀘스트는 아직 이루지 못했다
    seen = await read_table(client, me, table)
    assert (status_of(seen, '왕녀 구출'), status_of(seen, '숨은 비밀')) == ('succeeded', 'active')
    assert held_items(seen, ME) == [('치유 물약', 1)]


async def test_a_reward_can_be_delivered_by_the_next_quest(client: AsyncClient, me: dict[str, str], narrated):
    world = await make_world(client, me)
    reward = [{'entry_id': world['potion']['id'], 'count': 2}]
    rules = [
        quest(world, goal('reach_place', world['gate']), reward=reward),
        second(quest(world, delivery(world, 'potion', 2)), world),
    ]
    table = await start(client, me, world, rules)

    await close_round(client, table, narrated, me)

    # 앞 퀘스트의 보상을 뒤 퀘스트가 셀 때 이미 가졌다
    seen = await read_table(client, me, table)
    assert (status_of(seen, '왕녀 구출'), status_of(seen, '숨은 비밀')) == ('succeeded', 'succeeded')
    assert held_items(seen, ME) == []


# --- 서술 ---


async def test_the_narrator_sees_what_was_handed_over(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    friend: dict[str, str],
    narrated,
    session: AsyncSession,
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    world = await make_world(client, me)
    table = await start(client, me, world, [quest(world, delivery(world, 'potion', 1))], friend)
    await stock(session, table, FRIEND, world['potion'], 1)

    await close_round(client, table, narrated, me, friend)

    (request,) = narrator.requests
    knight, healer = request.moves
    assert knight.handed_over == []
    assert healer.handed_over == [HandOverNote(quest='왕녀 구출', name='치유 물약', count=1)]
    assert healer.items == []


def test_the_handed_over_line():
    notes = [
        HandOverNote(quest='약초 배달', name='약초', count=2),
        HandOverNote(quest='편지 전하기', name='편지', count=1),
    ]

    assert describe_handed_over(notes) == '(넘긴 물건: 약초 배달에 약초 2개, 편지 전하기에 편지 1개)'


def test_the_move_line_carries_what_was_handed_over():
    handed = [HandOverNote(quest='약초 배달', name='약초', count=2)]

    line = describe_move(Move(character_name='약사', content='주위를 살핀다.', handed_over=handed))

    assert line == '약사: 주위를 살핀다. (넘긴 물건: 약초 배달에 약초 2개)'


# --- 고르게 나누기 ---


@pytest.mark.parametrize(
    ('holdings', 'need', 'taken'),
    [
        ([3, 2, 1], 4, [2, 1, 1]),
        ([2, 2], 3, [2, 1]),
        ([5, 0, 1], 3, [2, 0, 1]),
        ([1, 5], 4, [1, 3]),
        ([1, 1], 5, [1, 1]),
        ([4], 0, [0]),
        ([], 2, []),
    ],
)
def test_split_evenly(holdings: list[int], need: int, taken: list[int]):
    assert split_evenly(holdings, need) == taken
