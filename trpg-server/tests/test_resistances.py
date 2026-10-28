# trpg-server/tests/test_resistances.py

"""
저항(#886 ②)을 검증한다. 저항 한 줄은 성질과 단계(resist 저항, immune 면역, vulnerable 약점)다.

저항이 오는 곳은 셋이다. 캐릭터와 NPC 의 시트(타고난 것), 착용한 장비의 아이템 규칙(입고 있는 동안),
부상(상태)의 정의(입고 있는 동안). 저항과 면역이면 그 성질의 부상과, 그 성질을 단 수치를 내리는 맞추기를 받지 않는다.
약점은 부상과 맞추기에 아무것도 하지 않는다(피해는 #886 ③).

판은 다른 시험의 것을 빌린다.
  - test_monster_turns.py: 수로 입구에 쥐 한 마리. 독 뿜기(피해 없이 중독)를 쓴다. 엘프의 판정은 민첩·보통이다.
    중독된 엘프는 판정에 불리하다(눈 둘). 막았으면 중독되지 않아 눈 하나다.
  - test_item_effects.py: 독 단검(가벼운 피해와 중독), 기절 가루(기절). 악역영애(비올레타)는 장면의 인물이다.
  - test_resource_rounds.py 와 같은 모양의 스태미나 룰북: 0 에 닿으면 중독(문턱)이다.

넷을 본다.
  - 모양: 한 성질에 한 줄, 부상의 저항과 맞추기의 성질은 규칙의 성질이다. 성질은 내리는 맞추기에만,
    저항은 착용하는 물건에만 단다.
  - 어디서 오는가: 시트와 착용한 것과 입은 부상의 저항을 모은다. 몬스터는 타입과 시트의 면역을 더한다.
  - 판: 시트의 저항이 테이블의 시트로 간다. 공격과 물건의 부상, 내리는 맞추기, 수치의 문턱, 후유증을 막는다.
    게시할 때 모르는 성질은 nature_invalid 다.
  - 서술과 되돌리기: 막아 낸 부상과 수치를 같은 말로 적는다. 되돌리면 저항과 성질의 칸을 뺀다.
"""

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import ItemKind
from app.assets.scenarios.publishing import attack_fault
from app.assets.scenarios.schemas import ItemRule, MonsterAttack
from app.assets.scenarios.snapshot import MonsterSnapshot, NpcSheetSnapshot
from app.engine.dice import ScriptedDice
from app.engine.item_effects import AdjustEffect, is_resisted
from app.engine.monster_kinds import MonsterKind
from app.engine.ruleset import Resistance, ResourceHolder, Ruleset, blocked_natures
from app.engine.templates import SRD5
from app.rounds.injuries import expire_all
from app.rounds.move_lines import describe_impact, describe_monster_turn
from app.rounds.narration_request import to_impact, to_turn_note
from app.tables import resistances
from app.tables.injuries import Moment
from app.tables.items import CatalogItem
from app.tables.models import TableInjury
from tests import test_friendly_fire as friendly
from tests import test_injuries as hurt
from tests import test_item_effects as item_world
from tests import test_monster_turns as turns
from tests import test_resource_rounds as stamina
from tests.sheets import make_sheet
from tests.test_attack_costs import rewrite_content
from tests.test_attack_effects import DRAIN, MANA, SPIT, injuries_of, turn_outcome
from tests.test_npc_sheets import refused
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

me = turns.me
friend = friendly.friend
FRIEND = friendly.FRIEND
ME = turns.ME
PASS = turns.PASS
FAIL = turns.FAIL
RESIST_POISON = {'nature': 'poison', 'level': 'resist'}
IMMUNE_POISON = {'nature': 'poison', 'level': 'immune'}
WEAK_TO_POISON = {'nature': 'poison', 'level': 'vulnerable'}
FAST_ELF = make_sheet(dex=10)
FAST_RAT = make_sheet(max_hp=4, dex=14)
# 입고 있는 동안 독에 저항하는 상태
STONESKIN = {
    'key': 'stoneskin',
    'name': '돌 피부',
    'fact': '살갗이 돌처럼 굳었다.',
    'healing': 'permanent',
    'resistances': [RESIST_POISON],
}


def rules_with(**fields) -> dict:
    return {**SRD5.model_dump(mode='json'), **fields}


def resisting(*lines: dict) -> list[Resistance]:
    return [Resistance.model_validate(line) for line in lines]


# --- 모양 ---


def test_a_nature_is_resisted_once():
    with pytest.raises(ValidationError, match='같은 성질의 저항'):
        ItemRule.model_validate(
            {'entry_id': str(uuid.uuid4()), 'slots': ['body'], 'resistances': [RESIST_POISON, IMMUNE_POISON]}
        )
    with pytest.raises(ValidationError):
        Resistance.model_validate({'nature': 'poison', 'level': 'halved'})


def test_an_injury_grants_only_the_rules_natures():
    rules = Ruleset.model_validate(rules_with(injuries=[*SRD5.model_dump(mode='json')['injuries'], STONESKIN]))

    assert rules.injuries[-1].resistances == tuple(resisting(RESIST_POISON))
    with pytest.raises(ValidationError, match='부상의 성질이 규칙에 없습니다'):
        stranger = {**STONESKIN, 'resistances': [{'nature': 'fire', 'level': 'resist'}]}
        Ruleset.model_validate(rules_with(injuries=[*SRD5.model_dump(mode='json')['injuries'], stranger]))


def test_only_a_lowering_adjust_carries_a_nature():
    lowering = AdjustEffect.model_validate({**DRAIN, 'nature': 'poison'})

    assert lowering.nature == 'poison'
    with pytest.raises(ValidationError, match='내리는 맞추기'):
        AdjustEffect.model_validate({**DRAIN, 'amount': 2, 'nature': 'poison'})


def test_a_skill_drain_names_a_nature_of_the_rules():
    skill = {
        'key': 'wither',
        'name': '시들게 하기',
        'target': 'foe',
        'check': {'ability': 'int', 'difficulty': None},
        'effects': [{**DRAIN, 'nature': 'fire'}],
    }
    mana = {**MANA, 'holders': ['characters']}

    with pytest.raises(ValidationError):
        Ruleset.model_validate(rules_with(resources=[mana], skills=[skill]))
    known = Ruleset.model_validate(
        rules_with(resources=[mana], skills=[{**skill, 'effects': [{**DRAIN, 'nature': 'poison'}]}])
    )
    assert known.skills[0].effects[0].nature == 'poison'


def test_only_a_worn_thing_carries_resistances():
    with pytest.raises(ValidationError, match='칸\\(slots\\)이 있는 물건'):
        ItemRule.model_validate({'entry_id': str(uuid.uuid4()), 'resistances': [RESIST_POISON]})


@pytest.mark.parametrize(
    ('lines', 'blocked'),
    [
        ([RESIST_POISON], {'poison'}),
        ([IMMUNE_POISON], {'poison'}),
        ([WEAK_TO_POISON], set()),
        ([WEAK_TO_POISON, {'nature': 'stun', 'level': 'immune'}], {'stun'}),
    ],
    ids=['resist', 'immune', 'vulnerable', 'mixed'],
)
def test_resist_and_immune_block_and_vulnerable_does_not(lines: list[dict], blocked: set[str]):
    assert blocked_natures(resisting(*lines)) == blocked


def test_only_a_lowering_adjust_of_a_blocked_nature_is_resisted():
    drain = AdjustEffect.model_validate({**DRAIN, 'nature': 'poison'})

    assert is_resisted(drain, frozenset({'poison'}))
    assert not is_resisted(drain, frozenset({'stun'}))
    assert not is_resisted(AdjustEffect.model_validate(DRAIN), frozenset({'poison'}))
    # 올리는 맞추기는 성질이 있어도(모양 검사를 건너뛴 것) 막지 않는다
    raising = AdjustEffect.model_construct(kind='adjust', resource='mana', amount=2, nature='poison')
    assert not is_resisted(raising, frozenset({'poison'}))


@pytest.mark.parametrize(('nature', 'fault'), [('poison', False), ('fire', True)])
def test_an_attack_drain_names_a_nature_of_the_rules(nature: str, fault: bool):
    rules = Ruleset.model_validate(rules_with(resources=[{**MANA, 'holders': ['characters']}]))
    attack = MonsterAttack.model_validate({**SPIT, 'effects': [{**DRAIN, 'nature': nature}]})

    assert attack_fault(rules, attack, ResourceHolder.MONSTERS) is fault


# --- 어디서 오는가 ---


AMULET = uuid.uuid4()
CLOAK = uuid.uuid4()


BOOK = uuid.uuid4()


def catalog() -> dict[uuid.UUID, CatalogItem]:
    """독을 막는 부적과 기절에 약한 망토와 정신을 막는 책(착용하지 않는 물건이라 들고만 다닌다)."""
    return {
        BOOK: CatalogItem(
            BOOK, '책', ItemKind.GEAR, resistances=tuple(resisting({'nature': 'mind', 'level': 'immune'}))
        ),
        AMULET: CatalogItem(
            AMULET, '부적', ItemKind.GEAR, slots=('head',), resistances=tuple(resisting(IMMUNE_POISON))
        ),
        CLOAK: CatalogItem(
            CLOAK,
            '망토',
            ItemKind.GEAR,
            slots=('body',),
            resistances=tuple(resisting({'nature': 'stun', 'level': 'vulnerable'})),
        ),
    }


def stoneskin_rules() -> Ruleset:
    return Ruleset.model_validate(rules_with(injuries=[*SRD5.model_dump(mode='json')['injuries'], STONESKIN]))


def test_a_character_gathers_sheet_worn_and_injuries():
    rules = stoneskin_rules()
    worn = [SimpleNamespace(entry_id=CLOAK, slots=['body'])]
    stone = TableInjury(injury='stoneskin', round_number=1)
    sheet = SimpleNamespace(resistances=[{'nature': 'mind', 'level': 'resist'}], worn=worn, injuries=[stone])

    gathered = resistances.of_member(rules, catalog(), sheet)

    assert [(one.nature, one.level) for one in gathered] == [
        ('mind', 'resist'),
        ('stun', 'vulnerable'),
        ('poison', 'resist'),
    ]
    assert resistances.member_blocked(rules, catalog(), sheet) == {'mind', 'poison'}
    # 풀린 상태는 저항을 주지 않는다
    stone.ended_at = datetime.now(UTC)
    assert resistances.member_blocked(rules, catalog(), sheet) == {'mind'}


def test_an_npc_wears_only_its_equipment():
    definition = NpcSheetSnapshot.model_validate(
        {
            'entry_id': str(uuid.uuid4()),
            'sheet': make_sheet(),
            'equipment': [{'entry_id': str(AMULET), 'count': 1, 'chance': 0, 'wear': ['head']}],
            'inventory': [{'entry_id': str(BOOK), 'count': 1, 'chance': 0}],
            'resistances': [{'nature': 'sense', 'level': 'immune'}],
        }
    )
    npc = SimpleNamespace(items=[], injuries=[])

    assert resistances.npc_blocked(SRD5, catalog(), npc, definition) == {'sense', 'poison'}
    # 시트를 적지 않은 인물은 입은 부상의 것뿐이다
    assert resistances.npc_blocked(SRD5, catalog(), npc, None) == frozenset()


def test_a_monster_adds_its_worn_things_to_its_immunities():
    definition = MonsterSnapshot.model_validate(
        {
            'id': str(uuid.uuid4()),
            'name': '해골 병사',
            'content': '녹슨 창',
            'kind': MonsterKind.BEAST,
            'sheet': make_sheet(),
            'equipment': [
                {'entry_id': str(CLOAK), 'count': 1, 'chance': 0, 'wear': ['body']},
                {'entry_id': str(AMULET), 'count': 1, 'chance': 0, 'wear': ['head']},
            ],
            'immune': ['stun'],
        }
    )
    monster = SimpleNamespace(items=[], injuries=[])

    # 시트는 기절, 쓴 부적은 독. 망토의 약점은 면역을 지우지 않는다
    assert resistances.monster_blocked(SRD5, catalog(), monster, definition) == {'poison', 'stun'}


def test_an_aftermath_of_a_blocked_nature_is_not_taken():
    broken = TableInjury(injury='broken_arm', source='injury_table', round_number=1, heals_at=5)
    sheet = SimpleNamespace(injuries=[broken], died_at=None)
    member = SimpleNamespace(user_id=ME, character_name='엘프', sheet=sheet)
    scene = SimpleNamespace(npcs=[], cast=[], monsters=[], all_monsters=[])
    guard = SimpleNamespace(member=lambda _: frozenset({'body'}))
    moment = Moment(round_number=2, now=0, scene_end=10)

    # 후유증 표의 1 은 굽은 팔(몸)이다. 몸을 막으면 입지 않는다
    (ended,) = expire_all([member], scene, SRD5, ScriptedDice([1]), uuid.uuid4(), moment, guard)

    assert (ended.aftermath['injury'], ended.aftermath['immune']) == (None, 'crooked_arm')
    assert [row.injury for row in sheet.injuries] == ['broken_arm']


# --- 게시 ---


async def scenario_with(client: AsyncClient, me: dict, **fields) -> dict:
    """test_item_effects.py 의 수로 시나리오에 칸들을 바꿔 단다."""
    world = await item_world.make_world(client, me)
    scenario = await item_world.make_scenario(client, me, world, item_world.the_items(world))
    url = f'{turns.SCENARIOS_URL}/{scenario["id"]}'
    patched = await client.patch(url, json={key: value(world) for key, value in fields.items()}, headers=me)
    assert patched.status_code == status.HTTP_200_OK, patched.text
    return {**world, 'scenario': scenario}


FIRE = [{'nature': 'fire', 'level': 'resist'}]


@pytest.mark.parametrize(
    'fields',
    [
        {'default_sheet': lambda _: {**make_sheet(), 'resistances': FIRE}},
        {'npc_sheets': lambda world: [{'entry_id': world['lady']['id'], 'sheet': make_sheet(), 'resistances': FIRE}]},
        {
            'items': lambda world: [
                {'entry_id': world['dagger']['id'], 'kind': 'gear', 'slots': ['main_hand'], 'resistances': FIRE}
            ]
        },
        {
            'items': lambda world: [
                {'entry_id': world['dagger']['id'], 'kind': 'consumable', 'effects': [{**DRAIN, 'nature': 'fire'}]}
            ]
        },
    ],
    ids=['sheet', 'npc-sheet', 'worn-thing', 'drain'],
)
async def test_a_nature_the_rules_lack_is_refused(client: AsyncClient, me: dict, fields: dict):
    world = await scenario_with(client, me, **fields)

    assert 'nature_invalid' in await refused(client, me, world['scenario'])


async def test_known_natures_are_published(client: AsyncClient, me: dict):
    world = await scenario_with(
        client,
        me,
        default_sheet=lambda _: {**make_sheet(), 'resistances': [RESIST_POISON]},
        npc_sheets=lambda world: [
            {'entry_id': world['lady']['id'], 'sheet': make_sheet(), 'resistances': [IMMUNE_POISON]}
        ],
    )

    response = await client.post(f'{turns.SCENARIOS_URL}/{world["scenario"]["id"]}/versions', json={}, headers=me)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    snapshot = response.json()['snapshot']
    assert (snapshot['default_sheet']['resistances'], snapshot['npc_sheets'][0]['resistances']) == (
        [RESIST_POISON],
        [IMMUNE_POISON],
    )


# --- 공격 ---


async def resisting_elf(client: AsyncClient, me: dict, *lines: dict) -> dict:
    """그 저항을 가진 엘프가 독을 뿜는 쥐와 마주한 테이블."""
    return await turns.start_table(
        client, me, rat_sheet=FAST_RAT, attacks=[SPIT], sheet={**FAST_ELF, 'resistances': list(lines)}
    )


async def test_the_sheet_s_resistances_are_handed_out(client: AsyncClient, me: dict):
    table = await resisting_elf(client, me, RESIST_POISON)

    read = (await client.get(turns.table_url(table), headers=me)).json()

    assert read['members'][0]['sheet']['resistances'] == [RESIST_POISON]


@pytest.mark.parametrize(
    ('line', 'rolls', 'poisoned'),
    [
        (RESIST_POISON, [PASS, FAIL], False),
        (IMMUNE_POISON, [PASS, FAIL], False),
        (WEAK_TO_POISON, [PASS, FAIL, FAIL], True),
    ],
    ids=['resist', 'immune', 'vulnerable'],
)
async def test_a_resisting_elf_is_not_poisoned_by_the_spit(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, line: dict, rolls: list[int], poisoned: bool
):
    table = await resisting_elf(client, me, line)
    # 쥐의 맞히기, 엘프의 판정(중독되면 눈 둘)
    dice = turns.load_dice(app, rolls)

    await turns.declare(client, me, table, turns.REST, turns.rest())

    (injured,) = (await turn_outcome(session, table))['injured']
    assert (injured['injury'] == 'poisoned', injured.get('immune')) == (poisoned, None if poisoned else 'poisoned')
    assert await injuries_of(session, table) == ([('poisoned', 'attack')] if poisoned else [])
    assert dice.remaining == 0


async def test_a_state_grants_its_resistance(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await turns.start_table(client, me, rat_sheet=FAST_RAT, attacks=[SPIT], sheet=FAST_ELF)

    def with_stoneskin(content: dict) -> None:
        content['rulebook']['rules']['injuries'].append(STONESKIN)

    await rewrite_content(session, table['id'], with_stoneskin)
    await session.execute(
        text(
            'INSERT INTO table_injuries (id, table_id, sheet_id, injury, source, round_number) '
            "SELECT :id, table_id, id, 'stoneskin', 'item', 1 FROM table_sheets WHERE table_id = :table_id"
        ),
        {'id': uuid.uuid4(), 'table_id': uuid.UUID(table['id'])},
    )
    await session.commit()
    turns.load_dice(app, [PASS, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    (injured,) = (await turn_outcome(session, table))['injured']
    assert injured['immune'] == 'poisoned'
    assert await injuries_of(session, table) == [('stoneskin', 'item')]


async def drained(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, *lines: dict) -> dict:
    """마나를 단 판에서 쥐가 독의 마나 빨기(-2)를 쓴다. 엘프는 그 저항을 가진다. 결과의 바뀐 수치들이다."""
    table = await resisting_elf(client, me, *lines)

    def with_mana(content: dict) -> None:
        content['rulebook']['rules']['resources'] = [MANA]
        content['monsters'][0]['attacks'] = [{**SPIT, 'name': '독 빨기', 'effects': [{**DRAIN, 'nature': 'poison'}]}]

    await rewrite_content(session, table['id'], with_mana)
    turns.load_dice(app, [PASS, FAIL])
    await turns.declare(client, me, table, turns.REST, turns.rest())
    return {'table': table, 'shifts': (await turn_outcome(session, table))['resources']}


async def test_a_resisted_drain_leaves_the_resource(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    result = await drained(client, app, me, session, RESIST_POISON)

    (shift,) = result['shifts']
    assert (shift['before'], shift['after'], shift['resisted'], shift['user_id']) == (6, 6, 'poison', str(ME))
    events = await turns.events_of(client, me, result['table'])
    assert [event for event in events if event['type'] == 'resource_changed'] == []


async def test_a_drain_with_a_nature_lowers_one_who_does_not_resist(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    result = await drained(client, app, me, session, WEAK_TO_POISON)

    assert [(one['before'], one['after'], one.get('resisted')) for one in result['shifts']] == [(6, 4, None)]


# --- 물건 ---


async def item_table(client: AsyncClient, me: dict, **fields) -> dict:
    """test_item_effects.py 의 수로에 칸들을 바꿔 달고 혼자 시작한다."""
    world = await scenario_with(client, me, **fields)
    scenario = world['scenario']
    await item_world.post(client, f'{turns.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await item_world.post(client, turns.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(turns.table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(turns.table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': started.json()}


def amulet_items(world: dict) -> list[dict]:
    """물건 넷에 독을 막는 연막탄을 머리에 쓴다(착용하는 장비로 바꾼다)."""
    smoke = {'entry_id': world['smoke']['id'], 'kind': 'gear', 'slots': ['head'], 'resistances': [IMMUNE_POISON]}
    return [*item_world.the_items(world)[:3], smoke]


def amulet_worn(world: dict) -> list[dict]:
    names = ('dagger', 'powder', 'potion')
    return [
        *({'entry_id': world[name]['id'], 'count': 1} for name in names),
        {'entry_id': world['smoke']['id'], 'count': 1, 'wear': ['head']},
    ]


async def test_a_worn_thing_keeps_the_poison_out(client: AsyncClient, app: FastAPI, me: dict):
    world = await item_table(client, me, items=amulet_items, starting_items=amulet_worn)
    # 자기에게 쓰면 굴리지 않는다. 피해의 눈만 쓴다
    dice = item_world.load_dice(app, [3])

    closing = await item_world.declare(client, me, world['table'], '단검을 핥는다.', item_world.use(world['dagger']))

    (injured,) = item_world.outcome_of(closing)['item_use']['injured']
    assert (injured['injury'], injured['immune']) == (None, 'poisoned')
    after = await item_world.read_table(client, me, world['table'])
    assert item_world.sheet_of(after, ME)['injuries'] == []
    assert dice.remaining == 0
    smoke = next(item for item in after['items'] if item['entry_id'] == world['smoke']['id'])
    assert smoke['resistances'] == [IMMUNE_POISON]


async def test_a_person_immune_to_stun_shrugs_off_the_powder(client: AsyncClient, app: FastAPI, me: dict):
    immune = {'nature': 'stun', 'level': 'immune'}
    world = await item_table(
        client,
        me,
        npc_sheets=lambda world: [
            {'entry_id': world['lady']['id'], 'sheet': make_sheet(max_hp=10), 'resistances': [immune]}
        ],
    )
    lady = (await item_world.people(client, me, world['table']))['people'][0]
    item_world.load_dice(app, [PASS])

    closing = await item_world.declare(
        client, me, world['table'], '가루를 뿌린다.', item_world.use(world['powder'], npc=lady['id'])
    )

    (injured,) = item_world.outcome_of(closing)['item_use']['injured']
    assert (injured['injury'], injured['immune']) == (None, 'stunned')
    assert (await item_world.people(client, me, world['table']))['people'][0]['injuries'] == []


# --- 수치의 문턱 ---


async def test_a_threshold_injury_is_kept_out(client: AsyncClient, me: dict, session: AsyncSession):
    lorebook = await stamina.post(client, turns.LOREBOOKS_URL, me, title='고개')
    rulebook = await stamina.post(
        client, turns.RULEBOOKS_URL, me, title='지친 룰북', template='srd5', resources=[stamina.STAMINA]
    )
    sheet = {'abilities': stamina.ABILITIES, 'max_hp': 10, 'resistances': [IMMUNE_POISON]}
    scenario = await stamina.post(
        client,
        turns.SCENARIOS_URL,
        me,
        title='고개',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        openings=['긴 고갯길이다.'],
        default_sheet=sheet,
    )
    await stamina.post(client, f'{turns.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await stamina.post(client, turns.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(turns.table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.post(turns.table_url(table, '/start'), headers=me)
    await stamina.set_stamina(session, 1)

    await stamina.declare(client, me, table, '걷는다.')

    changed = await stamina.events_of(client, me, table, 'resource_changed')
    assert stamina.payloads(changed, 'before', 'after') == [(1, 0)]
    assert await stamina.events_of(client, me, table, 'injury_gained') == []


# --- 서술 ---


def test_the_narrator_hears_what_was_kept_out():
    turn = {
        'kind': 'monster',
        'name': '독거미',
        'outcome': {
            'attack': {'name': '독니'},
            'character_name': '엘프',
            'success': True,
            'effect': None,
            'injured': [{'injury': None, 'immune': 'poisoned', 'name': '중독'}],
            'resources': [
                {'resource': 'mana', 'name': '마나', 'before': 5, 'after': 5, 'max': 7, 'resisted': 'poison'}
            ],
        },
    }

    line = describe_monster_turn(to_turn_note(turn).monster)

    assert line == '독거미: 엘프에게 독니 (맞음) [막아 낸 부상: 중독] [수치: 마나 막아 냄]'


def test_a_character_s_kept_out_injury_is_told():
    effect = {
        'kind': 'damage',
        'character_name': '드워프',
        'amount': 9,
        'after': 1,
        'max_hp': 12,
        'downed': False,
        'injury_roll': {'injury': None, 'immune': 'poisoned', 'name': '중독'},
    }

    assert describe_impact(to_impact(effect)) == '→ 드워프 피해 9 (HP 1/12). 막아 낸 부상: 중독'


# --- 되돌리기 ---


def test_going_back_takes_the_resistances_and_natures_out():
    migration = load_migration('resistances')
    rules = {
        'injuries': [STONESKIN],
        'skills': [{'key': 'wither', 'effects': [{**DRAIN, 'nature': 'poison'}]}],
        'natures': [],
    }
    row = {
        'default_sheet': {**make_sheet(), 'skills': [], 'resistances': [RESIST_POISON]},
        'pregens': [{'name': '기사', 'sheet': {**make_sheet(), 'resistances': []}}, {'name': '빈 칸', 'sheet': None}],
        'npc_sheets': [
            {'entry_id': 'a', 'resistances': [IMMUNE_POISON], 'attacks': [{'effects': [{**DRAIN, 'nature': 'poison'}]}]}
        ],
        'monster_sheets': [{'monster_id': 'b', 'attacks': [{'name': '물기'}]}],
        'items': [
            {'entry_id': 'c', 'resistances': [RESIST_POISON], 'effects': [{**DRAIN, 'nature': 'poison'}]},
            {'entry_id': 'd'},
        ],
    }

    back = migration.scenario_without_resistances(json.loads(json.dumps(row)))

    assert migration.rules_without_resistances(rules) == {
        'injuries': [{key: value for key, value in STONESKIN.items() if key != 'resistances'}],
        'skills': [{'key': 'wither', 'effects': [DRAIN]}],
        'natures': [],
    }
    assert back == {
        'default_sheet': {**make_sheet(), 'skills': []},
        'pregens': [{'name': '기사', 'sheet': make_sheet()}, {'name': '빈 칸', 'sheet': None}],
        'npc_sheets': [{'entry_id': 'a', 'attacks': [{'effects': [DRAIN]}]}],
        'monster_sheets': [{'monster_id': 'b', 'attacks': [{'name': '물기'}]}],
        'items': [{'entry_id': 'c', 'effects': [DRAIN]}, {'entry_id': 'd'}],
    }
    assert migration.normalized(
        {'default_sheet': None, 'pregens': None, 'npc_sheets': [], 'monster_sheets': None, 'items': []}
    ) == {
        'default_sheet': None,
        'pregens': [],
        'npc_sheets': [],
        'monster_sheets': [],
        'items': [],
    }


async def test_going_back_rewrites_the_scenarios_and_rulebooks_in_the_database(
    client: AsyncClient, me: dict, session: AsyncSession
):
    migration = load_migration('resistances')
    world = await scenario_with(
        client,
        me,
        default_sheet=lambda _: {**make_sheet(), 'resistances': [RESIST_POISON]},
        items=lambda world: [{'entry_id': world['smoke']['id'], 'slots': ['head'], 'resistances': [IMMUNE_POISON]}],
    )
    scenario_id = uuid.UUID(world['scenario']['id'])
    plain = await session.scalar(text('SELECT npc_sheets FROM scenarios WHERE asset_id = :id'), {'id': scenario_id})

    await session.run_sync(lambda sync: migration.rewrite_scenarios(sync.connection()))
    await session.run_sync(lambda sync: migration.rewrite_rulebooks(sync.connection()))
    await session.commit()

    row = (
        await session.execute(
            text('SELECT default_sheet, items, npc_sheets FROM scenarios WHERE asset_id = :id'), {'id': scenario_id}
        )
    ).one()
    assert 'resistances' not in row.default_sheet
    assert ['resistances' in rule for rule in row.items] == [False]
    assert row.npc_sheets == [{k: v for k, v in one.items() if k != 'resistances'} for one in plain]
    injuries = await session.scalar(text("SELECT rules -> 'injuries' FROM rulebooks"))
    assert all('resistances' not in injury for injury in injuries)


# --- 부상 표와 겨눈 쪽 ---


async def test_a_big_hit_does_not_break_a_resisting_arm(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await hurt.start_table(client, me)
    await session.execute(
        text('UPDATE table_sheets SET resistances = CAST(:lines AS JSONB)'),
        {'lines': json.dumps([{'nature': 'body', 'level': 'resist'}])},
    )
    await session.commit()
    hurt.load_dice(app, [FAIL, 3, 4, hurt.BROKEN_ARM])

    closing = await hurt.declare(client, me, world['table'], hurt.JUMP, hurt.jump())

    roll = closing['declarations'][0]['outcome']['effect']['injury_roll']
    assert (roll['injury'], roll['immune']) == (None, 'broken_arm')


async def test_a_person_s_sheet_keeps_the_eye(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    world = await hurt.start_table(client, me)

    def body_immune(content: dict) -> None:
        content['npc_sheets'][0]['resistances'] = [{'nature': 'body', 'level': 'immune'}]

    await rewrite_content(session, world['table']['id'], body_immune)
    hurt.load_dice(app, [PASS, 8, 8, hurt.LOST_EYE])

    closing = await hurt.declare(client, me, world['table'], hurt.PUNCH, hurt.punch(world['lady']['id'], 'heavy'))

    roll = hurt.npc_effect(closing)['injury_roll']
    assert (roll['injury'], roll['immune']) == (None, 'lost_eye')


async def test_a_friend_resists_the_thrown_poison(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    world = await friendly.start(client, me, friend)
    table = world['table']
    await friendly.allow(client, me, friend, table, 'full')
    await session.execute(
        text('UPDATE table_sheets SET resistances = CAST(:lines AS JSONB) WHERE user_id = :user_id'),
        {'lines': json.dumps([IMMUNE_POISON]), 'user_id': FRIEND},
    )
    await session.commit()
    item_world.load_dice(app, [PASS, 3])

    closing = await friendly.strike_friend(client, me, friend, table, friendly.throw(world['dagger'], FRIEND))

    (injured,) = item_world.outcome_of(closing)['item_throw']['injured']
    assert (injured['injury'], injured['immune']) == (None, 'poisoned')
