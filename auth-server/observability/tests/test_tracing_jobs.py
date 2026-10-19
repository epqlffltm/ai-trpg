# auth-server/observability/tests/test_tracing_jobs.py

"""
작업 한 번(워커의 한 바퀴, 예약 명령)이 span 하나로 남는지, 할 일이 없던 바퀴의 추적은 버리는지 검증한다.
observability/jobs.py 의 run_as_job, observability/spans.py 의 job_span 과 record_handled,
observability/idle_rounds.py 의 DropIdleRounds.
"""

import io
import logging
import uuid

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from accounts.identity import person_key
from accounts.models import WelcomeCredit
from accounts.tests.billing_stub import SECRET, BillingStub
from observability.context import current_ids, job_scope, outgoing_headers, request_scope
from observability.identifiers import new_trace
from observability.idle_rounds import DropIdleRounds
from observability.jobs import JOB_FAILED_ERROR_CODE, run_as_job
from observability.spans import (
    ATTRIBUTE_HANDLED,
    ATTRIBUTE_JOB_ID,
    job_span,
    record_handled,
    span_trace,
    span_traceparent,
)
from observability.tests.helpers import rendered
from observability.tests.spans import hex_trace_id, record_spans, traceparent_of

JOBS_LOGGER = 'observability.jobs'
OPERATION = 'welcome_credit.deliver'


class JobSpanTests(SimpleTestCase):
    def setUp(self) -> None:
        self.spans = record_spans(self)

    def test_a_job_is_a_span_of_its_own_trace(self):
        with self.assertLogs(JOBS_LOGGER, logging.DEBUG) as captured, run_as_job(OPERATION) as job_id:
            seen = current_ids()

        span = self.spans.find(OPERATION)
        self.assertIsNone(span.parent)
        self.assertEqual(span.attributes[ATTRIBUTE_JOB_ID], job_id)
        self.assertEqual(span.attributes['result'], 'success')
        # 작업 안의 로그와 끝난 줄이 이 span 의 추적을 단다
        self.assertEqual(seen['trace_id'], hex_trace_id(span))
        self.assertEqual(rendered(captured.records)[0]['trace_id'], hex_trace_id(span))

    def test_a_failed_job_marks_its_span(self):
        with self.assertLogs(JOBS_LOGGER, logging.ERROR), self.assertRaises(RuntimeError), run_as_job(OPERATION):
            raise RuntimeError('connect failed: postgres://auth:super-secret@db/trpg')

        span = self.spans.find(OPERATION)
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, JOB_FAILED_ERROR_CODE)
        self.assertEqual(span.events, ())

    def test_a_job_stopped_by_an_interrupt_is_not_an_error(self):
        # 워커를 Ctrl+C 로 멈춘 것이다
        with self.assertRaises(KeyboardInterrupt), job_span(OPERATION, 'job-1'):
            raise KeyboardInterrupt

        span = self.spans.find(OPERATION)
        self.assertNotEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes['result'], 'cancelled')

    def test_an_idle_round_and_what_it_did_are_not_sent(self):
        with run_as_job(OPERATION):
            record_handled(0)

        with run_as_job(OPERATION):
            with self.spans.parent():
                pass
            record_handled(0)

        self.assertEqual(self.spans.exporter.get_finished_spans(), ())

    def test_a_round_that_did_something_is_sent_with_what_it_did(self):
        with run_as_job(OPERATION):
            with self.spans.parent():
                pass
            record_handled(2)

        span = self.spans.find(OPERATION)
        self.assertEqual(span.attributes[ATTRIBUTE_HANDLED], 2)
        self.assertEqual(len(self.spans.exporter.get_finished_spans()), 2)

    def test_a_failed_idle_round_is_still_sent(self):
        with self.assertLogs(JOBS_LOGGER, logging.ERROR), self.assertRaises(RuntimeError), run_as_job(OPERATION):
            record_handled(0)
            raise RuntimeError('DB 가 없다')

        self.assertEqual(self.spans.find(OPERATION).status.status_code, StatusCode.ERROR)

    def test_a_job_without_a_count_is_sent(self):
        # 예약 명령은 처리한 수를 적지 않는다
        with run_as_job('account.delete_unverified'):
            pass

        self.spans.find('account.delete_unverified')

    def test_the_identifiers_follow_the_span(self):
        with self.spans.parent() as parent:
            context = parent.get_span_context()
            trace_id = f'{context.trace_id:032x}'
            with request_scope('request-12345', new_trace()):
                expected = f'00-{trace_id}-{context.span_id:016x}-{context.trace_flags:02x}'
                self.assertEqual(outgoing_headers(), {'traceparent': expected})
                self.assertEqual(span_traceparent(), expected)
            with job_scope('job-12345'):
                self.assertEqual(current_ids()['trace_id'], trace_id)

    def test_without_a_span_the_identifiers_are_unchanged(self):
        self.assertIsNone(span_trace())
        self.assertIsNone(span_traceparent())
        self.assertEqual(outgoing_headers(), {})


class DropIdleRoundsTests(SimpleTestCase):
    def setUp(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.processor = DropIdleRounds(SimpleSpanProcessor(self.exporter))
        self.provider.add_span_processor(self.processor)
        self.addCleanup(self.provider.shutdown)

    def test_spans_outside_a_job_pass_straight_through(self):
        tracer = self.provider.get_tracer('test')
        with tracer.start_as_current_span('POST /api/v1/auth/login'), tracer.start_as_current_span('db SELECT'):
            pass

        self.assertEqual(len(self.exporter.get_finished_spans()), 2)

    def test_flushing_reaches_the_inner_processor(self):
        self.assertTrue(self.processor.force_flush())


@override_settings(BILLING_SECRET=SECRET)
class WorkerTests(TestCase):
    def setUp(self) -> None:
        self.spans = record_spans(self)

    def run_worker(self) -> None:
        call_command('send_welcome_credits', '--once', stdout=io.StringIO())

    def test_an_idle_worker_round_leaves_no_trace(self):
        with BillingStub() as stub, override_settings(BILLING_URL=stub.url):
            self.run_worker()

        self.assertEqual(self.spans.names(), [])

    def test_a_worker_round_that_called_billing_is_one_trace(self):
        WelcomeCredit.objects.create(
            recipient_key=person_key('person-1'), user_public_id=uuid.uuid4(), next_attempt_at=timezone.now()
        )
        with BillingStub() as stub, override_settings(BILLING_URL=stub.url):
            self.run_worker()

        job = self.spans.find(OPERATION)
        call = self.spans.find('HTTP POST')
        self.assertEqual(job.attributes[ATTRIBUTE_HANDLED], 1)
        self.assertEqual(call.parent.span_id, job.context.span_id)
        self.assertEqual(stub.requests[0].headers['Traceparent'], traceparent_of(call))
        queries = [span for span in self.spans.ended() if span.name.startswith('db ')]
        self.assertTrue(queries)
        self.assertTrue(all(query.context.trace_id == job.context.trace_id for query in queries))
