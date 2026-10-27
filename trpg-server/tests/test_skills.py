# trpg-server/tests/test_skills.py

"""
기술과 주문(#805 ①, 판 형식 66)을 검증한다. 규칙(app/engine/ruleset.py 의 Skill), 룰북의 고치기, 시나리오의 시트의
아는 기술과 게시 검사, 시트, 기술을 쓰는 행동(받기, 판정, 기록), 서술의 줄, 판의 형식과 마이그레이션이다.

판은 가벼운 규칙(light)이다. 마나(3 + 마음, 10 까지)를 쓰고, 캐릭터는 몸 3, 재치 2, 마음 4 라 마나의 최대는 7 이다.
룰북의 기술은 셋이다. 치유의 손길(마나 2, 동료, 가볍게 회복), 정신 집중(스태미나 2, 자신, 마나 +1),
저주(마나 1, 동료, 가벼운 피해). 기본 시트는 치유의 손길과 저주를 안다(정신 집중은 모른다).
나(엘프)와 동료(영애)가 앉는다. 부상을 입히는 기술만은 부상이 있는 srd5 에 마나를 더한 판에서 본다.
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
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_65
from app.engine.ruleset import Ruleset
from app.engine.sheet import CharacterSheet
from app.engine.templates import from_template
from app.rounds.move_lines import describe_skill
from app.rounds.narrator import Impact, ResourceNote, SkillNote
from app.rounds.router import visible_outcome
from app.tables.sheets import build_player_made
from tests import test_monster_combat as combat
from tests.sheets import SHEET as SRD5_SHEET
from tests.test_npc_sheets import refused
from tests.test_ruleset import load_migration

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
FRIEND = combat.FRIEND
me = combat.me
friend = combat.friend
post = combat.post
table_url = combat.table_url
declare = combat.declare
send = combat.send
events_of = combat.events_of

LIGHT = from_template('light')
ABILITIES = {'body': 3, 'wits': 2, 'heart': 4}
HEAL = {
    'key': 'healing_touch',
    'name': '치유의 손길',
    'cost': {'resource': 'mana', 'amount': 2},
    'target': 'ally',
    'effects': [{'kind': 'heal', 'magnitude': 'light'}],
}
FOCUS = {
    'key': 'focus',
    'name': '정신 집중',
    'cost': {'resource': 'stamina', 'amount': 2},
    'effects': [{'kind': 'adjust', 'resource': 'mana', 'amount': 1}],
}
HEX = {
    'key': 'hex',
    'name': '저주',
    'cost': {'resource': 'mana', 'amount': 1},
    'target': 'ally',
    'effects': [{'kind': 'damage', 'magnitude': 'light'}],
}


def skill(key: str) -> dict:
    return {'kind': 'skill', 'skill': key}


def rules_with(*skills: dict) -> dict:
    return {**LIGHT.model_dump(mode='json'), 'skills': list(skills)}


async def start(client: AsyncClient, me: dict, friend: dict, known: list[str] | None = None) -> dict:
    """세 기술의 가벼운 룰북으로 나와 동료가 앉아 시작한다. 기본 시트가 known 의 기술을 안다."""
    rulebook = await post(client, combat.RULEBOOKS_URL, me, title='기술', template='light', skills=[HEAL, FOCUS, HEX])
    sheet = {'abilities': ABILITIES, 'max_hp': 10, 'skills': ['healing_touch', 'hex'] if known is None else known}
    return await start_with(client, me, friend, rulebook, sheet)


async def start_with(client: AsyncClient, me: dict, friend: dict, rulebook: dict, sheet: dict) -> dict:
    """이 룰북과 기본 시트로 나와 동료가 앉아 시작한다."""
    lorebook = await post(client, combat.LOREBOOKS_URL, me, title='탑')
    scenario = await post(
        client,
        combat.SCENARIOS_URL,
        me,
        title='탑',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        openings=['탑 꼭대기다.'],
        default_sheet=sheet,
    )
    await post(client, f'{combat.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    await client.post(f'{combat.TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    for headers, name in ((me, '엘프'), (friend, '영애')):
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    return (await client.post(table_url(table, '/start'), headers=me)).json()


async def set_sheet(session: AsyncSession, user_id: uuid.UUID, **values) -> None:
    """서비스를 거치지 않고 시트의 HP 나 수치를 정한다."""
    if 'hp' in values:
        await session.execute(
            text('UPDATE table_sheets SET hp = :hp WHERE user_id = :user_id'), {'hp': values['hp'], 'user_id': user_id}
        )
    if 'resources' in values:
        await session.execute(
            text('UPDATE table_sheets SET resources = CAST(:values AS JSONB) WHERE user_id = :user_id'),
            {'values': json.dumps(values['resources']), 'user_id': user_id},
        )
    await session.commit()


def outcome_of(round_: dict, user_id: uuid.UUID = ME) -> dict:
    return next(d for d in round_['declarations'] if d['user_id'] == str(user_id))['outcome']


def mana_of(table: dict, user_id: uuid.UUID) -> int:
    sheet = next(member for member in table['members'] if member['user_id'] == str(user_id))['sheet']
    return next(one['value'] for one in sheet['resources'] if one['key'] == 'mana')


# --- 규칙 ---


def test_the_light_template_has_two_example_skills():
    assert [one.key for one in LIGHT.skills] == ['healing_touch', 'focus']
    assert from_template('srd5').skills == ()


@pytest.mark.parametrize(
    ('broken', 'message'),
    [
        ({**HEAL, 'cost': {'resource': 'gold', 'amount': 1}}, '비용'),
        ({**HEAL, 'effects': [{'kind': 'heal', 'magnitude': 'huge'}]}, '효과'),
        ({**FOCUS, 'effects': [{'kind': 'adjust', 'resource': 'gold', 'amount': 1}]}, '효과'),
    ],
)
def test_a_skill_must_point_at_what_the_rules_have(broken: dict, message: str):
    with pytest.raises(ValidationError, match=message):
        Ruleset.model_validate(rules_with(broken))


def test_skills_are_not_repeated_and_cost_at_least_one():
    with pytest.raises(ValidationError, match='같은 기술'):
        Ruleset.model_validate(rules_with(HEAL, HEAL))
    with pytest.raises(ValidationError):
        Ruleset.model_validate(rules_with({**HEAL, 'cost': {'resource': 'mana', 'amount': 0}}))
    with pytest.raises(ValidationError, match='두 번'):
        CharacterSheet.model_validate({'abilities': ABILITIES, 'max_hp': 10, 'skills': ['hex', 'hex']})


# --- 룰북 ---


async def test_the_skills_of_a_rulebook_can_be_changed(client: AsyncClient, me: dict):
    rulebook = await post(client, combat.RULEBOOKS_URL, me, title='가벼운', template='light')
    url = f'{combat.RULEBOOKS_URL}/{rulebook["id"]}'

    replaced = await client.patch(url, json={'skills': [HEX]}, headers=me)
    wrong = await client.patch(url, json={'skills': [{**HEX, 'cost': {'resource': 'gold', 'amount': 1}}]}, headers=me)
    # 저주가 쓰는 마나를 지우면 수치의 칸이 틀렸다. 둘을 함께 고치면 된다
    orphaned = await client.patch(url, json={'resources': []}, headers=me)
    both = await client.patch(url, json={'resources': [], 'skills': []}, headers=me)

    assert [one['key'] for one in rulebook['rules']['skills']] == ['healing_touch', 'focus']
    assert [one['key'] for one in replaced.json()['rules']['skills']] == ['hex']
    assert (wrong.status_code, wrong.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'skills')
    assert (orphaned.status_code, orphaned.json()['field']) == (status.HTTP_422_UNPROCESSABLE_CONTENT, 'resources')
    assert both.status_code == status.HTTP_200_OK
    assert (both.json()['rules']['resources'], both.json()['rules']['skills']) == ([], [])


# --- 시트 ---


async def test_a_sheet_knows_the_skills_of_its_scenario_sheet(client: AsyncClient, me: dict, friend: dict):
    table = await start(client, me, friend)

    sheet = table['members'][0]['sheet']

    assert sheet['skills'] == ['healing_touch', 'hex']


async def test_an_unknown_skill_on_a_sheet_is_refused_at_publishing(client: AsyncClient, me: dict):
    lorebook = await post(client, combat.LOREBOOKS_URL, me, title='탑')
    rulebook = await post(client, combat.RULEBOOKS_URL, me, title='가벼운', template='light')
    scenario = await post(
        client,
        combat.SCENARIOS_URL,
        me,
        title='탑',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        openings=['탑이다.'],
        default_sheet={'abilities': ABILITIES, 'max_hp': 10, 'skills': ['fireball']},
    )

    assert 'sheet_skill_invalid' in await refused(client, me, scenario)


def test_a_player_made_character_knows_the_skills_of_the_default_sheet():
    default = CharacterSheet(abilities=ABILITIES, max_hp=10, skills=['healing_touch'])
    snapshot = SimpleNamespace(
        rulebook=SimpleNamespace(rules=LIGHT), player_made_hp=SimpleNamespace(base=8, cap=20), default_sheet=default
    )

    made = build_player_made(snapshot, {'body': 2, 'wits': 3, 'heart': 4})
    bare = build_player_made(SimpleNamespace(**{**vars(snapshot), 'default_sheet': None}), ABILITIES)

    assert (made.skills, bare.skills) == (['healing_touch'], [])


# --- 쓰기 ---


async def test_a_healing_touch_costs_mana_and_heals_a_friend(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    table = await start(client, me, friend)
    await set_sheet(session, FRIEND, hp=3)
    combat.load_dice(app, [2])

    await declare(client, me, table, '영애의 상처를 어루만진다.', {**skill('healing_touch'), 'target': str(FRIEND)})
    closing = await declare(client, friend, table, '숨을 고른다.')

    used = outcome_of(closing)
    assert used['skill_use']['used'] is True
    assert used['skill_use']['cost'] == [{'resource': 'mana', 'name': '마나', 'before': 7, 'after': 5, 'max': 7}]
    assert (used['effect']['user_id'], used['effect']['kind'], used['effect']['after']) == (str(FRIEND), 'recovery', 5)
    read = (await client.get(table_url(table), headers=me)).json()
    assert mana_of(read, ME) == 5
    (event,) = await events_of(client, me, table, 'skill_used')
    assert (event['payload']['skill'], event['payload']['target']['user_id']) == ('healing_touch', str(FRIEND))
    (paid,) = await events_of(client, me, table, 'resource_changed')
    assert (paid['payload']['user_id'], paid['payload']['source'], paid['caused_by_sequence']) == (
        str(ME),
        'skill',
        event['sequence'],
    )


async def test_one_cannot_use_a_skill_one_does_not_know_or_cannot_pay(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession
):
    table = await start(client, me, friend)

    unknown = await send(client, me, table, '집중한다.', skill('focus'))
    missing = await send(client, me, table, '불을 부른다.', skill('fireball'))
    await set_sheet(session, ME, resources={'mana': 1})
    short = await send(client, me, table, '어루만진다.', skill('healing_touch'))

    assert (unknown.status_code, unknown.json()['reason']) == (status.HTTP_409_CONFLICT, 'skill_not_known')
    assert (missing.status_code, missing.json()['detail']) == (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        'action.skill 가 이 테이블의 규칙에 없습니다.',
    )
    assert (short.status_code, short.json()['reason']) == (status.HTTP_409_CONFLICT, 'skill_cost_short')


async def test_a_self_only_skill_takes_no_one_else(client: AsyncClient, me: dict, friend: dict):
    table = await start(client, me, friend, known=['focus'])

    response = await send(client, me, table, '집중한다.', {**skill('focus'), 'target': str(FRIEND)})
    stored = await declare(client, me, table, '집중한다.', skill('focus'))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    mine = next(d for d in stored['declarations'] if d['user_id'] == str(ME))
    assert mine['action']['target'] == str(ME)


async def test_a_skill_that_cannot_be_paid_when_its_turn_comes_is_not_used(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession
):
    table = await start(client, me, friend)
    await declare(client, me, table, '어루만진다.', skill('healing_touch'))
    await set_sheet(session, ME, resources={'mana': 1})

    closing = await declare(client, friend, table, '지켜본다.')

    used = outcome_of(closing)['skill_use']
    assert (used['used'], used['reason'], used['cost']) == (False, 'cost_short', [])
    assert mana_of((await client.get(table_url(table), headers=me)).json(), ME) == 1


async def test_a_harmful_skill_on_a_friend_follows_friendly_fire(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    table = await start(client, me, friend)

    off = await send(client, me, table, '저주한다.', {**skill('hex'), 'target': str(FRIEND)})
    await client.put(table_url(table, '/friendly-fire'), json={'friendly_fire': 'full'}, headers=me)
    await client.put(table_url(table, '/members/me/friendly-fire'), json={'friendly_fire': 'full'}, headers=friend)
    combat.load_dice(app, [2])
    await declare(client, me, table, '저주한다.', {**skill('hex'), 'target': str(FRIEND)})
    closing = await declare(client, friend, table, '움찔한다.')

    assert off.json()['reason'] == 'friendly_fire_off'
    assert (outcome_of(closing)['effect']['kind'], outcome_of(closing)['effect']['after']) == ('damage', 8)


async def test_an_injury_from_a_skill_is_kept_as_from_a_skill(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    poison = {
        'key': 'venom',
        'name': '독침',
        'cost': {'resource': 'mana', 'amount': 1},
        'target': 'ally',
        'effects': [{'kind': 'injure', 'injury': 'poisoned'}],
    }
    mana = {'key': 'mana', 'name': '마나', 'max': {'base': 6}}
    rulebook = await post(
        client, combat.RULEBOOKS_URL, me, title='독', template='srd5', resources=[mana], skills=[poison]
    )
    table = await start_with(client, me, friend, rulebook, {**SRD5_SHEET, 'skills': ['venom']})
    await client.put(table_url(table, '/friendly-fire'), json={'friendly_fire': 'full'}, headers=me)
    await client.put(table_url(table, '/members/me/friendly-fire'), json={'friendly_fire': 'full'}, headers=friend)

    await declare(client, me, table, '독침을 쏜다.', {**skill('venom'), 'target': str(FRIEND)})
    closing = await declare(client, friend, table, '따끔하다.')

    assert outcome_of(closing)['skill_use']['injured'][0]['injury'] == 'poisoned'
    stored = await session.execute(text('SELECT source FROM table_injuries'))
    assert stored.scalars().all() == ['skill']


# --- 보이기와 서술 ---


def test_a_hidden_cost_is_left_out_for_others():
    outcome = {
        'skill_use': {
            'cost': [{'resource': 'mana', 'before': 3, 'after': 1, 'max': 7, 'user_id': str(ME), 'visibility': 'owner'}]
        }
    }

    assert visible_outcome(outcome, ME)['skill_use']['cost'][0]['after'] == 1
    assert visible_outcome(outcome, FRIEND)['skill_use']['cost'] == []


def test_the_narration_line_of_a_skill():
    used = SkillNote(
        name='치유의 손길',
        done=True,
        target='영애',
        cost=[ResourceNote(name='마나', value=3, max=7, before=5)],
        impact=Impact(kind='recovery', character_name='영애', amount=2, hp=5, max_hp=10, downed=False),
    )
    failed = SkillNote(name='정신 집중', done=False, reason='cost_short')

    assert describe_skill(used).startswith('(쓴 기술: 치유의 손길 → 영애, 마나 5 → 3/7) ')
    assert describe_skill(failed) == '(쓰려던 기술: 정신 집중. 비용이 모자랐다)'


# --- 판의 형식과 마이그레이션 ---


def test_an_old_document_reads_with_no_skills():
    old = {'format': 65, 'rulebook': {'title': '룰북', 'rules': {'template': 'srd5'}}}

    upgraded = upgrade_from_65(old)

    assert (SNAPSHOT_FORMAT >= 66, UPGRADES[65] is upgrade_from_65) == (True, True)
    assert (upgraded['format'], upgraded['rulebook']['rules']['skills']) == (66, [])
    assert 'skills' not in old['rulebook']['rules']


def test_the_migration_fills_rulebooks_and_strips_known_skills_on_the_way_back():
    migration = load_migration('skills')

    assert migration.with_skills({'template': 'light'}) == {'template': 'light', 'skills': []}
    assert migration.without_skills({'template': 'light', 'skills': [HEAL]}) == {'template': 'light'}
    pregens = [{'name': '엘프', 'sheet': {'abilities': ABILITIES, 'max_hp': 10, 'skills': ['hex']}}, {'name': '빈'}]
    assert migration.pregens_without_known(pregens) == [
        {'name': '엘프', 'sheet': {'abilities': ABILITIES, 'max_hp': 10}},
        {'name': '빈', 'sheet': None},
    ]
