# trpg-server/tests/test_resource_holders.py

"""
NPC 와 몬스터의 수치(#804 ③ 의 가진 쪽)를 검증한다. 규칙(holders), 가진 쪽마다의 수치, 라운드가 닫힐 때의 변화와 문턱,
물건의 맞추기, 장면의 응답, 이벤트, 서술의 말, 되돌리는 마이그레이션이다.

판은 수로의 시나리오(tests/test_item_throws.py)다. 수로 입구에 쥐 두 마리가 있고, 악역영애가 장면에 나온다.
판을 시작한 뒤 판의 규칙에 분노(rage)를 단다. 몬스터와 NPC 가 가지고(캐릭터는 없다), 고정값 4, 비운 채 시작하고,
라운드마다 1 씩 오르고, 가득 차면 기절(stunned)을 입는다. 모두가 숫자를 본다.
화염병은 분노를 2 내리는 물건으로 바꾼다.
"""

import json
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import resources as engine
from app.engine.ruleset import InjuryNature, Resource, ResourceHolder, Ruleset
from app.engine.templates import from_template
from app.rounds import resource_rounds
from app.rounds.cast import CastMember
from app.rounds.move_lines import describe_resource
from app.rounds.moves import to_people, word_notes
from app.rounds.narrator import PersonState
from app.rounds.prompt import person_line
from app.rounds.records import resource_holder, resource_payload
from app.tables import resources as table_resources
from app.tables.models import TableNpc
from tests import test_item_throws as throws
from tests import test_monster_combat as combat
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

me = combat.me
declare = combat.declare
events_of = combat.events_of

RAGE = {
    'key': 'rage',
    'name': '분노',
    'max': {'base': 4},
    'start': 'min',
    'each_round': {'kind': 'raise', 'amount': 1},
    'at_max': 'stunned',
    'holders': ['monsters', 'npcs'],
}
# 몬스터만 가지고 가진 쪽만 보는 수치. 몬스터에는 주인이 없어 아무도 숫자를 보지 않는다
SECRET = {'key': 'secret', 'name': '비밀', 'max': {'base': 3}, 'holders': ['monsters'], 'visibility': 'owner'}
CALMING = [{'kind': 'adjust', 'resource': 'rage', 'amount': -2}]
ABILITIES = {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'cha': 10}


def bearer(values: dict):
    """DB 없는 가진 쪽. 능력치와 수치의 값만 있다."""
    return type('Bearer', (), {'abilities': ABILITIES, 'resources': dict(values), 'injuries': []})()


async def give_rage(session: AsyncSession, table: dict, *resources: dict) -> None:
    """시작한 판의 규칙에 수치들(주지 않으면 분노)을 달고, 화염병을 분노를 내리는 물건으로 바꾼다."""
    content = (
        await session.execute(text('SELECT content FROM game_tables WHERE id = :id'), {'id': table['id']})
    ).scalar()
    content['rulebook']['rules']['resources'] = list(resources) or [RAGE]
    for rule in content['items']:
        if rule.get('throw') is not None and rule['effects']:
            rule['effects'] = CALMING
    await session.execute(
        text('UPDATE game_tables SET content = CAST(:content AS JSONB) WHERE id = :id'),
        {'content': json.dumps(content), 'id': table['id']},
    )
    await session.commit()


async def set_rage(session: AsyncSession, monster_id: str, value: int) -> None:
    await session.execute(
        text('UPDATE table_monsters SET resources = CAST(:values AS JSONB) WHERE id = :id'),
        {'values': json.dumps({'rage': value}), 'id': uuid.UUID(monster_id)},
    )
    await session.commit()


def of_monster(events: list[dict], monster_id: str) -> list[dict]:
    return [event['payload'] for event in events if event['payload'].get('monster_id') == monster_id]


# --- 규칙과 계산 ---


def test_a_resource_belongs_to_characters_unless_told():
    assert Resource.model_validate({'key': 'mana', 'name': '마나', 'max': {'base': 3}}).holders == ('characters',)
    with pytest.raises(ValidationError, match='holders'):
        Resource.model_validate({**RAGE, 'holders': ['npcs', 'npcs']})
    with pytest.raises(ValidationError):
        Resource.model_validate({**RAGE, 'holders': []})


def test_each_side_reads_only_the_resources_it_holds():
    mana = {'key': 'mana', 'name': '마나', 'max': {'base': 3}}
    rules = Ruleset.model_validate({**from_template('srd5').model_dump(mode='json'), 'resources': [mana, RAGE]})
    one = bearer({})

    assert [level.resource.key for level in table_resources.levels_of(rules, one)] == ['mana']
    assert [level.resource.key for level in table_resources.levels_of(rules, one, ResourceHolder.MONSTERS)] == ['rage']
    # 가지지 않는 수치는 맞추지 않는다
    assert table_resources.adjust(rules, one, 'rage', 2) is None
    assert table_resources.adjust(rules, one, 'rage', 2, ResourceHolder.NPCS).after == 2


def test_an_event_names_the_npc_or_monster_apart_from_the_resource():
    shift = {'resource': 'rage', 'name': '분노', 'before': 1, 'after': 2, 'max': 4, 'user_id': None}

    assert resource_holder({'entry_id': 'e', 'name': '악역영애'}) == {'entry_id': 'e', 'character_name': '악역영애'}
    assert resource_payload(3, {'monster_id': 'm', 'name': '수로 쥐 1'}, shift, 'round') == {
        'round': 3,
        'monster_id': 'm',
        'character_name': '수로 쥐 1',
        'resource': 'rage',
        'name': '분노',
        'before': 1,
        'after': 2,
        'max': 4,
        'source': 'round',
    }


def test_the_narration_gets_words_for_npcs_and_monsters():
    rules = Ruleset.model_validate({**from_template('srd5').model_dump(mode='json'), 'resources': [RAGE]})
    notes = word_notes(rules, bearer({'rage': 4}), ResourceHolder.NPCS)

    line = person_line(PersonState(name='악역영애', condition='멀쩡함', resources=notes))

    assert line == '- 악역영애: 멀쩡함. 수치: 분노 가득'
    assert engine.band_of(1, 0, 4) == '모자람'


def test_a_monster_immune_to_the_threshold_injury_does_not_take_it():
    rules = Ruleset.model_validate({**from_template('srd5').model_dump(mode='json'), 'resources': [RAGE]})
    rat = bearer({'rage': 4})

    gained, _ = resource_rounds.follow_thresholds(
        rules, rat, uuid.uuid4(), 2, ResourceHolder.MONSTERS, frozenset({InjuryNature.STUN})
    )

    assert (gained, rat.injuries) == ([], [])


def test_people_carry_their_resources_as_words_to_the_narrator():
    rules = Ruleset.model_validate({**from_template('srd5').model_dump(mode='json'), 'resources': [RAGE]})
    npc = TableNpc(entry_id=uuid.uuid4(), abilities=ABILITIES, max_hp=10, hp=10, status='alive', resources={'rage': 1})
    npc.attitude = 'neutral'

    (person,) = to_people([CastMember(entry_id=npc.entry_id, name='악역영애', npc=npc)], rules)

    assert [describe_resource(note) for note in person.resources] == ['분노 모자람']


# --- 라운드가 닫힐 때 ---


async def test_monsters_and_npcs_grow_their_rage_and_break_at_the_top(
    client: AsyncClient, me: dict, session: AsyncSession
):
    world = await throws.start_table(client, me)
    table = world['table']
    await give_rage(session, table, RAGE, SECRET)
    rat = await combat.monster_named(client, me, table, '수로 쥐 1')
    await set_rage(session, rat['id'], 3)

    await declare(client, me, table, throws.LOOK)

    changed = await events_of(client, me, table, 'resource_changed')
    assert [(one['character_name'], one['before'], one['after']) for one in of_monster(changed, rat['id'])] == [
        ('수로 쥐 1', 3, 4)
    ]
    assert [one['payload']['character_name'] for one in changed if 'entry_id' in one['payload']] == ['악역영애']
    gained = await events_of(client, me, table, 'injury_gained')
    assert [(one['injury'], one['source']) for one in of_monster(gained, rat['id'])] == [('stunned', 'resource')]
    cast = await combat.scene(client, me, table)
    seen = next(monster for monster in cast['monsters'] if monster['id'] == rat['id'])
    # 가진 쪽만 보는 비밀은 장면에 싣지 않는다
    assert seen['resources'] == [{'key': 'rage', 'name': '분노', 'value': 4, 'min': 0, 'max': 4}]
    assert seen['injuries'] == ['stunned']
    assert cast['people'][0]['resources'][0]['value'] == 1
    # 캐릭터는 분노를 가지지 않는다
    read = (await client.get(combat.table_url(table), headers=me)).json()
    assert read['members'][0]['sheet']['resources'] == []


async def test_a_calming_throw_lowers_the_rage_of_a_monster(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await throws.start_table(client, me)
    table = world['table']
    # 몬스터만 가진다. 인물의 것으로 맞추면 아무 일도 없다
    await give_rage(session, table, {**RAGE, 'holders': ['monsters']})
    rat = await combat.monster_named(client, me, table, '수로 쥐 1')
    await set_rage(session, rat['id'], 3)
    combat.load_dice(app, [combat.PASS])

    closing = await declare(client, me, table, throws.THROW, throws.throw(world['firebomb'], monster=rat['id']))

    thrown = throws.outcome_of(closing, combat.ME)['item_throw']
    assert [(one['resource'], one['before'], one['after']) for one in thrown['resources']] == [('rage', 3, 1)]
    changed = of_monster(await events_of(client, me, table, 'resource_changed'), rat['id'])
    assert [(one['source'], one['before'], one['after']) for one in changed] == [('item', 3, 1), ('round', 1, 2)]


# --- 마이그레이션 ---


def test_the_migration_drops_the_holders_on_the_way_back():
    migration = load_migration('resource_holders')

    back = migration.without_holders({'template': 'srd5', 'resources': [RAGE]})

    assert 'holders' not in back['resources'][0]
    assert migration.without_holders({'template': 'srd5', 'resources': []}) == {'template': 'srd5', 'resources': []}
    assert migration.TABLES == ('table_npcs', 'table_monsters')
