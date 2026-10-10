# game-server/tests/test_config.py

"""
설정을 읽는 규칙을 검증한다. 이 파일의 테스트는 .env 를 읽지 않는다.
"""

import pytest
from pydantic import ValidationError

from app.core.config import NARRATION_BUDGET_SECONDS, Settings

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
    'LLM_FALLBACK_MODELS',
    'LLM_TIMEOUT_SECONDS',
    'LLM_SUPPORTS_REASONING',
    'EMBEDDER',
    'EMBEDDING_MODEL',
    'EMBEDDING_BASE_URL',
    'EMBEDDING_TIMEOUT_SECONDS',
    'AI_LOG_HMAC_KEY',
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
    assert settings.llm_timeout_seconds == 60.0
    assert settings.llm_supports_reasoning is True
    # 넘어갈 모델은 없다. 적은 모델 하나만 부른다
    assert settings.llm_fallback_models == ''


def test_the_models_are_the_first_then_the_fallbacks():
    settings = Settings(_env_file=None, llm_model=' gemma4:26b ', llm_fallback_models='a, b ,,c')

    assert settings.llm_models() == ['gemma4:26b', 'a', 'b', 'c']


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


@pytest.mark.parametrize(
    ('name', 'value'),
    [
        ('NARRATOR', 'gpt'),
        ('LLM_TIMEOUT_SECONDS', '0'),
        # 한 번 부르는 시간이 서술 하나의 상한보다 길면 멈춘 라운드의 판정과 어긋난다
        ('LLM_TIMEOUT_SECONDS', str(NARRATION_BUDGET_SECONDS + 1)),
    ],
)
def test_rejects_a_narrator_setting_it_does_not_know(monkeypatch: pytest.MonkeyPatch, name: str, value: str):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# --- 임베딩 ---


def test_the_embedder_is_fake_by_default():
    settings = Settings(_env_file=None)

    # 테스트와 CI 는 모델 없이 돈다. 실제 모델은 각자의 .env 에서 켠다
    assert settings.embedder == 'fake'
    assert settings.embedding_model == 'bge-m3'


def test_the_embedding_address_falls_back_to_the_llm_address(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('LLM_BASE_URL', 'http://127.0.0.1:1234/v1')

    assert Settings(_env_file=None).embedding_url() == 'http://127.0.0.1:1234/v1'


def test_the_embedding_address_can_be_its_own(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('EMBEDDING_BASE_URL', 'http://127.0.0.1:9000/v1')

    assert Settings(_env_file=None).embedding_url() == 'http://127.0.0.1:9000/v1'


def test_an_embedder_without_a_model_does_not_start(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('EMBEDDER', 'llm')
    monkeypatch.setenv('EMBEDDING_MODEL', '  ')

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# --- 입력 지문의 키 ---


def test_there_is_no_digest_key_by_default():
    assert Settings(_env_file=None).digest_key() is None


def test_the_digest_key_is_read_as_bytes_and_kept_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('AI_LOG_HMAC_KEY', ' 0123abcd ')

    settings = Settings(_env_file=None)

    assert settings.digest_key() == b'0123abcd'
    # 설정을 찍어도 키가 보이지 않는다
    assert '0123abcd' not in repr(settings)
