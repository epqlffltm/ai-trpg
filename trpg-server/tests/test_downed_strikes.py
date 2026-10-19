# trpg-server/tests/test_downed_strikes.py

"""
몬스터와 싸우는 NPC 가 쓰러진 캐릭터를 치는 것(#369, app/rounds/downed_strikes.py)을 검증한다.

판은 test_monster_turns.py 의 것이다. 수로 입구에 수로 쥐가 있고 쥐가 먼저 움직인다(민첩 14).
엘프의 최대 HP 는 2 라서 물기(가벼움 1d4)에 4 를 맞으면 큰 타격으로 쓰러진다(SRD5 는 최대 HP 의 50%).
룰북은 SRD5 다. 죽음의 굴림은 d20, 목표 10, 실패 3 번이면 죽는다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.

보는 것.
  - 라운드를 닫기 시작할 때 이미 쓰러져 있던 캐릭터는 대상이다. 이번 라운드에 쓰러진 캐릭터는 아니다.
  - 맞히면 피해 없이 죽음의 굴림 실패가 쌓인다. 큰 타격으로 쓰러졌으면 2, 아니면 1 이다. 빗나가면 아무 일도 없다.
  - 실패가 다 모이면 그 자리에서 죽는다. 이벤트는 죽음의 굴림으로 죽었을 때와 같고(character_died) 까닭이 다르다.
  - 일행이 모두 쓰러져도 몬스터가 마무리한다. 서술의 줄에 실패의 수가 붙는다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import death
from app.engine.health import Change, ChangeKind
from app.engine.injury import is_big_hit
from app.engine.ruleset import InjuryTriggers
from app.engine.templates import SRD5
from app.rounds.downed_strikes import can_be_struck, strike_downed
from app.rounds.move_lines import describe_monster_turn
from app.rounds.narrator import DownedStrikeNote, MonsterTurnNote
from app.rounds.npc_attacks import targets_of
from app.tables.models import TableSheet
from app.tables.sheets import clear_death_saves
from tests.sheets import make_sheet
from tests.test_monster_turns import (
    FAIL,
    ME,
    PASS,
    REST,
    bearer,
    declare,
    events_of,
    load_dice,
    rest,
    start_table,
    turns_of,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

# 쓰러질 때 굴리는 부상 표(d20)의 눈. 1~10 은 부상이 없다
NO_INJURY = 1
# 죽음의 굴림의 눈. 목표 10
SAVE_PASS = 20
QUICK = make_sheet(max_hp=4, dex=14)


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def sheet_of(session: AsyncSession, table: dict) -> TableSheet:
    query = select(TableSheet).where(TableSheet.table_id == uuid.UUID(table['id']), TableSheet.user_id == ME)
    return await session.scalar(query.execution_options(populate_existing=True))


async def downed_in_round_one(client: AsyncClient, app: FastAPI, me: dict, narrated, count: int = 1) -> dict:
    """라운드 1. 쥐가 물기(4)로 엘프를 큰 타격으로 쓰러뜨린다. 엘프는 차례를 잃는다."""
    table = await start_table(client, me, rat_sheet=QUICK, sheet=make_sheet(max_hp=2), count=count)
    load_dice(app, [PASS, 4, NO_INJURY] if count == 1 else [20, 1, PASS, 4, NO_INJURY])
    await declare(client, me, table, REST, rest())
    await narrated()
    return table


# --- 대상 ---


async def test_a_character_downed_this_round_is_not_struck_again(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    # 쥐 둘. 앞의 쥐가 엘프를 쓰러뜨리고, 뒤의 쥐는 칠 캐릭터가 없다
    table = await downed_in_round_one(client, app, me, narrated, count=2)

    first, second, lost = await turns_of(session, table, 1)

    assert first['outcome']['effect']['downed'] is True
    assert second['outcome'] == {'skipped': 'no_target'}
    assert lost['kind'] == 'pc'
    sheet = await sheet_of(session, table)
    assert (sheet.hp, sheet.downed_by_big_hit, sheet.death_failures) == (0, True, 0)


async def test_a_character_already_down_is_struck_and_fails_twice_after_a_big_hit(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await downed_in_round_one(client, app, me, narrated)
    # 라운드 2. 엘프는 글만 낸다. 쥐가 쓰러진 엘프를 맞힌다(피해의 눈 없음), 그다음 라운드 끝의 죽음의 굴림(성공)
    dice = load_dice(app, [PASS, SAVE_PASS])

    await declare(client, me, table, '숨을 헐떡인다.')
    await narrated()

    (turn,) = await turns_of(session, table, 2)
    assert turn['outcome']['effect'] is None
    assert turn['outcome']['downed_strike'] == {'added': 2, 'failures': 2, 'limit': 3, 'fate': 'dying'}
    sheet = await sheet_of(session, table)
    assert (sheet.death_successes, sheet.death_failures, sheet.died_at) == (1, 2, None)
    assert dice.remaining == 0


async def test_a_miss_on_a_downed_character_does_nothing(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await downed_in_round_one(client, app, me, narrated)
    load_dice(app, [FAIL, SAVE_PASS])

    await declare(client, me, table, '숨을 헐떡인다.')
    await narrated()

    (turn,) = await turns_of(session, table, 2)
    assert turn['outcome']['downed_strike'] == {'added': 0, 'failures': 0, 'limit': 3, 'fate': 'dying'}
    assert (await sheet_of(session, table)).death_failures == 0


async def test_the_monster_finishes_off_a_party_that_is_all_down(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await downed_in_round_one(client, app, me, narrated)
    load_dice(app, [PASS, SAVE_PASS])
    await declare(client, me, table, '숨을 헐떡인다.')
    await narrated()
    # 라운드 3. 또 맞아 실패가 다 모인다(2 + 2 이지만 3 에서 멈춘다). 죽었으니 죽음의 굴림은 없다
    dice = load_dice(app, [PASS])

    await declare(client, me, table, '눈을 감는다.')
    await narrated()

    (turn,) = await turns_of(session, table, 3)
    assert turn['outcome']['downed_strike'] == {'added': 1, 'failures': 3, 'limit': 3, 'fate': 'dead'}
    assert (await sheet_of(session, table)).died_at is not None
    assert dice.remaining == 0


async def test_the_strike_and_the_death_are_recorded_and_narrated(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    table = await downed_in_round_one(client, app, me, narrated)
    load_dice(app, [PASS, SAVE_PASS])
    await declare(client, me, table, '숨을 헐떡인다.')
    await narrated()
    load_dice(app, [PASS])
    await declare(client, me, table, '눈을 감는다.')
    await narrated()

    events = await events_of(client, me, table)
    attacks = [event for event in events if event['type'] == 'monster_attacked']
    (died,) = [event for event in events if event['type'] == 'character_died']

    assert attacks[-1]['payload']['downed_strike'] == {'added': 1, 'failures': 3, 'limit': 3, 'fate': 'dead'}
    assert 'roll' not in attacks[-1]['payload']
    assert died['caused_by_sequence'] == attacks[-1]['sequence']
    assert died['payload'] == {'round': 3, 'user_id': str(ME), 'character_name': '엘프', 'cause': 'struck_down'}
    narrations = [event for event in events if event['type'] == 'gm_narration']
    assert (
        '쓰러진 엘프에게 물기 (맞음) → 엘프 죽음의 굴림 실패 +2 (실패 2/3, 죽어 가는 중)'
        in (narrations[-2]['payload']['text'])
    )
    assert '→ 엘프 죽음의 굴림 실패 +1 (실패 3/3, 죽음)' in narrations[-1]['payload']['text']


# --- DB 를 쓰지 않는 작은 함수들 ---


def change(amount: int, before: int = 10, kind: ChangeKind = ChangeKind.DAMAGE) -> Change:
    return Change(kind=kind, rolls=(amount,), amount=amount, before=before, after=max(before - amount, 0))


@pytest.mark.parametrize(
    ('hit', 'expected'),
    [(change(5), True), (change(4), False), (change(9, before=3), True), (change(5, kind=ChangeKind.RECOVERY), False)],
)
def test_a_big_hit_is_half_the_max_hp_in_srd5(hit: Change, expected: bool):
    assert is_big_hit(SRD5, hit, 10) is expected


def test_without_big_hits_in_the_rules_nothing_is_big():
    triggers = InjuryTriggers(big_hit_percent=None, downed=True, called_shot=True)
    rules = SRD5.model_copy(update={'injury_triggers': triggers})

    assert is_big_hit(rules, change(10), 10) is False


@pytest.mark.parametrize(
    ('successes', 'failures', 'count', 'expected'),
    [
        (0, 0, 1, death.Struck(added=1, failures=1, limit=3, fate=death.Fate.DYING)),
        (1, 1, 2, death.Struck(added=2, failures=3, limit=3, fate=death.Fate.DEAD)),
        # 죽는 수를 넘겨 세지 않는다
        (0, 2, 2, death.Struck(added=1, failures=3, limit=3, fate=death.Fate.DEAD)),
        # 고비를 넘긴 캐릭터도 쌓이고, 닿지 않으면 고비를 넘긴 채다
        (3, 0, 1, death.Struck(added=1, failures=1, limit=3, fate=death.Fate.STABLE)),
        (3, 2, 1, death.Struck(added=1, failures=3, limit=3, fate=death.Fate.DEAD)),
        # 빗나감
        (0, 1, 0, death.Struck(added=0, failures=1, limit=3, fate=death.Fate.DYING)),
    ],
)
def test_failures_pile_up_to_the_limit(successes: int, failures: int, count: int, expected: death.Struck):
    assert death.add_failures(SRD5.death_save, successes, failures, count) == expected


def test_a_big_hit_makes_a_downed_character_fail_twice():
    assert (death.struck_failures(True), death.struck_failures(False)) == (2, 1)


def member(hp: int = 10, dead: bool = False, **fields) -> SimpleNamespace:
    sheet = SimpleNamespace(
        hp=hp,
        died_at=object() if dead else None,
        death_successes=0,
        death_failures=0,
        downed_by_big_hit=False,
        **fields,
    )
    return SimpleNamespace(user_id=uuid.uuid4(), sheet=sheet)


def judging_with(*members: SimpleNamespace, downed=(), rules=SRD5) -> SimpleNamespace:
    return SimpleNamespace(
        ruleset=rules,
        downed_at_start=frozenset(person.user_id for person in downed),
        table=SimpleNamespace(members=list(members)),
    )


def test_who_can_be_struck():
    standing, fresh, old, dead = member(), member(hp=0), member(hp=0), member(hp=0, dead=True)
    judging = judging_with(standing, fresh, old, dead, downed=[old, dead])

    assert [can_be_struck(judging, person) for person in (standing, fresh, old, dead)] == [True, False, True, False]


def test_without_death_saves_a_downed_character_is_never_struck():
    old = member(hp=0)
    rules = SRD5.model_copy(update={'death_save': None})

    assert can_be_struck(judging_with(old, downed=[old], rules=rules), old) is False


def test_a_fighting_npc_also_strikes_those_already_down():
    standing, fresh, old = member(), member(hp=0), member(hp=0)

    assert targets_of(judging_with(standing, fresh, old, downed=[old])) == [standing, old]


def test_an_ordinary_fall_fails_once():
    old = member(hp=0)

    struck = strike_downed(judging_with(old, downed=[old]), old, hit=True)

    assert struck == {'added': 1, 'failures': 1, 'limit': 3, 'fate': 'dying'}
    assert old.sheet.death_failures == 1


def test_getting_up_forgets_how_one_fell():
    sheet = SimpleNamespace(death_successes=2, death_failures=1, downed_by_big_hit=True)

    clear_death_saves(sheet)

    assert (sheet.death_successes, sheet.death_failures, sheet.downed_by_big_hit) == (0, 0, False)


def test_the_line_says_the_target_was_down():
    note = MonsterTurnNote(
        name='수로 쥐',
        attack='물기',
        target='엘프',
        hit=False,
        downed=DownedStrikeNote(added=0, failures=1, limit=3, fate='dying'),
    )

    assert describe_monster_turn(note) == '수로 쥐: 쓰러진 엘프에게 물기 (빗나감)'
