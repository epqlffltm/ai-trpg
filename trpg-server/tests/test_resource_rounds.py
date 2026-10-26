# trpg-server/tests/test_resource_rounds.py

"""
수치의 라운드마다의 변화와 문턱(#804 ②)을 검증한다. 규칙(each_round, at_min, at_max), 계산(app/engine/resources.py),
라운드가 닫힐 때의 일(app/rounds/resource_rounds.py), 기록, 되돌리는 마이그레이션이다.

판은 d20 판타지(srd5)에 수치 하나를 단 룰북이다. 스태미나(고정값 3, 가득에서 시작)는 라운드마다 1 씩 줄고,
0 에 닿으면 중독(poisoned, 판정에 불리)을 입는다. 스태미나 물약(+2)을 마시면 0 을 벗어나 풀린다.
중독은 원래 3 라운드면 풀리는 부상이지만, 문턱으로 입은 것은 라운드로 풀리지 않는다.
"""

import json
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import resources as engine
from app.engine.ruleset import Resource, Ruleset
from app.engine.templates import from_template
from app.rounds import resource_rounds
from app.tables import injuries
from app.tables import resources as table_resources
from app.tables.models import InjurySource
from tests import test_monster_combat as combat
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
me = combat.me
post = combat.post
table_url = combat.table_url
declare = combat.declare
events_of = combat.events_of

SRD5 = from_template('srd5')
ABILITIES = {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'cha': 10}
STAMINA = {
    'key': 'stamina',
    'name': '스태미나',
    'max': {'base': 3},
    'each_round': {'kind': 'lower', 'amount': 1},
    'at_min': 'poisoned',
}
POTION = [{'kind': 'adjust', 'resource': 'stamina', 'amount': 2}]


def ruleset_with(*resources: dict) -> Ruleset:
    """srd5 에 수치들을 단 규칙."""
    return Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'resources': list(resources)})


def level(resource: dict, value: int) -> engine.Level:
    """수치 하나의 지금. 고정값(능력치를 쓰지 않는다)이라 최대는 base 다."""
    parsed = Resource.model_validate(resource)
    return engine.Level(resource=parsed, value=value, maximum=parsed.max.base)


def sheet_of(values: dict) -> SimpleNamespace:
    """DB 없는 시트. 수치의 값과 부상 목록만 있다."""
    return SimpleNamespace(abilities=ABILITIES, resources=dict(values), injuries=[])


async def start(client: AsyncClient, me: dict) -> dict:
    """스태미나 룰북의 판에서 혼자 시작한다. 스태미나 물약 둘을 가지고 시작한다."""
    lorebook = await post(client, combat.LOREBOOKS_URL, me, title='고개')
    entries = f'{combat.LOREBOOKS_URL}/{lorebook["id"]}/entries'
    potion = await post(client, entries, me, name='스태미나 물약', kind='item', keywords=[], content='쓴 물약')
    rulebook = await post(client, combat.RULEBOOKS_URL, me, title='지친 룰북', template='srd5', resources=[STAMINA])
    scenario = await post(
        client,
        combat.SCENARIOS_URL,
        me,
        title='고개',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        openings=['긴 고갯길이다.'],
        default_sheet={'abilities': ABILITIES, 'max_hp': 10},
        starting_items=[{'entry_id': potion['id'], 'count': 2}],
        items=[{'entry_id': potion['id'], 'kind': 'consumable', 'effects': POTION}],
    )
    await post(client, f'{combat.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    started = await client.post(table_url(table, '/start'), headers=me)
    return {'potion': potion, 'table': started.json()}


async def set_stamina(session: AsyncSession, value: int) -> None:
    await session.execute(
        text('UPDATE table_sheets SET resources = CAST(:values AS JSONB) WHERE user_id = :user_id'),
        {'values': json.dumps({'stamina': value}), 'user_id': ME},
    )
    await session.commit()


def payloads(events: list[dict], *fields: str) -> list[tuple]:
    return [tuple(event['payload'][field] for field in fields) for event in events]


# --- 규칙과 계산 ---


def test_thresholds_are_touched_at_the_floor_and_the_ceiling():
    madness = {'key': 'madness', 'name': '광기', 'max': {'base': 5}, 'at_max': 'stunned', 'at_min': 'deafened'}

    assert engine.thresholds_of(level(madness, 0)) == ['deafened']
    assert engine.thresholds_of(level(madness, 3)) == []
    assert engine.thresholds_of(level(madness, 5)) == ['stunned']
    # 문턱에 부상이 없으면 닿아도 아무것도 없다
    assert engine.thresholds_of(level({**STAMINA, 'at_min': None}, 0)) == []
    # 둘이 같은 부상을 원하면 한 번이다
    assert engine.wanted_injuries([level(STAMINA, 0), level({**STAMINA, 'key': 'focus'}, 0)]) == ['poisoned']


def test_a_ruleset_rejects_a_threshold_injury_it_does_not_have():
    ruleset_with(STAMINA)

    with pytest.raises(ValidationError, match='문턱'):
        ruleset_with({**STAMINA, 'at_max': 'cursed'})
    with pytest.raises(ValidationError):
        Resource.model_validate({**STAMINA, 'each_round': {'kind': 'raise'}})


def test_each_round_shifts_only_the_resources_that_have_it():
    ruleset = ruleset_with(STAMINA, {'key': 'mana', 'name': '마나', 'max': {'base': 4}})
    sheet = sheet_of({'stamina': 2})

    shifts = table_resources.each_round(ruleset, sheet)

    assert [(shift.resource.key, shift.before, shift.after) for shift in shifts] == [('stamina', 2, 1)]
    assert sheet.resources == {'stamina': 1}


def test_the_injury_follows_the_threshold_and_comes_back_after_a_cure():
    ruleset = ruleset_with(STAMINA)
    sheet = sheet_of({'stamina': 0})
    table_id = uuid.uuid4()

    gained, ended = resource_rounds.follow_thresholds(ruleset, sheet, table_id, 3)
    again, _ = resource_rounds.follow_thresholds(ruleset, sheet, table_id, 4)

    assert (gained[0]['injury'], gained[0]['source'], ended, again) == ('poisoned', 'resource', [], [])
    (row,) = sheet.injuries
    assert (row.source, row.ends_after_round, row.heals_at) == (InjurySource.RESOURCE, None, None)
    # 다른 길로 풀렸어도 아직 문턱이면 다시 입는다
    injuries.end(row)
    back, _ = resource_rounds.follow_thresholds(ruleset, sheet, table_id, 5)
    assert [one['injury'] for one in back] == ['poisoned']
    # 문턱을 벗어나면 풀린다
    sheet.resources = {'stamina': 2}
    _, released = resource_rounds.follow_thresholds(ruleset, sheet, table_id, 6)
    assert [one.injury for one in released] == ['poisoned']
    assert injuries.active(sheet.injuries) == []


def test_an_injury_from_elsewhere_is_neither_doubled_nor_released():
    ruleset = ruleset_with(STAMINA)
    sheet = sheet_of({'stamina': 0})
    injuries.inflict(sheet.injuries, uuid.uuid4(), 'poisoned', InjurySource.ITEM, 1, 4, None)

    gained, _ = resource_rounds.follow_thresholds(ruleset, sheet, uuid.uuid4(), 2)
    sheet.resources = {'stamina': 3}
    _, released = resource_rounds.follow_thresholds(ruleset, sheet, uuid.uuid4(), 3)

    assert (gained, released) == ([], [])
    assert [row.source for row in injuries.active(sheet.injuries)] == [InjurySource.ITEM]


# --- 라운드가 닫힐 때 ---


async def test_stamina_runs_out_round_by_round_and_the_potion_lifts_the_poison(
    client: AsyncClient, me: dict, session: AsyncSession, narrated
):
    world = await start(client, me)
    table = world['table']
    await set_stamina(session, 1)

    await declare(client, me, table, '걷는다.')
    await narrated()
    # 0 에 머문다. 이미 입고 있어 또 입지 않는다. 원래 3 라운드면 풀리지만 문턱의 부상은 풀리지 않는다
    for _ in range(3):
        await declare(client, me, table, '계속 걷는다.')
        await narrated()
    await declare(client, me, table, '물약을 마신다.', {'kind': 'use', 'item': world['potion']['id']})

    changed = await events_of(client, me, table, 'resource_changed')
    assert payloads(changed, 'source', 'before', 'after') == [('round', 1, 0), ('item', 0, 2), ('round', 2, 1)]
    gained = await events_of(client, me, table, 'injury_gained')
    assert payloads(gained, 'round', 'injury', 'source', 'ends_after_round') == [(1, 'poisoned', 'resource', None)]
    ended = await events_of(client, me, table, 'injury_ended')
    assert payloads(ended, 'round', 'injury', 'reason') == [(5, 'poisoned', 'resource')]
    read = (await client.get(table_url(table), headers=me)).json()
    assert read['members'][0]['sheet']['resources'][0]['value'] == 1


# --- 마이그레이션 ---


def test_the_migration_drops_the_new_fields_on_the_way_back():
    migration = load_migration('resource_thresholds')
    rules = {'template': 'srd5', 'resources': [{**STAMINA, 'max': {'base': 3, 'ability': None, 'cap': None}}]}

    back = migration.without_thresholds(rules)

    assert set(back['resources'][0]) == {'key', 'name', 'max'}
    assert migration.without_thresholds({'template': 'srd5', 'resources': []}) == {'template': 'srd5', 'resources': []}
    assert 'resource' in migration.SOURCES and 'resource' not in migration.OLD_SOURCES
