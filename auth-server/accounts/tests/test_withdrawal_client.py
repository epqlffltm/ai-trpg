# auth-server/accounts/tests/test_withdrawal_client.py

"""
탈퇴를 다른 서버에 알리는 요청(withdrawal_client.py, #603)을 검증한다.

요청을 보내는 부분을 가짜로 바꾸지 않는다. 이 PC 에 띄운 가짜 서버(billing_stub.py)로 실제로 보내서,
나가는 주소, 서명, 본문을 그대로 받아 본다. 가짜 서버는 결제 서버의 이름이지만 어느 서버의 자리에도 선다.
"""

import json
import uuid
from datetime import UTC, datetime

from django.test import SimpleTestCase, override_settings

from accounts.models import WithdrawalTarget
from accounts.tests.billing_stub import SECRET, BillingStub
from accounts.withdrawal_client import (
    DESTINATIONS,
    WithdrawalUndeliveredError,
    configured_targets,
    is_configured,
    send_withdrawal,
)

USER_ID = uuid.UUID('11111111-2222-4333-8444-555555555555')
WITHDRAWN_AT = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
PROCESSED = b'{"status":"processed"}'

# 서버마다 받는 주소의 머리. 받는 쪽이 이 주소를 만든다(docs/architecture/withdrawal.md)
EXPECTED_PREFIXES = {
    'billing': '/api/v1/billing',
    'notification': '/api/v1/notification',
    'game': '/api/v1/game',
    'board': '/api/v1/board',
    'asset': '/api/v1/asset',
    'chat': '/api/v1/chat',
}


def pointing_at(stub: BillingStub, target: str, secret: str = SECRET) -> override_settings:
    """그 서버의 주소와 비밀을 가짜 서버로 바꾼다."""
    destination = DESTINATIONS[target]
    return override_settings(**{destination.url_setting: stub.url, destination.secret_setting: secret})


class RequestShapeTests(SimpleTestCase):
    def test_every_server_gets_the_same_shape_at_its_own_prefix(self):
        self.assertEqual(set(DESTINATIONS), set(WithdrawalTarget))
        for target in WithdrawalTarget:
            with self.subTest(target=target), BillingStub(status_code=200, body=PROCESSED) as stub:
                with pointing_at(stub, target):
                    send_withdrawal(target=target, user_public_id=USER_ID, withdrawn_at=WITHDRAWN_AT)

                request = stub.requests[0]
                self.assertEqual(request.method, 'POST')
                self.assertEqual(request.path, f'{EXPECTED_PREFIXES[target]}/service/users/{USER_ID}/withdrawal')
                # 받는 서버가 같은 비밀로 다시 만들어 맞춰 본다. 주소까지 서명이 덮는다
                self.assertTrue(request.has_valid_signature())
                self.assertEqual(json.loads(request.body), {'withdrawn_at': '2026-10-28T03:00:00+00:00'})

    def test_anything_but_processed_means_try_again_later(self):
        # 404 는 그 서버에 받는 주소가 아직 없는 것이다. 버리지 않고 다시 보낸다
        answers = [(404, b''), (202, PROCESSED), (200, b'{"status":"applied"}'), (200, b'not json'), (500, b'')]
        for status_code, body in answers:
            with (
                self.subTest(status_code=status_code, body=body),
                BillingStub(status_code=status_code, body=body) as stub,
                pointing_at(stub, WithdrawalTarget.GAME),
                self.assertRaises(WithdrawalUndeliveredError),
            ):
                send_withdrawal(target=WithdrawalTarget.GAME, user_public_id=USER_ID, withdrawn_at=WITHDRAWN_AT)

    def test_without_a_secret_nothing_is_sent(self):
        with (
            BillingStub(status_code=200, body=PROCESSED) as stub,
            pointing_at(stub, WithdrawalTarget.BOARD, secret=''),
            self.assertRaisesMessage(WithdrawalUndeliveredError, 'BOARD_SECRET'),
        ):
            send_withdrawal(target=WithdrawalTarget.BOARD, user_public_id=USER_ID, withdrawn_at=WITHDRAWN_AT)

        self.assertEqual(stub.requests, [])


class ConfiguredTests(SimpleTestCase):
    @override_settings(
        BILLING_SECRET=SECRET, NOTIFICATION_SECRET='', GAME_SECRET='', BOARD_SECRET='', ASSET_SECRET='', CHAT_SECRET=''
    )
    def test_only_servers_with_a_secret_are_told(self):
        self.assertEqual(configured_targets(), ['billing'])
        self.assertFalse(is_configured(WithdrawalTarget.ASSET))

    @override_settings(
        BILLING_SECRET=SECRET,
        NOTIFICATION_SECRET='',
        GAME_SECRET='',
        BOARD_SECRET='',
        ASSET_SECRET=SECRET,
        CHAT_SECRET=SECRET,
    )
    def test_writing_a_secret_opens_that_server(self):
        self.assertEqual(configured_targets(), ['billing', 'asset', 'chat'])
