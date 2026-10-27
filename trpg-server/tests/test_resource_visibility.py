# trpg-server/tests/test_resource_visibility.py

"""
수치를 누가 보나(#804 ③ 의 보이기)를 검증한다. 규칙(visibility), 네 단계의 말(app/engine/resources.py 의 band_of),
시트와 라운드의 결과와 이벤트의 거르기, 서술의 말이다.

판은 d20 판타지(srd5)에 수치 셋을 단 룰북이다. 모두 고정값 6, 가득에서 시작하고 짧은 휴식에 2 오른다.
마나는 모두가 보고, 광기는 가진 사람만 보고, 비밀은 엔진만 본다. 나(엘프)와 동료(영애)가 앉는다.
"""

import json
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import resources as engine
from app.engine.resources import BAND_EMPTY, BAND_FULL, BAND_LOW, BAND_PLENTY
from app.engine.ruleset import Resource
from app.rounds.move_lines import describe_resource
from app.rounds.moves import level_note
from app.rounds.narration_request import to_shift_note
from app.rounds.router import visible_outcome
from tests import test_monster_combat as combat

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = combat.ME
FRIEND = combat.FRIEND
me = combat.me
friend = combat.friend
post = combat.post
table_url = combat.table_url
declare = combat.declare
events_of = combat.events_of

ABILITIES = {'str': 10, 'dex': 10, 'con': 10, 'int': 10, 'wis': 10, 'cha': 10}
SHORT_RAISE = {'short': {'kind': 'raise', 'amount': 2}}


def resource(key: str, name: str, visibility: str) -> dict:
    return {'key': key, 'name': name, 'max': {'base': 6}, 'rest': SHORT_RAISE, 'visibility': visibility}


MANA = resource('mana', '마나', 'everyone')
MADNESS = resource('madness', '광기', 'owner')
SECRET = resource('secret', '비밀', 'engine')


async def start(client: AsyncClient, me: dict, friend: dict) -> dict:
    """수치 셋의 룰북으로 나와 동료가 앉아 시작한다."""
    lorebook = await post(client, combat.LOREBOOKS_URL, me, title='탑')
    rulebook = await post(
        client, combat.RULEBOOKS_URL, me, title='숨긴 룰북', template='srd5', resources=[MANA, MADNESS, SECRET]
    )
    scenario = await post(
        client,
        combat.SCENARIOS_URL,
        me,
        title='탑',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        openings=['탑 꼭대기다.'],
        default_sheet={'abilities': ABILITIES, 'max_hp': 10},
    )
    await post(client, f'{combat.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    await client.post(f'{combat.TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    for headers, name in ((me, '엘프'), (friend, '영애')):
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    return (await client.post(table_url(table, '/start'), headers=me)).json()


async def lower_mine(session: AsyncSession) -> None:
    """내 수치 셋을 모두 1 로 둔다."""
    await session.execute(
        text('UPDATE table_sheets SET resources = CAST(:values AS JSONB) WHERE user_id = :user_id'),
        {'values': json.dumps({'mana': 1, 'madness': 1, 'secret': 1}), 'user_id': ME},
    )
    await session.commit()


def keys_on_sheet(table: dict, user_id: uuid.UUID) -> list[str]:
    sheet = next(member for member in table['members'] if member['user_id'] == str(user_id))['sheet']
    return [one['key'] for one in sheet['resources']]


def my_rest(round_: dict) -> dict:
    return next(d for d in round_['declarations'] if d['user_id'] == str(ME))['outcome']['rest']


# --- 말과 보이기 ---


@pytest.mark.parametrize(
    ('value', 'band'),
    [(6, BAND_FULL), (3, BAND_PLENTY), (4, BAND_PLENTY), (2, BAND_LOW), (1, BAND_LOW), (0, BAND_EMPTY)],
)
def test_a_hidden_value_reads_as_one_of_four_words(value: int, band: str):
    assert engine.band_of(value, 0, 6) == band


def test_who_sees_the_numbers():
    assert engine.shown_to('everyone', is_owner=False)
    assert engine.shown_to('owner', is_owner=True)
    assert not engine.shown_to('owner', is_owner=False)
    assert not engine.shown_to('engine', is_owner=True)
    assert Resource.model_validate({'key': 'mana', 'name': '마나', 'max': {'base': 3}}).visibility == 'everyone'


def test_an_old_outcome_without_visibility_is_seen_by_everyone():
    old = {'rest': {'resources': [{'resource': 'mana', 'name': '마나', 'before': 1, 'after': 3, 'max': 6}]}}

    assert visible_outcome(old, uuid.uuid4()) == old
    assert visible_outcome(None, uuid.uuid4()) is None


# --- 시트 ---


async def test_each_one_sees_the_numbers_the_rules_let_them(client: AsyncClient, me: dict, friend: dict):
    table = await start(client, me, friend)

    mine = (await client.get(table_url(table), headers=me)).json()
    theirs = (await client.get(table_url(table), headers=friend)).json()

    # 나는 내 광기를 본다. 동료는 내 마나만 본다. 비밀은 아무도 보지 않는다
    assert keys_on_sheet(mine, ME) == ['mana', 'madness']
    assert keys_on_sheet(theirs, ME) == ['mana']
    assert keys_on_sheet(mine, FRIEND) == ['mana']


# --- 결과와 이벤트 ---


async def test_a_rest_shows_hidden_changes_only_to_whom_the_rules_allow(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    table = await start(client, me, friend)
    await lower_mine(session)
    combat.load_dice(app, [4])

    await declare(client, me, table, '숨을 돌린다.', {'kind': 'rest', 'length': 'short'})
    closing = await declare(client, friend, table, '지켜본다.')

    mine = (await client.get(table_url(table, '/rounds/1'), headers=me)).json()
    assert [one['resource'] for one in my_rest(mine)['resources']] == ['mana', 'madness']
    assert [one['resource'] for one in my_rest(closing)['resources']] == ['mana']
    changed = await events_of(client, friend, table, 'resource_changed')
    # 엔진만 보는 비밀은 적지 않는다. 가진 사람만 보는 광기는 숫자 없이 적는다
    assert [event['payload'] for event in changed] == [
        {
            'round': 1,
            'user_id': str(ME),
            'character_name': '엘프',
            'resource': 'mana',
            'name': '마나',
            'before': 1,
            'after': 3,
            'max': 6,
            'source': 'rest',
            'visibility': 'everyone',
        },
        {
            'round': 1,
            'user_id': str(ME),
            'character_name': '엘프',
            'resource': 'madness',
            'name': '광기',
            'source': 'rest',
            'visibility': 'owner',
        },
    ]


# --- 서술 ---


def test_the_narration_gets_words_for_hidden_resources():
    hidden = {'resource': 'madness', 'name': '광기', 'before': 1, 'after': 3, 'max': 6, 'min': 0, 'visibility': 'owner'}
    shown = {**hidden, 'name': '마나', 'visibility': 'everyone'}
    madness = Resource.model_validate(MADNESS)

    assert describe_resource(to_shift_note(hidden)) == '광기 넉넉함'
    assert describe_resource(to_shift_note(shift_without_visibility(shown))) == '마나 1 → 3/6'
    assert describe_resource(level_note(engine.Level(resource=madness, value=0, maximum=6))) == '광기 바닥'


def shift_without_visibility(shift: dict) -> dict:
    """보이기와 최소가 없던 옛 문서."""
    return {key: value for key, value in shift.items() if key not in ('visibility', 'min')}
