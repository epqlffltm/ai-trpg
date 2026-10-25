# trpg-server/tests/test_treat_aids.py

"""
치료에 붙여 쓰는 소모품(#277, 의료 키트)을 검증한다.

srd5 템플릿: 치료는 지혜로 한다. 팔 골절의 치료 난이도는 어려움(목표 20)이고, 성공하면 3일 앞당겨진다.
실패하면 치료 실패 표(d100)를 굴린다. 77 은 아무 일 없음이다. 시트의 지혜는 10(보정 0)이다.
프리젠 약사가 의료 키트(치료 보정 +2) 둘, 붕대(치료 보정 없는 소모품) 하나, 밧줄 하나를 가진다.

넷을 본다.
  - 시나리오: treat_bonus 는 소모품에만, 1~10 이다. 판 형식 60. 테이블의 물건 목록에 실린다.
  - 받기: 치료 보정이 있는 판의 물건이고 가지고 있어야 한다.
  - 닫힐 때: 그 보정이 판정의 보정에 더해진다. 성공하든 실패하든 하나 없어진다. 차례에 없으면 보정 없이 치료한다.
  - 기록과 서술: 치료의 결과와 이벤트(injury_treated)에 쓴 물건(aid)이 적히고, 치료의 줄에 붙는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_59
from app.rounds.move_lines import describe_treatment
from app.rounds.narrator import TreatmentNote
from tests import test_item_actions as actions
from tests.sheets import SHEET
from tests.test_item_cures import worn, wound
from tests.test_npc_sheets import published
from tests.test_table_items import take as take_away

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = actions.ME
FRIEND = actions.FRIEND
NO_SUCH_ID = actions.NO_SUCH_ID
SCENARIOS_URL = actions.SCENARIOS_URL
RULEBOOKS_URL = actions.RULEBOOKS_URL
LOREBOOKS_URL = actions.LOREBOOKS_URL
TABLES_URL = actions.TABLES_URL

me = actions.me
friend = actions.friend
post = actions.post
table_url = actions.table_url
declare = actions.declare
declared = actions.declared
held = actions.held
read_table = actions.read_table
first_round = actions.first_round
events_of = actions.events_of
load_dice = actions.load_dice

# 치료 판정의 눈. 보정 0 으로 어려움(20)에 18 은 실패, 의료 키트(+2)를 더하면 성공이다
JUST_SHORT = 18
FAIL = 1
# 치료 실패 표(d100)의 눈. 아무 일 없음
NOTHING = 77
KIT_BONUS = 2


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """물건 셋(의료 키트, 붕대, 밧줄)."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='약방의 물건들')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind='item')

    return {
        'lorebook': lorebook,
        'kit': await entry('의료 키트'),
        'bandage': await entry('붕대'),
        'rope': await entry('밧줄'),
    }


def the_items(lore: dict) -> list[dict]:
    """의료 키트는 치료 보정 +2 의 소모품, 붕대는 보정이 없는 소모품, 밧줄은 장비다."""
    return [
        {'entry_id': lore['kit']['id'], 'kind': 'consumable', 'treat_bonus': KIT_BONUS},
        {'entry_id': lore['bandage']['id'], 'kind': 'consumable'},
        {'entry_id': lore['rope']['id'], 'kind': 'gear'},
    ]


async def scenario_with(client: AsyncClient, me: dict, lore: dict) -> dict:
    """그 아이템 규칙을 적은 시나리오. 프리젠 약사가 의료 키트 둘, 붕대 하나, 밧줄 하나를 가진다."""
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    pregen_items = [
        {'entry_id': lore['kit']['id'], 'count': 2},
        {'entry_id': lore['bandage']['id'], 'count': 1},
        {'entry_id': lore['rope']['id'], 'count': 1},
    ]
    body = {
        'title': '약방의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['약방이다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        'items': the_items(lore),
        'pregens': [{'name': '약사', 'sheet': SHEET, 'items': pregen_items}],
    }
    return await post(client, SCENARIOS_URL, me, **body)


@pytest.fixture
async def table(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """둘이 앉아 시작한 테이블. 나는 기사(소지품 없음), 친구는 약사다. 첫 라운드가 열려 있다."""
    scenario = await scenario_with(client, me, lore)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    created = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': created['invite_code']}, headers=friend)
    await client.put(table_url(created, '/character'), json={'name': '기사'}, headers=me)
    await client.put(table_url(created, '/character'), json={'pregen_index': 0}, headers=friend)
    started = await client.post(table_url(created, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


def treat(item: dict | None = None, target: uuid.UUID | None = None) -> dict:
    """팔 골절을 치료하는 행동. 붙여 쓸 물건과 대상을 줄 수 있다. 대상을 비우면 자기 자신이다."""
    action = {'kind': 'treat', 'injury': 'broken_arm'}
    if item is not None:
        action['item'] = item['id']
    if target is not None:
        action['target'] = str(target)
    return action


async def outcome_of(client: AsyncClient, headers: dict, table: dict, user_id: uuid.UUID) -> dict:
    declarations = (await first_round(client, headers, table))['declarations']
    return next(d for d in declarations if d['user_id'] == str(user_id))['outcome']


async def play(client: AsyncClient, me: dict, friend: dict, table: dict, action: dict, narrated) -> None:
    """약사가 그 행동을 하고 기사는 주위를 살핀다. 라운드가 닫히고 서술이 끝날 때까지 기다린다."""
    await declared(client, friend, table, action)
    await declared(client, me, table)
    await narrated()


# --- 시나리오 ---


@pytest.mark.parametrize(
    'fields',
    [
        {'kind': 'gear', 'treat_bonus': 2},
        {'kind': 'consumable', 'treat_bonus': 0},
        {'kind': 'consumable', 'treat_bonus': 11},
    ],
    ids=['gear', 'zero', 'over-max'],
)
def test_rejects_misshaped_treat_bonuses(fields: dict):
    with pytest.raises(ValidationError):
        ItemRule.model_validate({'entry_id': NO_SUCH_ID, **fields})


async def test_the_bonus_is_frozen_and_listed(client: AsyncClient, me: dict, lore: dict, table: dict):
    read = await read_table(client, me, table)

    assert {item['name']: item['treat_bonus'] for item in read['items']} == {'의료 키트': 2, '붕대': None, '밧줄': None}


async def test_the_version_is_format_60(client: AsyncClient, me: dict, lore: dict):
    scenario = await scenario_with(client, me, lore)

    document = await published(client, me, scenario)

    assert document['format'] == SNAPSHOT_FORMAT >= 60
    assert [rule.treat_bonus for rule in read_snapshot(document).items] == [2, None, None]


def test_an_old_snapshot_reads_as_aiding_nothing():
    document = {'format': 59, 'items': [{'entry_id': NO_SUCH_ID, 'kind': 'consumable'}]}

    upgraded = upgrade_from_59(document)

    assert (upgraded['format'], upgraded['items'][0]['treat_bonus']) == (60, None)
    assert 'treat_bonus' not in document['items'][0]
    assert UPGRADES[59] is upgrade_from_59


# --- 받기 ---


async def test_the_aid_is_saved_with_the_treatment(
    client: AsyncClient, friend: dict, lore: dict, table: dict, session: AsyncSession
):
    await wound(session, table, FRIEND, 'broken_arm')

    await declared(client, friend, table, treat(lore['kit']))

    mine = next(d for d in (await first_round(client, friend, table))['declarations'] if d['user_id'] == str(FRIEND))
    assert mine['action'] == {
        'kind': 'treat',
        'injury': 'broken_arm',
        'target': str(FRIEND),
        'npc': None,
        'item': lore['kit']['id'],
    }


@pytest.mark.parametrize('name', ['bandage', 'rope'])
async def test_only_what_has_a_bonus_can_aid(
    client: AsyncClient, friend: dict, lore: dict, table: dict, session: AsyncSession, name: str
):
    await wound(session, table, FRIEND, 'broken_arm')

    response = await declare(client, friend, table, treat(lore[name]))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'item' in response.text


async def test_an_unknown_thing_cannot_aid(client: AsyncClient, friend: dict, table: dict, session: AsyncSession):
    await wound(session, table, FRIEND, 'broken_arm')

    response = await declare(client, friend, table, treat({'id': NO_SUCH_ID}))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_only_what_is_held_can_aid(client: AsyncClient, me: dict, lore: dict, table: dict, session: AsyncSession):
    await wound(session, table, ME, 'broken_arm')

    response = await declare(client, me, table, treat(lore['kit']))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert 'item_not_held' in response.text


# --- 닫힐 때 ---


async def test_the_bonus_turns_a_near_miss_into_a_success(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, FRIEND, 'broken_arm')
    load_dice(app, [JUST_SHORT])

    await play(client, me, friend, table, treat(lore['kit']), narrated)

    outcome = await outcome_of(client, me, table, FRIEND)
    assert (outcome['roll'], outcome['modifier'], outcome['total'], outcome['success']) == (18, 2, 20, True)
    assert outcome['treatment']['aid'] == {
        'entry_id': lore['kit']['id'],
        'name': '의료 키트',
        'bonus': KIT_BONUS,
        'used': True,
        'reason': None,
        'remaining': 1,
    }
    assert ('의료 키트', 1) in held(await read_table(client, me, table), FRIEND)


async def test_without_the_aid_the_same_roll_fails(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, table: dict, session, narrated
):
    await wound(session, table, FRIEND, 'broken_arm')
    load_dice(app, [JUST_SHORT, NOTHING])

    await play(client, me, friend, table, treat(), narrated)

    outcome = await outcome_of(client, me, table, FRIEND)
    assert (outcome['modifier'], outcome['success'], outcome['treatment']['aid']) == (0, False, None)
    assert ('의료 키트', 2) in held(await read_table(client, me, table), FRIEND)


async def test_a_failed_treatment_still_uses_the_aid_up(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, FRIEND, 'broken_arm')
    load_dice(app, [FAIL, NOTHING])

    await play(client, me, friend, table, treat(lore['kit']), narrated)

    outcome = await outcome_of(client, me, table, FRIEND)
    assert (outcome['success'], outcome['treatment']['aid']['used']) == (False, True)
    assert outcome['treatment']['mishap']['kind'] == 'nothing'
    assert ('의료 키트', 1) in held(await read_table(client, me, table), FRIEND)
    assert worn(await read_table(client, me, table), FRIEND) == ['broken_arm']


async def test_an_aid_can_help_treat_someone_else(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, ME, 'broken_arm')
    load_dice(app, [JUST_SHORT])

    await play(client, me, friend, table, treat(lore['kit'], ME), narrated)

    outcome = await outcome_of(client, me, table, FRIEND)
    assert (outcome['success'], outcome['treatment']['patient']['character_name']) == (True, '기사')
    assert ('의료 키트', 1) in held(await read_table(client, me, table), FRIEND)


async def test_what_was_taken_meanwhile_does_not_aid(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, FRIEND, 'broken_arm')
    load_dice(app, [JUST_SHORT, NOTHING])
    await declared(client, friend, table, treat(lore['kit']))
    # 선언한 뒤 차례가 오기 전에 의료 키트가 모두 없어졌다
    await take_away(session, table, FRIEND, lore['kit'])
    await declared(client, me, table)
    await narrated()

    outcome = await outcome_of(client, me, table, FRIEND)
    assert (outcome['modifier'], outcome['success']) == (0, False)
    assert outcome['treatment']['aid'] == {
        'entry_id': lore['kit']['id'],
        'name': '의료 키트',
        'bonus': 0,
        'used': False,
        'reason': 'not_held',
        'remaining': 0,
    }
    # 쓰지 못한 물건은 서술자에게 주지 않는다
    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '→ 약사의 팔 골절 치료 실패' in second['scene']
    assert '쓴 물건: 의료 키트' not in second['scene']


# --- 기록과 서술 ---


async def test_the_aid_is_in_the_treatment_event(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, FRIEND, 'broken_arm')
    load_dice(app, [JUST_SHORT])

    await play(client, me, friend, table, treat(lore['kit']), narrated)

    (treated,) = await events_of(client, me, table, 'injury_treated')
    assert treated['payload']['aid'] == {
        'entry_id': lore['kit']['id'],
        'name': '의료 키트',
        'bonus': KIT_BONUS,
        'used': True,
        'reason': None,
        'remaining': 1,
    }


async def test_a_treatment_without_an_aid_has_no_aid_in_its_event(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, table: dict, session, narrated
):
    await wound(session, table, FRIEND, 'broken_arm')
    load_dice(app, [JUST_SHORT, NOTHING])

    await play(client, me, friend, table, treat(), narrated)

    (treated,) = await events_of(client, me, table, 'injury_treated')
    assert 'aid' not in treated['payload']


async def test_the_narrator_hears_what_aided(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, FRIEND, 'broken_arm')
    load_dice(app, [JUST_SHORT])

    await play(client, me, friend, table, treat(lore['kit']), narrated)

    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '→ 약사의 팔 골절 치료(쓴 물건: 의료 키트 +2): 앞당겨짐' in second['scene']


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (
            TreatmentNote(injury='팔 골절', patient='토르빈', aid='의료 키트', aid_bonus=2, minutes_left=150),
            '→ 토르빈의 팔 골절 치료(쓴 물건: 의료 키트 +2): 앞당겨짐, 낫기까지 2시간 30분',
        ),
        (
            TreatmentNote(injury='팔 골절', patient='토르빈', aid='붕대', aid_bonus=1, mishap='nothing'),
            '→ 토르빈의 팔 골절 치료(쓴 물건: 붕대 +1) 실패: 별일 없음',
        ),
        (TreatmentNote(injury='팔 골절', patient='토르빈', healed=True), '→ 토르빈의 팔 골절 치료: 다 나음'),
    ],
    ids=['aided', 'aided-failure', 'no-aid'],
)
def test_the_line_names_what_aided(note: TreatmentNote, line: str):
    assert describe_treatment(note) == line
