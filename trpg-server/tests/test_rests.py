# trpg-server/tests/test_rests.py

"""
쉬기(#285, 판 형식 28)를 검증한다.

다섯을 본다.
  - 규칙: 짧은 휴식(SRD5 1시간, 보통 1d8), 긴 휴식(8시간, 최대 HP 까지), 되살아나기(8시간, d20 10 이상),
    저절로 회복하기(SRD5 에는 없다). 말이 안 되는 값은 받지 않는다. 옛 판과 옛 룰북은 SRD5 의 것으로 읽는다.
  - 쉬기(선언): 쉬는 라운드는 적어도 그 휴식의 시간만큼 이어진다. 라운드가 닫힐 때 회복한다.
  - 깨지기: 쉬는 라운드에 맞으면 회복하지 않는다. 몬스터 옆에서도 쉴 수는 있다.
  - 되살아나기: 고비를 넘기고 쓰러진 캐릭터는 한 장면에 규칙의 시간이 흐르면 굴린다. 죽어 가는 캐릭터는 굴리지 않는다.
  - 저절로 회복하기: 규칙이 켰을 때만. 시계의 눈금을 지날 때마다 회복한다.

주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 남은 눈이 없는지까지 본다. 생각과 다르게 굴렸으면 드러난다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_27
from app.engine.action import RestAction
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.rounds import rests
from app.rounds.errors import ActionNotInRulesError
from tests import test_character_death as death_tests
from tests import test_monster_turns as monster_tests
from tests.narration_model import with_model
from tests.test_character_death import (
    FRIEND,
    LAUGH,
    LIVE,
    ME,
    PLAIN,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    declare,
    knock_me_down,
    load_dice,
    read_events,
    read_round,
    saves_of,
    send,
    start_duo,
    table_url,
)
from tests.test_ruleset import load_migration
from tests.test_table_clock import wait

pytestmark = pytest.mark.usefixtures('clean_tables')

# 죽음 테스트의 픽스처를 그대로 쓴다. 방장(엘프)과 함께 앉는 사람(영애). 둘 다 최대 HP 10 이다
me = death_tests.me
friend = death_tests.friend

HOUR = 60
SHORT = {'kind': 'rest', 'length': 'short'}
LONG = {'kind': 'rest', 'length': 'long'}
NAP = '잠깐 숨을 돌린다.'
SLEEP = '모닥불 옆에서 잔다.'


async def set_hp(session: AsyncSession, user_id: uuid.UUID, hp: int) -> None:
    await session.execute(
        text('UPDATE table_sheets SET hp = :hp WHERE user_id = :user_id'), {'hp': hp, 'user_id': user_id}
    )
    await session.commit()


async def make_stable(session: AsyncSession, user_id: uuid.UUID = ME) -> None:
    """쓰러진 캐릭터가 고비를 넘긴 것으로 한다. 죽음의 굴림의 성공(셋)이 다 모였다."""
    await session.execute(
        text('UPDATE table_sheets SET death_successes = 3 WHERE user_id = :user_id'), {'user_id': user_id}
    )
    await session.commit()


async def passed(client: AsyncClient, headers: dict, table: dict) -> int:
    """마지막으로 열린 라운드가 열릴 때 흐른 시간(분)."""
    return (await read_events(client, headers, table, 'round_opened'))[-1]['payload']['passed_minutes']


def rest_outcome(round_: dict, user_id: uuid.UUID = ME) -> dict:
    declaration = next(item for item in round_['declarations'] if item['user_id'] == str(user_id))
    return declaration['outcome']['rest']


# --- 규칙 ---


def test_the_template_rests_the_srd_way():
    rest = SRD5.rest

    assert (rest.short.minutes, rest.short.heal) == (HOUR, 'moderate')
    assert rest.long.minutes == 8 * HOUR
    assert (rest.revive.minutes, rest.revive.target) == (8 * HOUR, 10)
    assert rest.natural is None


def with_rest(**changes) -> dict:
    return {**SRD5.model_dump(mode='json'), 'rest': {**SRD5.model_dump(mode='json')['rest'], **changes}}


@pytest.mark.parametrize(
    'rules',
    [
        # 짧은 휴식이 긴 휴식보다 짧지 않다
        with_rest(short={'minutes': 8 * HOUR, 'heal': 'moderate'}),
        # 규칙에 없는 등급
        with_rest(short={'minutes': HOUR, 'heal': 'huge'}),
        with_rest(natural={'every_minutes': HOUR, 'heal': 'huge'}),
        # 되살아나기의 목표값이 d20 의 가장 큰 눈보다 크다
        with_rest(revive={'minutes': HOUR, 'target': 21}),
        # 저절로 회복하는 간격이 너무 짧다, 한 장면에 담을 수 없을 만큼 길다
        with_rest(natural={'every_minutes': 9, 'heal': 'light'}),
        with_rest(long={'minutes': 7 * 24 * HOUR + 1}),
        with_rest(unknown=1),
    ],
)
def test_rejects_a_rest_that_makes_no_sense(rules: dict):
    with pytest.raises(ValidationError):
        Ruleset.model_validate(rules)


def test_a_ruleset_may_have_no_rest_or_no_revival():
    no_rest = Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'rest': None})
    no_revival = Ruleset.model_validate(with_rest(revive=None))

    assert no_rest.rest is None
    assert no_revival.rest.revive is None


def test_an_old_version_reads_the_template_rest():
    old = {'format': 27, 'rulebook': {'title': '룰북', 'rules': {'die': 20}}}

    upgraded = upgrade_from_27(old)

    assert upgraded['rulebook']['rules'] == {'die': 20, 'rest': SRD5.model_dump(mode='json')['rest']}
    assert upgraded['format'] == 28
    assert 'rest' not in old['rulebook']['rules']
    assert UPGRADES[27] is upgrade_from_27


def test_the_migration_fills_the_same_rest_and_takes_it_back():
    migration = load_migration('rulebook_rest')
    old = {'die': 20}

    filled = migration.with_rest(old)

    assert filled['rest'] == SRD5.model_dump(mode='json')['rest']
    # 두 번 돌려도 같고, 이미 있는 쉬기는 건드리지 않는다
    assert migration.with_rest(filled) == filled
    assert migration.with_rest({'rest': None}) == {'rest': None}
    assert migration.without_rest(filled) == old


def test_a_ruleset_without_rest_refuses_resting():
    no_rest = Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'rest': None})

    with pytest.raises(ActionNotInRulesError):
        rests.accept_rest(no_rest, RestAction(kind='rest', length='short'))


# --- 쉬기 ---


async def test_a_short_rest_heals_by_the_rule_and_takes_an_hour(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await set_hp(session, ME, 3)
    dice = load_dice(app, [5])

    await declare(client, me, table, NAP, SHORT)
    await declare(client, friend, table, LAUGH)
    await narrated()

    assert rest_outcome(await read_round(client, me, table, 1)) == {
        'length': 'short',
        'minutes': HOUR,
        'rested': True,
        'reason': None,
        'rolls': [5],
        'before': 3,
        'after': 8,
        'max_hp': 10,
    }
    assert (await saves_of(client, me, table, '엘프'))[0] == 8
    assert await passed(client, me, table) == HOUR
    assert dice.remaining == 0


async def test_a_long_rest_heals_fully_and_takes_eight_hours(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await set_hp(session, ME, 2)
    dice = load_dice(app, [])

    await declare(client, me, table, SLEEP, LONG)
    await declare(client, friend, table, LAUGH)
    await narrated()

    outcome = rest_outcome(await read_round(client, me, table, 1))
    assert (outcome['rolls'], outcome['before'], outcome['after']) == ([], 2, 10)
    assert await passed(client, me, table) == 8 * HOUR
    assert dice.remaining == 0


async def test_the_longer_rest_sets_the_pace(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    load_dice(app, [4])

    await declare(client, me, table, NAP, SHORT)
    await declare(client, friend, table, SLEEP, LONG)
    await narrated()

    # 한 사람이 여덟 시간 자면 그 라운드는 모두에게 여덟 시간이다
    assert await passed(client, me, table) == 8 * HOUR


async def test_the_rest_is_shown_to_everyone(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await set_hp(session, ME, 3)
    load_dice(app, [5])

    await declare(client, me, table, NAP, SHORT)
    await declare(client, friend, table, LAUGH)
    await narrated()

    (rested,) = await read_events(client, friend, table, 'character_rested')
    assert rested['actor_id'] is None
    assert rested['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '엘프',
        'cause': 'rest',
        'length': 'short',
        'rested': True,
        'reason': None,
        'rolls': [5],
        'before': 3,
        'after': 8,
        'max_hp': 10,
    }


@pytest.mark.parametrize('length', ['nap', '', None])
async def test_an_unknown_length_is_refused(client: AsyncClient, me: dict, friend: dict, length):
    table = await start_duo(client, me, friend)

    response = await send(client, me, table, NAP, {'kind': 'rest', 'length': length})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 깨지기 ---


@pytest.fixture
def solo(signing_key) -> dict[str, str]:
    """쥐가 있는 수로에 혼자 앉는 사람의 머리말."""
    return monster_tests.bearer(signing_key, ME)


async def test_resting_beside_a_monster_is_broken_by_its_hit(
    client: AsyncClient, app: FastAPI, solo: dict, session: AsyncSession
):
    # 쥐가 먼저(민첩 14). 물기 20(맞힘), 피해 3. 엘프는 쉰다(굴리지 않는다). 다쳤으니 회복을 굴리지 않는다
    dice = monster_tests.load_dice(app, [monster_tests.PASS, 3])
    table = await monster_tests.start_table(client, solo, rat_sheet=monster_tests.make_sheet(max_hp=4, dex=14))

    closing = await monster_tests.declare(client, solo, table, NAP, SHORT)

    outcome = rest_outcome(closing)
    assert (outcome['rested'], outcome['reason']) == (False, 'hurt')
    assert (outcome['rolls'], outcome['before'], outcome['after']) == ([], 7, 7)
    assert await monster_tests.hp_of(session, table) == 7
    assert dice.remaining == 0


async def test_resting_beside_a_monster_works_when_it_misses(
    client: AsyncClient, app: FastAPI, solo: dict, session: AsyncSession
):
    # 쉴 수 없는 곳은 없다. 쥐가 빗나가면(1) 쉰 만큼 회복한다(1d8 의 5)
    dice = monster_tests.load_dice(app, [monster_tests.FAIL, 5])
    table = await monster_tests.start_table(client, solo, rat_sheet=monster_tests.make_sheet(max_hp=4, dex=14))
    await set_hp(session, ME, 4)

    closing = await monster_tests.declare(client, solo, table, NAP, SHORT)

    assert rest_outcome(closing)['rested'] is True
    assert await monster_tests.hp_of(session, table) == 9
    assert dice.remaining == 0


# --- 되살아나기 ---


async def test_a_stable_character_gets_up_after_a_long_rest(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await make_stable(session)
    # 고비를 넘겨 죽음의 굴림은 굴리지 않는다. 친구가 여덟 시간 자는 동안 되살아나기 15(목표 10)
    dice = load_dice(app, [15])

    await declare(client, friend, table, SLEEP, LONG)
    await narrated()

    assert await saves_of(client, me, table, '엘프') == (1, 0, 0, False)
    (revived,) = await read_events(client, friend, table, 'character_revived')
    assert revived['payload'] == {
        'round': 2,
        'user_id': str(ME),
        'character_name': '엘프',
        'roll': 15,
        'target': 10,
        'success': True,
        'hp': 1,
    }
    assert dice.remaining == 0


async def test_a_failed_revival_leaves_the_character_down(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await make_stable(session)
    dice = load_dice(app, [5])

    await declare(client, friend, table, SLEEP, LONG)
    await narrated()

    # 쓰러진 채로, 고비를 넘긴 채로 있다. 다음에 그만큼 흐르면 다시 굴린다
    assert await saves_of(client, me, table, '엘프') == (0, 3, 0, False)
    (revived,) = await read_events(client, friend, table, 'character_revived')
    assert (revived['payload']['success'], revived['payload']['hp']) == (False, 0)
    assert dice.remaining == 0


async def test_a_dying_character_does_not_revive(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    # 아직 죽어 가는 중이다. 죽음의 굴림(15, 성공)만 굴리고 되살아나기는 굴리지 않는다
    dice = load_dice(app, [LIVE])

    await declare(client, friend, table, SLEEP, LONG)
    await narrated()

    assert await saves_of(client, me, table, '엘프') == (0, 1, 0, False)
    assert await read_events(client, friend, table, 'character_revived') == []
    assert dice.remaining == 0


async def test_a_short_scene_does_not_revive(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await make_stable(session)
    # 친구의 짧은 휴식(1시간)으로는 되살아나기에 모자란다. 친구는 가득 차 있어도 회복을 굴린다(1d8 의 3)
    dice = load_dice(app, [3])

    await declare(client, friend, table, NAP, SHORT)
    await narrated()

    assert await read_events(client, friend, table, 'character_revived') == []
    assert dice.remaining == 0


# --- 저절로 회복하기 ---


async def start_with_natural_recovery(client: AsyncClient, me: dict, friend: dict, session: AsyncSession) -> dict:
    """
    한 시간마다 가볍게(1d4) 저절로 회복하는 룰북으로 시작한 테이블.

    룰북은 템플릿에서만 만든다. 판을 굳히기 전에 DB 에서 룰북의 쉬기를 고친다. 판은 굳힐 때의 룰북을 담는다.
    """
    rulebook = (await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)).json()
    natural = '{"every_minutes": 60, "heal": "light"}'
    await session.execute(
        text("UPDATE rulebooks SET rules = jsonb_set(rules, '{rest,natural}', CAST(:natural AS JSONB))"),
        {'natural': natural},
    )
    await session.commit()
    body = {'title': '추격전', 'rulebook_id': rulebook['id'], 'openings': ['사이렌이 울린다.'], 'default_sheet': PLAIN}
    scenario = (await client.post(SCENARIOS_URL, json=with_model(body), headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def test_the_clock_heals_when_the_rules_say_so(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_with_natural_recovery(client, me, friend, session)
    await set_hp(session, ME, 3)
    # 둘이 두 시간을 기다린다. 8시에서 10시까지 눈금 둘(9시, 10시)을 지난다.
    # 엘프는 2, 3 을 회복한다. 친구는 가득 차 있어 굴리지 않는다. 기다리는 것은 쉬는 것이 아니다
    dice = load_dice(app, [2, 3])

    await declare(client, me, table, LAUGH, wait(2 * HOUR))
    await declare(client, friend, table, LAUGH, wait(2 * HOUR))
    await narrated()

    assert (await saves_of(client, me, table, '엘프'))[0] == 8
    (recovered,) = await read_events(client, friend, table, 'character_rested')
    payload = recovered['payload']
    assert (payload['cause'], payload['length'], payload['rolls'], payload['after']) == ('natural', None, [2, 3], 8)
    assert dice.remaining == 0


async def test_the_template_does_not_heal_by_itself(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    await set_hp(session, ME, 3)
    dice = load_dice(app, [])

    await declare(client, me, table, LAUGH, wait(8 * HOUR))
    await declare(client, friend, table, LAUGH, wait(8 * HOUR))
    await narrated()

    # 쉬지 않으면 여덟 시간이 흘러도 그대로다
    assert (await saves_of(client, me, table, '엘프'))[0] == 3
    assert dice.remaining == 0


# --- 작은 함수들 ---


def member(hp: int = 5, died: bool = False) -> SimpleNamespace:
    """앉은 사람 하나. 휴식이 깨졌는지 보는 데 쓰는 칸만 있다."""
    sheet = SimpleNamespace(hp=0 if died else hp, max_hp=10, died_at='2026-10-16' if died else None)
    return SimpleNamespace(user_id=ME, sheet=sheet)


@pytest.mark.parametrize(
    ('who', 'hurt', 'reason'),
    [
        (member(), set(), None),
        (member(), {ME}, rests.Broken.HURT),
        (member(hp=0), {ME}, rests.Broken.DOWNED),
        (member(died=True), {ME}, rests.Broken.DEAD),
        # 다친 다른 사람은 이 사람의 휴식을 깨지 않는다
        (member(), {FRIEND}, None),
    ],
)
def test_what_breaks_a_rest(who: SimpleNamespace, hurt: set, reason):
    assert rests.broken_by(who, hurt) == reason


@pytest.mark.parametrize(
    ('start', 'end', 'ticks'),
    [
        # 8시 → 8시 10분: 눈금을 지나지 않는다. 8시 50분 → 9시 10분: 9시를 지난다
        (8 * HOUR, 8 * HOUR + 10, 0),
        (8 * HOUR + 50, 9 * HOUR + 10, 1),
        # 정각에 열려 정각에 끝나면 끝나는 정각만 센다
        (8 * HOUR, 10 * HOUR, 2),
    ],
)
def test_ticks_are_counted_on_the_clock(start: int, end: int, ticks: int):
    natural = Ruleset.model_validate(with_rest(natural={'every_minutes': HOUR, 'heal': 'light'})).rest.natural

    assert rests.ticks_between(natural, start, end) == ticks
