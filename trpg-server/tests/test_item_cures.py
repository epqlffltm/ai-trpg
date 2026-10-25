# trpg-server/tests/test_item_cures.py

"""
부상을 푸는 소모품(#277, 해독제)을 검증한다.

srd5 템플릿의 부상: 중독(poisoned), 기절(stunned), 실명(blinded)은 짧은 것, 팔 골절(broken_arm)은 오래 가는 것이다.
팔 골절이 나으면 후유증 표(d20)를 굴린다. 1~5 는 굽은 팔이다. 한쪽 눈 잃음(lost_eye)은 결손이라 풀지 못한다.

넷을 본다.
  - 시나리오: 풀기는 효과 목록(#800)의 cure 다. 소모품에만, 같은 부상 두 번 없이, 정한 수까지 적는다. 아니면 422 다.
  - 게시: 푸는 부상은 룰북의 부상이고 결손이 아니어야 한다(item_cure_invalid). 형식 58 의 옛 판은 아무것도 풀지 않는다.
  - 닫힐 때: 쓰면 대상이 입은 그 부상들이 끝난다. 오래 가는 것이 나으면 후유증 표를 굴린다.
    그 부상이 없어도 물건은 쓴다. 다른 부상은 그대로다.
  - 기록과 서술: 쓴 것의 이벤트에 푼 것(cured)이 적히고, 푼 부상마다 부상이 끝난 이벤트(cured)가 잇는다.

부상은 싸워서 입히지 않고 DB 에 바로 적는다(wound). 푸는 것만 보려는 것이다.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.schemas import ItemRule
from app.assets.scenarios.snapshot import SNAPSHOT_FORMAT, read_snapshot
from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_57
from app.engine.item_effects import EFFECT_MAX_CURES
from app.rounds.move_lines import describe_item_action
from app.rounds.narrator import ItemActionNote
from app.tables.models import TableInjury, TableSheet
from tests import test_item_actions as actions
from tests.sheets import SHEET
from tests.test_npc_sheets import published, refused

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = actions.ME
FRIEND = actions.FRIEND
STRANGER = actions.STRANGER
SCENARIOS_URL = actions.SCENARIOS_URL
RULEBOOKS_URL = actions.RULEBOOKS_URL
LOREBOOKS_URL = actions.LOREBOOKS_URL
TABLES_URL = actions.TABLES_URL

me = actions.me
friend = actions.friend
post = actions.post
table_url = actions.table_url
use = actions.use
declare = actions.declare
declared = actions.declared
held = actions.held
read_table = actions.read_table
first_round = actions.first_round
events_of = actions.events_of
load_dice = actions.load_dice

# 팔 골절의 후유증 표(d20)의 눈. 1~5 는 굽은 팔이다
CROOKED = 3
CLEAN = 10
# 짧은 부상이 풀릴 라운드. 첫 라운드가 닫힐 때 저절로 풀리지 않게 멀리 둔다
LATER = 5
# 팔 골절이 저절로 낫는 시각. 첫 라운드에 닿지 않게 멀리 둔다
FAR = 100 * 24 * 60


@pytest.fixture
async def lore(client: AsyncClient, me: dict[str, str]) -> dict:
    """물건 넷(해독제, 부목, 만병통치약, 밧줄)."""
    lorebook = await post(client, LOREBOOKS_URL, me, title='약방의 물건들')
    url = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'

    async def entry(name: str) -> dict:
        return await post(client, url, me, name=name, keywords=[], content=f'{name}의 설명', kind='item')

    return {
        'lorebook': lorebook,
        'antidote': await entry('해독제'),
        'splint': await entry('부목'),
        'panacea': await entry('만병통치약'),
        'rope': await entry('밧줄'),
    }


def cures(*keys: str) -> dict:
    """그 부상들을 푸는 효과(#800)."""
    return {'kind': 'cure', 'injuries': list(keys)}


HEAL_LIGHT = {'kind': 'heal', 'magnitude': 'light'}


def the_items(lore: dict) -> list[dict]:
    """해독제는 중독을, 부목은 팔 골절을 푼다. 만병통치약은 가볍게 회복하고 중독과 기절을 푼다."""
    return [
        {'entry_id': lore['antidote']['id'], 'kind': 'consumable', 'effects': [cures('poisoned')]},
        {'entry_id': lore['splint']['id'], 'kind': 'consumable', 'effects': [cures('broken_arm')]},
        {
            'entry_id': lore['panacea']['id'],
            'kind': 'consumable',
            'effects': [HEAL_LIGHT, cures('poisoned', 'stunned')],
        },
        {'entry_id': lore['rope']['id'], 'kind': 'gear'},
    ]


def cured_keys(effects: list) -> list[str]:
    """효과 목록에서 푸는 부상들."""
    return [key for effect in effects if effect['kind'] == 'cure' for key in effect['injuries']]


async def scenario_with(client: AsyncClient, me: dict, lore: dict, items: list[dict]) -> dict:
    """그 아이템 규칙을 적은 시나리오. 프리젠 약사가 해독제 둘, 부목 하나, 만병통치약 하나를 가진다."""
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    pregen_items = [
        {'entry_id': lore['antidote']['id'], 'count': 2},
        {'entry_id': lore['splint']['id'], 'count': 1},
        {'entry_id': lore['panacea']['id'], 'count': 1},
    ]
    body = {
        'title': '약방의 모험',
        'rulebook_id': rulebook['id'],
        'openings': ['약방이다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'lorebook_ids': [lore['lorebook']['id']],
        'items': items,
        'pregens': [{'name': '약사', 'sheet': SHEET, 'items': pregen_items}],
    }
    return await post(client, SCENARIOS_URL, me, **body)


@pytest.fixture
async def table(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """둘이 앉아 시작한 테이블. 나는 기사(소지품 없음), 친구는 약사다. 첫 라운드가 열려 있다."""
    scenario = await scenario_with(client, me, lore, the_items(lore))
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    created = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': created['invite_code']}, headers=friend)
    await client.put(table_url(created, '/character'), json={'name': '기사'}, headers=me)
    await client.put(table_url(created, '/character'), json={'pregen_index': 0}, headers=friend)
    started = await client.post(table_url(created, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return started.json()


async def wound(session: AsyncSession, table: dict, user_id: uuid.UUID, key: str, ended: bool = False) -> None:
    """
    그 사람이 1 라운드에 그 부상을 입은 것으로 DB 에 바로 적는다. 짧은 것과 오래 가는 것은 멀리 가서야 끝난다.

    ended 면 이미 끝난(풀렸거나 나은) 부상이다. 기록에만 남아 있다.
    """
    table_id = uuid.UUID(table['id'])
    sheet_id = await session.scalar(
        select(TableSheet.id).where(TableSheet.table_id == table_id, TableSheet.user_id == user_id)
    )
    lasting = key == 'broken_arm'
    row = TableInjury(
        table_id=table_id,
        sheet_id=sheet_id,
        injury=key,
        source='injury_table',
        round_number=1,
        ends_after_round=None if lasting else LATER,
        heals_at=FAR if lasting else None,
        ended_at=datetime.now(UTC) if ended else None,
    )
    session.add(row)
    await session.commit()


def worn(table: dict, user_id: uuid.UUID) -> list[str]:
    """그 사람이 지금 입고 있는 부상들의 이름표."""
    member = next(member for member in table['members'] if member['user_id'] == str(user_id))
    return [injury['injury'] for injury in member['sheet']['injuries']]


async def item_use(client: AsyncClient, headers: dict, table: dict, user_id: uuid.UUID) -> dict:
    """첫 라운드의 그 사람의 선언에 적힌 물건을 쓴 결과."""
    declarations = (await first_round(client, headers, table))['declarations']
    return next(d for d in declarations if d['user_id'] == str(user_id))['outcome']['item_use']


async def play(client: AsyncClient, me: dict, friend: dict, table: dict, action: dict, narrated) -> None:
    """약사가 그 행동을 하고 기사는 주위를 살핀다. 라운드가 닫히고 서술이 끝날 때까지 기다린다."""
    await declared(client, friend, table, action)
    await declared(client, me, table)
    await narrated()


# --- 시나리오: 모양 ---


async def test_cures_are_saved_and_read_back(client: AsyncClient, me: dict, lore: dict):
    scenario = await scenario_with(client, me, lore, the_items(lore))

    read = (await client.get(f'{SCENARIOS_URL}/{scenario["id"]}', headers=me)).json()

    assert [cured_keys(rule['effects']) for rule in read['items']] == [
        ['poisoned'],
        ['broken_arm'],
        ['poisoned', 'stunned'],
        [],
    ]


@pytest.mark.parametrize(
    'fields',
    [
        {'kind': 'gear', 'effects': [cures('poisoned')]},
        {'kind': 'consumable', 'effects': [cures('poisoned', 'poisoned')]},
        {'kind': 'consumable', 'effects': [cures(*[f'injury_{n}' for n in range(EFFECT_MAX_CURES + 1)])]},
        {'kind': 'consumable', 'effects': [cures('Not A Key')]},
        {'kind': 'consumable', 'effects': [cures()]},
        {'kind': 'consumable', 'cures': ['poisoned']},
    ],
    ids=['gear', 'twice', 'too-many', 'bad-key', 'none', 'old-field'],
)
def test_rejects_misshaped_cures(fields: dict):
    with pytest.raises(ValidationError):
        ItemRule.model_validate({'entry_id': actions.NO_SUCH_ID, **fields})


def test_up_to_the_most_cures_fit():
    keys = [f'injury_{n}' for n in range(EFFECT_MAX_CURES)]

    rule = ItemRule.model_validate({'entry_id': actions.NO_SUCH_ID, 'kind': 'consumable', 'effects': [cures(*keys)]})

    assert rule.effects[0].injuries == keys


async def test_a_gear_with_cures_is_refused_by_the_api(client: AsyncClient, me: dict, lore: dict):
    items = [{'entry_id': lore['rope']['id'], 'kind': 'gear', 'effects': [cures('poisoned')]}]
    body = {'title': '약방의 모험', 'items': items}

    response = await client.post(SCENARIOS_URL, json=actions.asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text


# --- 게시 ---


async def test_cures_are_frozen_into_the_version(client: AsyncClient, me: dict, lore: dict):
    scenario = await scenario_with(client, me, lore, the_items(lore))

    document = await published(client, me, scenario)

    assert document['format'] == SNAPSHOT_FORMAT >= 62
    rules = read_snapshot(document).items
    effects = [[effect.model_dump(mode='json') for effect in rule.effects] for rule in rules]
    assert [cured_keys(one) for one in effects] == [['poisoned'], ['broken_arm'], ['poisoned', 'stunned'], []]


@pytest.mark.parametrize('key', ['no_such_injury', 'lost_eye'], ids=['unknown', 'permanent'])
async def test_a_cure_must_be_a_curable_injury_of_the_rulebook(client: AsyncClient, me: dict, lore: dict, key: str):
    items = [{'entry_id': lore['antidote']['id'], 'kind': 'consumable', 'effects': [cures('poisoned', key)]}]
    scenario = await scenario_with(client, me, lore, items)

    assert 'item_cure_invalid' in await refused(client, me, scenario)


def test_an_old_snapshot_reads_as_curing_nothing():
    document = {'format': 57, 'items': [{'entry_id': actions.NO_SUCH_ID, 'kind': 'consumable'}]}

    upgraded = upgrade_from_57(document)

    assert (upgraded['format'], upgraded['items'][0]['cures']) == (58, [])
    assert 'cures' not in document['items'][0]
    assert UPGRADES[57] is upgrade_from_57


async def test_the_table_lists_what_each_thing_cures(client: AsyncClient, me: dict, table: dict):
    read = await read_table(client, me, table)

    assert [cured_keys(item['effects']) for item in read['items']] == [
        ['poisoned'],
        ['broken_arm'],
        ['poisoned', 'stunned'],
        [],
    ]


# --- 받기 ---


async def test_a_cure_is_aimed_at_oneself_by_default(client: AsyncClient, friend: dict, lore: dict, table: dict):
    await declared(client, friend, table, use(lore['antidote']))

    mine = next(d for d in (await first_round(client, friend, table))['declarations'] if d['user_id'] == str(FRIEND))
    assert mine['action'] == {
        'kind': 'use',
        'item': lore['antidote']['id'],
        'target': str(FRIEND),
        'npc': None,
        'monster': None,
        'lethal': False,
    }


async def test_a_cure_needs_someone_seated(client: AsyncClient, friend: dict, lore: dict, table: dict):
    response = await declare(client, friend, table, use(lore['antidote'], STRANGER))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'target' in response.text


# --- 닫힐 때 ---


async def test_an_antidote_cures_its_user(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await wound(session, table, FRIEND, 'poisoned')

    await play(client, me, friend, table, use(lore['antidote']), narrated)

    after = await read_table(client, me, table)
    assert worn(after, FRIEND) == []
    assert ('해독제', 1) in held(after, FRIEND)
    used = await item_use(client, me, table, FRIEND)
    assert (used['used'], used['cured']) == (True, [{'injury': 'poisoned', 'name': '중독'}])


async def test_only_the_injuries_it_cures_end(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await wound(session, table, ME, 'stunned')
    await wound(session, table, ME, 'poisoned')
    await wound(session, table, ME, 'broken_arm')

    await play(client, me, friend, table, use(lore['antidote'], ME), narrated)

    after = await read_table(client, me, table)
    assert worn(after, ME) == ['stunned', 'broken_arm']
    assert [one['injury'] for one in (await item_use(client, me, table, FRIEND))['cured']] == ['poisoned']


async def test_one_thing_may_cure_several_injuries(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await wound(session, table, ME, 'stunned')
    await wound(session, table, ME, 'poisoned')

    await play(client, me, friend, table, use(lore['panacea'], ME), narrated)

    after = await read_table(client, me, table)
    assert worn(after, ME) == []
    assert [one['name'] for one in (await item_use(client, me, table, FRIEND))['cured']] == ['기절', '중독']


async def test_a_lasting_injury_heals_and_rolls_its_aftermath(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, ME, 'broken_arm')
    load_dice(app, [CROOKED])

    await play(client, me, friend, table, use(lore['splint'], ME), narrated)

    after = await read_table(client, me, table)
    assert worn(after, ME) == ['crooked_arm']
    assert held(after, FRIEND) == [('해독제', 2), ('만병통치약', 1)]


async def test_a_clean_heal_leaves_nothing(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, ME, 'broken_arm')
    load_dice(app, [CLEAN])

    await play(client, me, friend, table, use(lore['splint'], ME), narrated)

    assert worn(await read_table(client, me, table), ME) == []
    assert await events_of(client, me, table, 'injury_gained') == []


async def test_it_is_used_up_even_when_there_is_nothing_to_cure(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await wound(session, table, FRIEND, 'blinded')

    await play(client, me, friend, table, use(lore['antidote']), narrated)

    after = await read_table(client, me, table)
    assert (worn(after, FRIEND), ('해독제', 1) in held(after, FRIEND)) == (['blinded'], True)
    used = await item_use(client, me, table, FRIEND)
    assert (used['used'], used['cured']) == (True, [])
    assert await events_of(client, me, table, 'injury_ended') == []


async def test_an_injury_that_already_ended_is_not_cured_again(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await wound(session, table, FRIEND, 'poisoned', ended=True)

    await play(client, me, friend, table, use(lore['antidote']), narrated)

    assert (await item_use(client, me, table, FRIEND))['cured'] == []
    assert await events_of(client, me, table, 'injury_ended') == []


async def test_what_was_cured_does_not_end_again_later(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await wound(session, table, FRIEND, 'poisoned')

    await play(client, me, friend, table, use(lore['antidote']), narrated)

    rows = list(await session.scalars(select(TableInjury).execution_options(populate_existing=True)))
    assert [(row.injury, row.ended_at is not None) for row in rows] == [('poisoned', True)]
    (ended,) = await events_of(client, me, table, 'injury_ended')
    assert ended['payload']['reason'] == 'cured'


# --- 기록과 서술 ---


async def test_curing_is_recorded_after_the_use(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, table: dict, session, narrated
):
    await wound(session, table, ME, 'broken_arm')
    load_dice(app, [CROOKED])

    await play(client, me, friend, table, use(lore['splint'], ME), narrated)

    (used,) = await events_of(client, me, table, 'item_used')
    (ended,) = await events_of(client, me, table, 'injury_ended')
    (gained,) = await events_of(client, me, table, 'injury_gained')
    assert used['payload']['cured'] == [{'injury': 'broken_arm', 'name': '팔 골절'}]
    assert ended['caused_by_sequence'] == used['sequence']
    assert ended['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '기사',
        'injury': 'broken_arm',
        'reason': 'cured',
    }
    assert gained['caused_by_sequence'] == ended['sequence']
    assert (gained['payload']['injury'], gained['payload']['source']) == ('crooked_arm', 'aftermath')


async def test_the_narrator_hears_what_was_cured(
    client: AsyncClient, me: dict, friend: dict, lore: dict, table: dict, session: AsyncSession, narrated
):
    await wound(session, table, ME, 'poisoned')

    await play(client, me, friend, table, use(lore['antidote'], ME), narrated)

    second = (await client.get(table_url(table, '/rounds/current'), headers=me)).json()
    assert '약사: 주위를 살핀다. (쓴 물건: 해독제 → 기사) [풀린 부상: 중독]' in second['scene']


@pytest.mark.parametrize(
    ('note', 'line'),
    [
        (
            ItemActionNote(kind='use', name='해독제', count=1, done=True, cured=['중독']),
            '(쓴 물건: 해독제) [풀린 부상: 중독]',
        ),
        (
            ItemActionNote(kind='use', name='만병통치약', count=1, done=True, target='영애', cured=['기절', '중독']),
            '(쓴 물건: 만병통치약 → 영애) [풀린 부상: 기절, 중독]',
        ),
        (ItemActionNote(kind='use', name='해독제', count=1, done=True), '(쓴 물건: 해독제)'),
    ],
    ids=['one', 'several-to-another', 'nothing'],
)
def test_the_line_names_what_was_cured(note: ItemActionNote, line: str):
    assert describe_item_action(note) == line
