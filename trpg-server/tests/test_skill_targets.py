# trpg-server/tests/test_skill_targets.py

"""
상대에게 쓰는 기술과 맞히는 판정(#805 ②, app/rounds/skill_actions.py 의 judge_rolled_skill)을 검증한다.

판은 물건 던지기의 지하 수로다(tests/test_item_throws.py). 수로 입구에 수로 쥐 둘(최대 HP 4), 깊은 수로에 해골 병사,
어디서나 닿는 악역영애(비올레타). 룰북은 srd5 에 마나(6)를 더하고 기술 셋을 둔다.
  - 마력 화살: 마나 1, 상대, 지능·보통의 맞히기, 가벼운 피해
  - 독침: 마나 1, 상대, 판정을 비워 룰북의 맞히는 판정(민첩·보통), 중독
  - 저주: 마나 1, 동료, 매력의 맞히기(난이도는 룰북의 기본), 가벼운 피해
기본 시트(모두 10)가 셋을 다 안다. 주사위는 판정의 눈을 먼저, 피해의 눈을 그다음에 쓴다.

넷을 본다.
  - 규칙: 자신에게만 쓰는 기술에는 판정이 없다. 상대에게 쓰는 기술은 기술이나 룰북에 판정이 있어야 한다.
  - 받기: 상대에게 쓰는 기술은 인물이나 몬스터 하나를 치기처럼 겨눈다. 자신과 동료에게 쓰는 기술은 겨누지 않는다.
  - 닫힐 때: 비용을 내고 굴린다. 맞히면 효과가 들고, 빗나가도 비용은 낸다. 겨눈 몬스터가 없으면 쓰지 않는다.
    판정이 있는 기술을 동료에게 쓰면 굴린다.
  - 기록과 서술: skill_used 뒤에 판정(check_rolled)과 맞은 쪽의 변화가 잇는다. 기술의 줄은 판정 앞에 붙는다.
"""

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.action import SkillAction
from app.engine.ruleset import Ruleset, Skill
from app.engine.templates import SRD5
from app.tables.models import NpcStatus
from tests import test_item_throws as throws
from tests import test_monster_combat as combat
from tests.sheets import SHEET

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
FRIEND = combat.FRIEND
me = combat.me
friend = combat.friend
post = combat.post
table_url = combat.table_url
load_dice = combat.load_dice
send = combat.send
declare = combat.declare
monster_named = combat.monster_named
state_of = combat.state_of
events_of = combat.events_of
outcome_of = throws.outcome_of
kill = throws.kill

FAIL = combat.FAIL
PASS = combat.PASS
NO_INJURY = combat.NO_INJURY
NO_SUCH_ID = throws.NO_SUCH_ID

CAST = '주문을 왼다.'
LOOK = '주위를 살핀다.'
MANA = {'key': 'mana', 'name': '마나', 'max': {'base': 6}}
BOLT = {
    'key': 'arcane_bolt',
    'name': '마력 화살',
    'cost': {'resource': 'mana', 'amount': 1},
    'target': 'foe',
    'effects': [{'kind': 'damage', 'magnitude': 'light'}],
    'check': {'ability': 'int', 'difficulty': 'medium'},
}
STING = {
    'key': 'sting',
    'name': '독침',
    'cost': {'resource': 'mana', 'amount': 1},
    'target': 'foe',
    'effects': [{'kind': 'injure', 'injury': 'poisoned'}],
}
HEX = {
    'key': 'hex',
    'name': '저주',
    'cost': {'resource': 'mana', 'amount': 1},
    'target': 'ally',
    'effects': [{'kind': 'damage', 'magnitude': 'light'}],
    'check': {'ability': 'cha'},
}


def cast(key: str, **target) -> dict:
    return {'kind': 'skill', 'skill': key, **target}


async def start(client: AsyncClient, me: dict, *others: dict) -> dict:
    """수로의 판을 기술의 룰북으로 시작한다. 나(엘프)와 others(드워프 기사)가 앉는다."""
    world = await throws.make_world(client, me)
    world['rulebook'] = await post(
        client, combat.RULEBOOKS_URL, me, title='주문', template='srd5', resources=[MANA], skills=[BOLT, STING, HEX]
    )
    scenario = await throws.make_scenario(client, me, world, [])
    sheet = {**SHEET, 'skills': ['arcane_bolt', 'sting', 'hex']}
    url = f'{combat.SCENARIOS_URL}/{scenario["id"]}'
    assert (await client.patch(url, json={'default_sheet': sheet}, headers=me)).status_code == status.HTTP_200_OK
    await post(client, f'{url}/versions', me)
    table = await post(client, combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    for headers, name in zip([me, *others], ['엘프', '드워프 기사'], strict=False):
        if headers is not me:
            await client.post(f'{combat.TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': started.json()}


def rules_with(**skill) -> dict:
    return {**SRD5.model_dump(mode='json'), 'resources': [MANA], 'skills': [{**BOLT, **skill}]}


# --- 규칙 ---


def test_a_self_only_skill_has_no_check():
    with pytest.raises(ValidationError, match='자신에게만'):
        Skill.model_validate({**BOLT, 'target': 'self'})


@pytest.mark.parametrize(
    ('skill', 'item_check', 'message'),
    [
        ({'check': {'ability': 'luck'}}, True, '맞히는 판정'),
        ({'check': {'ability': 'int', 'difficulty': 'impossible'}}, True, '맞히는 판정'),
        ({'check': None}, False, '상대에게 쓰는 기술'),
    ],
    ids=['unknown-ability', 'unknown-difficulty', 'no-check-anywhere'],
)
def test_a_foe_skill_needs_a_check_the_rules_know(skill: dict, item_check: bool, message: str):
    rules = rules_with(**skill)
    if not item_check:
        rules['item_check'] = None

    with pytest.raises(ValidationError, match=message):
        Ruleset.model_validate(rules)


def test_a_foe_skill_may_leave_the_check_to_the_rulebook():
    rules = Ruleset.model_validate(rules_with(check=None))

    assert rules.skills[0].check is None


@pytest.mark.parametrize(
    'fields',
    [{'target': str(ME), 'npc': NO_SUCH_ID}, {'npc': NO_SUCH_ID, 'monster': NO_SUCH_ID}, {'lethal': True}],
    ids=['target-and-npc', 'npc-and-monster', 'lethal-alone'],
)
def test_a_skill_aims_at_one_thing(fields: dict):
    with pytest.raises(ValidationError):
        SkillAction.model_validate(cast('arcane_bolt', **fields))


# --- 받기 ---


@pytest.mark.parametrize(
    ('action', 'field'),
    [
        (cast('arcane_bolt'), 'target'),
        (cast('arcane_bolt', target=str(ME)), 'target'),
        (cast('arcane_bolt', monster=NO_SUCH_ID), 'monster'),
        (cast('arcane_bolt', npc=NO_SUCH_ID), 'npc'),
        (cast('sting', npc=NO_SUCH_ID, lethal=True), 'lethal'),
    ],
    ids=['no-aim', 'seated', 'monster-elsewhere', 'person-not-here', 'lethal-without-harm'],
)
async def test_a_foe_skill_aims_like_a_blow(client: AsyncClient, me: dict, action: dict, field: str):
    world = await start(client, me)

    response = await send(client, me, world['table'], CAST, action)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert field in response.text


async def test_a_skill_for_oneself_and_friends_does_not_aim_at_a_monster(client: AsyncClient, me: dict):
    world = await start(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')

    response = await send(client, me, world['table'], CAST, cast('hex', monster=rat['id']))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'monster' in response.text


async def test_a_dead_monster_is_not_aimed_at(client: AsyncClient, me: dict, session: AsyncSession):
    world = await start(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    await kill(session, rat['id'])

    response = await send(client, me, world['table'], CAST, cast('arcane_bolt', monster=rat['id']))

    assert (response.status_code, response.json()['reason']) == (status.HTTP_409_CONFLICT, 'monster_dead')


# --- 닫힐 때 ---


async def test_a_bolt_that_hits_pays_and_hurts_the_monster(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await start(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3, NO_INJURY])

    closing = await declare(client, me, world['table'], CAST, cast('arcane_bolt', monster=rat['id']))

    outcome = outcome_of(closing, ME)
    used = outcome['skill_use']
    assert (used['used'], used['ability'], used['difficulty']) == (True, 'int', 'medium')
    assert used['target'] == {'monster_id': rat['id'], 'entry_id': None, 'user_id': None, 'name': '수로 쥐 1'}
    assert [(one['before'], one['after']) for one in used['cost']] == [(6, 5)]
    assert (outcome['success'], outcome['monster_effect']['amount']) == (True, 3)
    assert await state_of(session, rat['id']) == (1, NpcStatus.ALIVE)


async def test_a_miss_still_costs(client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession):
    world = await start(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [FAIL])

    closing = await declare(client, me, world['table'], CAST, cast('arcane_bolt', monster=rat['id']))

    outcome = outcome_of(closing, ME)
    assert (outcome['success'], outcome['monster_effect'], outcome['skill_use']['used']) == (False, None, True)
    assert [one['after'] for one in outcome['skill_use']['cost']] == [5]
    assert await state_of(session, rat['id']) == (4, NpcStatus.ALIVE)


@pytest.mark.parametrize(('lethal', 'expected'), [(False, NpcStatus.DOWNED), (True, NpcStatus.DEAD)])
async def test_a_bolt_may_be_lethal(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession, lethal: bool, expected: NpcStatus
):
    world = await start(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 4, NO_INJURY])

    await declare(client, me, world['table'], CAST, cast('arcane_bolt', monster=rat['id'], lethal=lethal))

    assert await state_of(session, rat['id']) == (0, expected)


async def test_a_sting_rolls_the_rulebook_s_check_and_poisons_a_person(
    client: AsyncClient, app: FastAPI, me: dict, session: AsyncSession
):
    world = await start(client, me)
    load_dice(app, [PASS])

    closing = await declare(client, me, world['table'], CAST, cast('sting', npc=world['lady']['id']))

    used = outcome_of(closing, ME)['skill_use']
    assert (used['ability'], used['difficulty']) == ('dex', 'medium')
    assert [one['injury'] for one in used['injured']] == ['poisoned']
    stored = await session.execute(text('SELECT source FROM table_injuries'))
    assert stored.scalars().all() == ['skill']


async def test_a_monster_killed_meanwhile_is_not_cast_at(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession, narrated
):
    world = await start(client, me, friend)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    await declare(client, friend, world['table'], CAST, cast('arcane_bolt', monster=rat['id']))
    await kill(session, rat['id'])
    await declare(client, me, world['table'], LOOK)
    await narrated()

    outcome = outcome_of(await throws.first_round(client, me, world['table']), FRIEND)
    assert (outcome['skill_use']['used'], outcome['skill_use']['reason']) == (False, 'target_gone')
    assert (outcome['target_gone']['reason'], outcome['skill_use']['cost']) == ('dead', [])
    assert 'roll' not in outcome
    assert await events_of(client, me, world['table'], 'check_rolled') == []


async def test_a_checked_skill_on_a_friend_rolls(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    world = await start(client, me, friend)
    await client.put(table_url(world['table'], '/friendly-fire'), json={'friendly_fire': 'full'}, headers=me)
    await client.put(
        table_url(world['table'], '/members/me/friendly-fire'), json={'friendly_fire': 'full'}, headers=friend
    )
    load_dice(app, [FAIL])

    await declare(client, me, world['table'], CAST, cast('hex', target=str(FRIEND)))
    closing = await declare(client, friend, world['table'], LOOK)

    outcome = outcome_of(closing, ME)
    assert (outcome['success'], outcome['effect'], outcome['skill_use']['ability']) == (False, None, 'cha')
    assert outcome['skill_use']['target']['user_id'] == str(FRIEND)
    assert [one['after'] for one in outcome['skill_use']['cost']] == [5]


async def test_a_checked_skill_on_oneself_does_not_roll(client: AsyncClient, app: FastAPI, me: dict):
    world = await start(client, me)
    load_dice(app, [2])

    closing = await declare(client, me, world['table'], CAST, cast('hex'))

    outcome = outcome_of(closing, ME)
    assert 'roll' not in outcome
    assert (outcome['skill_use']['ability'], outcome['effect']['kind']) == (None, 'damage')


# --- 기록과 서술 ---


async def test_the_skill_is_recorded_before_its_check(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3, NO_INJURY])
    await declare(client, me, world['table'], CAST, cast('arcane_bolt', monster=rat['id']))
    await narrated()

    (acted,) = await events_of(client, me, world['table'], 'player_action')
    (used,) = await events_of(client, me, world['table'], 'skill_used')
    (paid,) = await events_of(client, me, world['table'], 'resource_changed')
    (rolled,) = await events_of(client, me, world['table'], 'check_rolled')
    (changed,) = await events_of(client, me, world['table'], 'monster_changed')
    assert used['caused_by_sequence'] == acted['sequence']
    assert (paid['caused_by_sequence'], rolled['caused_by_sequence']) == (used['sequence'], used['sequence'])
    assert changed['caused_by_sequence'] == rolled['sequence']
    assert used['payload']['target'] == {'monster_id': rat['id'], 'name': '수로 쥐 1'}
    assert (rolled['payload']['ability'], rolled['payload']['difficulty']) == ('int', 'medium')


async def test_the_narrator_hears_the_skill_before_the_check(client: AsyncClient, app: FastAPI, me: dict, narrated):
    world = await start(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3, NO_INJURY])
    await declare(client, me, world['table'], CAST, cast('arcane_bolt', monster=rat['id']))
    await narrated()

    second = (await client.get(table_url(world['table'], '/rounds/current'), headers=me)).json()
    assert f'엘프: {CAST} (쓴 기술: 마력 화살 → 수로 쥐 1, 마나 6 → 5/6) (' in second['scene']
