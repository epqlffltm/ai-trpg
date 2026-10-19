# trpg-server/app/observability/db_spans.py

"""
쿼리마다 span 을 건다. SQLAlchemy 의 엔진 이벤트(커서가 문장을 보내기 전과 뒤, 실패했을 때)에 단다.

이름은 문장의 종류와 테이블이다(db UPDATE rounds). 테이블을 모르는 문장(손으로 쓴 text)은 종류만 적는다.
문장과 값은 싣지 않는다. 값에 사용자 번호가 들어간다. 실패하면 SQLSTATE(23505 같은 것)만 적는다.
오류의 글에는 값이 섞일 수 있다.

부모 span 이 기록 중일 때만 건다(요청이나 작업 안의 쿼리). 그 밖의 쿼리는 남기지 않는다.
SQLAlchemy 의 비동기는 안에서 greenlet 으로 갈아타지만 contextvars 는 따라간다. 그래서 이벤트에서 지금의 span 이 보인다.
"""

from typing import Any

from opentelemetry.trace import Span, SpanKind, StatusCode
from sqlalchemy import event
from sqlalchemy.engine import Connection, ExceptionContext, ExecutionContext
from sqlalchemy.ext.asyncio import AsyncEngine

from app.observability.spans import is_recording, tracer

# 쿼리 span 의 이름 앞부분
SPAN_NAME_PREFIX = 'db '
# 종류를 읽지 못한 문장의 이름
UNKNOWN_OPERATION = 'QUERY'
# 문장의 종류로 받는 낱말의 가장 긴 길이. 그보다 길면 종류가 아니라고 본다
MAX_OPERATION_LENGTH = 16
# 이 엔진이 건 span 을 실행의 맥락(ExecutionContext)에 걸어 두는 이름
SPAN_ATTRIBUTE = '_trpg_query_span'
# DB 가 낸 오류가 아닐 때(연결이 끊겼다, 시간이 넘었다)의 설명
UNKNOWN_SQL_STATE = 'error'


def operation_of(statement: str) -> str:
    """문장의 종류(SELECT, INSERT, UPDATE, DELETE). 첫 낱말이다. 읽지 못하면 QUERY 다."""
    words = statement.split(maxsplit=1)
    if not words or not words[0].isalpha() or len(words[0]) > MAX_OPERATION_LENGTH:
        return UNKNOWN_OPERATION
    return words[0].upper()


def table_of(context: ExecutionContext | None) -> str | None:
    """
    문장이 다루는 테이블. 하나일 때만 돌려준다. 모르면 None 이다.

    INSERT, UPDATE, DELETE 는 고치는 테이블이 하나다. SELECT 는 FROM 이 하나일 때만 적는다.
    손으로 쓴 문장(text)은 테이블을 모른다.
    """
    statement = getattr(getattr(context, 'compiled', None), 'statement', None)
    table = getattr(statement, 'table', None)
    if table is not None:
        return getattr(table, 'name', None)
    froms = statement.get_final_froms() if hasattr(statement, 'get_final_froms') else []
    names = [name for name in (getattr(found, 'name', None) for found in froms) if isinstance(name, str)]
    return names[0] if len(froms) == 1 and len(names) == 1 else None


def query_attributes(operation: str, table: str | None) -> dict[str, str]:
    """쿼리 span 에 싣는 것. 종류와 테이블뿐이다."""
    attributes = {'db.system.name': 'postgresql', 'db.operation.name': operation}
    if table is not None:
        attributes['db.collection.name'] = table
    return attributes


def query_span_name(operation: str, table: str | None) -> str:
    """쿼리 span 의 이름(db SELECT rounds)."""
    return SPAN_NAME_PREFIX + (f'{operation} {table}' if table else operation)


def sql_state(error: BaseException | None) -> str:
    """
    오류의 SQLSTATE. DB 가 낸 오류가 아니면 error 다.

    asyncpg 의 오류는 sqlstate 를 가진다.
    SQLAlchemy 가 감싼 것(AsyncAdapt_asyncpg_dbapi.Error)도 같은 이름으로 옮겨 둔다.
    """
    for candidate in (error, getattr(error, '__cause__', None)):
        code = getattr(candidate, 'sqlstate', None)
        if isinstance(code, str) and code:
            return code
    return UNKNOWN_SQL_STATE


def start_query_span(
    _conn: Connection, _cursor: Any, statement: str, _parameters: Any, context: ExecutionContext | None, _many: bool
) -> None:
    """문장을 보내기 전. 부모 span 이 있으면 span 을 시작해 실행의 맥락에 걸어 둔다."""
    if context is None or not is_recording():
        return
    operation = operation_of(statement)
    table = table_of(context)
    span = tracer().start_span(
        query_span_name(operation, table), kind=SpanKind.CLIENT, attributes=query_attributes(operation, table)
    )
    setattr(context, SPAN_ATTRIBUTE, span)


def take_query_span(context: ExecutionContext | None) -> Span | None:
    """실행의 맥락에 걸어 둔 span 을 떼어 돌려준다. 없으면 None 이다. 같은 span 을 두 번 끝내지 않게 뗀다."""
    span = getattr(context, SPAN_ATTRIBUTE, None)
    if span is not None:
        delattr(context, SPAN_ATTRIBUTE)
    return span


def end_query_span(
    _conn: Connection, _cursor: Any, _statement: str, _parameters: Any, context: ExecutionContext | None, _many: bool
) -> None:
    """문장을 보내고 답을 받은 뒤. span 을 끝낸다."""
    span = take_query_span(context)
    if span is not None:
        span.end()


def fail_query_span(exception_context: ExceptionContext) -> None:
    """문장이 실패했을 때. SQLSTATE 만 적고 span 을 끝낸다."""
    span = take_query_span(exception_context.execution_context)
    if span is not None:
        span.set_status(StatusCode.ERROR, sql_state(exception_context.original_exception))
        span.end()


def instrument_engine(engine: AsyncEngine) -> None:
    """엔진에 쿼리 span 을 단다. 여러 번 불러도 한 번만 단다. 테스트는 엔진 하나를 여러 앱이 함께 쓴다."""
    target = engine.sync_engine
    if event.contains(target, 'before_cursor_execute', start_query_span):
        return
    event.listen(target, 'before_cursor_execute', start_query_span)
    event.listen(target, 'after_cursor_execute', end_query_span)
    event.listen(target, 'handle_error', fail_query_span)
