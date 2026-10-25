# board-server/contract/tests/test_authors.py

"""
글쓴이의 닉네임.

닉네임은 access 토큰에 실려 온다(인증 서버의 nickname 클레임). 로그인한 요청마다 적어 두고(authors 표),
글과 댓글의 응답에 author_nickname 으로 싣는다. 사람은 시험마다 새로 만든다.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from harness.database import Database
from harness.tokens import new_user_id
from tests.urls import ME, POSTS, board_posts, comment, post, post_comments, post_pin

# 미리 적어 둔 이름의 고친 시각
OLD_UPDATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def writer() -> str:
    return new_user_id()


@pytest.fixture
def reader() -> str:
    return new_user_id()


@pytest.fixture
def as_user(headers_for: Callable[..., dict[str, str]]) -> Callable[..., dict[str, str]]:
    """이 사람의 토큰을 실은 머리말. nickname 을 주지 않으면 이름이 없는 토큰이다."""

    def make(user_id: str, nickname: str | None = None) -> dict[str, str]:
        return headers_for(user_id, nickname=nickname)

    return make


@pytest.fixture
def write(client: httpx.Client, as_user: Callable[..., dict[str, str]]) -> Callable[..., httpx.Response]:
    """글을 쓴다."""

    def run(user_id: str, nickname: str | None = None, board: str = 'free') -> httpx.Response:
        return client.post(
            board_posts(board), headers=as_user(user_id, nickname), json={'title': '글', 'content': '본문입니다.'}
        )

    return run


@pytest.fixture
def written_id(write: Callable[..., httpx.Response]) -> Callable[..., str]:
    """글을 써서 그 번호를 돌려준다."""

    def run(user_id: str, nickname: str | None = None) -> str:
        response = write(user_id, nickname)
        assert response.status_code == httpx.codes.CREATED
        return response.json()['id']

    return run


@pytest.fixture
def add_comment(client: httpx.Client, as_user: Callable[..., dict[str, str]]) -> Callable[..., httpx.Response]:
    """댓글을 단다. parent_id 를 주면 답글이다."""

    def run(post_id: str, user_id: str, nickname: str | None = None, parent_id: str | None = None) -> httpx.Response:
        body: dict[str, Any] = {'content': '댓글입니다.'}
        if parent_id is not None:
            body['parent_id'] = parent_id
        return client.post(post_comments(post_id), headers=as_user(user_id, nickname), json=body)

    return run


@pytest.fixture
def visit(client: httpx.Client, as_user: Callable[..., dict[str, str]]) -> Callable[..., None]:
    """로그인한 채로 게시판을 연다. 화면이 처음에 부르는 것과 같다."""

    def run(user_id: str, nickname: str | None = None) -> None:
        assert client.get(ME, headers=as_user(user_id, nickname)).status_code == httpx.codes.OK

    return run


def read(client: httpx.Client, post_id: str) -> dict[str, Any]:
    """글 하나를 로그인 없이 읽는다."""
    return client.get(post(post_id)).json()


def listed(client: httpx.Client) -> list[dict[str, Any]]:
    """자유 게시판의 글 목록을 로그인 없이 읽는다."""
    return client.get(board_posts('free')).json()['items']


def threads(client: httpx.Client, post_id: str) -> list[dict[str, Any]]:
    """한 글의 댓글 목록을 로그인 없이 읽는다."""
    return client.get(post_comments(post_id)).json()['items']


def insert_author(database: Database, user_id: str, nickname: str) -> None:
    """이름을 미리 적어 둔다. 고친 시각은 OLD_UPDATED_AT 이다."""
    database.execute(
        'INSERT INTO authors (user_id, nickname, updated_at) VALUES (%s, %s, %s)', (user_id, nickname, OLD_UPDATED_AT)
    )


# 글쓴이의 닉네임을 싣는다


def test_nickname_is_in_write_response_and_stored(write, database: Database, writer: str):
    response = write(writer, '모험가')

    assert response.status_code == httpx.codes.CREATED
    assert response.json()['author_id'] == writer
    assert response.json()['author_nickname'] == '모험가'
    assert database.row('authors', 'user_id', writer)['nickname'] == '모험가'


def test_nickname_appears_in_read_list_pinned_and_search(
    client: httpx.Client, written_id, operator: dict[str, str], writer: str, reader: str
):
    mine = written_id(writer, '모험가')
    pinned_id = written_id(reader, '구경꾼')
    client.put(post_pin(pinned_id), headers=operator)

    assert read(client, mine)['author_nickname'] == '모험가'
    body = client.get(board_posts('free')).json()
    assert [item['author_nickname'] for item in body['pinned']] == ['구경꾼']
    assert [item['author_nickname'] for item in body['items']] == ['모험가']
    found = client.get(POSTS, params={'q': '본문'}).json()
    assert [item['author_nickname'] for item in found['items']] == ['구경꾼', '모험가']


def test_nickname_appears_on_comments_and_replies(client: httpx.Client, written_id, add_comment, writer, reader):
    post_id = written_id(writer, '모험가')

    written = add_comment(post_id, reader, '구경꾼')
    reply = add_comment(post_id, writer, '모험가', written.json()['id'])

    assert written.json()['author_nickname'] == '구경꾼'
    assert reply.json()['author_nickname'] == '모험가'
    [thread] = threads(client, post_id)
    assert thread['author_nickname'] == '구경꾼'
    assert [item['author_nickname'] for item in thread['replies']] == ['모험가']


def test_deleted_comment_shows_no_name(client: httpx.Client, written_id, add_comment, as_user, writer, reader):
    post_id = written_id(writer, '모험가')
    parent = add_comment(post_id, reader, '구경꾼').json()['id']
    add_comment(post_id, writer, '모험가', parent)
    client.delete(comment(parent), headers=as_user(reader, '구경꾼'))

    [thread] = threads(client, post_id)

    assert thread['author_id'] is None
    assert thread['author_nickname'] is None


# 닉네임이 바뀌면


def test_writing_with_new_name_renames_old_posts(client: httpx.Client, write, written_id, writer):
    old = written_id(writer, '모험가')

    write(writer, '용사')

    assert read(client, old)['author_nickname'] == '용사'
    assert [item['author_nickname'] for item in listed(client)] == ['용사', '용사']


def test_visiting_with_new_name_renames_old_posts(client: httpx.Client, written_id, visit, writer):
    old = written_id(writer, '모험가')

    visit(writer, '용사')

    assert read(client, old)['author_nickname'] == '용사'


def test_public_endpoints_do_not_take_name_from_token(client: httpx.Client, written_id, as_user, writer):
    old = written_id(writer, '모험가')

    # 로그인 없이 부르는 주소는 토큰을 보지 않는다
    client.get(post(old), headers=as_user(writer, '용사'))

    assert read(client, old)['author_nickname'] == '모험가'


def test_other_users_name_is_untouched(client: httpx.Client, written_id, visit, writer, reader):
    theirs = written_id(reader, '구경꾼')

    visit(writer, '모험가')

    assert read(client, theirs)['author_nickname'] == '구경꾼'


def test_same_name_does_not_update_row(database: Database, visit, writer):
    insert_author(database, writer, '모험가')

    visit(writer, '모험가')

    assert database.row('authors', 'user_id', writer)['updated_at'] == OLD_UPDATED_AT


def test_different_name_updates_row_and_time(database: Database, visit, writer):
    insert_author(database, writer, '모험가')

    visit(writer, '용사')

    row = database.row('authors', 'user_id', writer)
    assert row['nickname'] == '용사'
    assert row['updated_at'] > OLD_UPDATED_AT


# 닉네임을 모를 때


def test_token_without_name_writes_null(write, database: Database, writer):
    response = write(writer)

    assert response.status_code == httpx.codes.CREATED
    assert response.json()['author_nickname'] is None
    assert database.row('authors', 'user_id', writer) is None


def test_token_without_name_keeps_stored_name(client: httpx.Client, written_id, visit, writer):
    post_id = written_id(writer, '모험가')

    visit(writer)

    assert read(client, post_id)['author_nickname'] == '모험가'


def test_later_token_with_name_names_old_posts(client: httpx.Client, written_id, visit, writer):
    post_id = written_id(writer)

    visit(writer, '모험가')

    assert read(client, post_id)['author_nickname'] == '모험가'


@pytest.mark.parametrize(
    'nickname',
    [
        pytest.param('모험\n가', id='줄바꿈'),
        pytest.param('a​b', id='보이지 않는 글자'),
        pytest.param('a' * 51, id='너무 긴 것'),
    ],
)
def test_unacceptable_name_is_not_stored_but_token_is_accepted(write, database: Database, writer, nickname: str):
    response = write(writer, nickname)

    assert response.status_code == httpx.codes.CREATED
    assert response.json()['author_nickname'] is None
    assert database.row('authors', 'user_id', writer) is None
