# trpg-server/tests/test_away_seats.py

"""
자리 비움(#1345)을 검증한다. 선언을 연속으로 내지 않은 사람에게는 서술 값을 걸지 않고, 더 오래면 자리에서 뺀다.

보는 것
  - 세기: 기다렸는데 내지 않으면 하나 늘고, 내면 0 이다. 닫은 방장은 낸 것으로 본다.
    쓰러진 사람, 차례대로 진행하는 테이블에서 차례가 아닌 사람은 세지 않는다.
  - 값: 연속 2번 내지 않은 사람은 다음 라운드부터 청구가 없다. 돌아와 내면 그다음 라운드부터 다시 건다.
  - 빼기: 연속 5번이면 서버가 뺀다(떠난 길 away). 떠난 테이블에 남는다. 모두 빼게 되면 아무도 빼지 않는다.
  - 이벤트: member_away(닫힘의 묶음), member_away_removed.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.rounds import presence
from app.rounds.models import Declaration, Round
from app.tables.away import AWAY_ROUNDS, REMOVE_ROUNDS, is_away, missed
from app.tables.models import GameTable, TableMember, TableSheet, TurnMode
from tests.test_npc_actions import bearer, declare, events_of, table_url
from tests.test_past_tables import PAST_URL
from tests.test_round_time_limit import FRIEND, ME, current, start_with

pytestmark = pytest.mark.usefixtures('clean_tables')

LAUGH = '크게 웃는다.'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장. 매 라운드 선언한다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """자리를 비우는 사람."""
    return bearer(signing_key, FRIEND)


async def play_round(client: AsyncClient, me: dict[str, str], table: dict, narrated) -> None:
    """방장만 선언하고 방장이 닫는다. 친구는 내지 않은 라운드가 하나 는다."""
    await declare(client, me, table, LAUGH)
    closed = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    assert closed.status_code == status.HTTP_202_ACCEPTED, closed.text
    await narrated()


async def payers(client: AsyncClient, headers: dict[str, str], table: dict) -> list[str]:
    """지금 라운드의 서술 값을 내는 사람들."""
    number = (await current(client, headers, table))['number']
    response = await client.get(table_url(table, f'/rounds/{number}/charges'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [charge['user_id'] for charge in response.json()]


async def test_someone_who_misses_two_rounds_is_not_charged(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=60)

    await play_round(client, me, table, narrated)
    # 한 번 내지 않은 것은 봐준다
    assert sorted(await payers(client, me, table)) == sorted([str(ME), str(FRIEND)])

    await play_round(client, me, table, narrated)

    # 두 번째로 내지 않았다. 다음 라운드부터 값을 걸지 않는다. 자리는 그대로다
    (away,) = await events_of(client, me, table, 'member_away')
    assert await payers(client, me, table) == [str(ME)]
    assert away['payload'] == {'round': 2, 'user_id': str(FRIEND), 'character_name': '캐릭터1'}
    assert str(FRIEND) in [
        member['user_id'] for member in (await client.get(table_url(table), headers=me)).json()['members']
    ]


async def test_coming_back_starts_charging_again(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=60)
    for _ in range(AWAY_ROUNDS):
        await play_round(client, me, table, narrated)

    # 값이 걸리지 않은 라운드에도 낼 수 있다. 그 라운드는 값 없이 받는다
    await declare(client, friend, table, LAUGH)
    await declare(client, me, table, LAUGH)
    await narrated()

    # 냈으니 0 으로 돌아갔다. 다음 라운드부터 다시 건다
    assert sorted(await payers(client, me, table)) == sorted([str(ME), str(FRIEND)])


async def test_someone_away_for_five_rounds_is_removed(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=60)

    for _ in range(REMOVE_ROUNDS):
        await play_round(client, me, table, narrated)

    (removed,) = await events_of(client, me, table, 'member_away_removed')
    detail = (await client.get(table_url(table), headers=me)).json()
    past = (await client.get(PAST_URL, headers=friend)).json()
    assert removed['payload'] == {'round': REMOVE_ROUNDS, 'user_id': str(FRIEND), 'character_name': '캐릭터1'}
    assert [member['user_id'] for member in detail['members']] == [str(ME)]
    # 떠난 테이블에 남는다. 떠난 길은 away 다
    assert [(row['table_id'], row['kind']) for row in past['items']] == [(table['id'], 'away')]
    # 나간 사람은 그 테이블의 지금 것을 읽지 못한다
    assert (await client.get(table_url(table), headers=friend)).status_code == status.HTTP_404_NOT_FOUND


async def test_the_host_who_closes_is_not_away(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with(client, me, friend, round_time_limit=60)
    await declare(client, friend, table, LAUGH)

    # 방장은 선언하지 않고 닫기만 한다. 자리에 있다
    for _ in range(REMOVE_ROUNDS):
        await declare(client, friend, table, LAUGH)
        await client.post(table_url(table, '/rounds/current/close'), headers=me)
        await narrated()

    assert await events_of(client, me, table, 'member_away') == []
    assert sorted(await payers(client, me, table)) == sorted([str(ME), str(FRIEND)])


# --- 세기. DB 를 쓰지 않는다 ---


def member_with(hp: int = 5) -> TableMember:
    """시트가 있는 자리 하나. hp 가 0 이면 쓰러져 있다."""
    sheet = TableSheet(abilities={}, max_hp=10, hp=hp, number=1)
    return TableMember(user_id=uuid.uuid4(), character_name='엘프', sheets=[sheet])


def round_with(*declared: TableMember, actor: TableMember | None = None) -> Round:
    """선언을 낸 사람들이 있는 열린 라운드."""
    round_ = Round(number=1, scene='장면', arrivals=[], actor_id=actor.user_id if actor else None)
    round_.declarations = [
        Declaration(user_id=member.user_id, character_name='엘프', content=LAUGH) for member in declared
    ]
    return round_


def test_declaring_resets_and_missing_counts():
    here, gone = member_with(), member_with()
    table = GameTable(members=[here, gone], away_counts={str(here.user_id): 1})

    newly = presence.count(table, round_with(here), closer_id=None)

    assert (missed(table, here.user_id), missed(table, gone.user_id)) == (0, 1)
    assert newly == []
    # 0 이면 지운다
    assert table.away_counts == {str(gone.user_id): 1}


def test_the_second_miss_makes_someone_away_once():
    here, gone = member_with(), member_with()
    table = GameTable(members=[here, gone], away_counts={str(gone.user_id): AWAY_ROUNDS - 1})

    first = presence.count(table, round_with(here), closer_id=None)
    second = presence.count(table, round_with(here), closer_id=None)

    # 막 자리 비움이 된 때에만 알린다. 이미 비운 사람은 다시 알리지 않는다
    assert first == [gone]
    assert second == []
    assert is_away(table, gone.user_id)


def test_downed_characters_are_not_counted():
    here, downed = member_with(), member_with(hp=0)
    table = GameTable(members=[here, downed], away_counts={str(downed.user_id): 1})

    presence.count(table, round_with(here), closer_id=None)

    assert missed(table, downed.user_id) == 1


def test_only_the_actor_is_counted_when_taking_turns():
    actor, waiting = member_with(), member_with()
    table = GameTable(members=[actor, waiting], turn_mode=TurnMode.TURNS, away_counts={})

    presence.count(table, round_with(actor=actor), closer_id=None)

    assert (missed(table, actor.user_id), missed(table, waiting.user_id)) == (1, 0)


def test_nobody_is_removed_if_it_would_empty_the_table():
    one, two = member_with(), member_with()
    all_gone = {str(one.user_id): REMOVE_ROUNDS, str(two.user_id): REMOVE_ROUNDS}

    assert presence.to_remove(GameTable(members=[one, two], away_counts=all_gone)) == []
    assert presence.to_remove(GameTable(members=[one, two], away_counts={str(two.user_id): REMOVE_ROUNDS})) == [two]
