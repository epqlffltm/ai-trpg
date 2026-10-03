# game-server/tests/test_config.py

"""
설정을 읽는 규칙을 검증한다. 이 파일의 테스트는 .env 를 읽지 않는다.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = 'postgresql+asyncpg://game:password@127.0.0.1:5432/trpg'
AUTH_JWKS_URL = 'http://127.0.0.1:8000/api/v1/auth/jwks'

# 기본값이 있는 설정. 개발자의 환경에 남아 있으면 기본값을 검증할 수 없으므로 지우고 시작한다
OPTIONAL_VARIABLES = ('DEBUG', 'DB_SCHEMA', 'JWT_ISSUER', 'JWT_AUDIENCE')


@pytest.fixture(autouse=True)
def only_the_required_values_are_set(monkeypatch: pytest.MonkeyPatch):
    """이 파일의 테스트는 필수 값만 정해진 환경에서 시작한다."""
    for name in OPTIONAL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('DATABASE_URL', DATABASE_URL)
    monkeypatch.setenv('AUTH_JWKS_URL', AUTH_JWKS_URL)


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


def test_refuses_to_start_without_a_jwks_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv('AUTH_JWKS_URL')

    # 어느 서버의 키를 믿을지 모르는 채로 뜨면 안 된다
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_token_names_match_the_auth_server_by_default():
    settings = Settings(_env_file=None)

    # 인증 서버의 JWT_ISSUER, JWT_AUDIENCE 기본값과 짝이 맞아야 한다
    assert settings.jwt_issuer == 'ai-trpg-auth'
    assert settings.jwt_audience == 'ai-trpg-game'


def test_ignores_unknown_values_in_the_env_file(tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('DEBUG=true\nSOMETHING_ELSE=1\n', encoding='utf-8')

    settings = Settings(_env_file=env_file)

    assert settings.debug is True
