# trpg-server/tests/test_turn_order.py

"""
차례대로 진행하는 방식(#287, app/rounds/turn_order.py)을 검증한다.

판은 라운드 API 의 추격전이다(tests/test_rounds_api.py). 나(엘프, 방장)와 친구(영애)가 앉는다. 몬스터도 맵도 없다.
srd5 의 차례 능력치는 민첩이고 둘 다 10 이라, 바퀴의 순서는 서버의 주사위(d20, 큰 눈이 먼저)로 가른다.
주사위는 바퀴를 시작할 때마다 앉은 순서로 둘을 굴린다(나, 친구).

보는 것.
  - 옵션: 만들 때 고르고, 모집 중에만 방장이 바꾼다(이벤트가 남는다). 기본은 한꺼번에
  - 라운드: 차례의 주인만 선언하고, 내면 바로 닫힌다. 서술에는 주인의 한 일만 들어간다
  - 바퀴: 둘의 차례가 끝나면 다음 바퀴의 순서를 굴리고 cycle 이 오른다. 게임 안의 시간은 바퀴가 바뀔 때만 흐른다
  - 서술 값: 차례의 주인만 낸다
  - 건너뛰기: 방장이 닫으면 주인이 아무것도 하지 않은 것으로 넘어간다
  - 되돌리기: 앞 차례로 되돌리면 그 차례의 주인과 바퀴가 돌아오고 서술 값을 걸 사람이 바뀐다
  - 작은 함수: 떠난 사람과 쓰러진 사람은 건너뛴다. 바퀴의 기다림은 모두 기다렸을 때만 시간을 건너뛴다
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.rounds import turn_order, waits
from app.tables.models import TurnMode
from tests import test_monster_turns as turns
from tests import test_rounds_api as rounds_api

pytestmark = pytest.mark.usefixtures('clean_tables')

ME, FRIEND = rounds_api.ME, rounds_api.FRIEND
me, friend = rounds_api.me, rounds_api.friend
TABLES_URL = rounds_api.TABLES_URL
rounds_url = rounds_api.rounds_url
current = rounds_api.current
# 바퀴의 주사위(나, 친구). 친구가 먼저다
FRIEND_FIRST = [5, 15]
ME_FIRST = [15, 5]


async def start_turns(client: AsyncClient, app: FastAPI, me: dict, friend: dict, order: list[int]) -> dict:
    """차례대로 진행하는 둘의 테이블을 시작한다. order 는 첫 바퀴의 주사위다."""
    dice = turns.load_dice(app, order)
    table = await rounds_api.start_duo(client, me, friend, turn_mode='turns')
    assert dice.remaining == 0
    return table


async def put_declaration(client: AsyncClient, headers: dict, table: dict, content: str):
    return await client.put(rounds_url(table, '/current/declaration'), json={'content': content}, headers=headers)


async def opened_events(client: AsyncClient, headers: dict, table: dict) -> list[dict]:
    events = await turns.events_of(client, headers, table)
    return [event['payload'] for event in events if event['type'] == 'round_opened']


# --- 옵션 ---


async def test_the_mode_is_chosen_and_changed_only_while_recruiting(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    table = await rounds_api.open_table(client, me)
    assert table['turn_mode'] == 'together'

    by_member = await client.put(f'{TABLES_URL}/{table["id"]}/turn-mode', json={'turn_mode': 'turns'}, headers=friend)
    changed = await client.put(f'{TABLES_URL}/{table["id"]}/turn-mode', json={'turn_mode': 'turns'}, headers=me)

    assert by_member.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
    assert (changed.status_code, changed.json()['turn_mode']) == (status.HTTP_200_OK, 'turns')
    seen = await turns.events_of(client, me, table)
    assert [event['payload'] for event in seen if event['type'] == 'turn_mode_changed'] == [{'turn_mode': 'turns'}]

    turns.load_dice(app, [10])
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '엘프'}, headers=me)
    await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)
    late = await client.put(f'{TABLES_URL}/{table["id"]}/turn-mode', json={'turn_mode': 'together'}, headers=me)
    assert late.status_code == status.HTTP_409_CONFLICT


# --- 차례와 바퀴 ---


async def test_only_the_actor_declares_and_the_turn_closes_at_once(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    table = await start_turns(client, app, me, friend, FRIEND_FIRST)

    first = await current(client, me, table)
    assert (first['number'], first['cycle'], first['actor_id']) == (1, 1, str(FRIEND))
    assert first['waiting_for'] == [str(FRIEND)]
    refused = await put_declaration(client, me, table, rounds_api.MY_ACTION)
    assert (refused.status_code, refused.json()['reason']) == (status.HTTP_409_CONFLICT, 'not_your_turn')

    await rounds_api.declare(client, friend, table, rounds_api.FRIENDS_ACTION)
    await narrated()

    second = await current(client, me, table)
    assert (second['number'], second['cycle'], second['actor_id']) == (2, 1, str(ME))
    # 서술에는 그 차례의 주인이 한 일만 들어간다
    assert second['scene'] == f'[1 라운드의 결과]\n영애: {rounds_api.FRIENDS_ACTION}'


async def test_a_new_cycle_rolls_the_order_again_and_moves_the_clock(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    table = await start_turns(client, app, me, friend, FRIEND_FIRST)
    await rounds_api.declare(client, friend, table, rounds_api.FRIENDS_ACTION)
    await narrated()
    # 바퀴의 마지막 차례를 닫을 때 다음 바퀴의 순서를 굴린다. 이번에는 내가 먼저다
    dice = turns.load_dice(app, ME_FIRST)

    await rounds_api.declare(client, me, table, rounds_api.MY_ACTION)
    await narrated()

    assert dice.remaining == 0
    third = await current(client, me, table)
    assert (third['number'], third['cycle'], third['actor_id']) == (3, 2, str(ME))
    opened = await opened_events(client, me, table)
    # 같은 바퀴의 두 번째 차례에는 시간이 흐르지 않고, 바퀴가 바뀌면 흐른다
    assert [(one['cycle'], one['passed_minutes'] > 0) for one in opened] == [(1, False), (1, False), (2, True)]


async def test_only_the_actor_pays_for_the_turn(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    table = await start_turns(client, app, me, friend, FRIEND_FIRST)

    charges = await client.get(rounds_url(table, '/1/charges'), headers=me)

    assert [charge['user_id'] for charge in charges.json()] == [str(FRIEND)]


async def test_the_host_skips_a_turn(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    table = await start_turns(client, app, me, friend, FRIEND_FIRST)

    skipped = await client.post(rounds_url(table, '/current/close'), headers=me)
    await narrated()

    assert skipped.status_code == status.HTTP_202_ACCEPTED
    second = await current(client, me, table)
    assert (second['actor_id'], second['scene']) == (str(ME), '[1 라운드의 결과]\n영애: 아무것도 하지 않았다.')


async def test_reverting_brings_back_the_turn_and_who_pays(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated
):
    table = await start_turns(client, app, me, friend, FRIEND_FIRST)
    await rounds_api.declare(client, friend, table, rounds_api.FRIENDS_ACTION)
    await narrated()

    reverted = await client.post(rounds_url(table, '/current/revert'), headers=me)

    assert reverted.status_code == status.HTTP_200_OK, reverted.text
    again = await current(client, me, table)
    assert (again['number'], again['cycle'], again['actor_id']) == (1, 1, str(FRIEND))
    charges = (await client.get(rounds_url(table, '/1/charges'), headers=me)).json()
    payable = [charge['user_id'] for charge in charges if charge['status'] not in ('release_due', 'released')]
    assert payable == [str(FRIEND)]
    # 되돌아온 주인이 다시 내면 차례가 다시 넘어간다
    await rounds_api.declare(client, friend, table, rounds_api.FRIENDS_ACTION)
    await narrated()
    assert (await current(client, me, table))['actor_id'] == str(ME)


async def test_a_table_played_together_is_unchanged(client: AsyncClient, me: dict, friend: dict):
    table = await rounds_api.start_duo(client, me, friend)

    first = await current(client, me, table)

    assert (first['cycle'], first['actor_id']) == (1, None)
    assert sorted(first['waiting_for']) == sorted([str(ME), str(FRIEND)])


async def test_monsters_act_only_on_the_last_turn_of_a_cycle(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session, narrated
):
    turns.load_dice(app, FRIEND_FIRST)
    table = await turns.start_table(client, me, friend, table_fields={'turn_mode': 'turns'})
    # 친구(드워프 기사)의 차례. 바퀴의 마지막이 아니라 쥐는 차례를 받지 않는다. 굴림이 없다
    dice = turns.load_dice(app, [])

    await turns.declare(client, friend, table, '숨을 고른다.')
    await narrated()

    assert dice.remaining == 0
    assert await turns.turns_of(session, table, 1) == []
    # 내 차례가 바퀴의 마지막이다. 쥐가 차례를 받는다(남는 눈은 차례, 물기, 다음 바퀴의 순서에 쓴다)
    turns.load_dice(app, [1] * 12)
    await turns.declare(client, me, table, '숨을 고른다.')
    await narrated()

    kinds = [turn['kind'] for turn in await turns.turns_of(session, table, 2)]
    assert 'monster' in kinds


# --- 작은 함수 ---


def seat(user_id: uuid.UUID, hp: int = 5, died: bool = False) -> SimpleNamespace:
    sheet = SimpleNamespace(hp=hp, died_at='then' if died else None)
    return SimpleNamespace(user_id=user_id, sheet=sheet)


def test_the_next_actor_skips_those_who_left_fell_or_died():
    gone, down, dead, ready = (uuid.uuid4() for _ in range(4))
    table = SimpleNamespace(
        members=[seat(down, hp=0), seat(dead, died=True), seat(ready)],
        turn_queue=[str(gone), str(down), str(dead), str(ready)],
        turn_mode=TurnMode.TURNS,
    )

    assert turn_order.ends_cycle(table) is False
    assert turn_order.next_actor(table) == ready
    assert (table.turn_queue, turn_order.ends_cycle(table), turn_order.next_actor(table)) == ([], True, None)


def test_a_cycle_skips_time_only_when_every_turn_waited(monkeypatch: pytest.MonkeyPatch):
    stretched = []
    monkeypatch.setattr(waits.calendar, 'stretch_next_step', lambda table, minutes: stretched.append(minutes))
    actor = uuid.uuid4()

    def turn(waited: list, minutes: int | None) -> tuple[SimpleNamespace, SimpleNamespace]:
        outcome = {'wait': {'minutes': minutes}} if minutes is not None else {}
        declaration = SimpleNamespace(user_id=actor, outcome=outcome)
        table = SimpleNamespace(turn_mode=TurnMode.TURNS, turn_waits=waited, members=[seat(actor)])
        return table, SimpleNamespace(declarations=[declaration])

    # 바퀴 중간의 차례는 적어 두기만 한다
    middle, round_ = turn([], 60)
    waits.settle_turn(middle, round_, set(), cycle_end=False)
    assert (middle.turn_waits, stretched, round_.declarations[0].outcome['wait']['waited']) == ([60], [], True)
    # 마지막 차례도 기다렸으면 그중 가장 짧은 것으로 건너뛴다
    last, round_ = turn([60], 30)
    waits.settle_turn(last, round_, set(), cycle_end=True)
    assert stretched == [30]
    # 한 차례라도 기다리지 않았거나 맞았으면 건너뛰지 않는다
    acted, round_ = turn([60], None)
    waits.settle_turn(acted, round_, set(), cycle_end=True)
    hurt, round_ = turn([60], 30)
    waits.settle_turn(hurt, round_, {actor}, cycle_end=True)
    assert (stretched, acted.turn_waits, hurt.turn_waits) == ([30], [60, None], [60, None])
