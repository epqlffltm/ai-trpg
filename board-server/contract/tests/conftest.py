# board-server/contract/tests/conftest.py

"""
계약 시험이 함께 쓰는 준비물.

시험 전체에서 가짜 인증 서버 하나와 게시판 서버 하나를 띄운다. 시험마다 DB 의 글, 댓글, 신고, 닉네임을 비운다.
사람은 시험마다 새로 만든다(new_user_id). 서버가 최근에 적은 닉네임을 기억해 두는 것과 섞이지 않게 한다.

  DATABASE_URL          게시판 계정의 DB 주소(postgresql://board:...@.../trpg). 서버도 같은 주소를 쓴다
  BOARD_CONTRACT_SCHEMA 시험할 스키마. 기본 board_test. 마이그레이션을 먼저 적용해 둔다
"""

import os
from collections.abc import Callable, Iterator

import httpx
import pytest

from harness.auth import FakeAuthServer
from harness.database import Database
from harness.server import RunningServer, start_server
from harness.tokens import SigningKey, bearer, make_signing_key, make_token, new_user_id

# 시험이 쓰는 스키마. 개발용 데이터(board)를 건드리지 않는다
DEFAULT_SCHEMA = 'board_test'
# 인증 서버가 탈퇴를 알릴 때 서명하는 비밀. 서버에도 같은 값을 준다
AUTH_SERVER_SECRET = 'board-contract-auth-server-secret-0123456789'
# 서버를 부를 때 기다리는 상한(초)
REQUEST_TIMEOUT_SECONDS = 10
# 시험의 서명 키 ID
SIGNING_KID = 'contract-key'


def database_url() -> str:
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('DATABASE_URL 에 게시판 계정의 DB 주소를 적는다')
    return url


def contract_schema() -> str:
    return os.environ.get('BOARD_CONTRACT_SCHEMA', DEFAULT_SCHEMA)


@pytest.fixture(scope='session')
def signing_key() -> SigningKey:
    return make_signing_key(SIGNING_KID)


@pytest.fixture(scope='session')
def auth_server(signing_key: SigningKey) -> Iterator[FakeAuthServer]:
    server = FakeAuthServer()
    server.set_keys(signing_key.jwk())
    server.start()
    yield server
    server.stop()


@pytest.fixture(scope='session')
def board_server(auth_server: FakeAuthServer) -> Iterator[RunningServer]:
    server = start_server(database_url(), contract_schema(), auth_server.jwks_url, AUTH_SERVER_SECRET)
    yield server
    server.stop()


@pytest.fixture(scope='session')
def database() -> Iterator[Database]:
    db = Database(database_url(), contract_schema())
    yield db
    db.close()


@pytest.fixture(autouse=True)
def clean(database: Database, auth_server: FakeAuthServer, signing_key: SigningKey) -> None:
    """시험마다 데이터를 비우고 인증 서버를 처음 모양으로 돌린다."""
    database.clear()
    auth_server.set_failing(False)
    auth_server.set_keys(signing_key.jwk())


@pytest.fixture
def client(board_server: RunningServer) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=board_server.base_url, timeout=REQUEST_TIMEOUT_SECONDS) as http:
        yield http


@pytest.fixture
def token_for(signing_key: SigningKey) -> Callable[..., str]:
    """그 사람의 토큰을 만든다. 키워드로 한 가지씩 바꾼다(harness/tokens.py 의 make_token)."""

    def make(user_id: str, **options) -> str:
        return make_token(signing_key, user_id, **options)

    return make


@pytest.fixture
def headers_for(token_for: Callable[..., str]) -> Callable[..., dict[str, str]]:
    """그 사람의 토큰을 실은 머리말."""

    def make(user_id: str, **options) -> dict[str, str]:
        return bearer(token_for(user_id, **options))

    return make


@pytest.fixture
def user_id() -> str:
    """이 시험의 사람."""
    return new_user_id()


@pytest.fixture
def me(headers_for: Callable[..., dict[str, str]], user_id: str) -> dict[str, str]:
    """이 시험의 사람의 머리말. 닉네임이 실린 토큰이다."""
    return headers_for(user_id, nickname='글쓴이')


@pytest.fixture
def operator(headers_for: Callable[..., dict[str, str]]) -> dict[str, str]:
    """운영자의 머리말."""
    return headers_for(new_user_id(), nickname='운영자', operator=True)
