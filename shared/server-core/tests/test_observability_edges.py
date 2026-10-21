# shared/server-core/tests/test_observability_edges.py

"""
관측 코드(server_core/observability)의 가장자리를 검증한다. 보통의 요청으로는 지나가지 않는 길이다.
"""

import logging

from server_core.observability.formatter import CONTEXT_IDS_FIELD, context_ids
from server_core.observability.middleware import RequestLoggingMiddleware, full_template
from server_core.observability.setup import DropUnhandledNotice


def make_record(logger: str, message: str) -> logging.LogRecord:
    return logging.LogRecord(logger, logging.INFO, __file__, 1, message, None, None)


def test_a_template_that_takes_the_rest_of_the_path_is_kept_as_it_is():
    # 여러 마디를 한꺼번에 받는 틀은 마디 수를 셀 수 없다. 받은 틀을 그대로 쓴다
    assert full_template('/files/{name:path}', '/api/v1/asset/files/a/b/c') == '/files/{name:path}'


def test_a_template_longer_than_the_path_is_kept_as_it_is():
    assert full_template('/a/{b}/c/d', '/a/1') == '/a/{b}/c/d'


def test_identifiers_of_the_wrong_shape_are_not_written():
    record = make_record('tests', '글')
    setattr(record, CONTEXT_IDS_FIELD, 'not-a-dict')

    assert context_ids(record) == {}


def test_uvicorns_repeat_of_an_unhandled_error_is_dropped():
    # 같은 예외를 미들웨어가 이미 적었다. 두 번 적지 않는다
    notice = DropUnhandledNotice()
    repeated = logging.LogRecord(
        'uvicorn.error', logging.ERROR, __file__, 1, 'Exception in ASGI application', None, None
    )
    other = logging.LogRecord('uvicorn.error', logging.INFO, __file__, 1, 'Started server process', None, None)

    assert notice.filter(repeated) is False
    assert notice.filter(other) is True


async def test_a_scope_that_is_not_http_passes_through_untouched():
    # 서버가 뜨고 꺼질 때의 lifespan 은 요청이 아니다. 식별자를 걸지 않고 줄도 남기지 않는다
    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)

    middleware = RequestLoggingMiddleware(inner)
    await middleware({'type': 'lifespan'}, None, None)

    assert seen == [{'type': 'lifespan'}]
