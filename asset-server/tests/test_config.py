# asset-server/tests/test_config.py

"""
설정의 규칙을 검증한다. 틀린 설정이면 서버가 뜨지 않아야 한다.
"""

import pytest
from pydantic import ValidationError
from server_core.service_auth.signing import MIN_SECRET_LENGTH

from tests.conftest import make_test_settings


def test_does_not_start_without_a_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)

    with pytest.raises(ValidationError, match='database_url'):
        make_test_settings(_env_file=None)


def test_the_defaults_name_this_server():
    settings = make_test_settings(_env_file=None, db_schema='asset')

    # 토큰의 대상과 스키마는 이 서버의 이름이다(인증 서버의 JWT_AUDIENCE, docker/postgres/init 의 스키마와 같다)
    assert (settings.jwt_audience, settings.db_schema) == ('ai-trpg-asset', 'asset')


def test_an_empty_caller_secret_means_that_server_is_not_accepted():
    settings = make_test_settings(chat_server_secret='')

    assert settings.service_secrets() == {'chat': ''}


def test_does_not_start_with_a_short_caller_secret():
    with pytest.raises(ValidationError, match='32자 이상'):
        make_test_settings(chat_server_secret='short')


def test_a_caller_secret_of_exactly_the_minimum_starts():
    settings = make_test_settings(chat_server_secret='x' * MIN_SECRET_LENGTH)

    assert settings.service_secrets()['chat'] == 'x' * MIN_SECRET_LENGTH


def test_the_caller_secret_is_hidden_when_printed():
    settings = make_test_settings()

    assert settings.chat_server_secret.get_secret_value() not in repr(settings)
