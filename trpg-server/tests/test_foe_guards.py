# trpg-server/tests/test_foe_guards.py

"""
몬스터와 NPC 의 방어하기(#254, app/rounds/foe_guards.py)를 검증한다.

판은 다른 테스트 파일의 것을 빌린다. 수로 입구의 수로 쥐(tests/test_monster_turns.py, 최대 HP 4, 물기)와
싸우는 악역영애(tests/test_npc_turns.py). 엘프는 민첩 14 로 쥐보다 먼저다(차례의 주사위가 없다).
엘프의 걷어차기는 근력 보통(목표 15), 피해 1d8 이다. 판은 고정 난이도다(tests/conftest.py).

보는 것.
  - 시트: defends(below, chance)를 저장하고 판에 굳힌다. 둘 다 비우면 422 다
  - 정하기: 확률이면 판정 전에 d100 을 굴린다. HP 가 문턱 이하이면 굴리지 않고 방어한다
  - 방어하는 쥐는 치지 않는다(skipped defending). 그 쥐를 노린 걷어차기는 불리하고 결과에 guarded 가 붙는다
  - 방어하지 않으면 그대로다
  - 싸우는 NPC 도 같다
  - 서술: 차례의 줄 (방어 태세를 잡음 (치지 않음))
"""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import Defends
from app.assets.scenarios.snapshot import DefendsSnapshot
from app.engine.dice import ScriptedDice
from app.engine.templates import SRD5
from app.rounds import foe_guards
from app.rounds.monster_scene import SceneMonster
from app.rounds.move_lines import describe_monster_turn
from app.rounds.narration_request import to_monster_turn
from app.rounds.state import required
from app.tables.models import TableInjury
from tests import test_monster_npc_attacks as bystanders
from tests import test_monster_turns as turns
from tests import test_npc_actions as npc_actions
from tests import test_npc_steals as npc_steals
from tests import test_npc_turns as npc_fights
from tests.sheets import make_sheet

pytestmark = pytest.mark.usefixtures('clean_tables')

HALF = {'defends': {'chance': 50}}


async def kick_the_rat(client: AsyncClient, me: dict, table: dict, narrated) -> None:
    rat = (await turns.monsters_of(client, me, table))[0]
    await turns.declare(client, me, table, turns.KICK, turns.kick(rat['id']))
    await narrated()


async def outcomes(client: AsyncClient, me: dict, session: AsyncSession, table: dict) -> tuple[dict, dict]:
    """(엘프의 판정, 쥐의 차례)."""
    rounds = await client.get(turns.table_url(table, '/rounds/1'), headers=me)
    (declaration,) = rounds.json()['declarations']
    found = await turns.turns_of(session, table)
    return declaration['outcome'], next(turn for turn in found if turn['kind'] == 'monster')['outcome']


# --- 몬스터 ---


async def test_a_guarding_rat_holds_back_and_the_kick_is_hindered(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me, sheet=make_sheet(dex=14), rat_fields=HALF)
    # 확률(50) 의 주사위 10 → 방어한다. 걷어차기를 두 번(20, 3), 나쁜 3 으로 빗나간다. 쥐는 치지 않는다
    dice = turns.load_dice(app, [10, 20, 3])

    await kick_the_rat(client, me, table, narrated)

    assert dice.remaining == 0
    kick, rat = await outcomes(client, me, session, table)
    assert (kick['success'], kick['roll'], kick['guarded']) == (False, 3, True)
    assert rat == {'skipped': 'defending'}


async def test_a_rat_that_fails_the_chance_strikes_as_ever(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me, sheet=make_sheet(dex=14), rat_fields=HALF)
    # 확률의 주사위 60 → 방어하지 않는다. 걷어차기 1 로 빗나간다. 물기 1 로 빗나간다
    dice = turns.load_dice(app, [60, 1, 1])

    await kick_the_rat(client, me, table, narrated)

    assert dice.remaining == 0
    kick, rat = await outcomes(client, me, session, table)
    assert (kick['success'], kick.get('guarded')) == (False, None)
    assert (rat['success'], 'guarded' in rat) == (False, False)


async def test_a_hurt_rat_guards_without_a_roll(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me, sheet=make_sheet(dex=14), rat_fields={'defends': {'below': 50}})
    await session.execute(text('UPDATE table_monsters SET hp = 2 WHERE table_id = :id'), {'id': table['id']})
    await session.commit()
    # HP 2/4 는 50% 이하라 굴리지 않고 방어한다. 걷어차기를 두 번(1, 1)
    dice = turns.load_dice(app, [1, 1])

    await kick_the_rat(client, me, table, narrated)

    assert dice.remaining == 0
    _, rat = await outcomes(client, me, session, table)
    assert rat == {'skipped': 'defending'}


# --- 싸우는 NPC ---


async def test_a_fighting_npc_may_guard_too(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, npc_fights.ME)
    world = await npc_steals.start(client, me, attitude='hostile', attacks=[npc_fights.SWIPE], defends={'chance': 100})
    turns.load_dice(app, [npc_actions.FAIL])
    await npc_steals.send(client, me, world, npc_actions.punch(world['lady']['id']), content=npc_actions.PUNCH)
    await narrated()
    # 라운드 2. 싸우는 악역영애가 확률(100)의 주사위 1 로 방어한다. 엘프는 글만 낸다
    dice = turns.load_dice(app, [1])

    await npc_fights.laugh(client, me, world)
    await narrated()

    assert dice.remaining == 0
    (turn,) = npc_fights.npc_turns(await turns.turns_of(session, world['table'], 2))
    assert turn['outcome'] == {'skipped': 'defending'}


async def test_a_monster_striking_a_guarding_npc_is_hindered(
    client: AsyncClient, app: FastAPI, signing_key, session: AsyncSession, narrated
):
    me = turns.bearer(signing_key, turns.ME)
    world = await bystanders.make_world(client, me)
    body = bystanders.scenario_body(world)
    healer = body['npc_sheets'][0]
    healer.update(attitude='hostile', attacks=[npc_fights.SWIPE], defends={'chance': 100})
    world = {**world, 'table': await bystanders.open_table(client, me, body)}
    # 라운드 1. 쥐가 먼저 엘프를 고르고 빗나간다. 엘프의 주먹이 빗나가 약사와 싸움이 붙는다
    turns.load_dice(app, [bystanders.LATE, bystanders.EARLY, bystanders.ELF, 1, 1])
    await npc_steals.send(client, me, world, npc_actions.punch(world['healer']['id']), content=npc_actions.PUNCH)
    await narrated()
    # 라운드 2. 약사가 확률(100)로 방어한다. 쥐와 약사의 차례 점수가 같아 주사위로 가른다(쥐 20, 약사 1).
    # 쥐가 약사를 고르고, 물기를 두 번(20, 3) 굴려 나쁜 3 으로 빗나간다
    dice = turns.load_dice(app, [1, 20, 1, bystanders.HEALER, 20, 3])

    await npc_fights.laugh(client, me, world)
    await narrated()

    assert dice.remaining == 0
    found = await turns.turns_of(session, world['table'], 2)
    rat = next(turn for turn in found if turn['kind'] == 'monster')['outcome']
    healer_turn = next(turn for turn in found if turn['kind'] == 'npc')['outcome']
    assert (rat['target_name'], rat['success'], rat['guarded'], rat['roll']) == ('약사', False, True, 3)
    assert healer_turn == {'skipped': 'defending'}


# --- 시트 ---


async def test_the_sheet_keeps_when_to_guard(client: AsyncClient, signing_key, session: AsyncSession):
    me = turns.bearer(signing_key, turns.ME)
    table = await turns.start_table(client, me, rat_fields={'defends': {'below': 30, 'chance': 20}})
    response = await client.get(turns.table_url(table), headers=me)

    assert response.status_code == status.HTTP_200_OK
    stored = await session.scalar(text('SELECT content FROM game_tables WHERE id = :id'), {'id': table['id']})
    assert stored['monsters'][0]['defends'] == {'below': 30, 'chance': 20}
    with pytest.raises(ValidationError, match='below 나 chance'):
        Defends()


# --- 작은 함수들 ---


def test_when_a_foe_guards():
    dice = ScriptedDice([70, 30, 50])

    assert foe_guards.wants_guard(None, 1, 10, dice) is False
    assert foe_guards.wants_guard(DefendsSnapshot(below=30), 3, 10, dice) is True
    assert foe_guards.wants_guard(DefendsSnapshot(below=30), 4, 10, dice) is False
    # 문턱 위면 확률을 굴린다. 70 > 50 이라 방어하지 않고, 다음 30 ≤ 50 이라 방어한다
    assert foe_guards.wants_guard(DefendsSnapshot(below=30, chance=50), 4, 10, dice) is False
    assert foe_guards.wants_guard(DefendsSnapshot(chance=50), 10, 10, dice) is True
    # 확률과 같은 눈도 방어한다(이하)
    assert foe_guards.wants_guard(DefendsSnapshot(chance=50), 10, 10, dice) is True
    assert dice.remaining == 0


def test_a_stunned_foe_cannot_guard():
    stunned = cast(
        SceneMonster,
        SimpleNamespace(
            state=SimpleNamespace(id=1, hp=1, max_hp=10, injuries=[TableInjury(injury='stunned')]),
            definition=SimpleNamespace(defends=DefendsSnapshot(below=50)),
        ),
    )

    assert foe_guards.decide(SRD5, [stunned], [], ScriptedDice([])) == frozenset()


def test_the_turn_line_tells_the_guard():
    note = required(to_monster_turn({'name': '수로 쥐', 'outcome': {'skipped': 'defending'}}), 'monster')

    assert describe_monster_turn(note) == '수로 쥐: 방어 태세를 잡음 (치지 않음)'
