# chat-server/tests/test_config.py

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
    settings = make_test_settings(_env_file=None, db_schema='chat')

    # 토큰의 대상과 스키마는 이 서버의 이름이다(인증 서버의 JWT_AUDIENCE, docker/postgres/init 의 스키마와 같다)
    assert (settings.jwt_audience, settings.db_schema) == ('ai-trpg-chat', 'chat')


ASSET_URL = 'http://asset.test'


def test_without_an_asset_url_no_secret_is_needed():
    settings = make_test_settings(asset_url='', asset_secret='')

    assert settings.asset_url == ''


@pytest.mark.parametrize('secret', ['', 'x' * (MIN_SECRET_LENGTH - 1)])
def test_an_asset_url_needs_a_long_secret(secret: str):
    with pytest.raises(ValidationError, match='ASSET_SECRET'):
        make_test_settings(asset_url=ASSET_URL, asset_secret=secret)


def test_an_asset_url_with_a_secret_of_the_minimum_starts():
    settings = make_test_settings(asset_url=ASSET_URL, asset_secret='x' * MIN_SECRET_LENGTH)

    assert settings.asset_secret.get_secret_value() == 'x' * MIN_SECRET_LENGTH


def test_a_blank_asset_url_counts_as_not_written():
    settings = make_test_settings(asset_url='  ', asset_secret='')

    assert settings.asset_secret.get_secret_value() == ''


def test_the_asset_secret_is_hidden_when_printed():
    settings = make_test_settings(asset_url=ASSET_URL, asset_secret='s' * MIN_SECRET_LENGTH)

    assert 's' * MIN_SECRET_LENGTH not in repr(settings)
