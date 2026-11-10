# trpg-server/tests/test_turn_slots.py

"""
차례대로 진행하는 테이블(#287)에서 몬스터의 자리와 다음 차례까지 드는 태세(app/rounds/turn_order.py)를 검증한다.

판은 몬스터의 차례의 수로 입구다(tests/test_monster_turns.py). 나(엘프)와 친구(드워프 기사)가 입구에 서고 쥐 한 마리가
있다. 둘의 민첩은 10 이다. 첫 바퀴의 순서는 주사위(나 5, 친구 15)로 친구가 먼저다.

보는 것.
  - 쥐의 민첩이 둘보다 높으면 첫 차례(친구의 차례)에 함께 친다. 그 바퀴의 다음 차례에는 다시 치지 않는다
  - 쥐의 민첩이 둘보다 낮으면 바퀴의 마지막 차례(내 차례)에 친다
  - 친구가 자기 차례에 방어 태세를 잡으면 내 차례에 쥐가 친구를 칠 때도 불리하다. 친구의 다음 차례가 오면 지운다
  - 작은 함수: 차례를 받은 쪽은 다시 받지 않고, 다음 주인보다 앞에 서는 쪽만 받는다(같으면 캐릭터가 먼저)
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds import initiative, turn_order
from app.rounds.initiative import Turn, TurnKind
from app.tables.models import GameTable, TurnMode
from tests import test_monster_turns as turns
from tests.sheets import make_sheet

pytestmark = pytest.mark.usefixtures('clean_tables')

me, friend = turns.me, turns.friend
FRIEND_FIRST = [5, 15]
DEFEND = {'kind': 'defend'}


async def rat_table(client: AsyncClient, app: FastAPI, me: dict, friend: dict, dex: int) -> dict:
    """그 민첩의 쥐가 있는 차례대로의 둘의 테이블. 친구가 먼저다."""
    turns.load_dice(app, FRIEND_FIRST)
    rat = make_sheet(max_hp=4, dex=dex)
    return await turns.start_table(client, me, friend, rat_sheet=rat, table_fields={'turn_mode': 'turns'})


def monster_turns(found: list[dict]) -> list[dict]:
    return [turn for turn in found if turn['kind'] == 'monster']


async def stances(session: AsyncSession, table: dict) -> dict:
    query = select(GameTable.turn_stances).where(GameTable.id == uuid.UUID(table['id']))
    return await session.scalar(query.execution_options(populate_existing=True))


async def test_a_quick_rat_strikes_on_the_first_turn_and_only_once(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await rat_table(client, app, me, friend, dex=14)
    turns.load_dice(app, [1] * 10)

    await turns.declare(client, friend, table, '숨을 고른다.')
    await narrated()

    assert len(monster_turns(await turns.turns_of(session, table, 1))) == 1
    turns.load_dice(app, [1] * 10)
    await turns.declare(client, me, table, '숨을 고른다.')
    await narrated()

    # 이번 바퀴에 이미 쳤다
    assert monster_turns(await turns.turns_of(session, table, 2)) == []


async def test_a_slow_rat_strikes_on_the_last_turn(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await rat_table(client, app, me, friend, dex=6)
    dice = turns.load_dice(app, [])

    await turns.declare(client, friend, table, '숨을 고른다.')
    await narrated()

    assert (dice.remaining, monster_turns(await turns.turns_of(session, table, 1))) == (0, [])
    turns.load_dice(app, [1] * 10)
    await turns.declare(client, me, table, '숨을 고른다.')
    await narrated()

    assert len(monster_turns(await turns.turns_of(session, table, 2))) == 1


async def test_a_guard_lasts_until_the_next_turn(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await rat_table(client, app, me, friend, dex=6)
    turns.load_dice(app, [])
    await turns.declare(client, friend, table, '방패를 든다.', DEFEND)
    await narrated()
    assert await stances(session, table) == {str(turns.FRIEND): {'cover': None, 'defend': True}}
    # 내 차례. 쥐가 친구를 고르고(두 번째), 물기를 두 번 굴려 나쁜 것(1)을 쓴다. 그다음 바퀴의 순서(친구가 먼저)
    turns.load_dice(app, [2, 20, 1, *FRIEND_FIRST])

    await turns.declare(client, me, table, '숨을 고른다.')
    await narrated()

    (bite,) = monster_turns(await turns.turns_of(session, table, 2))
    assert (bite['outcome']['user_id'], bite['outcome']['roll'], bite['outcome']['guarded']) == (
        str(turns.FRIEND),
        1,
        True,
    )
    # 친구의 다음 차례가 열렸다. 태세는 거기까지다
    assert await stances(session, table) == {}


# --- 작은 함수 ---


def foe(rank_score: int, key: uuid.UUID, first: bool = False) -> Turn:
    monster = SimpleNamespace(state=SimpleNamespace(id=key))
    return Turn(kind=TurnKind.MONSTER, member=None, monster=monster, first=first, score=rank_score)


def test_a_foe_takes_its_slot_once_and_only_before_the_next_actor():
    done, fast, even, slow, sneaky = (uuid.uuid4() for _ in range(5))
    table = SimpleNamespace(turn_foes=[str(done)])
    before = initiative.rank_of(Turn(kind=TurnKind.PC, member=None, monster=None, first=False, score=10))
    gate = turn_order.FoeGate(table=table, before=before)

    assert gate.due(foe(14, done)) is False
    assert (gate.due(foe(14, fast)), gate.due(foe(10, even)), gate.due(foe(6, slow))) == (True, False, False)
    # 기습한 쪽은 누구보다 앞이다. 바퀴의 마지막 차례(before 가 None)에는 남은 쪽이 모두 받는다
    assert gate.due(foe(6, sneaky, first=True)) is True
    last = turn_order.FoeGate(table=table, before=None)
    assert (last.due(foe(6, slow)), last.due(foe(14, done))) == (True, False)


def test_a_stance_is_kept_from_the_outcome_and_dropped_on_the_next_turn():
    actor = uuid.uuid4()
    covered = SimpleNamespace(user_id=actor, outcome={'cover': {'place': None, 'value': 3}})
    table = SimpleNamespace(turn_mode=TurnMode.TURNS, turn_stances={}, members=[])
    round_ = SimpleNamespace(actor_id=actor, declarations=[covered])

    turn_order.keep_stance(table, round_)

    assert (turn_order.held_covers(table), turn_order.held_defenders(table)) == ({actor: 3}, frozenset())
    assert turn_order.stance_of({'cover': {'value': 0}}) is None
    turn_order.drop_stance(table, actor)
    assert table.turn_stances == {}
