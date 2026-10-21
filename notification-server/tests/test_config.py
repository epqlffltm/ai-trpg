# notification-server/tests/test_config.py

"""
설정의 규칙을 검증한다. 틀린 설정이면 서버가 뜨지 않아야 한다.
"""

import pytest
from pydantic import ValidationError

from tests.conftest import make_test_settings

LONG_ENOUGH = 'x' * 32


def test_an_empty_secret_means_that_server_is_not_accepted():
    settings = make_test_settings(board_server_secret='')

    assert settings.service_secrets()['board'] == ''


def test_does_not_start_with_a_short_secret():
    with pytest.raises(ValidationError, match='32자 이상'):
        make_test_settings(game_server_secret='short')


def test_does_not_start_when_two_servers_share_a_secret():
    # 하나가 새면 그 비밀로 다른 서버인 척 알림을 넣을 수 있다
    with pytest.raises(ValidationError, match='서버마다 달라야'):
        make_test_settings(game_server_secret=LONG_ENOUGH, billing_server_secret=LONG_ENOUGH)


def test_the_auth_server_secret_follows_the_same_rules():
    # 인증 서버의 비밀도 짧으면 안 되고, 알림을 넣는 서버의 것과 같으면 그 서버가 탈퇴를 꾸며 낼 수 있다
    with pytest.raises(ValidationError, match='32자 이상'):
        make_test_settings(auth_server_secret='short')
    with pytest.raises(ValidationError, match='서버마다 달라야'):
        make_test_settings(game_server_secret=LONG_ENOUGH, auth_server_secret=LONG_ENOUGH)


def test_the_auth_server_cannot_put_notifications():
    # 인증 서버의 비밀은 알림을 넣는 서버의 표에 없다. 탈퇴를 알릴 뿐이다
    settings = make_test_settings()

    assert settings.auth_server_secret.get_secret_value() not in settings.service_secrets().values()
    assert 'auth' not in settings.service_secrets()


def test_does_not_start_without_a_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)

    with pytest.raises(ValidationError, match='database_url'):
        make_test_settings(_env_file=None)


def test_the_secrets_are_hidden_when_printed():
    settings = make_test_settings()

    assert settings.game_server_secret.get_secret_value() not in repr(settings)
