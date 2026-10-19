# auth-server/observability/db_spans.py

"""
쿼리마다 span 을 건다. Django 의 연결에 문장을 보내는 일을 감싸는 것(execute_wrappers)을 단다.

이름은 문장의 종류와 테이블이다(db SELECT accounts_user). 테이블은 문장의 FROM, INTO, UPDATE 뒤의 첫 이름이다.
문장과 값은 싣지 않는다. 값에 이메일과 비밀번호의 해시가 들어간다. 실패하면 SQLSTATE(23505 같은 것)만 적는다.
오류의 글에는 값이 섞일 수 있다.

부모 span 이 기록 중일 때만 건다(요청이나 작업 안의 쿼리). 그 밖의 쿼리(서버가 뜰 때의 확인)는 남기지 않는다.
연결은 스레드마다 따로 맺는다. 연결을 맺을 때마다 단다(connection_created, observability/apps.py).
"""

import re
from collections.abc import Callable
from typing import Any

from opentelemetry.trace import SpanKind, StatusCode

from observability.spans import is_recording, tracer

# 쿼리 span 의 이름 앞부분
SPAN_NAME_PREFIX = 'db '
# 종류를 읽지 못한 문장의 이름
UNKNOWN_OPERATION = 'QUERY'
# 문장의 종류로 받는 낱말의 가장 긴 길이. 그보다 길면 종류가 아니라고 본다
MAX_OPERATION_LENGTH = 16
# 문장이 다루는 첫 테이블. Django 는 이름을 큰따옴표로 감싼다("accounts_user")
TABLE_PATTERN = re.compile(r'\b(?:FROM|INTO|UPDATE)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?', re.IGNORECASE)
# DB 가 낸 오류가 아닐 때(연결이 끊겼다)의 설명
UNKNOWN_SQL_STATE = 'error'


def operation_of(sql: str) -> str:
    """문장의 종류(SELECT, INSERT, UPDATE, DELETE). 첫 낱말이다. 읽지 못하면 QUERY 다."""
    words = sql.split(maxsplit=1)
    if not words or not words[0].isalpha() or len(words[0]) > MAX_OPERATION_LENGTH:
        return UNKNOWN_OPERATION
    return words[0].upper()


def table_of(sql: str) -> str | None:
    """문장이 다루는 첫 테이블. 없으면 None 이다(SELECT 1, SAVEPOINT)."""
    found = TABLE_PATTERN.search(sql)
    return found[1] if found else None


def query_attributes(operation: str, table: str | None) -> dict[str, str]:
    """쿼리 span 에 싣는 것. 종류와 테이블뿐이다."""
    attributes = {'db.system.name': 'postgresql', 'db.operation.name': operation}
    if table is not None:
        attributes['db.collection.name'] = table
    return attributes


def query_span_name(operation: str, table: str | None) -> str:
    """쿼리 span 의 이름(db SELECT accounts_user)."""
    return SPAN_NAME_PREFIX + (f'{operation} {table}' if table else operation)


def sql_state(error: BaseException | None) -> str:
    """
    오류의 SQLSTATE. DB 가 낸 오류가 아니면 error 다.

    psycopg 의 오류는 sqlstate 를 가진다. Django 가 감싼 오류(django.db.utils.Error)는 원래 오류를 __cause__ 에 둔다.
    """
    for candidate in (error, getattr(error, '__cause__', None)):
        code = getattr(candidate, 'sqlstate', None)
        if isinstance(code, str) and code:
            return code
    return UNKNOWN_SQL_STATE


def trace_query(execute: Callable, sql: str, params: Any, many: bool, context: dict) -> Any:
    """
    문장 하나를 보낸다. 부모 span 이 있으면 span 을 건다. Django 의 execute_wrappers 의 모양이다.

    예외는 그대로 올린다. span 에는 SQLSTATE 만 적는다.
    """
    if not is_recording():
        return execute(sql, params, many, context)
    operation = operation_of(sql)
    table = table_of(sql)
    with tracer().start_as_current_span(
        query_span_name(operation, table),
        kind=SpanKind.CLIENT,
        attributes=query_attributes(operation, table),
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            return execute(sql, params, many, context)
        except Exception as error:
            span.set_status(StatusCode.ERROR, sql_state(error))
            raise


def instrument_connection(connection) -> None:
    """연결에 쿼리 span 을 단다. 같은 연결에 두 번 달지 않는다."""
    if trace_query not in connection.execute_wrappers:
        connection.execute_wrappers.append(trace_query)


def on_connection_created(sender, connection, **kwargs) -> None:
    """연결을 맺었을 때 Django 가 부른다(connection_created). 그 연결에 쿼리 span 을 단다."""
    instrument_connection(connection)
