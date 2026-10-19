# docker/certbot/test_cert_check.py

"""
인증서의 남은 날짜 검사(cert_check.py)를 본다. 그 자리에서 만든 자체 서명 인증서를 쓴다.
네트워크와 Let's Encrypt 를 쓰지 않는다.

    사용(cryptography 가 있는 곳, 예: certbot 이미지 안):
        python3 -m unittest discover -s docker/certbot -p 'test_*.py'

stack-smoke.sh 의 check-staging 이 certbot 이미지 안에서 부른다.
"""

import datetime
import tempfile
import unittest
from pathlib import Path

from cert_check import MIN_DAYS_LEFT, days_left, is_fresh, main
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

NOW = datetime.datetime(2026, 10, 19, tzinfo=datetime.UTC)


def certificate_pem(not_after: datetime.datetime) -> bytes:
    """not_after 에 끝나는 자체 서명 인증서."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'staging.test')])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_after - datetime.timedelta(days=90))
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM)


def in_days(days: int) -> datetime.datetime:
    """지금부터 days 날 뒤."""
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=days)


class DaysLeftTests(unittest.TestCase):
    def test_counts_days_until_the_certificate_ends(self):
        pem = certificate_pem(NOW + datetime.timedelta(days=30))

        self.assertAlmostEqual(days_left(pem, NOW), 30, places=3)

    def test_an_expired_certificate_has_negative_days(self):
        pem = certificate_pem(NOW - datetime.timedelta(days=1))

        self.assertLess(days_left(pem, NOW), 0)

    def test_fresh_while_renewal_still_has_time(self):
        # certbot 은 30일 남았을 때 갱신한다. 그 뒤로 2주 동안 실패해도 아직 통과다
        self.assertTrue(is_fresh(certificate_pem(NOW + datetime.timedelta(days=MIN_DAYS_LEFT + 1)), NOW))

    def test_not_fresh_after_two_weeks_of_failed_renewals(self):
        self.assertFalse(is_fresh(certificate_pem(NOW + datetime.timedelta(days=MIN_DAYS_LEFT - 1)), NOW))


class MainTests(unittest.TestCase):
    def write(self, folder: str, content: bytes) -> str:
        path = Path(folder) / 'fullchain.pem'
        path.write_bytes(content)
        return str(path)

    def test_passes_for_a_new_certificate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, certificate_pem(in_days(89)))

            self.assertEqual(main(['cert_check.py', path]), 0)

    def test_fails_for_a_certificate_about_to_end(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, certificate_pem(in_days(3)))

            self.assertEqual(main(['cert_check.py', path]), 1)

    def test_fails_when_there_is_no_certificate(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(main(['cert_check.py', str(Path(folder) / 'fullchain.pem')]), 1)

    def test_fails_for_a_file_that_is_not_a_certificate(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(main(['cert_check.py', self.write(folder, b'not a certificate')]), 1)


if __name__ == '__main__':
    unittest.main()
