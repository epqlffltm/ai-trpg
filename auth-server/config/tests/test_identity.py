# auth-server/config/tests/test_identity.py

"""
본인확인 업체의 설정(config/identity.py)을 확인한다.

함수는 직접 부르고, 설정 파일에 이어졌는지는 설정을 새로 읽는 manage.py 를 띄워 본다(test_security.py 와 같다).
"""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.identity import DISABLED, FAKE, default_identity_provider, validate_identity_provider
from config.tests.test_security import PRODUCTION_ENVIRONMENT, run_manage

PRINT_PROVIDER = 'from django.conf import settings; print(settings.IDENTITY_PROVIDER)'


class IdentityProviderTests(SimpleTestCase):
    def test_the_default_is_fake_except_in_production(self):
        self.assertEqual(default_identity_provider('development'), FAKE)
        self.assertEqual(default_identity_provider('test'), FAKE)
        self.assertEqual(default_identity_provider('production'), DISABLED)

    def test_known_names_pass(self):
        self.assertEqual(validate_identity_provider('fake', 'development'), FAKE)
        self.assertEqual(validate_identity_provider('disabled', 'production'), DISABLED)

    def test_an_unknown_name_is_refused(self):
        for name in ('', 'nice', 'FAKE', 'fake '):
            with self.subTest(name), self.assertRaises(ImproperlyConfigured):
                validate_identity_provider(name, 'development')

    def test_production_refuses_the_fake_provider(self):
        # 가짜 업체는 적힌 생일을 그대로 믿는다. 운영에서 쓰면 누구나 성인이 된다
        with self.assertRaisesMessage(ImproperlyConfigured, 'IDENTITY_PROVIDER=fake'):
            validate_identity_provider('fake', 'production')


class IdentitySettingsTests(SimpleTestCase):
    def test_production_starts_with_identity_verification_off(self):
        result = run_manage('shell', '-c', PRINT_PROVIDER, **PRODUCTION_ENVIRONMENT)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[-1], DISABLED)

    def test_production_refuses_to_start_with_the_fake_provider(self):
        result = run_manage('check', **{**PRODUCTION_ENVIRONMENT, 'IDENTITY_PROVIDER': 'fake'})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('IDENTITY_PROVIDER', result.stderr)
