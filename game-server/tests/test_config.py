# game-server/tests/test_config.py

"""
설정을 읽는 규칙을 검증한다.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_debug_is_off_by_default():
    settings = Settings(_env_file=None)

    # 끄는 것을 잊으면 운영 서버의 API 구조가 드러난다. 기본을 꺼짐으로 둔다
    assert settings.debug is False


def test_reads_from_environment_variables(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('DEBUG', 'true')

    settings = Settings(_env_file=None)

    assert settings.debug is True


def test_rejects_a_value_of_the_wrong_type(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('DEBUG', 'maybe')

    # 잘못된 설정으로 뜨는 것보다 뜨지 않는 쪽이 낫다
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_ignores_unknown_values_in_the_env_file(tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('DEBUG=true\nSOMETHING_ELSE=1\n', encoding='utf-8')

    settings = Settings(_env_file=env_file)

    assert settings.debug is True
