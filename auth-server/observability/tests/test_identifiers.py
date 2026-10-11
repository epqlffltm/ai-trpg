# auth-server/observability/tests/test_identifiers.py

"""
요청과 작업의 식별자의 규칙(observability/identifiers.py)과 그것을 들고 있는 곳(context.py)을 검증한다.
"""

import re
import uuid

from django.test import SimpleTestCase

from observability.context import current_ids, job_scope, outgoing_headers, request_scope
from observability.identifiers import (
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

WELL_FORMED_REQUEST_IDS = ['0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b', 'req_12345678', 'A1b2.C3d4-E5f6', 'a' * 8, 'a' * 64]
MALFORMED_REQUEST_IDS = [
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
]
MALFORMED_TRACEPARENTS = [
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
]


class RequestIdTests(SimpleTestCase):
    def test_a_well_formed_request_id_is_kept(self):
        for value in WELL_FORMED_REQUEST_IDS:
            with self.subTest(value=value):
                self.assertEqual(accept_request_id(value), value)
                self.assertEqual(request_id_from(value), value)

    def test_a_malformed_request_id_is_replaced_with_a_new_uuid(self):
        for value in MALFORMED_REQUEST_IDS:
            with self.subTest(value=value):
                self.assertIsNone(accept_request_id(value))

                replaced = request_id_from(value)

                # 고쳐 쓰지 않고 새로 만든다. 받은 값의 어느 부분도 남지 않는다
                self.assertEqual(str(uuid.UUID(replaced)), replaced)
                self.assertNotEqual(replaced, value)

    def test_every_new_request_id_is_different(self):
        self.assertNotEqual(request_id_from(None), request_id_from(None))


class TraceTests(SimpleTestCase):
    def test_a_traceparent_carries_the_trace_on(self):
        trace = parse_traceparent(TRACEPARENT)

        self.assertEqual(trace, Trace(trace_id=TRACE_ID, flags='01'))
        self.assertEqual(trace_from(TRACEPARENT), trace)

    def test_a_malformed_traceparent_starts_a_new_trace(self):
        for value in MALFORMED_TRACEPARENTS:
            with self.subTest(value=value):
                self.assertIsNone(parse_traceparent(value))

                trace = trace_from(value)

                self.assertRegex(trace.trace_id, r'^[0-9a-f]{32}$')
                self.assertNotEqual(trace.trace_id, TRACE_ID)

    def test_an_outgoing_traceparent_keeps_the_trace_and_changes_the_parent(self):
        trace = Trace(trace_id=TRACE_ID, flags='01')

        first = format_traceparent(trace)
        second = format_traceparent(trace)

        self.assertRegex(first, rf'^00-{TRACE_ID}-[0-9a-f]{{16}}-01$')
        # 받는 쪽이 다시 읽을 수 있는 모양이다
        self.assertEqual(parse_traceparent(first), trace)
        self.assertNotEqual(first, second)


class ContextTests(SimpleTestCase):
    def test_identifiers_are_set_only_inside_the_scope(self):
        trace = new_trace()

        self.assertEqual(current_ids(), {})
        with request_scope('request-12345', trace):
            self.assertEqual(current_ids(), {'request_id': 'request-12345', 'trace_id': trace.trace_id})
            self.assertEqual(parse_traceparent(outgoing_headers()['traceparent']), trace)
        self.assertEqual(current_ids(), {})
        self.assertEqual(outgoing_headers(), {})

    def test_a_job_drops_the_request_id_and_keeps_the_trace(self):
        trace = new_trace()

        with request_scope('request-12345', trace), job_scope('job-12345678'):
            ids = current_ids()

        # 작업은 요청이 아니다. 요청의 식별자를 달고 있으면 안 된다
        self.assertEqual(ids, {'job_id': 'job-12345678', 'trace_id': trace.trace_id})

    def test_a_job_started_outside_a_request_gets_its_own_trace(self):
        with job_scope('job-12345678'):
            ids = current_ids()

        self.assertEqual(ids['job_id'], 'job-12345678')
        self.assertTrue(re.fullmatch(r'[0-9a-f]{32}', ids['trace_id']))
