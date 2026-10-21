# asset-server/tests/test_tracing_db.py

"""
쿼리마다 span 이 걸리는지 실제 DB 로 검증한다(app/observability/db_spans.py).
"""

import uuid

import pytest
from fastapi import FastAPI
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import column, delete, select, table, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.db_spans import instrument_engine, operation_of, query_span_name, sql_state, table_of
from tests.spans import SpanRecorder

# 값을 흉내 낸다. span 에 실리면 안 된다
SECRET_USER = uuid.UUID('0b5e7c1a-3d2f-4e8a-9c6b-1f2e3d4c5b6a')
# 쿼리를 보낼 테이블. 뼈대에는 아직 테이블이 없어서(#564) 이 테스트 동안만 있는 임시 테이블을 쓴다
PROBES = table('probes', column('owner_id'))


async def create_probes(session: AsyncSession) -> None:
    """이 세션에만 보이는 임시 테이블을 만든다. 세션이 끝나면 사라진다."""
    await session.execute(text('CREATE TEMP TABLE IF NOT EXISTS probes (owner_id uuid)'))


async def test_a_query_under_a_span_gets_a_span_named_by_its_table(session: AsyncSession, spans: SpanRecorder):
    await create_probes(session)
    with spans.parent() as parent:
        await session.execute(select(PROBES).where(PROBES.c.owner_id == SECRET_USER))

    span = spans.find('db SELECT probes')
    assert span.kind == SpanKind.CLIENT
    assert span.parent.span_id == parent.get_span_context().span_id
    assert span.attributes['db.system.name'] == 'postgresql'
    assert span.attributes['db.operation.name'] == 'SELECT'
    assert span.attributes['db.collection.name'] == 'probes'
    # 문장과 값은 싣지 않는다
    assert str(SECRET_USER) not in str(dict(span.attributes))
    assert 'WHERE' not in str(dict(span.attributes))


async def test_a_change_is_named_by_the_table_it_changes(session: AsyncSession, spans: SpanRecorder):
    await create_probes(session)
    with spans.parent():
        await session.execute(delete(PROBES).where(PROBES.c.owner_id == SECRET_USER))
        await session.rollback()

    assert spans.find('db DELETE probes').attributes['db.operation.name'] == 'DELETE'


async def test_a_hand_written_query_is_named_by_its_kind(session: AsyncSession, spans: SpanRecorder):
    with spans.parent():
        await session.execute(text('SELECT 1'))

    span = spans.find('db SELECT')
    assert 'db.collection.name' not in span.attributes


async def test_a_query_without_a_parent_gets_no_span(session: AsyncSession, spans: SpanRecorder):
    # 요청이나 작업 밖의 쿼리는 남기지 않는다
    await session.execute(text('SELECT 1'))

    assert spans.names() == []


async def test_a_failed_query_records_only_its_sql_state(session: AsyncSession, spans: SpanRecorder):
    with spans.parent() as parent:
        with pytest.raises(DBAPIError):
            await session.execute(text("SELECT 1 / 0 WHERE 'secret-value' = 'secret-value'"))
        # 쿼리의 span 만 끝낸다. 부모는 그대로 기록 중이다
        assert parent.is_recording()
    await session.rollback()

    span = spans.find('db SELECT')
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == '22012'
    assert span.events == ()
    assert 'secret-value' not in str(dict(span.attributes))


async def test_instrumenting_twice_does_not_double_the_spans(app: FastAPI, session: AsyncSession, spans: SpanRecorder):
    # 테스트는 엔진 하나를 여러 앱이 함께 쓴다. 앱을 만들 때마다 달아도 span 은 하나다
    instrument_engine(app.state.engine)

    with spans.parent():
        await session.execute(text('SELECT 1'))

    assert spans.names() == ['db SELECT']


@pytest.mark.parametrize(
    ('statement', 'operation'),
    [
        ('select 1', 'SELECT'),
        ('  DELETE FROM x', 'DELETE'),
        ('', 'QUERY'),
        ('(SELECT 1)', 'QUERY'),
        ('A' * 17, 'QUERY'),
    ],
)
def test_the_operation_is_the_first_word(statement: str, operation: str):
    assert operation_of(statement) == operation


def test_a_statement_without_one_table_has_no_table():
    assert table_of(None) is None
    assert query_span_name('SELECT', None) == 'db SELECT'


def test_the_sql_state_is_the_code_only():
    class Wrapped(Exception):
        pass

    inner = Exception('잔액이 user-0b9f5e0c 에 이미 있다')
    inner.sqlstate = '23505'
    outer = Wrapped('감쌌다')
    outer.__cause__ = inner

    assert sql_state(outer) == '23505'
    assert sql_state(ConnectionError('끊겼다')) == 'error'
    assert sql_state(None) == 'error'
