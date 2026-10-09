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
OPTIONAL_VARIABLES = (
    'DEBUG',
    'DB_SCHEMA',
    'JWT_ISSUER',
    'JWT_AUDIENCE',
    'NARRATOR',
    'LLM_BASE_URL',
    'LLM_MODEL',
    'LLM_TIMEOUT_SECONDS',
    'LLM_SUPPORTS_REASONING',
)


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


def test_an_error_does_not_show_the_values_it_read(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv('AUTH_JWKS_URL')
    env_file = tmp_path / '.env'
    env_file.write_text('DEBUG=maybe\nSOME_PASSWORD=do-not-print-me\n', encoding='utf-8')

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=env_file)

    # 오류 메시지는 화면과 로그에 남는다. 어느 설정이 틀렸는지만 알려 주고 값은 싣지 않는다
    message = str(caught.value)
    assert 'auth_jwks_url' in message
    assert 'do-not-print-me' not in message
    assert 'maybe' not in message
    assert 'password@' not in message


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


# --- 서술자 ---


def test_the_narrator_is_the_fake_one_by_default():
    settings = Settings(_env_file=None)

    # 모델이 없는 곳(CI, 처음 받은 사람의 PC)에서도 서버가 뜨고 테스트가 돈다
    assert settings.narrator == 'fake'


def test_the_model_is_looked_for_on_this_computer_by_default():
    settings = Settings(_env_file=None)

    assert settings.llm_base_url == 'http://127.0.0.1:11434/v1'
    assert settings.llm_timeout_seconds == 120.0
    assert settings.llm_supports_reasoning is True


def test_the_language_model_narrator_needs_a_model_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('NARRATOR', 'llm')

    # 모델 이름 없이 떴다가 첫 라운드를 닫을 때 실패하는 것보다 뜨지 않는 쪽이 낫다
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_the_language_model_narrator_reads_its_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('NARRATOR', 'llm')
    monkeypatch.setenv('LLM_MODEL', 'gemma4:26b')
    monkeypatch.setenv('LLM_BASE_URL', 'http://127.0.0.1:1234/v1')
    monkeypatch.setenv('LLM_TIMEOUT_SECONDS', '30')
    monkeypatch.setenv('LLM_SUPPORTS_REASONING', 'false')

    settings = Settings(_env_file=None)

    assert settings.narrator == 'llm'
    assert settings.llm_model == 'gemma4:26b'
    assert settings.llm_base_url == 'http://127.0.0.1:1234/v1'
    assert settings.llm_timeout_seconds == 30.0
    assert settings.llm_supports_reasoning is False


@pytest.mark.parametrize(('name', 'value'), [('NARRATOR', 'gpt'), ('LLM_TIMEOUT_SECONDS', '0')])
def test_rejects_a_narrator_setting_it_does_not_know(monkeypatch: pytest.MonkeyPatch, name: str, value: str):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
