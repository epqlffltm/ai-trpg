# board-server/tests/test_config.py

"""
설정(app/core/config.py)을 검증한다. 서버를 띄우지 않는다.

  - DATABASE_URL 은 postgresql:// 로 적어도 asyncpg 의 주소로 바꿔 쓴다(compose 와 계약 시험이 이 모양으로 넘긴다)
  - 띄우는 주소와 포트의 기본값은 NestJS 로 쓰던 때와 같다(127.0.0.1, 8002)
  - DB 연결은 이 서버의 몫(10)을 넘지 않는다
  - 탈퇴를 알리는 인증 서버의 서명 비밀이 짧으면 뜨지 않는다
"""

import pytest
from pydantic import ValidationError

from app.core.config import async_database_url
from tests.conftest import make_test_settings


@pytest.mark.parametrize(
    ('written', 'used'),
    [
        ('postgresql://board:pw@db:5432/trpg', 'postgresql+asyncpg://board:pw@db:5432/trpg'),
        ('postgres://board:pw@db:5432/trpg', 'postgresql+asyncpg://board:pw@db:5432/trpg'),
        ('postgresql+asyncpg://board:pw@db:5432/trpg', 'postgresql+asyncpg://board:pw@db:5432/trpg'),
    ],
)
def test_the_database_url_uses_the_async_driver(written: str, used: str):
    assert async_database_url(written) == used
    assert make_test_settings(database_url=written).database_url == used


def test_the_address_and_port_default_to_the_old_server():
    settings = make_test_settings()

    assert (settings.host, settings.port) == ('127.0.0.1', 8002)


def test_a_short_auth_server_secret_is_refused():
    with pytest.raises(ValidationError, match='AUTH_SERVER_SECRET'):
        make_test_settings(auth_server_secret='short')


def test_an_empty_auth_server_secret_is_allowed():
    assert make_test_settings(auth_server_secret='').auth_server_secret.get_secret_value() == ''


def test_the_service_name_is_board_server():
    assert make_test_settings().service_name == 'board-server'


def test_the_pool_stays_within_the_boards_share_of_connections():
    settings = make_test_settings()

    assert settings.db_pool_size + settings.db_max_overflow == 10
