# auth-server/accounts/tests/test_jwt_key_script.py

"""
JWT 개인키를 만드는 스크립트(scripts/generate_jwt_key.py)를 검증한다.

scripts 는 패키지가 아니라서 파일 경로로 불러온다.
"""

import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from django.conf import settings
from django.test import SimpleTestCase


def load_script():
    path = Path(settings.BASE_DIR) / 'scripts' / 'generate_jwt_key.py'
    spec = importlib.util.spec_from_file_location('generate_jwt_key', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WritePrivateFileTests(SimpleTestCase):
    def setUp(self):
        self.script = load_script()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.key_path = Path(folder.name) / 'keys' / 'jwt-private.pem'

    def test_writes_a_usable_private_key(self):
        self.script.write_new_private_file(self.key_path, self.script.generate_private_key_pem())

        # 읽어서 개인키로 쓸 수 있어야 한다. 줄바꿈이 바뀌거나 잘리면 여기서 실패한다
        serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)

    def test_does_not_overwrite_an_existing_key(self):
        self.script.write_new_private_file(self.key_path, b'first')

        with self.assertRaises(FileExistsError):
            self.script.write_new_private_file(self.key_path, b'second')

        # 덮어쓰면 그 키로 서명한 토큰이 전부 무효가 된다
        self.assertEqual(self.key_path.read_bytes(), b'first')

    @unittest.skipIf(os.name == 'nt', '윈도우에는 이 권한 체계가 없다')
    def test_only_the_owner_can_read_the_key(self):
        # 기본값대로면 다른 사용자도 읽을 수 있는 파일이 만들어지는 환경
        previous_umask = os.umask(0o022)
        self.addCleanup(os.umask, previous_umask)

        self.script.write_new_private_file(self.key_path, b'secret')

        mode = stat.S_IMODE(self.key_path.stat().st_mode)
        self.assertEqual(mode, 0o600)
