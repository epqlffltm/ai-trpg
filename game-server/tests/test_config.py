# game-server/tests/test_config.py

"""
설정을 읽는 규칙을 검증한다. 이 파일의 테스트는 .env 를 읽지 않는다.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = 'postgresql+asyncpg://game:password@127.0.0.1:5432/trpg'


@pytest.fixture(autouse=True)
def only_the_database_url_is_set(monkeypatch: pytest.MonkeyPatch):
    """이 파일의 테스트는 DB 주소만 정해진 환경에서 시작한다."""
    monkeypatch.delenv('DEBUG', raising=False)
    monkeypatch.delenv('DB_SCHEMA', raising=False)
    monkeypatch.setenv('DATABASE_URL', DATABASE_URL)


def test_debug_is_off_by_default():
    settings = Settings(_env_file=None)

    # 끄는 것을 잊으면 운영 서버의 API 구조가 드러난다. 기본을 꺼짐으로 둔다
    assert settings.debug is False


def test_schema_is_game_by_default():
    settings = Settings(_env_file=None)

    assert settings.db_schema == 'game'


def test_reads_from_environment_variables(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('DEBUG', 'true')

    settings = Settings(_env_file=None)

    assert settings.debug is True
    assert settings.database_url == DATABASE_URL


def test_rejects_a_value_of_the_wrong_type(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('DEBUG', 'maybe')

    # 잘못된 설정으로 뜨는 것보다 뜨지 않는 쪽이 낫다
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_refuses_to_start_without_a_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv('DATABASE_URL')

    # 기본 주소로 엉뚱한 DB 에 붙는 것보다 뜨지 않는 쪽이 낫다
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_ignores_unknown_values_in_the_env_file(tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('DEBUG=true\nSOMETHING_ELSE=1\n', encoding='utf-8')

    settings = Settings(_env_file=env_file)

    assert settings.debug is True
