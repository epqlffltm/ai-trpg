# trpg-server/tests/test_resources.py

"""
HP 말고 다른 수치(#804, 판 형식 65)를 검증한다. 규칙(app/engine/ruleset.py 의 Resource), 계산(app/engine/resources.py),
룰북의 고치기, 시트, 쉬기, 물건의 맞추기(adjust), 기록과 서술이다.

판은 가벼운 규칙(light)이다. 능력치는 몸·재치·마음(1~5, 점수가 곧 보정). 짧은 휴식 30분(보통 1d8), 긴 휴식 6시간.
템플릿의 예시는 마나(3 + 마음, 10 까지, 짧은 휴식에 2, 긴 휴식에 가득)와 스태미나(4 + 몸, 10 까지, 쉬면 가득)다.
캐릭터는 몸 3, 재치 2, 마음 4 다. 마나의 최대는 7, 스태미나의 최대는 7 이다.
물건은 마나 물약(마나 +3), 저주받은 책(마나 -2), 모르는 수치를 맞추는 것(게시할 때 막는다)이다.
"""

import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_64
from app.engine import resources as engine
from app.engine.dice import ScriptedDice
from app.engine.item_effects import AdjustEffect, is_harmful
from app.engine.ruleset import Resource, ResourceShift, Ruleset
from app.engine.templates import from_template
from app.rounds.move_lines import describe_item_action, describe_move, describe_rest
from app.rounds.narrator import ItemActionNote, Move, ResourceNote, RestNote
from app.rounds.rests import Broken, finish_rest
from tests import test_monster_combat as combat
from tests.test_npc_sheets import refused
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
FRIEND = combat.FRIEND
me = combat.me
friend = combat.friend
post = combat.post
table_url = combat.table_url
load_dice = combat.load_dice
declare = combat.declare
send = combat.send
events_of = combat.events_of

LIGHT = from_template('light')
SHEET = {'abilities': {'body': 3, 'wits': 2, 'heart': 4}, 'max_hp': 10}
SHORT = {'kind': 'rest', 'length': 'short'}
LONG = {'kind': 'rest', 'length': 'long'}
MANA_POTION = [{'kind': 'adjust', 'resource': 'mana', 'amount': 3}]
CURSED_BOOK = [{'kind': 'adjust', 'resource': 'mana', 'amount': -2}]


def resource(**fields) -> dict:
    """마나 하나. 고정값 6, 가득에서 시작한다. fields 로 칸을 바꾼다."""
    return {'key': 'mana', 'name': '마나', 'max': {'base': 6}, **fields}


def use(item: dict, **target) -> dict:
    return {'kind': 'use', 'item': item['id'], **target}


async def make_world(client: AsyncClient, me: dict, effects: list | None = None) -> dict:
    """가벼운 규칙의 룰북과 로어북(장소 하나, 물건 셋)을 만든다."""
    lorebook = await post(client, combat.LOREBOOKS_URL, me, title='탑')
    entries = f'{combat.LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str, kind: str) -> dict:
        return await post(client, entries, me, name=name, kind=kind, keywords=[], content=f'{name}의 글')

    return {
        'lorebook': lorebook,
        'rulebook': await post(client, combat.RULEBOOKS_URL, me, title='가벼운 룰북', template='light'),
        'potion': await entry('마나 물약', 'item'),
        'book': await entry('저주받은 책', 'item'),
        'odd': await entry('이상한 돌', 'item'),
    }


async def make_scenario(client: AsyncClient, me: dict, world: dict, odd: list | None = None) -> dict:
    """그 물건들로 시나리오를 만든다. 모두 물약과 책을 둘씩 가지고 시작한다. 물약은 던질 수도 있다."""
    items = [
        {'entry_id': world['potion']['id'], 'kind': 'consumable', 'effects': MANA_POTION, 'throw': {'ability': 'body'}},
        {'entry_id': world['book']['id'], 'kind': 'consumable', 'effects': CURSED_BOOK},
    ]
    if odd is not None:
        items.append({'entry_id': world['odd']['id'], 'kind': 'consumable', 'effects': odd})
    starting = [{'entry_id': world[name]['id'], 'count': 2} for name in ('potion', 'book')]
    return await post(
        client,
        combat.SCENARIOS_URL,
        me,
        title='탑',
        rulebook_id=world['rulebook']['id'],
        lorebook_ids=[world['lorebook']['id']],
        openings=['탑 꼭대기다.'],
        default_sheet=SHEET,
        starting_items=starting,
        items=items,
    )


async def start(client: AsyncClient, me: dict, *others: dict) -> dict:
    """가벼운 규칙의 탑에서 시작한다. 나(엘프)와 others(영애)가 앉는다."""
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world)
    await post(client, f'{combat.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '영애'], strict=False):
        if headers is not me:
            await client.post(f'{combat.TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': started.json()}


async def read_table(client: AsyncClient, headers: dict, table: dict) -> dict:
    return (await client.get(table_url(table), headers=headers)).json()


def resources_of(table: dict, user_id: uuid.UUID = ME) -> dict[str, tuple[int, int]]:
    """앉은 사람 하나의 수치들. 이름표에서 (값, 최대) 로."""
    sheet = next(member for member in table['members'] if member['user_id'] == str(user_id))['sheet']
    return {one['key']: (one['value'], one['max']) for one in sheet['resources']}


async def set_resources(session: AsyncSession, values: dict, user_id: uuid.UUID = ME) -> None:
    await session.execute(
        text('UPDATE table_sheets SET resources = CAST(:values AS JSONB) WHERE user_id = :user_id'),
        {'values': json.dumps(values), 'user_id': user_id},
    )
    await session.commit()


def outcome_of(round_: dict, user_id: uuid.UUID = ME) -> dict:
    return next(d for d in round_['declarations'] if d['user_id'] == str(user_id))['outcome']


# --- 규칙과 계산 ---


def test_the_maximum_adds_the_ability_modifier_and_stops_at_the_cap():
    mana = Resource.model_validate(resource(max={'base': 3, 'ability': 'heart', 'cap': 6}))

    assert engine.maximum_of(LIGHT, mana, {'heart': 2}) == 5
    assert engine.maximum_of(LIGHT, mana, {'heart': 5}) == 6
    # 능력치가 시트에 없으면 기준값이다
    assert engine.maximum_of(LIGHT, mana, {}) == 3


def test_a_low_modifier_never_puts_the_maximum_under_the_minimum():
    srd = from_template('srd5')
    focus = Resource.model_validate(resource(min=2, max={'base': 2, 'ability': 'int'}))

    # 점수 6 의 보정은 -2 다. 0 이 되지만 최소(2)다
    assert engine.maximum_of(srd, focus, {'int': 6}) == 2


def test_values_start_full_or_empty_and_missing_ones_read_as_the_start():
    madness = Resource.model_validate(resource(key='madness', name='광기', max={'base': 10}, start='min'))
    rules = LIGHT.model_copy(update={'resources': (*LIGHT.resources, madness)})

    assert engine.starting_values(rules, SHEET['abilities']) == {'mana': 7, 'stamina': 7, 'madness': 0}
    levels = engine.levels(rules, SHEET['abilities'], {'mana': 2, 'stamina': 99})
    # 적힌 값은 범위 안으로 읽는다. 적히지 않은 것은 시작 값이다
    assert [(level.value, level.maximum) for level in levels] == [(2, 7), (7, 7), (0, 10)]


@pytest.mark.parametrize(
    ('shift', 'after'),
    [
        ({'kind': 'raise', 'amount': 2}, 5),
        ({'kind': 'raise', 'amount': 9}, 7),
        ({'kind': 'lower', 'amount': 9}, 0),
        ({'kind': 'fill'}, 7),
        ({'kind': 'empty'}, 0),
    ],
    ids=['raise', 'raise-to-max', 'lower-to-min', 'fill', 'empty'],
)
def test_rest_shifts_stay_in_range(shift: dict, after: int):
    level = engine.Level(resource=LIGHT.resources[0], value=3, maximum=7)

    assert engine.shifted(level, ResourceShift.model_validate(shift)) == after


def test_adjusting_stays_in_range():
    level = engine.Level(resource=LIGHT.resources[0], value=3, maximum=7)

    assert (engine.adjusted(level, 3), engine.adjusted(level, 9), engine.adjusted(level, -9)) == (6, 7, 0)


@pytest.mark.parametrize(
    'fields',
    [
        {'max': {'base': 0}},
        {'min': 5, 'max': {'base': 5}},
        {'max': {'base': 1, 'ability': 'heart', 'cap': 0}},
        {'rest': {'short': {'kind': 'raise'}}},
        {'rest': {'long': {'kind': 'fill', 'amount': 2}}},
        {'start': 'half'},
        {'key': 'Mana'},
    ],
    ids=[
        'no-room',
        'min-equals-max',
        'cap-zero',
        'raise-without-amount',
        'fill-with-amount',
        'unknown-start',
        'bad-key',
    ],
)
def test_rejects_misshaped_resources(fields: dict):
    with pytest.raises(ValidationError):
        Resource.model_validate(resource(**fields))


def test_a_ruleset_rejects_unknown_abilities_and_repeated_resources():
    base = LIGHT.model_dump(mode='json')

    with pytest.raises(ValidationError, match='능력치'):
        Ruleset.model_validate({**base, 'resources': [resource(max={'base': 1, 'ability': 'str'})]})
    with pytest.raises(ValidationError, match='두 번'):
        Ruleset.model_validate({**base, 'resources': [resource(), resource()]})


def test_only_the_light_template_has_examples():
    assert [one.key for one in LIGHT.resources] == ['mana', 'stamina']
    assert from_template('srd5').resources == ()
    assert from_template('horror').resources == ()


def test_adjusting_down_is_harmful_and_zero_is_refused():
    assert is_harmful([AdjustEffect.model_validate(CURSED_BOOK[0])])
    assert not is_harmful([AdjustEffect.model_validate(MANA_POTION[0])])
    with pytest.raises(ValidationError):
        AdjustEffect.model_validate({'kind': 'adjust', 'resource': 'mana', 'amount': 0})


# --- 룰북 ---


async def test_a_rulebook_takes_its_resources_from_the_template_or_the_request(client: AsyncClient, me: dict):
    light = await post(client, combat.RULEBOOKS_URL, me, title='가벼운', template='light')
    own = await post(client, combat.RULEBOOKS_URL, me, title='내 것', template='srd5', resources=[resource()])

    assert [one['key'] for one in light['rules']['resources']] == ['mana', 'stamina']
    assert own['rules']['resources'] == [
        {
            'key': 'mana',
            'name': '마나',
            'min': 0,
            'max': {'base': 6, 'ability': None, 'cap': None},
            'start': 'max',
            'rest': {'short': None, 'long': None},
        }
    ]


async def test_the_resources_of_a_rulebook_can_be_changed(client: AsyncClient, me: dict):
    rulebook = await post(client, combat.RULEBOOKS_URL, me, title='가벼운', template='light')
    url = f'{combat.RULEBOOKS_URL}/{rulebook["id"]}'

    emptied = await client.patch(url, json={'resources': []}, headers=me)
    wrong = await client.patch(url, json={'resources': [resource(max={'base': 1, 'ability': 'str'})]}, headers=me)
    kept = await client.patch(url, json={'title': '새 이름'}, headers=me)

    assert emptied.status_code == status.HTTP_200_OK
    assert emptied.json()['rules']['resources'] == []
    assert wrong.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert wrong.json()['field'] == 'resources'
    # 다른 칸을 고쳐도 수치는 그대로다
    assert kept.json()['rules']['resources'] == []


# --- 시트 ---


async def test_a_sheet_starts_with_the_resources_of_the_rules(client: AsyncClient, me: dict):
    world = await start(client, me)

    read = await read_table(client, me, world['table'])

    assert resources_of(read) == {'mana': (7, 7), 'stamina': (7, 7)}
    sheet = read['members'][0]['sheet']
    assert sheet['resources'][0] == {'key': 'mana', 'name': '마나', 'value': 7, 'min': 0, 'max': 7}


# --- 쉬기 ---


async def test_a_short_rest_gives_back_some_mana_and_fills_stamina(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await start(client, me)
    await set_resources(session, {'mana': 1, 'stamina': 2})
    # 짧은 휴식의 회복(보통 1d8). HP 는 가득이라 그대로다
    load_dice(app, [4])

    closing = await declare(client, me, world['table'], '숨을 돌린다.', SHORT)

    rest = outcome_of(closing)['rest']
    assert rest['resources'] == [
        {'resource': 'mana', 'name': '마나', 'before': 1, 'after': 3, 'max': 7},
        {'resource': 'stamina', 'name': '스태미나', 'before': 2, 'after': 7, 'max': 7},
    ]
    assert resources_of(await read_table(client, me, world['table'])) == {'mana': (3, 7), 'stamina': (7, 7)}
    changed = await events_of(client, me, world['table'], 'resource_changed')
    assert [(one['payload']['resource'], one['payload']['after'], one['payload']['source']) for one in changed] == [
        ('mana', 3, 'rest'),
        ('stamina', 7, 'rest'),
    ]
    (rested,) = await events_of(client, me, world['table'], 'character_rested')
    assert changed[0]['caused_by_sequence'] == rested['sequence']


async def test_a_long_rest_fills_and_a_full_resource_is_not_written(
    client: AsyncClient, me: dict, session: AsyncSession
):
    world = await start(client, me)
    await set_resources(session, {'mana': 0})

    closing = await declare(client, me, world['table'], '잔다.', LONG)

    # 스태미나는 이미 가득이었다. 바뀐 것만 적는다
    assert outcome_of(closing)['rest']['resources'] == [
        {'resource': 'mana', 'name': '마나', 'before': 0, 'after': 7, 'max': 7}
    ]


# --- 물건의 맞추기 ---


async def test_a_mana_potion_raises_mana_up_to_the_maximum(client: AsyncClient, me: dict, session: AsyncSession):
    world = await start(client, me)
    await set_resources(session, {'mana': 5})

    closing = await declare(client, me, world['table'], '물약을 마신다.', use(world['potion']))

    used = outcome_of(closing)['item_use']
    assert used['resources'] == [{'resource': 'mana', 'name': '마나', 'before': 5, 'after': 7, 'max': 7}]
    assert resources_of(await read_table(client, me, world['table']))['mana'] == (7, 7)
    (changed,) = await events_of(client, me, world['table'], 'resource_changed')
    assert (changed['payload']['source'], changed['payload']['user_id']) == ('item', str(ME))
    (item_used,) = await events_of(client, me, world['table'], 'item_used')
    assert changed['caused_by_sequence'] == item_used['sequence']


async def test_a_full_resource_is_not_changed_by_a_potion(client: AsyncClient, me: dict):
    world = await start(client, me)

    closing = await declare(client, me, world['table'], '물약을 마신다.', use(world['potion']))

    assert outcome_of(closing)['item_use']['resources'] == []
    assert await events_of(client, me, world['table'], 'resource_changed') == []


async def test_draining_a_friend_follows_friendly_fire(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)
    table = world['table']

    refused_now = await send(client, me, table, '책을 읽힌다.', use(world['book'], target=str(FRIEND)))
    await client.put(table_url(table, '/friendly-fire'), json={'friendly_fire': 'full'}, headers=me)
    await client.put(table_url(table, '/members/me/friendly-fire'), json={'friendly_fire': 'full'}, headers=friend)
    await declare(client, me, table, '책을 읽힌다.', use(world['book'], target=str(FRIEND)))
    closing = await declare(client, friend, table, '읽는다.')

    assert refused_now.json()['reason'] == 'friendly_fire_off'
    assert outcome_of(closing)['item_use']['resources'][0]['after'] == 5
    assert resources_of(await read_table(client, me, table), FRIEND)['mana'] == (5, 7)


async def test_a_potion_thrown_to_a_friend_raises_their_mana(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    world = await start(client, me, friend)
    table = world['table']
    await set_resources(session, {'mana': 1}, FRIEND)
    load_dice(app, [10])

    await declare(
        client, me, table, '물약을 던진다.', {'kind': 'throw', 'item': world['potion']['id'], 'target': str(FRIEND)}
    )
    closing = await declare(client, friend, table, '받는다.')

    thrown = outcome_of(closing)['item_throw']
    assert thrown['resources'] == [{'resource': 'mana', 'name': '마나', 'before': 1, 'after': 4, 'max': 7}]
    assert resources_of(await read_table(client, me, table), FRIEND)['mana'] == (4, 7)
    (changed,) = await events_of(client, me, table, 'resource_changed')
    assert (changed['payload']['user_id'], changed['payload']['source']) == (str(FRIEND), 'item')


async def test_an_unknown_resource_is_refused_at_publishing(client: AsyncClient, me: dict):
    world = await make_world(client, me)
    scenario = await make_scenario(client, me, world, odd=[{'kind': 'adjust', 'resource': 'gold', 'amount': 1}])

    assert 'item_resource_invalid' in await refused(client, me, scenario)


# --- 판의 형식과 마이그레이션 ---


def test_an_old_document_reads_with_no_resources():
    old = {'format': 64, 'rulebook': {'title': '룰북', 'rules': {'template': 'srd5'}}, 'items': []}

    upgraded = upgrade_from_64(old)

    assert SNAPSHOT_FORMAT >= 65
    assert UPGRADES[64] is upgrade_from_64
    assert upgraded['format'] == 65
    assert upgraded['rulebook']['rules']['resources'] == []
    assert 'resources' not in old['rulebook']['rules']


def test_the_migration_fills_rulebooks_and_drops_adjust_on_the_way_back():
    migration = load_migration('resources')
    rules = {'template': 'light'}
    rule = {'entry_id': 'x', 'kind': 'consumable', 'effects': [{'kind': 'heal', 'magnitude': 'light'}, *MANA_POTION]}

    assert migration.with_resources(rules) == {'template': 'light', 'resources': []}
    assert migration.with_resources({**rules, 'resources': [resource()]})['resources'] == [resource()]
    assert migration.without_resources({**rules, 'resources': []}) == rules
    assert migration.without_adjust(rule)['effects'] == [{'kind': 'heal', 'magnitude': 'light'}]


# --- 서술 ---


def test_a_broken_rest_changes_no_resource():
    """다쳐 깨진 휴식은 회복하지 않고 수치도 바꾸지 않는다."""
    sheet = SimpleNamespace(hp=5, max_hp=10, died_at=None, abilities=SHEET['abilities'], resources={'mana': 1})
    member = SimpleNamespace(user_id=ME, sheet=sheet)
    declaration = SimpleNamespace(outcome={'rest': {'length': 'long', 'minutes': 480}})

    finish_rest(LIGHT, member, declaration, {ME}, set(), ScriptedDice([]))

    rest = declaration.outcome['rest']
    assert (rest['rested'], rest['reason'], rest['resources']) == (False, Broken.HURT, [])
    assert sheet.resources == {'mana': 1}


def test_the_narration_lines_carry_the_resources():
    mana = ResourceNote(name='마나', value=6, max=6, before=1)
    rest = RestNote(length='long', rested=True, before=2, after=10, max_hp=10, resources=[mana])
    used = ItemActionNote(kind='use', name='마나 물약', count=1, done=True, resources=[ResourceNote('마나', 5, 6, 2)])
    move = Move(
        character_name='엘프', content='잔다.', resources=[ResourceNote('마나', 3, 6), ResourceNote('스태미나', 4, 4)]
    )

    assert describe_rest(rest) == '(쉬기: 긴 휴식, HP 2 → 10/10, 마나 1 → 6/6)'
    assert describe_item_action(used) == '(쓴 물건: 마나 물약) [수치: 마나 2 → 5/6]'
    assert '[수치: 마나 3/6, 스태미나 4/4]' in describe_move(move)
