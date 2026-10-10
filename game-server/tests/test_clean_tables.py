# game-server/tests/test_clean_tables.py

"""
테스트가 시작할 때 테이블을 비우는 것(tests/conftest.py 의 clean_tables)을 검증한다.

비우는 일이 틀리면 다른 테스트가 앞 테스트의 찌꺼기 위에서 돌아, 원인을 알기 어려운 실패가 난다.
보는 것은 셋이다.
  - 빠지는 테이블이 없다. 스키마의 테이블이 모두 비울 목록에 있다.
  - 순서가 맞다. 가리키는 테이블을 먼저 지운다. 반대면 외래 키가 막는다.
  - 실제로 다 비워진다. 모든 테이블에 행을 넣은 뒤 비우고 센다.
"""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.call_log import DbCallLog
from app.ai.calls import CallRecord, CallScope, Outcome
from app.ai.provider import Reasoning
from app.main import API_PREFIX
from app.memory.indexing import index_table
from tests.cleaning import clear_tables, clearing_order
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

# 마이그레이션의 기록. 모델이 아니고, 지우면 안 된다
ALEMBIC_TABLE = 'alembic_version'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


async def schema_tables(session: AsyncSession) -> set[str]:
    """
    테스트 스키마에 실제로 있는 테이블의 이름들. 마이그레이션의 기록은 뺀다.

    current_schema(): 연결의 search_path 가 가리키는 스키마다. 테스트에서는 game_test 다(tests/conftest.py).
    """
    query = text('SELECT tablename FROM pg_tables WHERE schemaname = current_schema()')
    names = set(await session.scalars(query))
    return names - {ALEMBIC_TABLE}


async def row_counts(session: AsyncSession) -> dict[str, int]:
    """비울 테이블마다 행의 수. 이름은 모델에서 온 것이라 문장에 넣어도 된다. 사용자의 입력이 아니다."""
    counts = {}
    for table in clearing_order():
        counts[table.name] = await session.scalar(text(f'SELECT count(*) FROM {table.name}'))
    return counts


async def fill_every_table(client: AsyncClient, app: FastAPI, me: dict[str, str]) -> None:
    """
    API 로 모든 테이블에 행을 넣는다. 외래 키로 이어진 사슬이 끝까지 생긴다.

    룰북, 세계관, 로어북과 항목, 시나리오(로어북을 붙이고 판을 내고 소개 페이지까지), 테이블(시작해서 시트와 라운드와
    이벤트가 생기고, 굴리고, 선언하고, 채팅한다), 보관함.
    AI 호출의 기록만은 API 로 생기지 않는다(테스트의 서술자는 모델을 부르지 않는다). 기록장으로 직접 쓴다.
    로어북 항목의 벡터는 게시한 뒤 뒤에서 생긴다. 그 작업이 끝나기를 기다린다.
    지난 라운드의 벡터는 다음 서술을 맡길 때 생긴다. 혼자 앉은 테이블이라 선언하면 라운드가 닫히고 서술된다.
    서술을 기다린 뒤 색인을 직접 돌린다.
    """
    url = API_PREFIX
    rulebook = (await client.post(f'{url}/rulebooks', json={'title': '룰북'}, headers=me)).json()
    world = (await client.post(f'{url}/worlds', json={'title': '세계'}, headers=me)).json()
    lorebook = (await client.post(f'{url}/lorebooks', json={'title': '로어북'}, headers=me)).json()
    await client.post(f'{url}/lorebooks/{lorebook["id"]}/entries', json={'name': '항목'}, headers=me)
    body = {
        'title': '추격전',
        'rulebook_id': rulebook['id'],
        'world_id': world['id'],
        'lorebook_ids': [lorebook['id']],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': SHEET,
        'character_modes': ['custom', 'rolled'],
        'player_made_hp': {'base': 10, 'cap': 12},
    }
    scenario = (await client.post(f'{url}/scenarios', json=body, headers=me)).json()
    await client.post(f'{url}/scenarios/{scenario["id"]}/versions', json={}, headers=me)
    await app.state.jobs.drain()
    await client.patch(f'{url}/scenarios/{scenario["id"]}/listing', json={'tagline': '달린다'}, headers=me)

    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1}
    table = (await client.post(f'{url}/tables', json=body, headers=me)).json()
    table_url = f'{url}/tables/{table["id"]}'
    await client.post(f'{table_url}/character/roll', headers=me)
    await client.put(f'{table_url}/character', json={'name': '엘프'}, headers=me)
    await client.post(f'{table_url}/start', headers=me)
    await client.put(f'{table_url}/rounds/current/declaration', json={'content': '달린다.'}, headers=me)
    await app.state.jobs.drain()
    await index_table(app.state.session_factory, app.state.embedder, uuid.UUID(table['id']))
    await client.post(f'{table_url}/messages', json={'content': '안녕'}, headers=me)
    await client.post(f'{url}/personas', json={'name': '드워프'}, headers=me)

    record = CallRecord(
        scope=CallScope(purpose='narration', table_id=uuid.UUID(table['id']), round_number=1, host_id=ME),
        provider='fake',
        model='fake',
        prompt_version='narration-3',
        reasoning=Reasoning.NONE,
        outcome=Outcome.OK,
        latency_ms=0,
        text='바람이 분다.',
    )
    await DbCallLog(app.state.session_factory).write(record)


def test_tables_that_point_are_cleared_before_the_tables_they_point_to():
    order = [table.name for table in clearing_order()]

    for position, table in enumerate(clearing_order()):
        for key in table.foreign_keys:
            # 가리켜지는 테이블은 더 뒤에 있어야 한다
            assert order.index(key.column.table.name) > position, (table.name, key.column.table.name)


async def test_no_table_of_the_schema_is_left_out(session: AsyncSession):
    # 마이그레이션으로 만든 테이블이 모델에 없으면 비울 목록에서 빠진다. 그 찌꺼기가 다음 테스트로 넘어간다
    assert await schema_tables(session) == {table.name for table in clearing_order()}


async def test_cleaning_empties_every_table(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    await fill_every_table(client, app, me)
    before = await row_counts(session)
    assert [name for name, count in before.items() if count == 0] == []

    await clear_tables(app.state.engine)

    assert set((await row_counts(session)).values()) == {0}
