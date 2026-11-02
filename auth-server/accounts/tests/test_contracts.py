# auth-server/accounts/tests/test_contracts.py

"""
공통 규격의 시험 파일(shared/contracts/, #786)을 인증 서버의 코드로 읽는다.

같은 파일을 공용 코드(shared/server-core)와 결제 서버(Go)의 테스트도 읽는다.
셋 중 하나라도 어긋나면 그 쪽의 CI 가 떨어진다.
  - service-signature.json: 서버끼리의 서명(accounts/service_signature.py)
  - redaction.json: 로그 가리기(observability/redaction.py)
access 토큰의 검증(access-tokens.json)은 읽지 않는다. 인증 서버는 토큰을 발급하는 쪽이다.

DB 를 쓰지 않는다(SimpleTestCase).
"""

import json
from pathlib import Path

from django.test import SimpleTestCase

from accounts.service_signature import sign_request, verify_request
from observability.redaction import is_sensitive_name, scrub_text

CONTRACTS = Path(__file__).resolve().parents[3] / 'shared' / 'contracts'


def load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding='utf-8'))


class ServiceSignatureContractTests(SimpleTestCase):
    """서버끼리의 서명."""

    contract = load('service-signature.json')

    def test_signing_makes_the_same_header(self):
        for case in self.contract['sign']:
            with self.subTest(case['name']):
                header = sign_request(
                    secret=self.contract['secret'],
                    method=case['method'],
                    request_uri=case['path'],
                    body=case['body'].encode(),
                    sent_at=case['sent_at'],
                )
                self.assertEqual(header, case['header'])

    def test_verifying_accepts_only_the_valid(self):
        for case in self.contract['verify']:
            with self.subTest(case['name']):
                valid = verify_request(
                    secret=case.get('secret', self.contract['secret']),
                    header=case['header'],
                    method=case['method'],
                    request_uri=case['path'],
                    body=case['body'].encode(),
                    now=self.contract['now'],
                )
                self.assertIs(valid, case['valid'])


class RedactionContractTests(SimpleTestCase):
    """로그 가리기."""

    contract = load('redaction.json')

    def test_sensitive_names(self):
        for case in self.contract['names']:
            with self.subTest(case['name']):
                self.assertIs(is_sensitive_name(case['name']), case['sensitive'])

    def test_scrubbed_texts(self):
        for case in self.contract['texts']:
            with self.subTest(case['text']):
                self.assertEqual(scrub_text(case['text'], case['limit']), case['scrubbed'])
