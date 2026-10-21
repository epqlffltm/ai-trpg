# asset-server/tests/test_observability_identifiers.py

"""
요청과 작업의 식별자의 규칙(app/observability/identifiers.py)과 그것을 들고 있는 곳(context.py)을 검증한다.
"""

import asyncio
import re
import uuid

import pytest

from app.observability.context import current_ids, job_scope, outgoing_headers, request_scope
from app.observability.identifiers import (
    Trace,
    accept_request_id,
    format_traceparent,
    new_trace,
    parse_traceparent,
    request_id_from,
    trace_from,
)

TRACE_ID = '4bf92f3577b34da6a3ce929d0e0e4736'
TRACEPARENT = f'00-{TRACE_ID}-00f067aa0ba902b7-01'


@pytest.mark.parametrize(
    'value',
    ['0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b', 'req_12345678', 'A1b2.C3d4-E5f6', 'a' * 8, 'a' * 64],
)
def test_a_well_formed_request_id_is_kept(value: str):
    assert accept_request_id(value) == value
    assert request_id_from(value) == value


@pytest.mark.parametrize(
    'value',
    [
        None,
        '',
        'short',
        'a' * 65,
        'a' * 5000,
        'has space in it',
        'line\nbreak-12345',
        'carriage\rreturn-1',
        'tab\tinside-12345',
        'null\x00byte-12345',
        'escape\x1b[31m-12345',
        '한글로-된-식별자-12345',
        '{"injected":"json"}',
        'semi;colon-12345',
        'slash/inside-12345',
    ],
)
def test_a_malformed_request_id_is_replaced_with_a_new_uuid(value: str | None):
    assert accept_request_id(value) is None

    replaced = request_id_from(value)

    # 고쳐 쓰지 않고 새로 만든다. 받은 값의 어느 부분도 남지 않는다
    assert str(uuid.UUID(replaced)) == replaced
    assert replaced != value


def test_every_new_request_id_is_different():
    assert request_id_from(None) != request_id_from(None)


def test_a_traceparent_carries_the_trace_on():
    trace = parse_traceparent(TRACEPARENT)

    assert trace == Trace(trace_id=TRACE_ID, flags='01')
    assert trace_from(TRACEPARENT) == trace


@pytest.mark.parametrize(
    'value',
    [
        None,
        '',
        'garbage',
        TRACE_ID,
        # 모르는 버전
        f'01-{TRACE_ID}-00f067aa0ba902b7-01',
        f'ff-{TRACE_ID}-00f067aa0ba902b7-01',
        # 대문자
        f'00-{TRACE_ID.upper()}-00f067aa0ba902b7-01',
        # 길이가 틀리다
        f'00-{TRACE_ID[:-1]}-00f067aa0ba902b7-01',
        f'00-{TRACE_ID}-00f067aa0ba902-01',
        # 0 으로만 된 식별자
        f'00-{"0" * 32}-00f067aa0ba902b7-01',
        f'00-{TRACE_ID}-{"0" * 16}-01',
        # 줄바꿈으로 다른 값을 끼워 넣으려는 것
        f'{TRACEPARENT}\nX-Injected: 1',
        TRACEPARENT + 'x' * 500,
    ],
)
def test_a_malformed_traceparent_starts_a_new_trace(value: str | None):
    assert parse_traceparent(value) is None

    trace = trace_from(value)

    assert re.fullmatch(r'[0-9a-f]{32}', trace.trace_id)
    assert trace.trace_id != TRACE_ID


def test_an_outgoing_traceparent_keeps_the_trace_and_changes_the_parent():
    trace = Trace(trace_id=TRACE_ID, flags='01')

    first = format_traceparent(trace)
    second = format_traceparent(trace)

    assert re.fullmatch(rf'00-{TRACE_ID}-[0-9a-f]{{16}}-01', first)
    # 받는 쪽이 다시 읽을 수 있는 모양이다
    assert parse_traceparent(first) == trace
    assert first != second


def test_identifiers_are_set_only_inside_the_scope():
    trace = new_trace()

    assert current_ids() == {}
    with request_scope('request-12345', trace):
        assert current_ids() == {'request_id': 'request-12345', 'trace_id': trace.trace_id}
        assert parse_traceparent(outgoing_headers()['traceparent']) == trace
    assert current_ids() == {}
    assert outgoing_headers() == {}


def test_a_job_drops_the_request_id_and_keeps_the_trace():
    trace = new_trace()

    with request_scope('request-12345', trace), job_scope('job-12345678'):
        ids = current_ids()

    # 작업은 요청이 끝난 뒤에도 돈다. 요청의 식별자를 달고 있으면 안 된다
    assert ids == {'job_id': 'job-12345678', 'trace_id': trace.trace_id}


def test_a_job_started_outside_a_request_gets_its_own_trace():
    with job_scope('job-12345678'):
        ids = current_ids()

    assert ids['job_id'] == 'job-12345678'
    assert re.fullmatch(r'[0-9a-f]{32}', ids['trace_id'])


async def test_requests_handled_at_the_same_time_do_not_mix():
    seen: dict[str, dict[str, str]] = {}

    async def handle(request_id: str) -> None:
        with request_scope(request_id, new_trace()):
            # 다른 요청이 끼어들 틈을 준다
            await asyncio.sleep(0)
            seen[request_id] = current_ids()

    await asyncio.gather(handle('request-aaaa'), handle('request-bbbb'))

    assert seen['request-aaaa']['request_id'] == 'request-aaaa'
    assert seen['request-bbbb']['request_id'] == 'request-bbbb'
    assert seen['request-aaaa']['trace_id'] != seen['request-bbbb']['trace_id']
