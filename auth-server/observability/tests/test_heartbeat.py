# auth-server/observability/tests/test_heartbeat.py

"""
워커의 심장박동(observability/heartbeat.py)과, 두 워커가 언제 심장박동을 바꾸는지 검증한다(#258).
"""

import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings

from accounts import payment_eligibility, withdrawal
from accounts.management.commands import send_outgoing_mail, send_welcome_credits
from observability.heartbeat import beat


class HeartbeatFileTests(SimpleTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'heartbeat'

    def test_beat_creates_the_file(self):
        beat(str(self.path))

        self.assertTrue(self.path.exists())

    def test_beat_moves_the_time_forward(self):
        self.path.touch()
        os.utime(self.path, (0, 0))

        beat(str(self.path))

        self.assertGreater(self.path.stat().st_mtime, 0)

    def test_empty_path_does_nothing(self):
        # PC 에서 돌릴 때. 아무 파일도 만들지 않는다
        with patch('observability.heartbeat.Path.touch') as touch:
            beat('')

        touch.assert_not_called()

    def test_a_file_that_cannot_be_written_does_not_stop_the_worker(self):
        missing_folder = self.path / 'no-such-folder' / 'heartbeat'

        with self.assertLogs('observability.heartbeat', level='WARNING') as logs:
            beat(str(missing_folder))

        # 오류의 종류만 적는다
        self.assertIn('FileNotFoundError', logs.output[0])


class WorkerHeartbeatTests(TestCase):
    """두 워커는 DB 에 닿아 한 바퀴를 끝냈을 때만 심장박동을 바꾼다."""

    WORKERS = (
        (send_outgoing_mail, 'deliver_due_mail'),
        (send_welcome_credits, 'deliver_due_welcome_credits'),
    )

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'heartbeat'

    def one_round(self, module, deliver: str, **patched) -> None:
        """
        워커의 한 바퀴를 돈다.

        결제 서버에 맡기는 워커는 결제 자격도 보내고 탈퇴도 마치고 알린다(#603). 그것들은 비어 있는 것으로 둔다.
        메일 워커가 바퀴마다 세는 발송함에 남은 메일(DB 를 읽는다)도 0 으로 둔다.
        워커는 바퀴마다 끊긴 DB 연결을 버린다. 테스트의 트랜잭션 안에서는 그것이 연결을 닫아,
        실제로 DB 를 읽으면 실패한다.
        """
        command = module.Command(stdout=StringIO(), stderr=StringIO())
        with (
            override_settings(HEARTBEAT_FILE=str(self.path)),
            patch.object(module, deliver, **patched),
            patch.object(
                payment_eligibility, 'deliver_due_eligibility', return_value=payment_eligibility.DeliveryReport()
            ),
            patch.object(send_outgoing_mail, 'count_waiting_mail', return_value=0),
            patch.object(withdrawal, 'complete_due_withdrawals', return_value=0),
            patch.object(withdrawal, 'deliver_due_withdrawal_notices', return_value=withdrawal.DeliveryReport()),
        ):
            command._deliver_safely()

    def test_a_round_that_reached_the_database_beats(self):
        for module, deliver in self.WORKERS:
            with self.subTest(worker=module.__name__):
                self.path.unlink(missing_ok=True)

                self.one_round(module, deliver, return_value=module.DeliveryReport())

                self.assertTrue(self.path.exists())

    def test_a_round_that_could_not_reach_the_database_does_not_beat(self):
        for module, deliver in self.WORKERS:
            with self.subTest(worker=module.__name__):
                self.path.unlink(missing_ok=True)

                self.one_round(module, deliver, side_effect=OperationalError('connection refused'))

                # 워커는 살아 있지만 DB 에 닿지 못했다. healthcheck 가 unhealthy 로 알린다
                self.assertFalse(self.path.exists())
