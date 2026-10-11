# auth-server/observability/tests/test_jobs.py

"""
요청과 따로 도는 일에 식별자(job_id)가 걸리는지 검증한다(observability/jobs.py).
"""

import io
import logging
import uuid

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from observability.context import current_ids
from observability.jobs import run_as_job
from observability.tests.helpers import rendered

JOBS_LOGGER = 'observability.jobs'


class RunAsJobTests(SimpleTestCase):
    def test_a_job_gets_its_own_id(self):
        with run_as_job('mail.deliver_outgoing') as job_id:
            ids = current_ids()

        self.assertEqual(str(uuid.UUID(job_id)), job_id)
        self.assertEqual(ids['job_id'], job_id)
        self.assertNotIn('request_id', ids)
        # 끝나면 걸려 있던 것이 풀린다
        self.assertEqual(current_ids(), {})

    def test_every_job_gets_a_different_id(self):
        with run_as_job('mail.deliver_outgoing') as first:
            pass
        with run_as_job('mail.deliver_outgoing') as second:
            pass

        self.assertNotEqual(first, second)

    def test_logs_inside_a_job_carry_its_id(self):
        inner = logging.getLogger('tests.inside-a-job')

        with self.assertLogs(inner, logging.WARNING) as captured, run_as_job('mail.deliver_outgoing') as job_id:
            inner.warning('메일을 보내지 못하고 버렸다')

        (line,) = rendered(captured.records)
        self.assertEqual(line['job_id'], job_id)

    def test_a_failed_job_can_be_traced_by_its_id(self):
        seen: list[str] = []

        with self.assertLogs(JOBS_LOGGER, logging.ERROR) as captured, self.assertRaises(RuntimeError):
            with run_as_job('security.send_digest') as job_id:
                seen.append(job_id)
                raise RuntimeError('메일 서버가 죽었다')

        (line,) = rendered(captured.records)
        self.assertEqual(line['job_id'], seen[0])
        self.assertEqual(line['operation'], 'security.send_digest')
        self.assertEqual(line['result'], 'server_error')
        self.assertEqual(line['error_code'], 'job.failed')
        self.assertEqual(line['error_type'], 'RuntimeError')
        self.assertIsInstance(line['duration_ms'], int)

    def test_a_finished_job_is_logged_quietly(self):
        # 메일 워커는 1초마다 돈다. 잘 끝난 것을 info 로 적으면 로그를 메운다
        with self.assertLogs(JOBS_LOGGER, logging.DEBUG) as captured, run_as_job('mail.deliver_outgoing'):
            pass

        (line,) = rendered(captured.records)
        self.assertEqual(line['level'], 'debug')
        self.assertEqual(line['result'], 'success')


class CommandTests(TestCase):
    """관리 명령이 작업으로 도는지 본다."""

    def run_and_capture(self, command: str, *args: str) -> list[dict]:
        with self.assertLogs(JOBS_LOGGER, logging.DEBUG) as captured:
            # 명령이 화면에 찍는 안내는 버린다. 파일이 아니라 메모리에 받는다. /dev/null 은 Windows 에 없다
            call_command(command, *args, stdout=io.StringIO())
        return rendered(captured.records)

    def test_the_commands_run_as_jobs(self):
        commands = {
            ('send_outgoing_mail', '--once'): 'mail.deliver_outgoing',
            ('delete_unverified_users',): 'account.delete_unverified',
            ('send_security_digest',): 'security.send_digest',
        }
        for command, operation in commands.items():
            with self.subTest(command=command[0]):
                (line,) = self.run_and_capture(*command)

                self.assertEqual(line['operation'], operation)
                self.assertEqual(str(uuid.UUID(line['job_id'])), line['job_id'])
