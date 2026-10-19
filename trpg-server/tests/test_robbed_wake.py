# trpg-server/tests/test_robbed_wake.py

"""
쓰러진 동안 빼앗긴 NPC 가 깨어날 때의 반응(#494, app/rounds/wakes.py)과 새 태도 경계(wary)를 검증한다.

판은 test_npc_items.py 의 것이다. 악역영애가 부채와 금화 5개를 지녔다. 룰북은 SRD5 다(적대 10%, 경계 40%).
라운드 1 에 엘프가 악역영애를 쓰러뜨리고(금화는 남는다), 라운드 2 에 금화를 빼앗고, 라운드 3 에 상처를 싸매 일으킨다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 일으키는 판정, 회복의 양, 그다음이 반응의 백면체다.

보는 것.
  - 반응: 1~10 은 적대, 11~50 은 경계, 51~100 은 눈치채지 못한다. 태도는 더 날 선 쪽으로만 바뀐다.
  - 빼앗기지 않았으면 굴리지 않는다. 한 번 굴리면 적어 둔 것을 비운다.
  - 이벤트(npc_attitude_changed, robbed_while_down)는 그 인물이 일어난 변화에 잇는다. 서술의 판정 줄에 붙는다.
  - 경계하는 인물에게서는 훔치기의 방심 보정이 없다. 판의 처음 태도로도 적을 수 있다.
  - 판 형식 40: 규칙의 robbed_wake. 옛 판은 SRD5 의 것으로 읽는다. 룰북에는 마이그레이션이 채운다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import NpcAttitude
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_39
from app.engine.dice import ScriptedDice
from app.engine.ruleset import RobbedWake
from app.engine.templates import SRD5
from app.rounds.move_lines import describe_wake
from app.rounds.narrator import WakeNote
from app.rounds.wakes import reaction_of, wake_after
from app.tables.models import NpcStatus, TableNpc
from app.tables.npc_attitudes import sharpens
from app.tables.npcs import mark_robbed, take_robbed
from tests.test_loots import LOOT, lady_down, loot
from tests.test_npc_actions import PASS, TEND, bearer, events_of, load_dice, people, tend
from tests.test_npc_steals import ME, lady_state, outcome, send, start, steal_now
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key) -> dict[str, str]:
    return bearer(signing_key, ME)


async def rob_and_wake(client: AsyncClient, app: FastAPI, me: dict, narrated, roll: int | None, **fields) -> dict:
    """
    쓰러뜨리고(라운드 1), 빼앗고(라운드 2), 일으킨다(라운드 3). roll 은 반응의 백면체다(None 이면 눈을 두지 않는다).

    fields 는 악역영애의 시트에 더한다(처음 태도 등).
    """
    world = await start(client, me, **fields)
    await lady_down(client, app, me, world, narrated)
    load_dice(app, [])
    assert (await send(client, me, world, loot(world, 'coins'), content=LOOT)).status_code == status.HTTP_200_OK
    await narrated()
    world['dice'] = load_dice(app, [PASS, 2] + ([] if roll is None else [roll]))
    assert (await send(client, me, world, tend(world['lady']['id']), content=TEND)).status_code == status.HTTP_200_OK
    await narrated()
    return world


# --- 반응 ---


@pytest.mark.parametrize(
    ('roll', 'reaction', 'attitude'),
    [
        (1, 'hostile', 'hostile'),
        (10, 'hostile', 'hostile'),
        (11, 'wary', 'wary'),
        (50, 'wary', 'wary'),
        (51, None, 'neutral'),
    ],
)
async def test_waking_up_robbed_rolls_a_reaction(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    session: AsyncSession,
    narrated,
    roll: int,
    reaction: str | None,
    attitude: str,
):
    world = await rob_and_wake(client, app, me, narrated, roll)

    wake = (await outcome(client, me, world, 3))['wake']

    assert (wake['entry_id'], wake['name'], wake['roll'], wake['reaction']) == (
        world['lady']['id'],
        '악역영애',
        roll,
        reaction,
    )
    lady = await lady_state(session, world)
    assert (lady.status, lady.attitude, lady.robbed_round) == (NpcStatus.ALIVE, attitude, None)
    assert world['dice'].remaining == 0


async def test_a_change_is_recorded_and_narrated(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await rob_and_wake(client, app, me, narrated, 11)

    (changed,) = await events_of(client, me, world['table'], 'npc_attitude_changed')
    risen = (await events_of(client, me, world['table'], 'npc_changed'))[-1]

    assert changed['caused_by_sequence'] == risen['sequence']
    assert changed['payload'] == {
        'round': 3,
        'entry_id': world['lady']['id'],
        'name': '악역영애',
        'previous': 'neutral',
        'attitude': 'wary',
        'reason': 'robbed_while_down',
    }
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert '(깨어난 악역영애 이(가) 품이 빈 것을 알아챘다. 태도: 경계)' in narrations[-1]['payload']['text']
    (lady,) = [
        person for person in (await people(client, me, world['table']))['people'] if person['name'] == '악역영애'
    ]
    assert lady['attitude'] == 'wary'


async def test_not_noticing_leaves_no_trace(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await rob_and_wake(client, app, me, narrated, 51)

    assert await events_of(client, me, world['table'], 'npc_attitude_changed') == []
    narrations = await events_of(client, me, world['table'], 'gm_narration')
    assert '알아챘다' not in narrations[-1]['payload']['text']


@pytest.mark.parametrize(
    ('start_as', 'roll', 'expected'),
    [
        # 이미 적대면 무엇이 나와도 그대로다
        ('hostile', 1, 'hostile'),
        ('hostile', 11, 'hostile'),
        # 경계하던 인물은 적대가 나와야 바뀐다
        ('wary', 11, 'wary'),
        ('wary', 10, 'hostile'),
        # 우호하던 인물도 알아채면 경계한다
        ('friendly', 11, 'wary'),
    ],
)
async def test_the_attitude_only_sharpens(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    session: AsyncSession,
    narrated,
    start_as: str,
    roll: int,
    expected: str,
):
    world = await rob_and_wake(client, app, me, narrated, roll, attitude=start_as)

    wake = (await outcome(client, me, world, 3))['wake']

    assert (await lady_state(session, world)).attitude == expected
    assert (wake['attitude_change'] is None) is (start_as == expected)


async def test_waking_without_being_robbed_rolls_nothing(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await start(client, me)
    await lady_down(client, app, me, world, narrated)
    dice = load_dice(app, [PASS, 2])

    await send(client, me, world, tend(world['lady']['id']), content=TEND)
    await narrated()

    assert (await outcome(client, me, world, 2))['wake'] is None
    assert dice.remaining == 0


# --- 경계 ---


async def test_a_wary_npc_is_never_off_guard(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me, attitude='wary')

    stolen = await steal_now(client, app, me, world, 'coins', [1], narrated)

    # 아직 아무와도 싸우지 않았지만 경계하고 있어 방심 보정(-3)이 없다
    assert (stolen['check']['target'], stolen['factors']) == (15, [])


# --- 판과 룰북 ---


def test_an_old_snapshot_reads_the_srd5_reaction():
    document = {'format': 39, 'rulebook': {'title': '룰북', 'rules': {'die': 20}}}

    upgraded = upgrade_from_39(document)

    assert upgraded['format'] == 40
    assert upgraded['rulebook']['rules'] == {'die': 20, 'robbed_wake': {'hostile': 10, 'wary': 40}}
    assert 'robbed_wake' not in document['rulebook']['rules']
    assert UPGRADES[39] is upgrade_from_39


def test_the_migration_fills_the_srd5_reaction_once():
    migration = load_migration('robbed_wake')

    assert SRD5.model_dump(mode='json')['robbed_wake'] == migration.ROBBED_WAKE
    assert migration.with_robbed_wake({'die': 20}) == {'die': 20, 'robbed_wake': migration.ROBBED_WAKE}
    assert migration.with_robbed_wake({'robbed_wake': None}) == {'robbed_wake': None}
    assert migration.without_robbed_wake({'die': 20, 'robbed_wake': {}}) == {'die': 20}


def test_the_chances_cannot_pass_a_hundred():
    with pytest.raises(ValidationError):
        RobbedWake(hostile=60, wary=41)


# --- DB 를 쓰지 않는 작은 함수들 ---


@pytest.mark.parametrize(
    ('roll', 'expected'),
    [(1, NpcAttitude.HOSTILE), (10, NpcAttitude.HOSTILE), (11, NpcAttitude.WARY), (50, NpcAttitude.WARY), (51, None)],
)
def test_the_roll_picks_the_reaction(roll: int, expected: NpcAttitude | None):
    assert reaction_of(RobbedWake(hostile=10, wary=40), roll) == expected


@pytest.mark.parametrize(
    ('current', 'attitude', 'expected'),
    [
        (NpcAttitude.NEUTRAL, NpcAttitude.WARY, True),
        (NpcAttitude.WARY, NpcAttitude.WARY, False),
        (NpcAttitude.HOSTILE, NpcAttitude.WARY, False),
        (NpcAttitude.FRIENDLY, NpcAttitude.NEUTRAL, True),
    ],
)
def test_an_attitude_sharpens_only_forward(current: NpcAttitude, attitude: NpcAttitude, expected: bool):
    assert sharpens(current, attitude) is expected


def test_only_a_downed_npc_is_marked_robbed_once():
    downed = TableNpc(status=NpcStatus.DOWNED, robbed_round=None)
    dead = TableNpc(status=NpcStatus.DEAD, robbed_round=None)

    mark_robbed(downed, 2)
    mark_robbed(downed, 3)
    mark_robbed(dead, 2)

    assert (downed.robbed_round, dead.robbed_round) == (2, None)
    assert (take_robbed(downed), downed.robbed_round, take_robbed(downed)) == (True, None, False)


def test_without_a_rule_nothing_is_rolled_but_the_mark_is_cleared():
    npc = TableNpc(entry_id=uuid.uuid4(), status=NpcStatus.ALIVE, attitude='neutral', robbed_round=2)
    person = SimpleNamespace(entry_id=npc.entry_id, name='악역영애', npc=npc)
    judging = SimpleNamespace(cast=[person], ruleset=SimpleNamespace(robbed_wake=None), dice=ScriptedDice([]))
    effect = {'entry_id': str(npc.entry_id), 'status_before': 'downed', 'status': 'alive'}

    assert wake_after(judging, effect) is None
    assert npc.robbed_round is None


def test_the_wake_line():
    assert describe_wake(WakeNote('악역영애', '적대')) == '(깨어난 악역영애 이(가) 품이 빈 것을 알아챘다. 태도: 적대)'
