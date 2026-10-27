# trpg-server/tests/test_attack_costs.py

"""
몬스터와 인물의 공격의 비용(#805 ③-a, app/rounds/monster_attacks.py 의 affordable, pay)을 검증한다.

몬스터의 판은 test_monster_turns.py 의 것이다. 수로 입구에 쥐 한 마리(민첩 14 라 먼저 친다), 공격은 물기 하나다.
인물의 판은 test_npc_turns.py 의 것이다. 적대하는 악역영애가 라운드 1 에 싸움이 붙고 라운드 2 에 부채 후리기로 친다.
판을 시작한 뒤 판의 규칙에 마나(고정값 2, 몬스터와 인물이 가진다)를 달고, 공격에 마나 1 의 비용을 단다.

넷을 본다.
  - 시나리오: 공격의 비용은 그 쪽(몬스터, 인물)이 가진 규칙의 수치여야 한다. 아니면 게시의 문제다.
  - 차례: 고른 공격의 비용을 내고 친다. 빗나가도 낸다. 모자라면 굴리지 않고 아무것도 내지 않는다(cost_short).
  - 기록: 공격의 이벤트 뒤에 친 쪽의 수치가 바뀐 것(resource_changed, source attack)이 잇는다.
  - 서술: 낸 비용을 말로 붙이고, 모자라 못 한 차례도 적는다.
"""

import json
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.publishing import attack_fault
from app.assets.scenarios.schemas import MonsterAttack
from app.engine.ruleset import ResourceHolder, Ruleset
from app.engine.templates import SRD5
from app.rounds.move_lines import describe_monster_turn
from app.rounds.narration_request import to_turn_note
from app.rounds.narrator import MonsterTurnNote, ResourceNote
from tests import test_monster_turns as turns
from tests import test_npc_turns as npc_turns
from tests.sheets import SHEET, make_sheet
from tests.test_npc_sheets import refused

pytestmark = pytest.mark.usefixtures('clean_tables')

me = turns.me
ME = turns.ME
PASS = turns.PASS
FAIL = turns.FAIL
MANA = {'key': 'mana', 'name': '마나', 'max': {'base': 2}, 'holders': ['monsters', 'npcs']}
COST = {'resource': 'mana', 'amount': 1}
BITE = {**turns.BITE, 'cost': COST}
FAST_RAT = make_sheet(max_hp=4, dex=14)


async def rewrite_content(session: AsyncSession, table_id: str, change) -> None:
    """시작한 판의 내용(content)을 change 로 고친다. 판을 다시 게시하지 않고 규칙과 공격을 바꾼다."""
    content = (await session.execute(text('SELECT content FROM game_tables WHERE id = :id'), {'id': table_id})).scalar()
    change(content)
    await session.execute(
        text('UPDATE game_tables SET content = CAST(:content AS JSONB) WHERE id = :id'),
        {'content': json.dumps(content), 'id': table_id},
    )
    await session.commit()


def costly_monsters(content: dict) -> None:
    """마나를 달고 몬스터의 공격마다 비용을 단다."""
    content['rulebook']['rules']['resources'] = [MANA]
    for monster in content['monsters']:
        monster['attacks'] = [{**attack, 'cost': COST} for attack in monster['attacks']]


def costly_people(content: dict) -> None:
    """마나를 달고 인물의 공격마다 비용을 단다."""
    content['rulebook']['rules']['resources'] = [MANA]
    for sheet in content['npc_sheets']:
        sheet['attacks'] = [{**attack, 'cost': COST} for attack in sheet['attacks']]


async def set_mana(session: AsyncSession, table: str, value: int, table_name: str = 'table_monsters') -> None:
    """그 판의 모든 몬스터(또는 인물)의 마나를 정한다."""
    await session.execute(
        text(f'UPDATE {table_name} SET resources = CAST(:values AS JSONB) WHERE table_id = :id'),  # noqa: S608
        {'values': json.dumps({'mana': value}), 'id': uuid.UUID(table)},
    )
    await session.commit()


async def costly_rat(session: AsyncSession, client: AsyncClient, me: dict, mana: int) -> dict:
    table = await turns.start_table(client, me, rat_sheet=FAST_RAT)
    await rewrite_content(session, table['id'], costly_monsters)
    await set_mana(session, table['id'], mana)
    return table


# --- 시나리오 ---


def test_an_attack_may_carry_a_cost():
    attack = MonsterAttack.model_validate(BITE)

    assert (attack.cost.resource, attack.cost.amount) == ('mana', 1)
    with pytest.raises(ValidationError):
        MonsterAttack.model_validate({**BITE, 'cost': {'resource': 'mana', 'amount': 0}})


@pytest.mark.parametrize(
    ('holders', 'holder', 'fault'),
    [
        (['monsters', 'npcs'], ResourceHolder.MONSTERS, False),
        (['monsters', 'npcs'], ResourceHolder.NPCS, False),
        (['characters'], ResourceHolder.MONSTERS, True),
        (['monsters'], ResourceHolder.NPCS, True),
    ],
)
def test_the_cost_is_paid_from_what_that_side_holds(holders: list[str], holder: ResourceHolder, fault: bool):
    rules = Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'resources': [{**MANA, 'holders': holders}]})

    assert attack_fault(rules, MonsterAttack.model_validate(BITE), holder) is fault


def test_a_cost_on_a_resource_the_rules_lack_is_a_fault():
    assert attack_fault(SRD5, MonsterAttack.model_validate(BITE), ResourceHolder.MONSTERS) is True
    assert attack_fault(SRD5, MonsterAttack.model_validate(turns.BITE), ResourceHolder.MONSTERS) is False


async def problems_with(client: AsyncClient, me: dict, holders: list[str]) -> list[str]:
    """쥐의 물기와 악역영애의 부채 후리기에 마나의 비용을 단 시나리오. 마나는 holders 가 가진다. 게시의 문제들이다."""
    lorebook = await turns.post(client, turns.LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{turns.LOREBOOKS_URL}/{lorebook["id"]}/entries'
    gate = await turns.post(client, entries, me, name='수로 입구', kind='place')
    lady = await turns.post(client, entries, me, name='비올레타', kind='person', keywords=['악역영애'])
    bestiary = await turns.post(client, turns.BESTIARIES_URL, me, title='지하 수로의 것들')
    rat = await turns.post(
        client, f'{turns.BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='수로 쥐', kind='beast'
    )
    mana = {**MANA, 'holders': holders}
    rulebook = await turns.post(client, turns.RULEBOOKS_URL, me, title='룰북', template='srd5', resources=[mana])
    swipe = {**npc_turns.SWIPE, 'cost': COST}
    scenario = await turns.post(
        client,
        turns.SCENARIOS_URL,
        me,
        title='지하 수로',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        bestiary_ids=[bestiary['id']],
        openings=['물 떨어지는 소리가 난다. 악역영애가 웃는다.'],
        default_sheet=SHEET,
        npc_sheets=[{'entry_id': lady['id'], 'sheet': SHEET, 'attacks': [swipe]}],
        monster_sheets=[{'monster_id': rat['id'], 'sheet': turns.RAT_SHEET, 'attacks': [BITE]}],
        start_place=gate['id'],
        encounters=[{'place_id': gate['id'], 'monster_id': rat['id'], 'count': 1}],
    )
    return await refused(client, me, scenario)


@pytest.mark.parametrize(
    ('holders', 'expected'),
    [(['npcs'], ['monster_attack_invalid']), (['monsters'], ['npc_attack_invalid'])],
)
async def test_publishing_checks_who_pays(client: AsyncClient, me: dict, holders: list[str], expected: list[str]):
    problems = await problems_with(client, me, holders)

    assert [one for one in problems if one.endswith('attack_invalid')] == expected


# --- 몬스터의 차례 ---


async def test_a_monster_pays_and_strikes(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await costly_rat(session, client, me, mana=2)
    dice = turns.load_dice(app, [PASS, 3, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    outcome = (await turns.turns_of(session, table))[0]['outcome']
    assert [(one['resource'], one['before'], one['after']) for one in outcome['cost']] == [('mana', 2, 1)]
    assert (outcome['success'], outcome['attack']) == (True, turns.BITE)
    assert await turns.hp_of(session, table) == 7
    assert dice.remaining == 0


async def test_a_miss_still_costs(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await costly_rat(session, client, me, mana=1)
    turns.load_dice(app, [FAIL, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    outcome = (await turns.turns_of(session, table))[0]['outcome']
    assert (outcome['success'], [one['after'] for one in outcome['cost']]) == (False, [0])


async def test_a_monster_short_of_the_cost_does_nothing(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    table = await costly_rat(session, client, me, mana=0)
    # 쥐는 굴리지 않는다. 엘프의 판정만 굴린다
    dice = turns.load_dice(app, [FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    outcome = (await turns.turns_of(session, table))[0]['outcome']
    assert outcome == {'skipped': 'cost_short', 'attack': turns.BITE, 'user_id': str(ME), 'character_name': '엘프'}
    assert await turns.hp_of(session, table) == 10
    assert dice.remaining == 0
    kinds = [event['type'] for event in await turns.events_of(client, me, table)]
    assert 'monster_attacked' not in kinds


async def test_a_free_attack_keeps_its_old_shape(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    table = await turns.start_table(client, me, rat_sheet=FAST_RAT)
    turns.load_dice(app, [FAIL, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    assert 'cost' not in (await turns.turns_of(session, table))[0]['outcome']


async def test_the_cost_is_recorded_after_the_attack(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    table = await costly_rat(session, client, me, mana=2)
    turns.load_dice(app, [PASS, 3, FAIL])

    await turns.declare(client, me, table, turns.REST, turns.rest())

    events = await turns.events_of(client, me, table)
    attacked = next(event for event in events if event['type'] == 'monster_attacked')
    paid = next(
        event for event in events if event['type'] == 'resource_changed' and event['payload']['source'] == 'attack'
    )
    assert paid['caused_by_sequence'] == attacked['sequence']
    assert (paid['payload']['monster_id'], paid['payload']['character_name']) == (
        attacked['payload']['monster_id'],
        '수로 쥐',
    )
    assert (paid['payload']['before'], paid['payload']['after']) == (2, 1)
    # 낸 비용은 수치의 이벤트에만 적는다. 공격의 이벤트에는 DB 에도 싣지 않는다
    stored = await session.execute(text("SELECT payload FROM table_events WHERE type = 'monster_attacked'"))
    assert 'cost' not in stored.scalar_one()


# --- 인물의 차례 ---


async def test_a_person_pays_for_the_strike_too(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await npc_turns.armed_and_fighting(client, app, me, narrated)
    await rewrite_content(session, world['table']['id'], costly_people)
    await set_mana(session, world['table']['id'], 1, 'table_npcs')
    turns.load_dice(app, [npc_turns.MISS])

    await npc_turns.laugh(client, me, world)
    await narrated()

    (turn,) = npc_turns.npc_turns(await turns.turns_of(session, world['table'], 2))
    assert [(one['before'], one['after']) for one in turn['outcome']['cost']] == [(1, 0)]


async def test_a_person_short_of_the_cost_does_not_strike(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, narrated
):
    world = await npc_turns.armed_and_fighting(client, app, me, narrated)
    await rewrite_content(session, world['table']['id'], costly_people)
    await set_mana(session, world['table']['id'], 0, 'table_npcs')
    dice = turns.load_dice(app, [])

    await npc_turns.laugh(client, me, world)
    await narrated()

    (turn,) = npc_turns.npc_turns(await turns.turns_of(session, world['table'], 2))
    assert turn['outcome']['skipped'] == 'cost_short'
    assert dice.remaining == 0


# --- 서술 ---


def test_the_narrator_hears_the_cost_in_words():
    turn = {
        'kind': 'monster',
        'name': '흑마법사',
        'outcome': {
            'attack': {'name': '화염구'},
            'character_name': '엘프',
            'success': False,
            'effect': None,
            'cost': [{'resource': 'mana', 'name': '마나', 'before': 4, 'after': 3, 'max': 4, 'min': 0}],
        },
    }

    note = to_turn_note(turn).monster

    assert note.cost == [ResourceNote(name='마나', word='넉넉함')]
    assert describe_monster_turn(note) == '흑마법사: 엘프에게 화염구 (빗나감) [마나 넉넉함]'


def test_a_turn_short_of_the_cost_is_narrated():
    turn = {
        'kind': 'npc',
        'name': '흑마법사',
        'outcome': {
            'skipped': 'cost_short',
            'attack': {'name': '화염구'},
            'user_id': str(ME),
            'character_name': '엘프',
        },
    }

    note = to_turn_note(turn).npc

    assert note == MonsterTurnNote(name='흑마법사', attack='화염구', target='엘프', hit=False, short=True)
    assert describe_monster_turn(note) == '흑마법사: 엘프에게 화염구 (비용이 모자라 하지 못함)'


def test_other_skipped_turns_stay_silent():
    assert to_turn_note({'kind': 'monster', 'name': '쥐', 'outcome': {'skipped': 'downed'}}) is None
