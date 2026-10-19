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
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.call_log import DbCallLog
from app.ai.calls import CallRecord, CallScope, Outcome
from app.ai.provider import Reasoning
from app.catalog import service as catalog
from app.catalog.models import Grade, Provider
from app.catalog.schemas import CostCreate, ModelCreate, SnapshotSwitch
from app.engine.dice import ScriptedDice
from app.main import API_PREFIX
from app.memory.indexing import index_table
from app.notifications import outbox
from app.operators.models import ActionKind, PublishingBan, ReadKind, ScenarioSanction
from app.operators.sanctions import build_action
from app.operators.service import build_read
from app.tables.models import (
    GameTable,
    QuestStatus,
    TableFoundRoute,
    TableItem,
    TableMonster,
    TableMonsterItem,
    TablePlaceItem,
    TableQuest,
    TableSheet,
    TableVisit,
)
from app.whispers.models import Whisper
from tests.cleaning import clear_tables, clearing_order
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
# 쪽지를 받는 사람. 테이블에 앉지 않는다(DB 는 자리를 묻지 않는다)
OTHER = uuid.UUID('22222222-2222-4333-8444-555555555555')

# 마이그레이션의 기록. 모델이 아니고, 지우면 안 된다
ALEMBIC_TABLE = 'alembic_version'

# 모델 목록에 넣는 모델 하나와 그 원가. 서버 곁의 모델이다
CATALOG_MODEL = ModelCreate(
    slug='gemma',
    provider=Provider.LOCAL,
    api_model_id='gemma4:26b',
    display_name='Gemma',
    vendor='google',
    grade=Grade.BASIC,
    token_limit_field='max_tokens',
)
CATALOG_COST = CostCreate(input_per_mtok=0, output_per_mtok=0, effective_from='2026-10-17', checked_on='2026-10-17')


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

    룰북, 세계관, 로어북과 항목, 몬스터 도감과 몬스터, 시나리오(로어북과 도감을 붙이고 판을 내고 소개 페이지까지),
    테이블(시작해서 시트와 NPC 의 상태와 라운드와 이벤트가 생기고, 굴리고, 선언해서 다치고, 채팅한다), 보관함.
    AI 호출의 기록만은 API 로 생기지 않는다(테스트의 서술자는 모델을 부르지 않는다). 기록장으로 직접 쓴다.
    쪽지도 직접 넣는다. 받을 사람이 있어야 하는데 혼자 앉은 테이블이다.
    소지품도 직접 넣는다. 판에 물건이 있어야 하는데, 물건 항목을 더하면 위의 판과 서술이 달라진다.
    퀘스트도 같은 까닭으로 직접 넣는다(사건 항목). 서 본 곳과 찾은 길, 장소에 남은 물건도 같다(장소 항목).
    몬스터의 상태도 같다. 조우를 적으려면 장소 항목과 시작 장소가 있어야 한다.
    모델 목록과 원가, 날짜판을 바꾼 기록도 직접 넣는다. API 가 없고 관리 명령(scripts/models.py)으로만 생긴다.
    발송함도 직접 넣는다. 알림은 모델이 은퇴할 때만 생긴다.
    로어북 항목의 벡터는 게시한 뒤 뒤에서 생긴다. 그 작업이 끝나기를 기다린다.
    지난 라운드의 벡터는 다음 서술을 맡길 때 생긴다. 혼자 앉은 테이블이라 선언하면 라운드가 닫히고 서술된다.
    서술을 기다린 뒤 색인을 직접 돌린다.
    """
    url = API_PREFIX
    rulebook = (await client.post(f'{url}/rulebooks', json={'title': '룰북'}, headers=me)).json()
    world = (await client.post(f'{url}/worlds', json={'title': '세계'}, headers=me)).json()
    lorebook = (await client.post(f'{url}/lorebooks', json={'title': '로어북'}, headers=me)).json()
    # 인물 항목이라야 테이블을 시작할 때 NPC 의 상태가 생긴다
    entry = {'name': '항목', 'kind': 'person'}
    await client.post(f'{url}/lorebooks/{lorebook["id"]}/entries', json=entry, headers=me)
    bestiary = (await client.post(f'{url}/bestiaries', json={'title': '도감'}, headers=me)).json()
    monster_url = f'{url}/bestiaries/{bestiary["id"]}/monsters'
    monster = (await client.post(monster_url, json={'name': '몬스터'}, headers=me)).json()
    body = {
        'title': '추격전',
        'rulebook_id': rulebook['id'],
        'world_id': world['id'],
        'lorebook_ids': [lorebook['id']],
        'bestiary_ids': [bestiary['id']],
        'monster_sheets': [{'monster_id': monster['id'], 'sheet': SHEET}],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': SHEET,
        'default_npc_sheet': SHEET,
        'character_modes': ['custom', 'rolled'],
        'player_made_hp': {'base': 10, 'cap': 12},
    }
    scenario = (await client.post(f'{url}/scenarios', json=with_model(body), headers=me)).json()
    await client.post(f'{url}/scenarios/{scenario["id"]}/versions', json={}, headers=me)
    await app.state.jobs.drain()
    await client.patch(f'{url}/scenarios/{scenario["id"]}/listing', json={'tagline': '달린다'}, headers=me)

    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1}
    table = (await client.post(f'{url}/tables', json=body, headers=me)).json()
    table_url = f'{url}/tables/{table["id"]}'
    await client.post(f'{table_url}/character/roll', headers=me)
    await client.put(f'{table_url}/character', json={'name': '엘프'}, headers=me)
    await client.post(f'{table_url}/start', headers=me)
    # 심한 대가에 실패해 쓰러지고, 부상 표에서 20(한쪽 눈 잃음)이 나온다. 부상의 행이 생긴다
    app.state.dice = ScriptedDice([1, 8, 8, 20])
    action = {'kind': 'check', 'ability': 'dex', 'risk': 'heavy'}
    declaration = {'content': '달린다.', 'action': action}
    await client.put(f'{table_url}/rounds/current/declaration', json=declaration, headers=me)
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

    async with app.state.session_factory() as session:
        values = {'sender_id': ME, 'recipient_id': OTHER, 'content': '쉿', 'round_number': 1, 'sequence': 1}
        session.add(Whisper(table_id=uuid.UUID(table['id']), owner_id=ME, **values))
        sheet_id = await session.scalar(select(TableSheet.id).where(TableSheet.table_id == uuid.UUID(table['id'])))
        session.add(TableItem(table_id=uuid.UUID(table['id']), sheet_id=sheet_id, entry_id=uuid.uuid4(), count=1))
        session.add(TableQuest(table_id=uuid.UUID(table['id']), entry_id=uuid.uuid4(), status=QuestStatus.HIDDEN))
        session.add(TableVisit(table_id=uuid.UUID(table['id']), entry_id=uuid.uuid4()))
        session.add(TableFoundRoute(table_id=uuid.UUID(table['id']), from_place=uuid.uuid4(), to_place=uuid.uuid4()))
        placed = {'slot': 0, 'place_id': uuid.uuid4(), 'entry_id': uuid.uuid4(), 'count': 1, 'hidden': False}
        session.add(TablePlaceItem(table_id=uuid.UUID(table['id']), **placed))
        monster = {'monster_id': uuid.uuid4(), 'number': 1, 'place_id': uuid.uuid4(), 'abilities': {}, 'max_hp': 1}
        held = TableMonster(table_id=uuid.UUID(table['id']), hp=1, status='alive', **monster)
        held.items = [TableMonsterItem(slot=0, count=0)]
        session.add(held)
        # 덧붙이기만 하는 표. 트리거가 DELETE 를 막아 TRUNCATE 로 비워진다(tests/cleaning.py)
        session.add(build_read(ME, ReadKind.TABLE, uuid.UUID(table['id']), '신고', datetime.now(UTC)))
        session.add(build_action(ME, ActionKind.TABLE_END, uuid.UUID(table['id']), '신고', datetime.now(UTC)))
        version_id = await session.scalar(select(GameTable.version_id).where(GameTable.id == uuid.UUID(table['id'])))
        sanctioned = {'operator_id': OTHER, 'sanctioned_at': datetime.now(UTC), 'reason': '신고'}
        session.add(ScenarioSanction(version_id=version_id, scenario_id=uuid.uuid4(), owner_id=ME, **sanctioned))
        session.add(PublishingBan(user_id=ME, banned_at=datetime.now(UTC), reason='신고'))
        outbox.put(session, ME, 'narration_model.retiring', 'narration_model.retiring:1', {})
        await session.commit()

    async with app.state.session_factory() as session:
        await catalog.add_model(session, CATALOG_MODEL)
        await catalog.add_cost(session, CATALOG_MODEL.slug, CATALOG_COST)
        await catalog.switch_snapshot(session, CATALOG_MODEL.slug, SnapshotSwitch(api_model_id='gemma4:31b'))


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
    # 센 트랜잭션을 끝낸다. 덧붙이기만 하는 표는 TRUNCATE 로 비워서, 읽고 있는 트랜잭션이 있으면 그것을 기다린다
    await session.commit()

    await clear_tables(app.state.engine)

    assert set((await row_counts(session)).values()) == {0}
