# auth-server/accounts/tests/test_service_signature.py

"""
우리 서버끼리의 요청에 붙이는 서명을 검증한다.

서명은 두 서버 사이의 약속이다. 인증 서버(파이썬)가 만든 것을 결제 서버(Go)가 확인한다.
"""

import re

from django.test import SimpleTestCase

from accounts.service_signature import SIGNATURE_HEADER, sign_request, verify_request

SECRET = 'this-is-a-test-secret-of-32-chars!'
SENT_AT = 1772442000
PATH = '/api/v1/billing/service/grants/welcome'
BODY = b'{"user_id":"11111111-2222-4333-8444-555555555555"}'


def sign(**overrides) -> str:
    """테스트마다 달라지는 값만 넘기고 나머지는 기본값으로 서명한다."""
    fields = {'secret': SECRET, 'method': 'POST', 'request_uri': PATH, 'body': BODY, 'sent_at': SENT_AT}
    fields.update(overrides)
    return sign_request(**fields)


class SignRequestTests(SimpleTestCase):
    def test_is_the_value_the_billing_server_computes(self):
        # 결제 서버의 테스트에 같은 값이 적혀 있다(billing-server/internal/serviceauth/serviceauth_test.go).
        # 한쪽의 계산이 바뀌면 그쪽의 테스트가 깨진다. 두 서버를 함께 띄우지 않고도 약속을 지키는지 본다
        self.assertEqual(
            sign(),
            't=1772442000,v1=9270f18fd4635b8f4489bf06d6c6f42275f2b08ea19876090cb7c2ea02a62aec',
        )

    def test_has_the_time_and_a_lowercase_hex_digest(self):
        self.assertRegex(sign(), r'^t=1772442000,v1=[0-9a-f]{64}$')

    def test_covers_the_method_the_path_the_body_the_time_and_the_secret(self):
        original = sign()
        changed = {
            '다른 메서드': sign(method='DELETE'),
            '다른 주소': sign(request_uri='/api/v1/billing/service/holds'),
            '주소 뒤에 값을 붙였다': sign(request_uri=PATH + '?again=1'),
            '본문을 고쳤다': sign(body=BODY.replace(b'5555', b'6666')),
            '본문 끝에 빈칸': sign(body=BODY + b' '),
            '다른 시각': sign(sent_at=SENT_AT + 1),
            '다른 비밀': sign(secret='another-secret-that-is-32-chars!!'),
        }
        for name, signature in changed.items():
            with self.subTest(name):
                self.assertNotEqual(self._digest(signature), self._digest(original))

    def test_parts_cannot_trade_characters(self):
        # 세 부분 사이의 줄바꿈이 없으면 주소의 끝을 본문의 앞으로 옮겨도 같은 글자가 된다
        self.assertNotEqual(
            sign(request_uri=PATH + '/extra', body=b'{}'),
            sign(request_uri=PATH, body=b'/extra{}'),
        )

    def test_header_name_is_the_one_the_billing_server_reads(self):
        self.assertEqual(SIGNATURE_HEADER, 'X-Service-Signature')

    def _digest(self, signature: str) -> str:
        return re.fullmatch(r't=\d+,v1=([0-9a-f]{64})', signature).group(1)


class VerifyRequestTests(SimpleTestCase):
    """결제 서버가 서명해 보낸 요청을 확인한다(#352). 결제 서버의 internal/signature 와 같은 규칙이다."""

    def verify(self, header: str | None = None, **overrides) -> bool:
        fields = {'secret': SECRET, 'method': 'POST', 'request_uri': PATH, 'body': BODY, 'now': SENT_AT}
        fields.update(overrides)
        return verify_request(header=sign() if header is None else header, **fields)

    def test_accepts_the_value_the_billing_server_makes(self):
        # 결제 서버가 같은 비밀과 내용으로 만드는 값이다(위의 값과 같다)
        self.assertTrue(self.verify('t=1772442000,v1=9270f18fd4635b8f4489bf06d6c6f42275f2b08ea19876090cb7c2ea02a62aec'))

    def test_refuses_a_request_that_is_not_the_signed_one(self):
        refused = {
            '다른 메서드': {'method': 'PUT'},
            '다른 주소': {'request_uri': '/api/v1/auth/service/other'},
            '다른 본문': {'body': BODY + b' '},
            '다른 비밀': {'secret': 'another-secret-that-is-32-chars!!'},
        }
        for name, overrides in refused.items():
            with self.subTest(name):
                self.assertFalse(self.verify(**overrides))

    def test_refuses_a_bad_header(self):
        for header in ('', 'nope', 't=1772442000', 'v1=' + '0' * 64, 't=x,v1=' + '0' * 64, sign().upper()):
            with self.subTest(header=header):
                self.assertFalse(self.verify(header))

    def test_accepts_five_minutes_either_way_and_no_more(self):
        self.assertTrue(self.verify(now=SENT_AT + 300))
        self.assertTrue(self.verify(now=SENT_AT - 300))
        self.assertFalse(self.verify(now=SENT_AT + 301))
        self.assertFalse(self.verify(now=SENT_AT - 301))

    def test_an_empty_or_short_secret_accepts_nothing(self):
        # 설정이 빠진 서버는 서명을 하나도 받지 않는다. 빈 비밀로 만든 서명도 마찬가지다
        for secret in ('', 'short'):
            with self.subTest(secret=secret):
                header = sign(secret=secret)
                self.assertFalse(self.verify(header, secret=secret))
