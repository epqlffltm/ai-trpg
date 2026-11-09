# trpg-server/tests/test_defending.py

"""
방어하기(#254, app/rounds/guards.py)를 검증한다. 방어 태세를 잡은 캐릭터를 노린 몬스터와 NPC 의 공격은 불리하다.

판은 다른 테스트 파일의 것을 빌린다. 수로 입구의 수로 쥐(tests/test_monster_turns.py), 싸우는 악역영애
(tests/test_npc_turns.py). 쥐의 물기와 악역영애의 부채 후리기는 보통(목표 15)이다. 캐릭터와 쥐와 인물의 보정은 0 이다.

보는 것.
  - 받기: 방어하는 행동은 늘 받는다. 선언의 결과는 {defend: {guarded: true}} 다
  - 몬스터의 차례: 방어하는 캐릭터를 치면 두 번 굴려 나쁜 것을 쓴다. 결과와 이벤트에 guarded 가 붙는다.
    방어하지 않는 캐릭터를 치면 그대로다(guarded 가 없다)
  - 맞서는 굴림의 판에서도 공격하는 쪽만 불리하다. 받는 쪽은 한 번 굴린다
  - 싸우는 NPC 의 차례: 같다
  - 서술: 캐릭터의 줄에 (방어 태세: …), 차례의 줄에 [방어 태세: 불리]
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds.move_lines import DEFENDING, describe_monster_turn, describe_move
from app.rounds.narrator import MonsterTurnNote, Move
from tests import test_monster_turns as turns
from tests import test_npc_turns as npc_fights

pytestmark = pytest.mark.usefixtures('clean_tables')

DEFEND = {'kind': 'defend'}
# 차례의 주사위(엘프, 쥐). 쥐가 먼저 친다
LATE, EARLY = 1, 20


async def rat_turn(session: AsyncSession, table: dict) -> dict:
    found = await turns.turns_of(session, table)
    return next(turn for turn in found if turn['kind'] == 'monster')['outcome']


async def test_a_bite_on_a_defender_is_rolled_twice_and_keeps_the_worse(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me)
    # 물기를 두 번 굴린다(20, 3). 나쁜 3 을 써서 빗나간다. 방어는 굴림이 없다
    dice = turns.load_dice(app, [LATE, EARLY, 20, 3])

    await turns.declare(client, me, table, '방패를 든다.', DEFEND)
    await narrated()

    assert dice.remaining == 0
    outcome = await rat_turn(session, table)
    assert (outcome['success'], outcome['roll'], outcome['guarded'], outcome['effect']) == (False, 3, True, None)
    events = await turns.events_of(client, me, table)
    attacked = next(event for event in events if event['type'] == 'monster_attacked')
    assert attacked['payload']['guarded'] is True
    rounds = await client.get(turns.table_url(table, '/rounds/1'), headers=me)
    (declaration,) = rounds.json()['declarations']
    assert (declaration['action'], declaration['outcome']) == (DEFEND, {'defend': {'guarded': True}})


async def test_without_defending_the_bite_is_rolled_once(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me)
    # 엘프는 판정을 한다. 물기 20 으로 맞고 피해 3, 그다음 엘프의 판정
    dice = turns.load_dice(app, [LATE, EARLY, 20, 3, 10])

    await turns.declare(client, me, table, turns.REST, turns.rest())
    await narrated()

    assert dice.remaining == 0
    outcome = await rat_turn(session, table)
    assert (outcome['success'], 'guarded' in outcome) == (True, False)


@pytest.mark.opposed
async def test_in_an_opposed_board_only_the_attacker_is_hindered(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me)
    # 물기를 두 번(18, 9), 나쁜 9. 엘프의 민첩 한 번(8). 9 > 8 이라 맞는다. 피해 2
    dice = turns.load_dice(app, [LATE, EARLY, 18, 9, 8, 2])

    await turns.declare(client, me, table, '방패를 든다.', DEFEND)
    await narrated()

    assert dice.remaining == 0
    outcome = await rat_turn(session, table)
    assert (outcome['success'], outcome['roll'], outcome['guarded']) == (True, 9, True)
    assert (outcome['defense']['roll'], outcome['defense']['rolls']) == (8, [8])
    assert outcome['effect']['amount'] == 2


async def test_a_fighting_npc_is_hindered_too(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, npc_fights.ME)
    world = await npc_fights.armed_and_fighting(client, app, me, narrated)
    # 라운드 2. 엘프와 악역영애의 차례 점수가 같아 주사위로 가른다(악역영애가 먼저).
    # 부채 후리기를 두 번(19, 4), 나쁜 4 로 빗나간다
    dice = turns.load_dice(app, [npc_fights.LAST, npc_fights.FIRST, 19, 4])

    await npc_fights.send(client, me, world, DEFEND, content='방패를 든다.')
    await narrated()

    assert dice.remaining == 0
    (turn,) = npc_fights.npc_turns(await turns.turns_of(session, world['table'], 2))
    assert (turn['outcome']['success'], turn['outcome']['guarded'], turn['outcome']['roll']) == (False, True, 4)


# --- 서술 ---


def test_the_lines_tell_the_guard():
    move = Move(character_name='엘프', content='방패를 든다.', defending=True)
    bite = MonsterTurnNote(name='수로 쥐', attack='물기', target='엘프', hit=False, guarded=True)

    assert DEFENDING in describe_move(move)
    assert describe_monster_turn(bite) == '수로 쥐: 엘프에게 물기 (빗나감) [방어 태세: 불리]'
