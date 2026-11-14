# trpg-server/tests/test_round_revert.py

"""
방장이 바로 앞 라운드를 되돌린다(#288). app/rounds/reverting.py, app/rounds/snapshots.py.

보는 것
  - 되돌리면 닫기 직전의 게임 상태로 돌아가고, 같은 번호의 라운드가 그때의 장면과 선언으로 다시 열린다
  - 다시 닫으면 주사위를 새로 굴리고, 다음 라운드의 서술 값의 이름표가 앞서 지은 것과 겹치지 않는다
  - 되돌린 라운드는 기록으로 남지만 목록과 번호로 찾기, 기록 내려받기, 기억에 들지 않는다
  - 방장만, 바로 앞 라운드 하나만, 다음 라운드가 열린 뒤에 쪽지 말고 아무 일도 없었을 때만 된다
  - 테이블에 딸린 표는 모두 찍거나 왜 빼는지 적혀 있다(빠뜨리면 반쯤 되돌아간 상태가 남는다)
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import ForeignKeyConstraint, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.charges import reference_for, renewed_reference
from app.billing.models import NarrationCharge
from app.calendar.models import TableClock
from app.core.database import Base
from app.memory.models import RoundMemory
from app.rounds import snapshots
from app.rounds.models import Round, RoundSnapshot
from app.rounds.state import required
from app.tables.models import TableSheet
from tests.test_rounds_api import (
    FRIEND,
    ME,
    MY_ACTION,
    OPENINGS,
    TABLES_URL,
    bearer,
    current,
    declare,
    rounds_url,
    start_duo,
    start_solo,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

ANOTHER_ACTION = '브레이크를 밟는다.'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """방장의 머리말. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """함께 앉는 사람의 머리말. 캐릭터는 '영애'다."""
    return bearer(signing_key, FRIEND)


def revert_url(table: dict) -> str:
    return rounds_url(table, '/current/revert')


async def revert(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """앞 라운드를 되돌리고 다시 연 라운드를 돌려준다."""
    response = await client.post(revert_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def play_solo_round(client: AsyncClient, me: dict[str, str], table: dict, narrated, content: str = MY_ACTION):
    """혼자 앉은 테이블에서 선언 하나로 라운드를 닫고 서술이 끝나기를 기다린다."""
    await declare(client, me, table, content)
    await narrated()


async def events_of(client: AsyncClient, headers: dict[str, str], table: dict) -> list[dict]:
    response = await client.get(f'{TABLES_URL}/{table["id"]}/events', params={'limit': 100}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


async def my_sheet(session: AsyncSession, table: dict) -> TableSheet:
    query = select(TableSheet).where(TableSheet.table_id == uuid.UUID(table['id']), TableSheet.user_id == ME)
    return (await session.scalars(query.execution_options(populate_existing=True))).one()


async def clock_minutes(session: AsyncSession, table: dict) -> int:
    query = select(TableClock.minutes).where(TableClock.table_id == uuid.UUID(table['id']))
    return required(await session.scalar(query.execution_options(populate_existing=True)), 'clock')


async def damage_me(session: AsyncSession, table: dict, hp: int, money: int) -> None:
    """닫기가 바꾼 것처럼 내 캐릭터의 HP 와 돈을 바꾼다(찍은 뒤의 변화)."""
    await session.execute(
        update(TableSheet)
        .where(TableSheet.table_id == uuid.UUID(table['id']), TableSheet.user_id == ME)
        .values(hp=hp, money=money)
    )
    await session.commit()


# --- 되돌리기 ---


async def test_the_host_reverts_the_last_round(client: AsyncClient, me: dict, session: AsyncSession, narrated):
    table = await start_solo(client, me)
    before = await my_sheet(session, table)
    minutes = await clock_minutes(session, table)
    await play_solo_round(client, me, table, narrated)
    await damage_me(session, table, hp=3, money=before.money + 50)
    assert await clock_minutes(session, table) > minutes  # 2 라운드가 열리며 시간이 흘렀다

    reopened = await revert(client, me, table)

    # 같은 번호, 같은 장면, 옮겨 적힌 선언으로 다시 열린다. 결과는 아직 없다
    assert (reopened['number'], reopened['status'], reopened['scene']) == (1, 'open', OPENINGS[0])
    assert [(d['content'], d['outcome']) for d in reopened['declarations']] == [(MY_ACTION, None)]
    # 게임의 상태가 닫기 직전으로 돌아갔다. 시각도 돌아갔다
    sheet = await my_sheet(session, table)
    assert (sheet.hp, sheet.money) == (before.hp, before.money)
    assert await clock_minutes(session, table) == minutes


async def test_the_reverted_round_stays_as_a_record_but_out_of_sight(
    client: AsyncClient, me: dict, session: AsyncSession, narrated
):
    table = await start_solo(client, me)
    await play_solo_round(client, me, table, narrated)

    await revert(client, me, table)

    rows = (await session.scalars(select(Round).where(Round.table_id == uuid.UUID(table['id'])))).all()
    assert sorted((row.number, row.reverted_at is not None) for row in rows) == [(1, False), (1, True)]
    listed = (await client.get(rounds_url(table), headers=me)).json()
    assert [item['number'] for item in listed['items']] == [1]
    assert (await client.get(rounds_url(table, '/2'), headers=me)).status_code == status.HTTP_404_NOT_FOUND


async def test_closing_again_rolls_anew_and_opens_the_next_round(
    client: AsyncClient, me: dict, session: AsyncSession, narrated
):
    table = await start_solo(client, me)
    await play_solo_round(client, me, table, narrated)
    await revert(client, me, table)

    # 선언을 고치면 모두 낸 것이라 다시 닫힌다
    await play_solo_round(client, me, table, narrated, ANOTHER_ACTION)

    opened = await current(client, me, table)
    assert (opened['number'], opened['scene']) == (2, f'[1 라운드의 결과]\n엘프: {ANOTHER_ACTION}')
    # 새 2 라운드의 서술 값의 이름표는 되돌린 수가 붙어, 처음 2 라운드를 열 때 지은 것과 겹치지 않는다
    references = set(await session.scalars(select(NarrationCharge.reference)))
    assert reference_for(uuid.UUID(table['id']), 2, ME) in references
    assert reference_for(uuid.UUID(table['id']), 2, ME, reverts=1) in references


async def test_the_reverted_closing_is_marked_by_its_group(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me)
    await play_solo_round(client, me, table, narrated)

    await revert(client, me, table)

    events = await events_of(client, me, table)
    closed = next(event for event in events if event['type'] == 'round_closed')
    reverted = events[-1]
    assert (reverted['type'], reverted['actor_id']) == ('round_reverted', str(ME))
    assert reverted['payload']['number'] == 1
    assert reverted['payload']['group'] == closed['action_group_id']
    # 닫힘과 함께 적힌 서술과 다음 라운드의 열림도 그 묶음이다
    grouped = {event['type'] for event in events if event['action_group_id'] == closed['action_group_id']}
    assert {'round_closed', 'gm_narration', 'round_opened'} <= grouped


async def test_the_transcript_leaves_out_the_reverted_closing(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me)
    await play_solo_round(client, me, table, narrated)
    await revert(client, me, table)
    await play_solo_round(client, me, table, narrated, ANOTHER_ACTION)

    text = (await client.get(f'{TABLES_URL}/{table["id"]}/transcript', headers=me)).text

    assert '방장이 1 라운드를 되돌림' in text
    assert f'> {ANOTHER_ACTION}' in text
    assert f'> {MY_ACTION}' not in text
    assert f'엘프: {MY_ACTION}' not in text  # 되돌린 서술


async def test_the_memories_from_the_reverted_round_are_dropped(
    client: AsyncClient, me: dict, session: AsyncSession, narrated
):
    table = await start_solo(client, me)
    await play_solo_round(client, me, table, narrated)
    await play_solo_round(client, me, table, narrated, ANOTHER_ACTION)
    table_id = uuid.UUID(table['id'])
    for number in (1, 2):
        session.add(RoundMemory(table_id=table_id, model='test-embed', round_number=number, embedding=[0.1, 0.2]))
    await session.commit()

    await revert(client, me, table)

    query = select(RoundMemory.round_number).where(RoundMemory.table_id == table_id, RoundMemory.model == 'test-embed')
    assert list(await session.scalars(query)) == [1]


# --- 되돌릴 수 없는 때 ---


async def test_only_the_host_reverts(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await client.post(rounds_url(table, '/current/close'), headers=me)
    await narrated()

    response = await client.post(revert_url(table), headers=friend)

    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_the_first_round_has_nothing_to_revert(client: AsyncClient, me: dict):
    table = await start_solo(client, me)

    response = await client.post(revert_url(table), headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'nothing_to_revert'


async def test_only_one_round_back(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me)
    await play_solo_round(client, me, table, narrated)
    await play_solo_round(client, me, table, narrated, ANOTHER_ACTION)
    await revert(client, me, table)

    # 다시 연 2 라운드의 앞(1 라운드)은 찍어 둔 것이 없다. 찍은 것은 2 라운드의 닫기 직전 하나다
    response = await client.post(revert_url(table), headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'nothing_to_revert'


async def test_a_declaration_in_the_new_round_blocks_reverting(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await client.post(rounds_url(table, '/current/close'), headers=me)
    await narrated()
    await declare(client, friend, table, '드워프에게 손을 흔든다.')

    response = await client.post(revert_url(table), headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'revert_blocked'


async def test_someone_leaving_blocks_reverting(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await client.post(rounds_url(table, '/current/close'), headers=me)
    await narrated()
    left = await client.delete(f'{TABLES_URL}/{table["id"]}/members/me', headers=friend)
    assert left.status_code == status.HTTP_204_NO_CONTENT, left.text

    response = await client.post(revert_url(table), headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'revert_blocked'


async def test_a_whisper_does_not_block_reverting(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await client.post(rounds_url(table, '/current/close'), headers=me)
    await narrated()
    body = {'recipient_id': str(FRIEND), 'content': '몰래 하자'}
    sent = await client.post(f'{TABLES_URL}/{table["id"]}/whispers', json=body, headers=me)
    assert sent.status_code == status.HTTP_201_CREATED, sent.text

    reopened = await revert(client, me, table)

    assert reopened['number'] == 1


async def test_a_snapshot_of_another_shape_is_not_used(client: AsyncClient, me: dict, session: AsyncSession, narrated):
    table = await start_solo(client, me)
    await play_solo_round(client, me, table, narrated)
    snapshot = await session.get_one(RoundSnapshot, uuid.UUID(table['id']))
    state = {**snapshot.state, 'tables': {**snapshot.state['tables']}}
    state['tables']['table_sheets'] = {**state['tables']['table_sheets'], 'columns': ['id']}
    snapshot.state = state
    await session.commit()

    response = await client.post(revert_url(table), headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'nothing_to_revert'


# --- 무엇을 찍는가 ---


def belongs_to_a_table(name: str, tables: dict) -> bool:
    """이 표의 행이 테이블 하나에 딸리는가. game_tables 를 곧장, 또는 그런 표를 거쳐 가리킨다."""
    seen: set[str] = set()
    pending = [name]
    while pending:
        current_name = pending.pop()
        if current_name == 'game_tables':
            return True
        if current_name in seen:
            continue
        seen.add(current_name)
        for constraint in tables[current_name].constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                pending.append(constraint.referred_table.name)
    return False


def test_every_table_of_a_game_table_is_snapshotted_or_excused():
    tables = Base.metadata.tables
    owned = {name for name in tables if belongs_to_a_table(name, tables)}

    assert owned == set(snapshots.STATE_TABLES) | set(snapshots.EXCLUDED)
    assert not set(snapshots.STATE_TABLES) & set(snapshots.EXCLUDED)


def test_snapshotted_tables_are_listed_parents_first():
    order = {name: index for index, name in enumerate(snapshots.STATE_TABLES)}

    for name in snapshots.STATE_TABLES:
        for constraint in Base.metadata.tables[name].constraints:
            if isinstance(constraint, ForeignKeyConstraint) and constraint.referred_table.name in order:
                assert order[constraint.referred_table.name] < order[name], (name, constraint.referred_table.name)


def test_every_snapshotted_table_can_be_scoped_to_one_table():
    for table in snapshots.state_tables():
        assert 'table_id' in table.columns or table.name in snapshots.PARENT_SCOPES, table.name


@pytest.mark.parametrize(
    ('value', 'kind'),
    [(uuid.UUID('11111111-2222-4333-8444-555555555555'), 'id'), (datetime(2026, 11, 3, 9, 30, tzinfo=UTC), 'at')],
)
def test_values_come_back_as_they_were(value, kind):
    column = Base.metadata.tables['table_traps'].columns['id' if kind == 'id' else 'created_at']

    assert snapshots.decode_value(column, snapshots.encode_value(column, value)) == value


# --- 서술 값의 이름표 ---


def test_a_table_never_reverted_names_holds_as_before():
    table_id = uuid.UUID('22222222-2222-4333-8444-555555555555')

    assert reference_for(table_id, 3, ME) == f'narration:{table_id}:3:{ME}'
    assert reference_for(table_id, 3, ME, reverts=2) == f'narration:{table_id}:3:{ME}:v2'


def test_a_renewed_hold_keeps_its_first_name():
    first = f'narration:abc:3:{ME}:v1'

    assert renewed_reference(first, 1) == f'{first}:r1'
    assert renewed_reference(f'{first}:r1', 2) == f'{first}:r2'
