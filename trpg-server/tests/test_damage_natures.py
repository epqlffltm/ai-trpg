# trpg-server/tests/test_damage_natures.py

"""
피해의 성질과 피해의 저항(#886 ③)을 검증한다.

피해 하나에 성질은 하나다. 성질이 붙는 곳은 몬스터와 인물의 공격(attacks[].nature), 효과의 피해(effects[].nature),
무기(아이템 규칙의 nature)다. 공격은 공격의 성질이 먼저이고 없으면 무기의 것이다.
맞은 쪽은 그 성질을 단계 하나로 받는다. 면역이 하나라도 있으면 0, 저항과 약점이 함께면 그대로, 저항만이면 반(내림),
약점만이면 두 배다. 방어구가 깎은 뒤의 양에 건다.
몬스터는 타입과 시트의 면역도 면역이고, 시트에 저항(resistances)을 단다.

판은 다른 시험의 것을 빌린다.
  - test_monster_turns.py: 수로 입구에 쥐 한 마리. 엘프(시트를 바꿔 단다)를 친다.
    주사위는 맞히기, 피해, 엘프의 판정이다.
  - test_item_effects.py: 독 단검(효과를 바꿔 단다)을 인물(비올레타), 쥐(야수), 해골 병사(언데드, 독에 면역)에게 쓴다.
    주사위는 맞히기, 피해의 눈이다.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.publishing import attack_fault
from app.assets.scenarios.schemas import ItemRule, MonsterAttack, MonsterSheet
from app.engine.dice import ScriptedDice
from app.engine.health import ChangeKind, Nature, change_hp, find_magnitude, resist
from app.engine.ruleset import Resistance, ResistLevel, ResourceHolder, Ruleset, damage_level
from app.engine.templates import SRD5
from app.rounds.move_lines import describe_impact, describe_npc_impact
from app.rounds.narration_request import to_impact, to_npc_impact
from tests import test_item_effects as item_world
from tests import test_monster_turns as turns
from tests import test_npc_turns as npc_turns
from tests.sheets import make_sheet
from tests.test_attack_costs import rewrite_content
from tests.test_attack_effects import turn_outcome
from tests.test_npc_sheets import refused
from tests.test_resistances import item_table, scenario_with

pytestmark = pytest.mark.usefixtures('clean_tables')

me = turns.me
ME = turns.ME
PASS = turns.PASS
FAIL = turns.FAIL
RESIST, IMMUNE, WEAK = ResistLevel.RESIST, ResistLevel.IMMUNE, ResistLevel.VULNERABLE
VENOM = {'name': '독니', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light', 'nature': 'poison'}
FAST_RAT = make_sheet(max_hp=4, dex=14)
POISON_DAMAGE = {'kind': 'damage', 'magnitude': 'light', 'nature': 'poison'}


def lines(*pairs: tuple[str, ResistLevel]) -> list[Resistance]:
    return [Resistance(nature=nature, level=level) for nature, level in pairs]


# --- 계산 ---


@pytest.mark.parametrize(
    ('resistances', 'immune', 'expected'),
    [
        ([], frozenset(), None),
        ([('poison', RESIST)], frozenset(), RESIST),
        ([('poison', WEAK)], frozenset(), WEAK),
        ([('poison', RESIST), ('poison', WEAK)], frozenset(), None),
        ([('poison', WEAK), ('poison', IMMUNE)], frozenset(), IMMUNE),
        ([('poison', WEAK)], frozenset({'poison'}), IMMUNE),
        ([('stun', IMMUNE)], frozenset({'stun'}), None),
    ],
    ids=['plain', 'resist', 'vulnerable', 'cancel', 'immune-wins', 'kind-immune', 'other-nature'],
)
def test_the_sources_fold_into_one_level(resistances: list, immune: frozenset, expected):
    assert damage_level(lines(*resistances), 'poison', immune) == expected


@pytest.mark.parametrize(('level', 'amount'), [(None, 7), (RESIST, 3), (IMMUNE, 0), (WEAK, 14)])
def test_a_level_halves_zeroes_or_doubles(level, amount: int):
    assert resist(7, level) == amount


def test_the_armor_cuts_before_the_resistance():
    moderate = find_magnitude(SRD5, 'moderate')

    change = change_hp(ChangeKind.DAMAGE, moderate, 20, 20, ScriptedDice([8]), cut=3, nature=Nature('poison', RESIST))

    # 8 에서 방어구가 3 을 깎고, 남은 5 의 반(내림)이다
    assert (change.blocked, change.amount, change.after, change.nature, change.level) == (3, 2, 18, 'poison', RESIST)


def test_a_recovery_takes_no_nature():
    light = find_magnitude(SRD5, 'light')

    change = change_hp(ChangeKind.RECOVERY, light, 2, 10, ScriptedDice([3]), nature=Nature('poison', IMMUNE))

    assert (change.amount, change.after, change.nature) == (3, 5, None)


# --- 모양과 게시 ---


def test_a_nature_goes_only_with_harm_and_weapons():
    with pytest.raises(ValidationError, match='피해 등급'):
        MonsterAttack.model_validate({**VENOM, 'harm': None, 'effects': [{'kind': 'injure', 'injury': 'poisoned'}]})
    with pytest.raises(ValidationError, match='무기'):
        ItemRule.model_validate({'entry_id': str(uuid.uuid4()), 'slots': ['main_hand'], 'nature': 'poison'})
    ItemRule.model_validate({'entry_id': str(uuid.uuid4()), 'slots': ['main_hand'], 'attack': 1, 'nature': 'poison'})


@pytest.mark.parametrize(('nature', 'fault'), [('poison', False), ('fire', True)])
def test_an_attack_s_nature_is_one_of_the_rules(nature: str, fault: bool):
    attack = MonsterAttack.model_validate({**VENOM, 'nature': nature})

    assert attack_fault(SRD5, attack, ResourceHolder.MONSTERS) is fault


def test_a_skill_s_damage_names_a_nature_of_the_rules():
    skill = {
        'key': 'firebolt',
        'name': '불화살',
        'target': 'foe',
        'check': {'ability': 'int', 'difficulty': None},
        'effects': [{**POISON_DAMAGE, 'nature': 'fire'}],
    }

    with pytest.raises(ValidationError):
        Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'skills': [skill]})


@pytest.mark.parametrize(
    ('fields', 'problem'),
    [
        (
            {
                'monster_sheets': lambda world: [
                    {
                        'monster_id': world['rat']['id'],
                        'sheet': make_sheet(max_hp=4),
                        'resistances': [{'nature': 'fire', 'level': 'resist'}],
                    }
                ]
            },
            'monster_nature_invalid',
        ),
        (
            {
                'items': lambda world: [
                    {'entry_id': world['dagger']['id'], 'slots': ['main_hand'], 'attack': 1, 'nature': 'fire'}
                ]
            },
            'nature_invalid',
        ),
        (
            {
                'items': lambda world: [
                    {
                        'entry_id': world['dagger']['id'],
                        'kind': 'consumable',
                        'effects': [{**POISON_DAMAGE, 'nature': 'fire'}],
                    }
                ]
            },
            'nature_invalid',
        ),
    ],
    ids=['monster-sheet', 'weapon', 'damage-effect'],
)
async def test_a_nature_the_rules_lack_is_refused(client: AsyncClient, me: dict, fields: dict, problem: str):
    world = await scenario_with(client, me, **fields)

    assert problem in await refused(client, me, world['scenario'])


def test_a_monster_sheet_resists_by_level():
    sheet = MonsterSheet.model_validate(
        {
            'monster_id': str(uuid.uuid4()),
            'sheet': make_sheet(),
            'resistances': [{'nature': 'poison', 'level': 'resist'}],
        }
    )

    assert sheet.resistances == tuple(lines(('poison', RESIST)))


# --- 공격 ---


@pytest.mark.parametrize(
    ('line', 'hp', 'level'),
    [(None, 7, None), ('resist', 9, 'resist'), ('immune', 10, 'immune'), ('vulnerable', 4, 'vulnerable')],
    ids=['plain', 'resist', 'immune', 'vulnerable'],
)
async def test_a_venom_bite_follows_the_elf_s_resistance(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, line: str | None, hp: int, level: str | None
):
    resistances = [] if line is None else [{'nature': 'poison', 'level': line}]
    sheet = {**make_sheet(), 'resistances': resistances}
    table = await turns.start_table(client, me, rat_sheet=FAST_RAT, attacks=[VENOM], sheet=sheet)
    # 쥐의 맞히기, 피해의 눈 3, (두 배면 큰 타격이라 부상 표), 엘프의 판정
    table_roll = [turns.NO_INJURY] if line == 'vulnerable' else []
    dice = turns.load_dice(app, [PASS, 3, *table_roll, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    effect = (await turn_outcome(session, table))['effect']
    assert (effect['amount'], effect['after']) == (3 if line is None else 10 - hp, hp)
    assert effect['nature'] == {'key': 'poison', 'name': '독', 'level': level}
    assert await turns.hp_of(session, table) == hp
    assert dice.remaining == 0
    (changed,) = [event for event in await turns.events_of(client, me, table) if event['type'] == 'hp_changed']
    assert changed['payload']['nature'] == effect['nature']


async def test_an_attack_without_a_nature_leaves_no_trace(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    plain = {k: v for k, v in VENOM.items() if k != 'nature'}
    table = await turns.start_table(client, me, rat_sheet=FAST_RAT, attacks=[plain])
    turns.load_dice(app, [PASS, 3, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    assert 'nature' not in (await turn_outcome(session, table))['effect']


# --- 효과와 무기 ---


def venom_dagger(world: dict) -> list[dict]:
    """독 단검을 독의 피해 하나만 있는 소모품으로 바꾼다. 다른 물건은 그대로다."""
    dagger = {'entry_id': world['dagger']['id'], 'kind': 'consumable', 'effects': [POISON_DAMAGE]}
    return [dagger, *item_world.the_items(world)[1:]]


async def stab(client: AsyncClient, me: dict, world: dict, **target) -> dict:
    closing = await item_world.declare(client, me, world['table'], '찌른다.', item_world.use(world['dagger'], **target))
    return item_world.outcome_of(closing)


async def test_an_undead_takes_nothing_from_poison(client: AsyncClient, app: FastAPI, me: dict):
    world = await item_table(client, me, items=venom_dagger)
    skeleton = await item_world.monster_named(client, me, world['table'], '해골 병사')
    item_world.load_dice(app, [PASS, 3])

    outcome = await stab(client, me, world, monster=skeleton['id'])

    effect = outcome['monster_effect']
    assert (effect['amount'], effect['nature']) == (0, {'key': 'poison', 'name': '독', 'level': 'immune'})
    assert (await item_world.monster_named(client, me, world['table'], '해골 병사'))['condition'] == '멀쩡함'


async def test_a_rat_weak_to_poison_takes_double(client: AsyncClient, app: FastAPI, me: dict):
    world = await item_table(
        client,
        me,
        items=venom_dagger,
        monster_sheets=lambda world: [
            {
                'monster_id': world['rat']['id'],
                'sheet': make_sheet(max_hp=8),
                'resistances': [{'nature': 'poison', 'level': 'vulnerable'}],
            },
            {'monster_id': world['skeleton']['id'], 'sheet': make_sheet(max_hp=6)},
        ],
    )
    rat = await item_world.monster_named(client, me, world['table'], '수로 쥐')
    item_world.load_dice(app, [PASS, 3, 1])

    outcome = await stab(client, me, world, monster=rat['id'], lethal=True)

    assert (outcome['monster_effect']['amount'], outcome['monster_effect']['nature']['level']) == (6, 'vulnerable')


async def test_a_resisting_person_takes_half(client: AsyncClient, app: FastAPI, me: dict):
    world = await item_table(
        client,
        me,
        items=venom_dagger,
        npc_sheets=lambda world: [
            {
                'entry_id': world['lady']['id'],
                'sheet': make_sheet(max_hp=10),
                'resistances': [{'nature': 'poison', 'level': 'resist'}],
            }
        ],
    )
    lady = (await item_world.people(client, me, world['table']))['people'][0]
    item_world.load_dice(app, [PASS, 3])

    outcome = await stab(client, me, world, npc=lady['id'])

    assert (outcome['npc_effect']['amount'], outcome['npc_effect']['nature']['level']) == (1, 'resist')


async def test_a_self_inflicted_poison_follows_one_s_own_resistance(client: AsyncClient, app: FastAPI, me: dict):
    world = await item_table(
        client,
        me,
        items=venom_dagger,
        default_sheet=lambda _: {**make_sheet(), 'resistances': [{'nature': 'poison', 'level': 'immune'}]},
    )
    item_world.load_dice(app, [3])

    outcome = await stab(client, me, world)

    assert (outcome['effect']['amount'], outcome['effect']['after']) == (0, 10)


def poison_blade(world: dict) -> list[dict]:
    """독 단검을 독의 성질을 가진 무기(공격 보정 1, 주손)로 바꾼다."""
    blade = {'entry_id': world['dagger']['id'], 'kind': 'gear', 'slots': ['main_hand'], 'attack': 1, 'nature': 'poison'}
    return [blade, *item_world.the_items(world)[1:]]


def wielded(world: dict) -> list[dict]:
    return [
        {'entry_id': world['dagger']['id'], 'count': 1, 'wear': ['main_hand']},
        *({'entry_id': world[name]['id'], 'count': 1} for name in ('powder', 'potion', 'smoke')),
    ]


async def test_a_poison_blade_does_nothing_to_the_undead(client: AsyncClient, app: FastAPI, me: dict):
    world = await item_table(client, me, items=poison_blade, starting_items=wielded)
    skeleton = await item_world.monster_named(client, me, world['table'], '해골 병사')
    item_world.load_dice(app, [PASS, 5])
    strike = {
        'kind': 'check',
        'ability': 'str',
        'difficulty': 'medium',
        'harm': 'moderate',
        'monster': skeleton['id'],
        'lethal': True,
        'weapon': world['dagger']['id'],
    }

    closing = await item_world.declare(client, me, world['table'], '해골을 벤다.', strike)

    effect = item_world.outcome_of(closing)['monster_effect']
    assert (effect['amount'], effect['nature']['level']) == (0, 'immune')
    assert item_world.outcome_of(closing)['blow']['weapon']['name'] == '독 단검'


# --- 서술 ---


def test_the_narrator_hears_the_nature_and_the_level():
    member = {
        'kind': 'damage',
        'character_name': '엘프',
        'amount': 1,
        'after': 9,
        'max_hp': 10,
        'downed': False,
        'nature': {'key': 'poison', 'name': '독', 'level': 'resist'},
    }
    rat = {
        'kind': 'damage',
        'name': '수로 쥐',
        'amount': 6,
        'condition': '쓰러짐(의식 없음)',
        'nature': {'key': 'poison', 'name': '독', 'level': 'vulnerable'},
    }
    plain = {**member, 'nature': {'key': 'poison', 'name': '독', 'level': None}}

    assert describe_impact(to_impact(member)) == '→ 엘프 독 피해 1 (HP 9/10, 저항)'
    assert describe_npc_impact(to_npc_impact(rat)) == '→ 수로 쥐 독 피해 6 (쓰러짐(의식 없음), 약점)'
    assert describe_impact(to_impact(plain)) == '→ 엘프 독 피해 1 (HP 9/10)'


# --- 타고난 성질 ---


async def innate_rat(client: AsyncClient, me: dict, attack: dict) -> tuple[dict, Callable[[dict], None]]:
    """타고난 성질이 독인 쥐. 엘프는 독에 저항한다."""
    sheet = {**make_sheet(), 'resistances': [{'nature': 'poison', 'level': 'resist'}]}
    table = await turns.start_table(client, me, rat_sheet=FAST_RAT, attacks=[attack], sheet=sheet)

    def poisonous(content: dict) -> None:
        content['monsters'][0]['nature'] = 'poison'

    return table, poisonous


@pytest.mark.parametrize(
    ('attack', 'expected', 'hp'),
    [
        ({k: v for k, v in VENOM.items() if k != 'nature'}, {'key': 'poison', 'name': '독', 'level': 'resist'}, 9),
        ({**VENOM, 'nature': 'stun'}, {'key': 'stun', 'name': '기절', 'level': None}, 7),
    ],
    ids=['innate', 'attack-first'],
)
async def test_a_monster_s_innate_nature_comes_after_the_attack_s(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, attack: dict, expected: dict, hp: int
):
    table, poisonous = await innate_rat(client, me, attack)
    await rewrite_content(session, table['id'], poisonous)
    turns.load_dice(app, [PASS, 3, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    effect = (await turn_outcome(session, table))['effect']
    assert (effect['nature'], effect['after']) == (expected, hp)


async def test_a_person_s_innate_nature_marks_the_strike(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await npc_turns.armed_and_fighting(client, app, me, narrated, nature='poison')
    npc_turns.load_dice(app, [npc_turns.HIT, npc_turns.SCRATCH])

    await npc_turns.laugh(client, me, world)

    (turn,) = npc_turns.npc_turns(await turns.turns_of(session, world['table'], 2))
    assert turn['outcome']['effect']['nature'] == {'key': 'poison', 'name': '독', 'level': None}


@pytest.mark.parametrize(
    ('fields', 'problem'),
    [
        (
            {
                'monster_sheets': lambda world: [
                    {'monster_id': world['rat']['id'], 'sheet': make_sheet(max_hp=4), 'nature': 'fire'}
                ]
            },
            'monster_nature_invalid',
        ),
        (
            {'npc_sheets': lambda world: [{'entry_id': world['lady']['id'], 'sheet': make_sheet(), 'nature': 'fire'}]},
            'nature_invalid',
        ),
    ],
    ids=['monster', 'person'],
)
async def test_an_innate_nature_is_one_of_the_rules(client: AsyncClient, me: dict, fields: dict, problem: str):
    world = await scenario_with(client, me, **fields)

    assert problem in await refused(client, me, world['scenario'])


async def test_an_innate_nature_is_frozen_into_the_version(client: AsyncClient, me: dict):
    world = await scenario_with(
        client,
        me,
        monster_sheets=lambda world: [
            {'monster_id': world['rat']['id'], 'sheet': make_sheet(max_hp=4), 'nature': 'poison'},
            {'monster_id': world['skeleton']['id'], 'sheet': make_sheet(max_hp=6)},
        ],
        npc_sheets=lambda world: [{'entry_id': world['lady']['id'], 'sheet': make_sheet(), 'nature': 'stun'}],
    )

    response = await client.post(f'{turns.SCENARIOS_URL}/{world["scenario"]["id"]}/versions', json={}, headers=me)

    snapshot = response.json()['snapshot']
    assert sorted(monster['nature'] or '' for monster in snapshot['monsters']) == ['', 'poison']
    assert snapshot['npc_sheets'][0]['nature'] == 'stun'
