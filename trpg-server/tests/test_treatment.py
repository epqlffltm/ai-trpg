# trpg-server/tests/test_treatment.py

"""
치료와 오래 가는 부상의 회복(#114 다)을 검증한다.

오래 가는 부상(팔 골절, 다리 부상)은 입을 때 나을 게임 안의 시각(heals_at, 분)이 적히고(달력 2단계),
라운드가 닫힐 때 그 장면이 끝나는 때가 그 시각에 닿았으면 낫는다.
치료하는 행동(kind: treat)은 규칙의 치료 능력(srd5 는 지혜)과 그 부상의 치료 난이도로 판정한다.
  - 성공하면 나을 시각이 treat_minutes 만큼 앞당겨진다. 이 장면이 끝나는 때에 닿으면 그 자리에서 낫는다.
  - 실패하면 치료 실패 표(d100)를 굴린다. 아무 일 없음, 좀 아픔, 덧남, 즉사.
나을 때는 어느 길이든 후유증 표를 굴린다.

srd5 템플릿(판 형식 25): 팔 골절은 14일 뒤에 낫고 치료는 어려움(20), 성공마다 3일. 다리 부상은 7일, 보통(15), 2일.
엘프의 지혜는 10(보정 0)이다.
치료 실패 표: 1 즉사, 2~10 크게 덧남(+2일, 보통 피해), 11~30 덧남(+1일), 31~50 좀 아픔(가벼운 피해),
51~100 아무 일 없음.
테이블은 1일째 8시(480분)에 시작하고 첫 라운드의 장면은 8시 10분(490분)에 끝난다(기본 걸음 10분).

부상은 싸워서 입히지 않고 DB 에 바로 적어 둔다(wound). 치료와 회복만 보려는 것이다.
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.tokens import SigningKey
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_14
from app.calendar.clock import read_time
from app.engine.action import ActionKind, CheckAction, TreatAction, find_treat_fault, read_action
from app.engine.dice import ScriptedDice
from app.engine.injury import NO_HINDRANCE, Hindrance, ends_after, find_injury, heals_at, roll_aftermath
from app.engine.ruleset import Mishap, Ruleset
from app.engine.templates import SRD5
from app.engine.treatment import is_healed, lengthened, roll_mishap, shortened, treat, treatable
from app.rounds import prompt, service
from app.rounds.move_lines import describe_move, describe_treatment
from app.rounds.narrator import HealNote, Move, TreatmentNote
from app.tables.models import NpcStatus, TableInjury, TableSheet
from tests.test_injuries import make_format_13
from tests.test_npc_actions import (
    RecordingNarrator,
    bearer,
    declare,
    events_of,
    load_dice,
    people,
    send,
    start_table,
    state_of,
    table_url,
)
from tests.test_ruleset import load_migration
from tests.test_table_clock import wait

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

TREAT = '부러진 팔에 부목을 댄다.'
REST = '숨을 고른다.'

# 치료 실패 표(d100)의 눈
FATAL = 1
WORSEN_BADLY = 5
WORSEN = 20
PAIN = 40
NOTHING = 77
# 팔 골절의 후유증 표(d20). 1~5 는 굽은 팔이다
CROOKED = 3
CLEAN = 10

# 게임 안의 시각(분). 첫 라운드가 열린 때와 그 장면이 끝나는 때, 기본 걸음, 하루
OPENED = 8 * 60
SCENE_END = OPENED + 10
STEP = 10
DAY = 24 * 60
# 1 라운드에 입은 팔 골절이 저절로 낫는 시각. 14일 뒤(15일째 8시)
ARM_HEALS = OPENED + 14 * DAY
# 팔 골절의 치료에 한 번 성공하면 앞당겨지는 시간
TREATED = 3 * DAY
# 1 라운드에 입은 다리 부상이 저절로 낫는 시각(7일 뒤)과, 치료에 한 번 성공한 뒤의 시각(2일 앞당김)
LEG_HEALS = OPENED + 7 * DAY
LEG_TREATED = LEG_HEALS - 2 * DAY


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다(모든 능력치 10, 최대 HP 10)."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람. 캐릭터는 '드워프 기사'다."""
    return bearer(signing_key, FRIEND)


def treating(injury: str = 'broken_arm', **patient) -> dict:
    """치료하는 행동. 대상(target 이나 npc)을 비우면 자기 자신이다."""
    return {'kind': 'treat', 'injury': injury, **patient}


async def wound(
    session: AsyncSession,
    table: dict,
    key: str = 'broken_arm',
    heals_at: int | None = ARM_HEALS,
    user_id: uuid.UUID = ME,
    npc: dict | None = None,
    ends_after_round: int | None = None,
) -> None:
    """
    부상 하나를 DB 에 바로 적는다. 1 라운드에 입은 것으로 한다. npc 를 주면 그 NPC 가, 아니면 그 사람이 입는다.

    오래 가는 것은 나을 시각(heals_at), 짧은 것은 풀릴 라운드(ends_after_round)를 준다. 결손은 둘 다 None 이다.
    """
    table_id = uuid.UUID(table['id'])
    row = TableInjury(
        table_id=table_id,
        injury=key,
        source='injury_table',
        round_number=1,
        ends_after_round=ends_after_round,
        heals_at=heals_at,
    )
    if npc is not None:
        row.npc_entry_id = uuid.UUID(npc['id'])
    else:
        row.sheet_id = await session.scalar(
            select(TableSheet.id).where(TableSheet.table_id == table_id, TableSheet.user_id == user_id)
        )
    session.add(row)
    await session.commit()


async def sheet_of(client: AsyncClient, headers: dict[str, str], table: dict, index: int = 0) -> dict:
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['members'][index]['sheet']


async def injury_rows(session: AsyncSession) -> list[TableInjury]:
    """DB 에 적힌 부상들. 생긴 순서다."""
    query = select(TableInjury).order_by(TableInjury.created_at).execution_options(populate_existing=True)
    return list(await session.scalars(query))


def treated(round_: dict, index: int = 0) -> dict:
    """라운드의 선언 하나에 적힌 치료의 결과."""
    return round_['declarations'][index]['outcome']['treatment']


def at(minutes: int) -> dict:
    """게임 안의 시각을 응답의 모양으로(1일째 0시부터 흐른 분)."""
    time = read_time(minutes)
    return {'day': time.day, 'hour': time.hour, 'minute': time.minute, 'time_of_day': time.time_of_day.value}


# --- 규칙의 모양 ---


def test_the_template_treats_lasting_injuries_with_wisdom():
    assert SRD5.treatment.ability == 'wis'
    lasting = {injury.key: (injury.treat_difficulty, injury.treat_minutes) for injury in SRD5.injuries}
    assert lasting['broken_arm'] == ('hard', 3 * DAY)
    assert lasting['leg_wound'] == ('medium', 2 * DAY)
    # 짧은 것과 결손은 치료할 수 없다
    assert lasting['stunned'] == (None, None)
    assert lasting['lost_eye'] == (None, None)


def test_the_template_mishap_table_is_mostly_harmless_and_rarely_fatal():
    rows = SRD5.treatment.mishaps.rows
    assert SRD5.treatment.mishaps.sides == 100
    fatal = sum(row.high - row.low + 1 for row in rows if row.kind == Mishap.FATAL)
    nothing = sum(row.high - row.low + 1 for row in rows if row.kind == Mishap.NOTHING)
    assert (fatal, nothing) == (1, 50)


def srd5_with(**changes) -> dict:
    return {**SRD5.model_dump(mode='json'), **changes}


def injuries_with(key: str, **fields) -> list[dict]:
    """SRD5 의 부상 목록에서 하나의 칸만 바꾼 것."""
    return [
        {**injury, **fields} if injury['key'] == key else injury for injury in SRD5.model_dump(mode='json')['injuries']
    ]


def mishaps_with(*rows: dict) -> dict:
    return {'ability': 'wis', 'mishaps': {'sides': 2, 'rows': list(rows)}}


@pytest.mark.parametrize(
    'changes',
    [
        # 결손은 치료할 수 없다
        {'injuries': injuries_with('lost_eye', treat_difficulty='hard', treat_minutes=DAY)},
        # 짧은 것도 치료할 수 없다
        {'injuries': injuries_with('stunned', treat_difficulty='hard', treat_minutes=10)},
        # 난이도와 앞당기는 시간은 함께 적는다
        {'injuries': injuries_with('broken_arm', treat_minutes=None)},
        {'injuries': injuries_with('broken_arm', treat_difficulty=None)},
        # 규칙에 없는 난이도
        {'injuries': injuries_with('broken_arm', treat_difficulty='impossible')},
        # 치료할 수 있는 부상이 있는데 치료의 규칙이 없다
        {'treatment': None},
        # 규칙에 없는 능력
        {'treatment': {**SRD5.model_dump(mode='json')['treatment'], 'ability': 'luck'}},
        # 실패 표의 피해 등급이 규칙에 없다
        {'treatment': mishaps_with({'low': 1, 'high': 2, 'kind': 'pain', 'magnitude': 'deadly'})},
        # 덧남에는 늦춰지는 시간이, 좀 아픔에는 피해가 있어야 한다. 즉사와 아무 일 없음에는 피해가 없다
        {'treatment': mishaps_with({'low': 1, 'high': 2, 'kind': 'worsen'})},
        {'treatment': mishaps_with({'low': 1, 'high': 2, 'kind': 'pain'})},
        {'treatment': mishaps_with({'low': 1, 'high': 2, 'kind': 'fatal', 'magnitude': 'light'})},
        {'treatment': mishaps_with({'low': 1, 'high': 2, 'kind': 'nothing', 'delay_minutes': 3})},
        # 덧남은 이제 라운드가 아니라 시간이다(판 형식 25)
        {'treatment': mishaps_with({'low': 1, 'high': 2, 'kind': 'worsen', 'rounds': 3})},
        # 실패 표는 모든 눈을 덮는다
        {'treatment': mishaps_with({'low': 1, 'high': 1, 'kind': 'nothing'})},
        {'treatment': mishaps_with({'low': 2, 'high': 2, 'kind': 'nothing'})},
    ],
)
def test_rejects_treatment_rules_that_make_no_sense(changes: dict):
    with pytest.raises(ValidationError):
        Ruleset.model_validate(srd5_with(**changes))


def test_a_rule_without_treatment_is_fine_when_nothing_can_be_treated():
    untreated = [
        {**injury, 'treat_difficulty': None, 'treat_minutes': None}
        for injury in SRD5.model_dump(mode='json')['injuries']
    ]

    ruleset = Ruleset.model_validate(srd5_with(injuries=untreated, treatment=None))

    assert treatable(ruleset, 'broken_arm') is None


# --- 계산 ---


@pytest.mark.parametrize(
    ('key', 'can'), [('broken_arm', True), ('leg_wound', True), ('lost_eye', False), ('nose', False)]
)
def test_only_lasting_injuries_with_a_difficulty_can_be_treated(key: str, can: bool):
    assert (treatable(SRD5, key) is not None) is can


def test_treating_rolls_wisdom_against_the_difficulty_of_the_injury():
    hindered = treat(SRD5, find_injury(SRD5, 'broken_arm'), {'wis': 12}, ScriptedDice([18]), NO_HINDRANCE)

    # 지혜 12 는 보정 +1. 어려움(20)에 19 로 실패한다
    assert (hindered.check.modifier, hindered.check.total, hindered.check.target) == (1, 19, 20)
    assert hindered.check.success is False


def test_the_healers_own_injuries_hinder_the_treatment():
    hindrance = Hindrance(penalty=2, injuries=('lost_eye',))

    hindered = treat(SRD5, find_injury(SRD5, 'leg_wound'), {'wis': 10}, ScriptedDice([16]), hindrance)

    # 보통(15). 16 이지만 한쪽 눈을 잃어 지혜에 -2
    assert (hindered.check.total, hindered.check.success) == (14, False)


@pytest.mark.parametrize(
    ('roll', 'kind', 'delay', 'magnitude'),
    [
        (1, Mishap.FATAL, None, None),
        (2, Mishap.WORSEN, 2 * DAY, 'moderate'),
        (10, Mishap.WORSEN, 2 * DAY, 'moderate'),
        (11, Mishap.WORSEN, DAY, None),
        (31, Mishap.PAIN, None, 'light'),
        (51, Mishap.NOTHING, None, None),
        (100, Mishap.NOTHING, None, None),
    ],
)
def test_the_mishap_table_gives_the_row_of_the_roll(roll: int, kind: Mishap, delay: int | None, magnitude: str | None):
    rolled = roll_mishap(SRD5, ScriptedDice([roll]))

    assert (rolled.roll, rolled.kind, rolled.delay_minutes, rolled.magnitude) == (roll, kind, delay, magnitude)


def test_treatment_moves_the_time_of_healing():
    arm = find_injury(SRD5, 'broken_arm')

    # 3일 앞당긴다. 판의 기본 걸음과 상관없다
    assert shortened(ARM_HEALS, arm) == ARM_HEALS - TREATED
    assert not is_healed(ARM_HEALS - TREATED, SCENE_END)
    assert is_healed(SCENE_END, SCENE_END)
    assert is_healed(SCENE_END - 40, SCENE_END)
    assert lengthened(ARM_HEALS, roll_mishap(SRD5, ScriptedDice([WORSEN]))) == ARM_HEALS + DAY
    assert lengthened(ARM_HEALS, roll_mishap(SRD5, ScriptedDice([PAIN]))) == ARM_HEALS


def test_only_lasting_injuries_with_a_table_leave_aftermath():
    assert roll_aftermath(find_injury(SRD5, 'broken_arm'), ScriptedDice([CROOKED])).injury == 'crooked_arm'
    assert roll_aftermath(find_injury(SRD5, 'stunned'), ScriptedDice([])) is None
    assert roll_aftermath(find_injury(SRD5, 'lost_eye'), ScriptedDice([])) is None


def test_a_lasting_injury_heals_by_game_time_and_not_by_rounds():
    leg = find_injury(SRD5, 'leg_wound')

    # 7일 뒤
    assert heals_at(leg, OPENED) == LEG_HEALS
    assert ends_after(leg, 4) is None
    # 짧은 것과 결손은 나을 시각이 없다
    assert heals_at(find_injury(SRD5, 'stunned'), OPENED) is None
    assert heals_at(find_injury(SRD5, 'lost_eye'), OPENED) is None


def test_a_treatment_names_one_patient_and_no_ability():
    assert TreatAction(kind=ActionKind.TREAT, injury='broken_arm').target is None
    with pytest.raises(ValidationError):
        TreatAction(kind=ActionKind.TREAT, injury='broken_arm', target=ME, npc=STRANGER)
    with pytest.raises(ValidationError):
        TreatAction.model_validate({'kind': 'treat', 'injury': 'broken_arm', 'ability': 'wis'})


def test_a_stored_action_is_read_by_its_kind():
    assert isinstance(read_action({'kind': 'treat', 'injury': 'leg_wound'}), TreatAction)
    assert isinstance(read_action({'kind': 'check', 'ability': 'str'}), CheckAction)


def test_the_rules_must_be_able_to_treat_the_injury():
    assert find_treat_fault(SRD5, TreatAction(kind=ActionKind.TREAT, injury='broken_arm')) is None
    assert find_treat_fault(SRD5, TreatAction(kind=ActionKind.TREAT, injury='lost_eye')) == 'injury'


# --- 판의 형식 ---


def make_format_14() -> dict:
    """치료가 없던 때의 판. 부상은 있지만 치료의 칸이 없다."""
    document = UPGRADES[13](make_format_13())
    rules = dict(document['rulebook']['rules'])
    rules.pop('treatment', None)
    rules['injuries'] = [
        {key: value for key, value in injury.items() if key not in ('treat_difficulty', 'treat_rounds')}
        for injury in rules['injuries']
    ]
    return {**document, 'rulebook': {**document['rulebook'], 'rules': rules}}


def test_an_old_version_is_read_with_the_template_treatment():
    old = read_snapshot(make_format_14())

    assert old.rulebook.rules.treatment == SRD5.treatment
    # 성질은 뒤의 형식이 비워 채운다(#799)
    assert old.rulebook.rules.injuries == tuple(injury.model_copy(update={'natures': ()}) for injury in SRD5.injuries)


def test_upgrading_keeps_treatment_fields_already_there():
    document = make_format_14()
    rules = document['rulebook']['rules']
    rules['injuries'] = [
        {**rules['injuries'][0], 'treat_difficulty': None, 'treat_rounds': None},
        *rules['injuries'][1:],
    ]

    current = upgrade_from_14(document)

    assert current['format'] == 15
    assert current['rulebook']['rules']['injuries'][0]['treat_difficulty'] is None


# --- 받을 때의 검사 ---


async def test_treating_myself_fills_me_in(client: AsyncClient, app: FastAPI, me: dict[str, str], session):
    world = await start_table(client, me)
    await wound(session, world['table'])
    load_dice(app, [1, NOTHING])

    closing = await declare(client, me, world['table'], TREAT, treating())

    assert closing['declarations'][0]['action'] == {
        'kind': 'treat',
        'injury': 'broken_arm',
        'target': str(ME),
        'npc': None,
        'item': None,
    }


@pytest.mark.parametrize('injury', ['lost_eye', 'stunned', 'nose'])
async def test_an_injury_the_rules_cannot_treat_is_refused(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, injury: str
):
    world = await start_table(client, me)
    await wound(session, world['table'], 'lost_eye', None)

    response = await send(client, me, world['table'], TREAT, treating(injury))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'action.injury 가 이 테이블의 규칙에 없습니다.'}


async def test_an_injury_nobody_has_cannot_be_treated(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    response = await send(client, me, world['table'], TREAT, treating())

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_injured'


async def test_the_patient_must_be_seated_or_in_the_scene(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    # 드워프는 장면에 나오지 않았다
    await wound(session, world['table'], npc=world['dwarf'])

    stranger = await send(client, me, world['table'], TREAT, treating(target=str(STRANGER)))
    unseen = await send(client, me, world['table'], TREAT, treating(npc=world['dwarf']['id']))

    assert stranger.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert unseen.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_dead_cannot_be_treated(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await wound(session, world['table'], user_id=FRIEND)
    await wound(session, world['table'], npc=world['lady'])
    await session.execute(
        text('UPDATE table_sheets SET hp = 0, died_at = :now WHERE user_id = :user_id'),
        {'now': datetime.now(UTC), 'user_id': FRIEND},
    )
    await session.execute(text("UPDATE table_npcs SET hp = 0, status = 'dead'"))
    await session.commit()

    dead_friend = await send(client, me, world['table'], TREAT, treating(target=str(FRIEND)))
    dead_lady = await send(client, me, world['table'], TREAT, treating(npc=world['lady']['id']))

    assert dead_friend.json()['reason'] == 'patient_dead'
    assert dead_lady.json()['reason'] == 'npc_dead'


async def test_a_treatment_takes_no_ability(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    await wound(session, world['table'])

    response = await send(client, me, world['table'], TREAT, {**treating(), 'ability': 'str'})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 닫을 때: 성공 ---


async def test_a_successful_treatment_brings_healing_closer(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'])
    dice = load_dice(app, [20])

    closing = await declare(client, me, world['table'], TREAT, treating())

    result = closing['declarations'][0]['outcome']
    # 지혜(보정 0)로 어려움(20)
    assert (result['roll'], result['target'], result['success']) == (20, 20, True)
    assert treated(closing) == {
        'injury': 'broken_arm',
        'name': '팔 골절',
        'ability': 'wis',
        'difficulty': 'hard',
        'patient': {'user_id': str(ME), 'character_name': '엘프', 'entry_id': None, 'name': None},
        'treated': True,
        'heals_at': at(ARM_HEALS - TREATED),
        # 이 장면이 끝난 뒤(1일째 8시 10분)부터 12일째 8시까지
        'minutes_left': ARM_HEALS - TREATED - SCENE_END,
        'healed': False,
        'aftermath': None,
        'mishap': None,
        'died': False,
        'aid': None,
    }
    assert (await sheet_of(client, me, world['table']))['injuries'] == [
        {'injury': 'broken_arm', 'round': 1, 'ends_after_round': None, 'heals_at': at(ARM_HEALS - TREATED)}
    ]
    assert dice.remaining == 0
    (rolled,) = await events_of(client, me, world['table'], 'check_rolled')
    assert (rolled['payload']['ability'], rolled['payload']['difficulty']) == ('wis', 'hard')


async def test_a_one_eyed_healer_has_a_harder_time(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'], 'lost_eye', None)
    await wound(session, world['table'])
    load_dice(app, [20, NOTHING])

    closing = await declare(client, me, world['table'], TREAT, treating())

    result = closing['declarations'][0]['outcome']
    # 한쪽 눈을 잃어 지혜에 -2. 20 이 18 이 되어 어려움(20)에 못 미친다
    assert (result['total'], result['success']) == (18, False)
    assert result['hindrance']['injuries'] == ['lost_eye']


async def test_a_treatment_that_reaches_today_heals_and_rolls_aftermath(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    # 9시에 낫는다. 3일 앞당기면 이 장면(8시 10분까지)보다 앞이라 그 자리에서 낫는다
    await wound(session, world['table'], heals_at=OPENED + 60)
    dice = load_dice(app, [20, CROOKED])

    closing = await declare(client, me, world['table'], TREAT, treating())

    result = treated(closing)
    assert (result['healed'], result['heals_at']) == (True, None)
    assert result['aftermath'] == {
        'trigger': 'aftermath',
        'roll': CROOKED,
        'injury': 'crooked_arm',
        'ends_after_round': None,
        'heals_at': None,
        'immune': None,
    }
    assert (await sheet_of(client, me, world['table']))['injuries'] == [
        {'injury': 'crooked_arm', 'round': 1, 'ends_after_round': None, 'heals_at': None}
    ]
    arm, crooked = await injury_rows(session)
    assert arm.ended_at is not None
    assert (crooked.source, crooked.ended_at) == ('aftermath', None)
    assert dice.remaining == 0


async def test_healing_by_treatment_is_recorded_in_order(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'], heals_at=OPENED + 60)
    load_dice(app, [20, CROOKED])

    await declare(client, me, world['table'], TREAT, treating())

    (rolled,) = await events_of(client, me, world['table'], 'check_rolled')
    (treated_,) = await events_of(client, me, world['table'], 'injury_treated')
    (ended,) = await events_of(client, me, world['table'], 'injury_ended')
    (gained,) = await events_of(client, me, world['table'], 'injury_gained')
    assert treated_['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '엘프',
        'injury': 'broken_arm',
        'treated': True,
        'heals_at': None,
        'healed': True,
        'mishap': None,
        'died': False,
    }
    assert treated_['caused_by_sequence'] == rolled['sequence']
    assert (ended['payload']['reason'], ended['caused_by_sequence']) == ('treated', treated_['sequence'])
    assert (gained['payload']['injury'], gained['payload']['source']) == ('crooked_arm', 'aftermath')
    assert gained['caused_by_sequence'] == ended['sequence']


async def test_a_clean_aftermath_leaves_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'], heals_at=OPENED + 60)
    load_dice(app, [20, CLEAN])

    closing = await declare(client, me, world['table'], TREAT, treating())

    assert treated(closing)['aftermath']['injury'] is None
    assert (await sheet_of(client, me, world['table']))['injuries'] == []
    assert await events_of(client, me, world['table'], 'injury_gained') == []


async def test_an_npc_can_be_treated(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    await wound(session, world['table'], 'leg_wound', LEG_HEALS, npc=world['lady'])
    load_dice(app, [15])

    closing = await declare(client, me, world['table'], TREAT, treating('leg_wound', npc=world['lady']['id']))

    result = treated(closing)
    assert result['patient'] == {
        'user_id': None,
        'character_name': None,
        'entry_id': world['lady']['id'],
        'name': '악역영애',
    }
    assert (result['difficulty'], result['heals_at']) == ('medium', at(LEG_TREATED))
    (row,) = await injury_rows(session)
    assert row.heals_at == LEG_TREATED
    assert (await people(client, me, world['table']))['people'][0]['injuries'] == ['leg_wound']


async def test_a_friend_can_be_treated(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await wound(session, world['table'], 'leg_wound', LEG_HEALS, user_id=FRIEND)
    load_dice(app, [15])

    await declare(client, me, world['table'], TREAT, treating('leg_wound', target=str(FRIEND)))
    closing = await declare(client, friend, world['table'], REST)

    assert treated(closing)['patient']['character_name'] == '드워프 기사'
    assert (await sheet_of(client, me, world['table'], 1))['injuries'][0]['heals_at'] == at(LEG_TREATED)


async def test_the_second_healer_finds_nothing_left_to_treat(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await wound(session, world['table'], heals_at=OPENED + 60)
    # 내가 먼저 고친다(들어온 순서). 친구는 실패했지만 치료할 것이 없어 실패 표를 굴리지 않는다
    dice = load_dice(app, [20, CLEAN, 1])

    await declare(client, me, world['table'], TREAT, treating())
    closing = await declare(client, friend, world['table'], TREAT, treating(target=str(ME)))

    assert treated(closing, 0)['healed'] is True
    second = treated(closing, 1)
    assert (second['treated'], second['mishap'], second['healed']) == (False, None, False)
    assert dice.remaining == 0


async def test_both_healers_can_bring_healing_closer(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await wound(session, world['table'])
    load_dice(app, [20, 20])

    await declare(client, me, world['table'], TREAT, treating())
    closing = await declare(client, friend, world['table'], TREAT, treating(target=str(ME)))

    assert [treated(closing, index)['heals_at'] for index in (0, 1)] == [
        at(ARM_HEALS - TREATED),
        at(ARM_HEALS - 2 * TREATED),
    ]


async def test_a_patient_who_left_is_not_treated(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await wound(session, world['table'], user_id=FRIEND)
    dice = load_dice(app, [1])
    await declare(client, me, world['table'], TREAT, treating(target=str(FRIEND)))
    # 친구가 떠나서 남은 사람이 모두 냈다. 라운드가 저절로 닫히기 시작한다(#57)
    await client.delete(table_url(world['table'], '/members/me'), headers=friend)

    closed = await client.get(table_url(world['table'], '/rounds/1'), headers=me)

    result = closed.json()['declarations'][0]['outcome']['treatment']
    assert (result['treated'], result['patient']['user_id']) == (False, str(FRIEND))
    assert dice.remaining == 0


# --- 닫을 때: 실패 ---


async def test_a_failure_can_change_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'])
    load_dice(app, [1, NOTHING])

    closing = await declare(client, me, world['table'], TREAT, treating())

    result = treated(closing)
    assert result['mishap'] == {'roll': NOTHING, 'kind': 'nothing', 'delay_minutes': None, 'magnitude': None}
    assert (result['heals_at'], result['healed']) == (at(ARM_HEALS), False)
    assert closing['declarations'][0]['outcome']['effect'] is None


async def test_a_failure_can_make_it_worse_and_hurt_without_a_new_injury(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'])
    # 크게 덧남: 2일 늦어지고 보통(1d8) 피해. 6 은 최대 HP 의 절반이 넘지만 부상 표를 굴리지 않는다
    dice = load_dice(app, [1, WORSEN_BADLY, 6])

    closing = await declare(client, me, world['table'], TREAT, treating())

    assert treated(closing)['heals_at'] == at(ARM_HEALS + 2 * DAY)
    effect = closing['declarations'][0]['outcome']['effect']
    assert (effect['kind'], effect['magnitude'], effect['amount'], effect['after']) == ('damage', 'moderate', 6, 4)
    assert effect['injury_roll'] is None
    assert dice.remaining == 0
    (row,) = await injury_rows(session)
    assert row.heals_at == ARM_HEALS + 2 * DAY


async def test_a_failure_can_make_it_worse_without_hurting(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'])
    load_dice(app, [1, WORSEN])

    closing = await declare(client, me, world['table'], TREAT, treating())

    assert treated(closing)['heals_at'] == at(ARM_HEALS + DAY)
    assert treated(closing)['mishap']['delay_minutes'] == DAY
    assert treated(closing)['minutes_left'] == ARM_HEALS + DAY - SCENE_END
    assert closing['declarations'][0]['outcome']['effect'] is None


async def test_a_failure_can_just_hurt(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    await wound(session, world['table'])
    load_dice(app, [1, PAIN, 3])

    closing = await declare(client, me, world['table'], TREAT, treating())

    assert treated(closing)['heals_at'] == at(ARM_HEALS)
    effect = closing['declarations'][0]['outcome']['effect']
    assert (effect['magnitude'], effect['amount'], effect['after']) == ('light', 3, 7)
    (changed,) = await events_of(client, me, world['table'], 'hp_changed')
    (treated_,) = await events_of(client, me, world['table'], 'injury_treated')
    assert changed['caused_by_sequence'] == treated_['sequence']


async def test_a_failure_can_kill(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    await wound(session, world['table'])
    load_dice(app, [1, FATAL])

    closing = await declare(client, me, world['table'], TREAT, treating())

    result = treated(closing)
    assert (result['died'], result['heals_at']) == (True, None)
    sheet = await sheet_of(client, me, world['table'])
    assert (sheet['hp'], sheet['dead']) == (0, True)
    (died,) = await events_of(client, me, world['table'], 'character_died')
    (treated_,) = await events_of(client, me, world['table'], 'injury_treated')
    assert died['payload'] == {'round': 1, 'user_id': str(ME), 'character_name': '엘프', 'cause': 'treatment'}
    assert died['caused_by_sequence'] == treated_['sequence']


async def test_a_character_killed_by_a_failed_treatment_does_not_act(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await wound(session, world['table'], user_id=FRIEND)
    dice = load_dice(app, [1, FATAL])

    await declare(client, me, world['table'], TREAT, treating(target=str(FRIEND)))
    closing = await declare(
        client, friend, world['table'], REST, {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}
    )

    assert treated(closing)['died'] is True
    assert closing['declarations'][1]['outcome'] == {'turn_lost': 'dead'}
    assert dice.remaining == 0
    move = Move(character_name='드워프 기사', content=REST, dead=True)
    assert describe_move(move) == '드워프 기사: 숨을 고른다. (하려던 일을 하기 전에 죽었다)'


async def test_a_patient_who_died_earlier_in_the_round_is_not_treated(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    await wound(session, world['table'], npc=world['lady'])
    # 내 치료가 실패해 악역영애가 죽는다. 친구는 성공했지만 죽은 인물은 치료할 수 없다
    dice = load_dice(app, [1, FATAL, 20])

    await declare(client, me, world['table'], TREAT, treating(npc=world['lady']['id']))
    closing = await declare(client, friend, world['table'], TREAT, treating(npc=world['lady']['id']))

    second = treated(closing, 1)
    assert (second['treated'], second['heals_at']) == (False, None)
    assert dice.remaining == 0


async def test_a_failure_can_kill_an_npc(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    await wound(session, world['table'], npc=world['lady'])
    load_dice(app, [1, FATAL])

    closing = await declare(client, me, world['table'], TREAT, treating(npc=world['lady']['id']))

    assert treated(closing)['died'] is True
    assert await state_of(session, world['table'], world['lady']) == (0, NpcStatus.DEAD)
    assert await events_of(client, me, world['table'], 'character_died') == []


async def test_a_failure_hurts_an_npc_without_a_new_injury(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await wound(session, world['table'], npc=world['lady'])
    load_dice(app, [1, PAIN, 3])

    closing = await declare(client, me, world['table'], TREAT, treating(npc=world['lady']['id']))

    npc_effect = closing['declarations'][0]['outcome']['npc_effect']
    assert (npc_effect['amount'], npc_effect['lethal'], npc_effect['injury_roll']) == (3, False, None)
    assert await state_of(session, world['table'], world['lady']) == (7, NpcStatus.ALIVE)


# --- 시간이 지나 낫는다 ---


async def test_a_lasting_injury_heals_on_its_day_with_aftermath(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    # 2 라운드의 장면이 끝나는 8시 20분에 낫는다. 1 라운드의 장면은 8시 10분에 끝나 아직이다
    await wound(session, world['table'], heals_at=SCENE_END + STEP)
    load_dice(app, [])
    await declare(client, me, world['table'], REST)
    await narrated()

    dice = load_dice(app, [CROOKED])
    await declare(client, me, world['table'], REST)
    await narrated()

    assert dice.remaining == 0
    assert (await sheet_of(client, me, world['table']))['injuries'] == [
        {'injury': 'crooked_arm', 'round': 2, 'ends_after_round': None, 'heals_at': None}
    ]
    (ended,) = await events_of(client, me, world['table'], 'injury_ended')
    (gained,) = await events_of(client, me, world['table'], 'injury_gained')
    assert (ended['payload']['round'], ended['payload']['reason']) == (2, 'healed')
    assert (gained['payload']['source'], gained['caused_by_sequence']) == ('aftermath', ended['sequence'])
    request = narrator.requests[1]
    assert request.moves[0].healed == [HealNote(name='팔 골절', aftermath='굽은 팔')]
    text_ = '\n'.join(message.content for message in prompt.build_messages(request))
    assert '[나은 부상: 팔 골절(후유증: 굽은 팔)]' in text_


async def test_an_npc_out_of_the_scene_heals_without_an_event(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    app.state.narrator = RecordingNarrator()
    # 드워프는 장면에 나오지 않는다. 부를 이름이 없어 이벤트는 적지 않지만 낫기는 한다
    await wound(session, world['table'], 'leg_wound', SCENE_END + STEP, npc=world['dwarf'])
    load_dice(app, [])
    await declare(client, me, world['table'], REST)
    await narrated()
    (row,) = await injury_rows(session)
    assert row.ended_at is None

    dice = load_dice(app, [CLEAN])
    await declare(client, me, world['table'], REST)
    await narrated()

    (row,) = await injury_rows(session)
    assert row.ended_at is not None
    assert dice.remaining == 0
    assert await events_of(client, me, world['table'], 'injury_ended') == []


async def test_the_injuries_of_the_dead_stay_as_they_were(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me, friend)
    app.state.narrator = RecordingNarrator()
    await wound(session, world['table'], heals_at=SCENE_END + STEP, user_id=FRIEND)
    # 내 기절도 같은 때 풀린다. 풀 것이 있어 부상을 정리하는 길을 탄다
    await wound(session, world['table'], 'stunned', None, ends_after_round=2)
    await session.execute(
        text('UPDATE table_sheets SET hp = 0, died_at = :now WHERE user_id = :user_id'),
        {'now': datetime.now(UTC), 'user_id': FRIEND},
    )
    await session.commit()
    dice = load_dice(app, [])

    await declare(client, me, world['table'], REST)
    await narrated()
    await client.post(table_url(world['table'], '/rounds/current/close'), headers=me)
    await narrated()

    arm, stunned = await injury_rows(session)
    assert (arm.ended_at, stunned.ended_at is not None) == (None, True)
    assert dice.remaining == 0


async def test_a_night_of_rest_heals_what_ten_minute_rounds_would_not(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    app.state.narrator = RecordingNarrator()
    # 거의 다 나은 팔 골절. 6시간 뒤(14시)에 낫는다
    await wound(session, world['table'], heals_at=OPENED + 6 * 60)
    load_dice(app, [])
    await declare(client, me, world['table'], REST)
    await narrated()

    # 여덟 시간을 기다렸다. 2 라운드의 장면은 8시 10분에 시작해 16시 10분에 끝난다. 14시에 낫는 팔이 낫는다
    dice = load_dice(app, [CLEAN])
    await declare(client, me, world['table'], REST, wait(8 * 60))
    await narrated()

    assert dice.remaining == 0
    (row,) = await injury_rows(session)
    assert row.ended_at is not None
    (ended,) = await events_of(client, me, world['table'], 'injury_ended')
    assert (ended['payload']['round'], ended['payload']['reason']) == (2, 'healed')


async def test_ten_minute_rounds_do_not_heal_a_broken_arm_soon(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    app.state.narrator = RecordingNarrator()
    await wound(session, world['table'])
    load_dice(app, [])

    for _ in range(3):
        await declare(client, me, world['table'], REST)
        await narrated()

    # 세 라운드가 지나도 1일째 8시 40분이다. 팔은 15일째 8시에 낫는다
    (row,) = await injury_rows(session)
    assert (row.ended_at, row.heals_at) == (None, ARM_HEALS)
    assert (await sheet_of(client, me, world['table']))['injuries'][0]['heals_at'] == at(ARM_HEALS)


# --- 서술 ---


async def test_the_narrator_hears_of_the_treatment(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    await wound(session, world['table'])
    load_dice(app, [20])

    await declare(client, me, world['table'], TREAT, treating())
    await narrated()

    (request,) = narrator.requests
    verdict = request.moves[0].verdict
    assert (verdict.ability, verdict.difficulty) == ('지혜', '어려움')
    # 12일째 8시에 낫는다. 이 장면이 끝나는 1일째 8시 10분부터 10일 23시간 50분
    left = ARM_HEALS - TREATED - SCENE_END
    assert verdict.treatment == TreatmentNote(injury='팔 골절', patient='엘프', minutes_left=left)
    text_ = '\n'.join(message.content for message in prompt.build_messages(request))
    assert '→ 엘프의 팔 골절 치료: 앞당겨짐, 낫기까지 10일 23시간 50분' in text_


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (TreatmentNote(injury='팔 골절', patient='엘프', healed=True), '→ 엘프의 팔 골절 치료: 다 나음'),
        (
            TreatmentNote(injury='팔 골절', patient='엘프', healed=True, aftermath='굽은 팔'),
            '→ 엘프의 팔 골절 치료: 다 나음. 후유증: 굽은 팔',
        ),
        (
            TreatmentNote(injury='팔 골절', patient='엘프', mishap='worsen', worsened_minutes=50, minutes_left=350),
            '→ 엘프의 팔 골절 치료 실패: 상처가 덧남, 50분 늦어짐, 낫기까지 5시간 50분',
        ),
        # 이 장면 안에 나을 것이면 남은 시간을 적지 않는다
        (
            TreatmentNote(injury='팔 골절', patient='엘프', mishap='nothing', minutes_left=0),
            '→ 엘프의 팔 골절 치료 실패: 별일 없음',
        ),
        (
            TreatmentNote(injury='팔 골절', patient='엘프', mishap='fatal', died=True),
            '→ 엘프의 팔 골절 치료 실패: 즉사, 엘프 죽음',
        ),
        (
            TreatmentNote(injury='팔 골절', patient='엘프', treated=False),
            '→ 엘프의 팔 골절 치료: 치료할 부상이 이미 없었다',
        ),
        (TreatmentNote(injury='팔 골절', patient='', treated=False), '→ 팔 골절 치료: 치료할 부상이 이미 없었다'),
    ],
)
def test_the_treatment_is_told_in_one_line(note: TreatmentNote, line: str):
    assert describe_treatment(note) == line


async def test_narrating_again_does_not_treat_again(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    session: AsyncSession,
    narrated,
    monkeypatch: pytest.MonkeyPatch,
):
    world = await start_table(client, me)
    narrator = RecordingNarrator(fail_first=True)
    app.state.narrator = narrator
    await wound(session, world['table'])
    load_dice(app, [20])
    await declare(client, me, world['table'], TREAT, treating())
    await narrated()

    dice = load_dice(app, [20])
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(world['table'], '/rounds/current/close'), headers=me)
    await narrated()

    assert again.status_code == status.HTTP_202_ACCEPTED
    assert dice.remaining == 1
    (row,) = await injury_rows(session)
    assert row.heals_at == ARM_HEALS - TREATED
    assert narrator.requests[0] == narrator.requests[1]


# --- 마이그레이션 ---


async def test_the_migration_gives_lasting_injuries_a_day_of_healing(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    migration = load_migration('treatment')
    world = await start_table(client, me)
    await wound(session, world['table'], 'broken_arm', None)
    await wound(session, world['table'], 'lost_eye', None)
    # 그때의 판에는 오래 가는 부상이 라운드 수로 적혀 있었다(판 형식 25 전)
    await session.execute(
        text("UPDATE game_tables SET content = jsonb_set(content, '{rulebook,rules,injuries}', CAST(:old AS JSONB))"),
        {'old': json.dumps(migration.FALLBACK_LASTING)},
    )
    await session.commit()

    await session.execute(migration.fill_heal_rounds())
    await session.commit()

    arm, eye = await injury_rows(session)
    assert (arm.ends_after_round, eye.ends_after_round) == (31, None)


async def test_the_migration_reads_tables_without_injuries_in_their_rules_as_srd5(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    migration = load_migration('treatment')
    world = await start_table(client, me)
    await wound(session, world['table'], 'leg_wound', None)
    await session.execute(text("UPDATE game_tables SET content = content #- '{rulebook,rules,injuries}'"))
    await session.commit()

    await session.execute(migration.fill_heal_rounds())
    await session.commit()

    (leg,) = await injury_rows(session)
    assert leg.ends_after_round == 21


async def test_the_migration_fills_old_rulebooks_with_the_template_treatment(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    migration = load_migration('treatment')
    await start_table(client, me)
    strip = text(
        "UPDATE rulebooks SET rules = (rules - 'treatment') || jsonb_build_object('injuries', "
        "(SELECT jsonb_agg(item - 'treat_difficulty' - 'treat_rounds') "
        "FROM jsonb_array_elements(rules->'injuries') item))"
    )
    await session.execute(strip)
    await session.commit()

    minutes = load_migration('injury_minutes')
    # 두 번 돌려도 결과가 같다. 뒤의 마이그레이션이 기간을 분으로 옮긴다(판 형식 25)
    for _ in range(2):
        await session.execute(migration.fill_treatment())
        await session.execute(migration.fill_injuries())
        await session.run_sync(
            lambda sync: minutes.rewrite_rulebooks(sync.connection(), minutes.injury_to_minutes, minutes.row_to_minutes)
        )
    await session.commit()

    rules = await session.scalar(text('SELECT rules FROM rulebooks'))
    assert rules == SRD5.model_dump(mode='json')


async def test_the_clock_migration_moves_lasting_injuries_to_a_time_of_healing(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    migration = load_migration('injury_heals_at')
    world = await start_table(client, me)
    # 시간으로 낫기 전에 입은 것들. 팔은 31 라운드가 닫힐 때 나을 것이었다. 기절은 짧은 것이라 그대로다
    await wound(session, world['table'], heals_at=None, ends_after_round=31)
    await wound(session, world['table'], 'stunned', None, ends_after_round=3)
    await wound(session, world['table'], 'lost_eye', None)

    await session.execute(text(migration.TO_MINUTES))
    await session.commit()

    arm, stunned, eye = await injury_rows(session)
    # 지금 1 라운드(8시). 31 라운드가 닫힐 때의 장면 끝은 8시 + 31 × 10분
    assert (arm.ends_after_round, arm.heals_at) == (None, OPENED + 31 * STEP)
    assert (stunned.ends_after_round, stunned.heals_at) == (3, None)
    assert (eye.ends_after_round, eye.heals_at) == (None, None)

    await session.execute(text(migration.TO_ROUNDS))
    await session.commit()

    arm, stunned, eye = await injury_rows(session)
    # 되돌리면 같은 라운드로 돌아온다
    assert (arm.ends_after_round, arm.heals_at) == (31, None)


async def test_the_database_refuses_both_a_round_and_a_time(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)

    with pytest.raises(IntegrityError):
        await wound(session, world['table'], heals_at=ARM_HEALS, ends_after_round=31)
