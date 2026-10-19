# trpg-server/tests/test_npc_turns.py

"""
싸우는 NPC 의 차례와 공격(#487 2/2, app/rounds/npc_attacks.py)을 검증한다.

판은 test_npc_steals.py 의 것이다. 악역영애가 나오고, 시트의 능력치는 모두 10(보정 0), 최대 HP 는 10 이다.
앉은 사람의 시트도 모두 10 이라 차례 능력치(민첩)가 같다. 차례가 둘 이상이면 주사위로 가른다.
악역영애의 공격은 부채 후리기(민첩, 보통 15, 가벼움 1d4) 하나다. 주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다.
라운드 1 에 엘프가 주먹을 날려(빗나감) 싸움을 붙이고, 라운드 2 에 악역영애가 차례를 받는 것이 기본이다.

보는 것.
  - 치는 인물: 장면에 나왔고 살아 있고 적대이고 싸움이 붙었고 공격이 있다. 하나라도 빠지면 차례가 없다.
    이번 라운드에 싸움이 붙은 인물은 다음 라운드부터 친다.
  - 대상: 들킨 도둑, 이번 라운드에 싸운 사람, 그 밖의 서 있는 누구나의 차례다. 지난 라운드에 싸운 것은 보지 않는다.
  - 결과: 라운드의 turns 에 npc 의 차례로 적힌다. 이벤트(npc_attacked, hp_changed)와 서술의 줄에 남는다.
    이벤트에는 굴림의 숫자와 부상의 영향이 없다.
  - 앞 차례에 쓰러졌으면 치지 않는다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import NpcAttitude
from app.assets.scenarios.snapshot import AttackSnapshot
from app.engine.dice import ScriptedDice
from app.engine.templates import SRD5
from app.rounds import initiative
from app.rounds.move_lines import round_lines
from app.rounds.narration_request import to_turn_note
from app.rounds.narrator import MonsterTurnNote, TurnNote
from app.rounds.npc_attacks import INCAPACITATED, can_act, roll_attack, stopped_by
from app.tables.models import NpcStatus, TableInjury
from tests.test_monster_turns import turns_of
from tests.test_npc_actions import FAIL, LAUGH, NO_INJURY, PASS, PUNCH, bearer, events_of, load_dice, punch
from tests.test_npc_steals import FRIEND, ME, outcome, send, start, steal

pytestmark = pytest.mark.usefixtures('clean_tables')

SWIPE = {'name': '부채 후리기', 'ability': 'dex', 'difficulty': 'medium', 'harm': 'light'}
# 부채 후리기가 맞는 눈과 빗나가는 눈(보통 15, 보정 0), 가벼움(1d4)의 눈
HIT = 15
MISS = 14
SCRATCH = 3
# 같은 차례 점수를 가르는 주사위. 앞의 것이 먼저다
FIRST, LAST = 20, 1


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


async def laugh(client: AsyncClient, headers: dict, world: dict) -> None:
    """행동 없이 글만 낸다. 차례가 없다."""
    await send(client, headers, world, None, content=LAUGH)


async def pick_a_fight(client: AsyncClient, app: FastAPI, me: dict, world: dict, narrated, *others: dict) -> None:
    """라운드 1. 엘프가 악역영애에게 주먹을 날린다(빗나감). 싸움이 붙는다. others 는 글만 낸다."""
    load_dice(app, [FAIL])
    await send(client, me, world, punch(world['lady']['id']), content=PUNCH)
    for headers in others:
        await laugh(client, headers, world)
    await narrated()


async def armed_and_fighting(client: AsyncClient, app: FastAPI, me: dict, narrated, *others: dict, **fields) -> dict:
    """적대하고 부채 후리기를 지닌 악역영애와 라운드 1 에 싸움을 붙인 테이블. fields 로 시트의 칸을 바꾼다."""
    world = await start(client, me, *others, **{'attitude': 'hostile', 'attacks': [SWIPE], **fields})
    await pick_a_fight(client, app, me, world, narrated, *others)
    return world


def npc_turns(turns: list[dict]) -> list[dict]:
    return [turn for turn in turns if turn['kind'] == 'npc']


# --- 치는 인물 ---


async def test_a_fighting_hostile_npc_strikes_on_its_turn(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await armed_and_fighting(client, app, me, narrated)
    dice = load_dice(app, [HIT, SCRATCH])

    await laugh(client, me, world)
    await narrated()

    assert await turns_of(session, world['table'], 2) == [
        {
            'kind': 'npc',
            'first': False,
            'score': 10,
            'tiebreak': None,
            'entry_id': world['lady']['id'],
            'name': '악역영애',
            'outcome': {
                'attack': SWIPE,
                'user_id': str(ME),
                'character_name': '엘프',
                'roll': HIT,
                'modifier': 0,
                'total': HIT,
                'target': 15,
                'success': True,
                'effect': {
                    'kind': 'damage',
                    'magnitude': 'light',
                    'user_id': str(ME),
                    'character_name': '엘프',
                    'rolls': [SCRATCH],
                    'amount': SCRATCH,
                    'before': 10,
                    'after': 7,
                    'max_hp': 10,
                    'downed': False,
                    'injury_roll': None,
                },
                'hindrance': None,
            },
        }
    ]
    assert dice.remaining == 0


async def test_the_strike_is_recorded_without_numbers_and_narrated(
    client: AsyncClient, app: FastAPI, me: dict, narrated
):
    world = await armed_and_fighting(client, app, me, narrated)
    load_dice(app, [HIT, SCRATCH])
    await laugh(client, me, world)
    await narrated()

    (attacked,) = await events_of(client, me, world['table'], 'npc_attacked')
    hurt = (await events_of(client, me, world['table'], 'hp_changed'))[-1]

    assert attacked['payload'] == {
        'round': 2,
        'entry_id': world['lady']['id'],
        'name': '악역영애',
        'attack': SWIPE,
        'user_id': str(ME),
        'character_name': '엘프',
        'success': True,
    }
    assert attacked['actor_id'] is None
    assert hurt['caused_by_sequence'] == attacked['sequence']
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert '악역영애: 엘프에게 부채 후리기 (맞음)' in narrations[-1]['payload']['text']


async def test_a_miss_changes_nothing(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated):
    world = await armed_and_fighting(client, app, me, narrated)
    load_dice(app, [MISS])

    await laugh(client, me, world)
    await narrated()

    (turn,) = await turns_of(session, world['table'], 2)
    assert (turn['outcome']['success'], turn['outcome']['effect']) == (False, None)
    assert len(await events_of(client, me, world['table'], 'hp_changed')) == 0


@pytest.mark.parametrize(
    ('fields', 'fought'),
    [
        # 적대이기만 하다. 싸움이 붙지 않았다
        ({'attitude': 'hostile', 'attacks': [SWIPE]}, False),
        # 싸움은 붙었지만 중립이다
        ({'attitude': 'neutral', 'attacks': [SWIPE]}, True),
        # 우호하는 인물은 맞아도 치지 않는다
        ({'attitude': 'friendly', 'attacks': [SWIPE]}, True),
        # 공격을 적지 않았다
        ({'attitude': 'hostile'}, True),
    ],
)
async def test_who_does_not_strike(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated, fields: dict, fought: bool
):
    world = await start(client, me, **fields)
    if fought:
        await pick_a_fight(client, app, me, world, narrated)
    else:
        load_dice(app, [])
        await laugh(client, me, world)
        await narrated()
    dice = load_dice(app, [])

    await laugh(client, me, world)
    await narrated()

    assert await turns_of(session, world['table'], 2) == []
    assert await events_of(client, me, world['table'], 'npc_attacked') == []
    assert dice.remaining == 0


async def test_a_fight_started_this_round_is_fought_from_the_next(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await start(client, me, on_caught='fight', attacks=[SWIPE])
    # 라운드 1: 훔치다 들킨다(금화 12 에 1). 적대가 되고 싸움이 붙지만 이번 라운드에는 차례가 없다
    load_dice(app, [1])
    await send(client, me, world, steal(world, 'coins'))
    await narrated()
    assert (await outcome(client, me, world, 1))['steal']['fight'] is True
    dice = load_dice(app, [HIT, SCRATCH])

    await laugh(client, me, world)
    await narrated()

    assert await turns_of(session, world['table'], 1) == []
    (turn,) = await turns_of(session, world['table'], 2)
    assert (turn['kind'], turn['outcome']['user_id']) == ('npc', str(ME))
    assert dice.remaining == 0


# --- 대상 ---


async def test_the_caught_thief_is_struck_first(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await armed_and_fighting(client, app, me, narrated, friend)
    # 드워프 기사가 먼저 훔치다 들키고(1), 악역영애가 그를 친다. 대상을 고르는 주사위가 없다
    dice = load_dice(app, [FIRST, LAST, 1, HIT, SCRATCH])

    await laugh(client, me, world)
    await send(client, friend, world, steal(world, 'coins'))
    await narrated()

    (turn,) = npc_turns(await turns_of(session, world['table'], 2))
    assert turn['outcome']['user_id'] == str(FRIEND)
    assert dice.remaining == 0


async def test_someone_who_fought_it_this_round_is_struck_first(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await armed_and_fighting(client, app, me, narrated, friend)
    # 드워프 기사가 먼저 주먹을 날리고(빗나감), 악역영애가 그를 친다. 대상을 고르는 주사위가 없다
    dice = load_dice(app, [FIRST, LAST, FAIL, HIT, SCRATCH])

    await laugh(client, me, world)
    await send(client, friend, world, punch(world['lady']['id']), content=PUNCH)
    await narrated()

    (turn,) = npc_turns(await turns_of(session, world['table'], 2))
    assert turn['outcome']['user_id'] == str(FRIEND)
    assert dice.remaining == 0


async def test_otherwise_anyone_standing_may_be_struck(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    # 엘프는 지난 라운드에 싸웠다. 이번 라운드에는 아무도 싸우지 않아 둘 중에서 주사위(2)로 고른다
    world = await armed_and_fighting(client, app, me, narrated, friend)
    dice = load_dice(app, [2, HIT, SCRATCH])

    await laugh(client, me, world)
    await laugh(client, friend, world)
    await narrated()

    (turn,) = await turns_of(session, world['table'], 2)
    assert turn['outcome']['user_id'] == str(FRIEND)
    assert dice.remaining == 0


async def test_the_one_it_strikes_is_fighting_it(client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated):
    world = await armed_and_fighting(client, app, me, narrated, friend)
    # 악역영애가 먼저 엘프(주사위 1)를 치고, 드워프 기사가 그 틈에 훔친다(13)
    dice = load_dice(app, [LAST, FIRST, 1, HIT, SCRATCH, 13])

    await laugh(client, me, world)
    await send(client, friend, world, steal(world, 'coins'))
    await narrated()

    stolen = (await outcome(client, me, world, 2, FRIEND))['steal']
    # 엘프와 싸우는 중이라 정신이 팔렸다(-2). 싸움은 이미 붙어 싸움 전의 보정은 없다
    assert (stolen['check']['target'], stolen['factors'], stolen['stolen']) == (13, ['distracted'], True)
    assert dice.remaining == 0


# --- 움직이지 못함 ---


async def test_an_npc_downed_before_its_turn_does_not_strike(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await armed_and_fighting(client, app, me, narrated, friend, equipment=[], inventory=[])
    # 드워프 기사가 먼저 크게 쳐서 쓰러뜨린다(2d8 = 16, 부상 표는 부상 없음)
    dice = load_dice(app, [FIRST, LAST, PASS, 8, 8, NO_INJURY])

    await laugh(client, me, world)
    await send(client, friend, world, punch(world['lady']['id'], 'heavy'), content=PUNCH)
    await narrated()

    (turn,) = npc_turns(await turns_of(session, world['table'], 2))
    assert turn['outcome'] == {'skipped': 'downed'}
    assert await events_of(client, me, world['table'], 'npc_attacked') == []
    assert dice.remaining == 0


# --- DB 를 쓰지 않는 작은 함수들 ---


def person_with(**npc_fields) -> SimpleNamespace:
    """장면의 인물 하나. 기본은 살아 있고, 적대이고, 라운드 1 에 싸움이 붙었고, 부채 후리기를 지녔다."""
    npc = {
        'status': NpcStatus.ALIVE,
        'attitude': NpcAttitude.HOSTILE,
        'fought_round': 1,
        'abilities': {'dex': 10},
        'injuries': [],
        **npc_fields,
    }
    return SimpleNamespace(
        entry_id=uuid.uuid4(),
        name='악역영애',
        npc=SimpleNamespace(**npc),
        definition=SimpleNamespace(attacks=[AttackSnapshot(**SWIPE)]),
    )


@pytest.mark.parametrize(
    ('fields', 'expected'),
    [
        ({}, True),
        ({'status': NpcStatus.DOWNED}, False),
        ({'status': NpcStatus.DEAD}, False),
        ({'attitude': NpcAttitude.WARY}, False),
        ({'fought_round': None}, False),
    ],
)
def test_who_acts(fields: dict, expected: bool):
    assert can_act(person_with(**fields)) is expected


def test_without_a_sheet_no_one_acts():
    person = person_with()

    assert can_act(SimpleNamespace(**{**vars(person), 'definition': None})) is False


def test_a_stunned_npc_cannot_move():
    stunned = TableInjury(injury='stunned', ended_at=None)
    judging = SimpleNamespace(ruleset=SRD5)

    assert stopped_by(judging, person_with(injuries=[stunned])) == INCAPACITATED
    assert stopped_by(judging, person_with()) is None


def test_the_npcs_injuries_hinder_its_attack():
    limp = TableInjury(injury='limp', ended_at=None)
    judging = SimpleNamespace(ruleset=SRD5, dice=ScriptedDice([HIT]))

    rolled = roll_attack(judging, person_with(injuries=[limp]), AttackSnapshot(**SWIPE))

    # 절뚝거림은 민첩에 -1 이다. 15 가 14 가 되어 빗나간다
    assert (rolled.check.modifier, rolled.check.success, rolled.hindrance.injuries) == (-1, False, ('limp',))


def test_an_npc_turn_never_comes_first_by_surprise():
    person = person_with(abilities={'dex': 14})

    turn = initiative.npc_turn(SRD5, person)

    assert (turn.kind, turn.first, turn.score, turn.npc) == (initiative.TurnKind.NPC, False, 14, person)
    assert initiative.turn_document(turn) == {
        'kind': 'npc',
        'first': False,
        'score': 14,
        'tiebreak': None,
        'entry_id': str(person.entry_id),
        'name': '악역영애',
    }


def test_the_narrator_gets_the_npc_line_in_turn_order():
    turn = {
        'kind': 'npc',
        'name': '악역영애',
        'outcome': {'attack': SWIPE, 'character_name': '엘프', 'success': False, 'effect': None},
    }

    note = to_turn_note(turn)

    assert note == TurnNote(npc=MonsterTurnNote(name='악역영애', attack='부채 후리기', target='엘프', hit=False))
    assert round_lines([], [note]) == ['악역영애: 엘프에게 부채 후리기 (빗나감)']


def test_a_skipped_npc_turn_is_not_narrated():
    assert to_turn_note({'kind': 'npc', 'name': '악역영애', 'outcome': {'skipped': 'downed'}}) is None
