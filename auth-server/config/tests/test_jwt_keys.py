# auth-server/config/tests/test_jwt_keys.py

"""
JWT 키를 읽는 것(config/jwt_keys.py)과 공개키를 꺼내는 스크립트(scripts/export_jwt_public_key.py)를 검증한다(#21).
"""

import importlib.util
import io
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.jwt_keys import build_verification_keys, compute_key_id, derive_public_key_pem, read_public_key_pem


def private_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('ascii')


class KeyFilesTestCase(SimpleTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def write(self, name: str, text: str, newline: str = '\n') -> Path:
        path = self.folder / name
        path.write_text(text.replace('\n', newline), encoding='ascii', newline='')
        return path


class ReadPublicKeyTests(KeyFilesTestCase):
    def test_reads_a_public_key(self):
        public = derive_public_key_pem(private_pem())

        self.assertEqual(read_public_key_pem(self.write('a.pem', public)), public)

    def test_the_key_id_does_not_depend_on_line_endings(self):
        # 윈도우에서 저장해 CRLF 가 되어도 같은 키는 같은 kid 다. 다르면 그 키로 서명한 토큰을 알아보지 못한다
        public = derive_public_key_pem(private_pem())

        read = read_public_key_pem(self.write('crlf.pem', public, newline='\r\n'))

        self.assertEqual(compute_key_id(read), compute_key_id(public))

    def test_refuses_a_missing_file(self):
        with self.assertRaisesMessage(ImproperlyConfigured, '공개키 파일이 없습니다'):
            read_public_key_pem(self.folder / 'none.pem')

    def test_refuses_a_private_key(self):
        # 옛 개인키를 남겨 두지 않게 공개키만 받는다
        with self.assertRaisesMessage(ImproperlyConfigured, '공개키 파일이 아닙니다'):
            read_public_key_pem(self.write('private.pem', private_pem()))


class VerificationKeysTests(KeyFilesTestCase):
    def setUp(self):
        super().setUp()
        self.signing_public = derive_public_key_pem(private_pem())

    def test_the_signing_key_comes_first(self):
        other = derive_public_key_pem(private_pem())

        keys = build_verification_keys(self.signing_public, [self.write('other.pem', other)])

        self.assertEqual(list(keys), [compute_key_id(self.signing_public), compute_key_id(other)])

    def test_only_the_signing_key_without_extra_keys(self):
        self.assertEqual(list(build_verification_keys(self.signing_public, [])), [compute_key_id(self.signing_public)])

    def test_refuses_the_signing_key_listed_again(self):
        with self.assertRaisesMessage(ImproperlyConfigured, '같은 JWT 키가 두 번'):
            build_verification_keys(self.signing_public, [self.write('same.pem', self.signing_public)])

    def test_refuses_the_same_extra_key_twice(self):
        other = derive_public_key_pem(private_pem())
        paths = [self.write('one.pem', other), self.write('two.pem', other)]

        with self.assertRaisesMessage(ImproperlyConfigured, '같은 JWT 키가 두 번'):
            build_verification_keys(self.signing_public, paths)


def load_export_script():
    path = Path(settings.BASE_DIR) / 'scripts' / 'export_jwt_public_key.py'
    spec = importlib.util.spec_from_file_location('export_jwt_public_key', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExportScriptTests(KeyFilesTestCase):
    def setUp(self):
        super().setUp()
        self.script = load_export_script()
        self.private = private_pem()
        self.private_path = self.write('private.pem', self.private)
        self.public_path = self.folder / 'public' / 'old.pem'

    def run_script(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['export_jwt_public_key.py', *args]), redirect_stdout(out), redirect_stderr(err):
            code = self.script.main()
        return code, out.getvalue(), err.getvalue()

    def test_writes_the_public_key_and_prints_its_key_id(self):
        code, out, _ = self.run_script(str(self.private_path), str(self.public_path))

        public = derive_public_key_pem(self.private)
        self.assertEqual(code, 0)
        self.assertEqual(read_public_key_pem(self.public_path), public)
        # 서버가 내보낼 kid 와 같아야 한다
        self.assertIn(compute_key_id(public), out)

    def test_does_not_overwrite_a_file(self):
        self.public_path.parent.mkdir()
        self.public_path.write_text('something else', encoding='ascii')

        code, _, err = self.run_script(str(self.private_path), str(self.public_path))

        self.assertEqual(code, 1)
        self.assertIn('이미 파일이 있습니다', err)
        self.assertEqual(self.public_path.read_text(encoding='ascii'), 'something else')

    def test_reports_a_missing_or_wrong_private_key(self):
        missing, _, missing_err = self.run_script(str(self.folder / 'none.pem'), str(self.public_path))
        wrong, _, wrong_err = self.run_script(str(self.write('bad.pem', 'not a key')), str(self.public_path))

        self.assertEqual((missing, wrong), (1, 1))
        self.assertIn('개인키 파일이 없습니다', missing_err)
        self.assertIn('개인키 파일이 아닙니다', wrong_err)

    def test_needs_two_arguments(self):
        code, _, err = self.run_script(str(self.private_path))

        self.assertEqual(code, 2)
        self.assertIn('쓰는 법', err)
