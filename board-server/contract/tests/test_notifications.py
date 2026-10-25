# board-server/contract/tests/test_notifications.py

"""
댓글과 답글을 사용자의 알림함에 알리는 것(board-server/test/notifications.e2e-spec.ts).

알림 서버의 주소를 주지 않고 띄우므로 알림은 발송함(outgoing_notifications)에 적히기만 한다. 그 줄을 본다.

  - 발송함에 적기: 글에 단 댓글은 글쓴이에게, 답글은 그 댓글의 글쓴이에게 한 줄. 자기에게는 없다.
    댓글이 거절되면(없는 글, 답글에 단 답글) 알림도 없다.

보내는 일(다시 보내기, 실패로 두기, 오래된 줄 지우기)은 서버 안의 주기 작업이라 HTTP 로 정할 수 없다.
그것은 test/notifications.e2e-spec.ts 가 계속 본다.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from harness.database import Database
from harness.tokens import new_user_id
from tests.urls import board_posts, post_comments

Headers = Callable[..., dict[str, str]]


@pytest.fixture
def writer() -> str:
    return new_user_id()


@pytest.fixture
def commenter() -> str:
    return new_user_id()


@pytest.fixture
def replier() -> str:
    return new_user_id()


@pytest.fixture
def post_id(client: httpx.Client, headers_for: Headers, writer: str) -> str:
    """writer 가 자유 게시판에 쓴 글."""
    response = client.post(
        board_posts('free'), headers=headers_for(writer), json={'title': '첫 모험', 'content': '본문입니다.'}
    )
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def comment(
    client: httpx.Client, headers_for: Headers, user_id: str, post_id: str, parent_id: str | None = None
) -> httpx.Response:
    """글에 댓글을 단다. parent_id 를 주면 답글이다."""
    body: dict[str, str] = {'content': '댓글입니다.'}
    if parent_id is not None:
        body['parent_id'] = parent_id
    return client.post(post_comments(post_id), headers=headers_for(user_id), json=body)


def comment_id(
    client: httpx.Client, headers_for: Headers, user_id: str, post_id: str, parent_id: str | None = None
) -> str:
    """댓글을 달아 그 번호를 돌려준다."""
    response = comment(client, headers_for, user_id, post_id, parent_id)
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def outgoing(database: Database) -> list[dict[str, Any]]:
    """발송함의 모든 줄. 적은 차례다."""
    return database.execute('SELECT * FROM outgoing_notifications ORDER BY id')


# 발송함에 적기


def test_comment_on_someone_elses_post_writes_one_row_for_the_writer(
    client: httpx.Client, database: Database, headers_for: Headers, writer: str, commenter: str, post_id: str
):
    new_id = comment_id(client, headers_for, commenter, post_id)

    [notice] = outgoing(database)

    assert [str(notice['user_id']), notice['kind'], notice['status']] == [writer, 'post.commented', 'pending']
    assert notice['source_key'] == f'post.commented:{new_id}'
    assert notice['payload'] == {
        'board_slug': 'free',
        'post_id': post_id,
        'post_title': '첫 모험',
        'comment_id': new_id,
    }


def test_reply_goes_only_to_the_parent_comments_writer(
    client: httpx.Client,
    database: Database,
    headers_for: Headers,
    writer: str,
    commenter: str,
    replier: str,
    post_id: str,
):
    parent_id = comment_id(client, headers_for, commenter, post_id)
    reply_id = comment_id(client, headers_for, replier, post_id, parent_id)

    notices = outgoing(database)

    assert [[str(notice['user_id']), notice['kind']] for notice in notices] == [
        [writer, 'post.commented'],
        [commenter, 'comment.replied'],
    ]
    assert notices[1]['payload']['comment_id'] == reply_id
    assert notices[1]['payload']['parent_id'] == parent_id


def test_own_post_and_own_comment_are_not_notified(
    client: httpx.Client, database: Database, headers_for: Headers, writer: str, post_id: str
):
    own = comment_id(client, headers_for, writer, post_id)
    comment_id(client, headers_for, writer, post_id, own)

    assert outgoing(database) == []


def test_rejected_comment_has_no_notification(
    client: httpx.Client,
    database: Database,
    headers_for: Headers,
    writer: str,
    commenter: str,
    replier: str,
    post_id: str,
):
    parent_id = comment_id(client, headers_for, writer, post_id)
    reply_id = comment_id(client, headers_for, commenter, post_id, parent_id)
    database.execute('DELETE FROM outgoing_notifications')

    on_reply = comment(client, headers_for, replier, post_id, reply_id)
    on_missing_post = comment(client, headers_for, commenter, '999999')

    assert [on_reply.status_code, on_missing_post.status_code] == [httpx.codes.BAD_REQUEST, httpx.codes.NOT_FOUND]
    assert outgoing(database) == []
