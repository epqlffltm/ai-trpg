# board-server/contract/tests/test_withdrawals.py

"""
인증 서버가 탈퇴를 알리는 API(POST /service/users/{id}/withdrawal)(board-server/test/withdrawals.e2e-spec.ts).

  - 정리: 그 사람의 글과 댓글(지운 것도)의 글쓴이를 비운다. 글과 댓글은 남는다. 신고한 사람을 비운다.
    닉네임과 그 사람에게 보낼 알림을 지운다. 다른 사람의 것은 그대로다
  - 보이는 것: 응답의 author_id 와 author_nickname 이 null 이고 author_withdrawn 이 true 다
  - 그 뒤: 탈퇴한 사람의 글에 댓글을 달아도 알림이 없다. 운영자는 지울 수 있다. 누구나 신고할 수 있다
  - 몇 번을 받아도, 모르는 사람이어도 200 processed 다
  - 인증 서버의 서명이 아니면 401, 본문과 주소가 틀리면 400 이다. 어느 쪽이든 아무것도 바꾸지 않는다
"""

from collections.abc import Callable

import httpx
import pytest

from harness.database import Database
from harness.signing import SIGNATURE_HEADER, sign
from harness.tokens import new_user_id
from tests.conftest import AUTH_SERVER_SECRET
from tests.urls import board_posts, comment, post, post_comments, post_reports, withdrawal

# 인증 서버가 보내는 본문(auth-server/accounts/withdrawal_client.py 의 isoformat)
BODY = '{"withdrawn_at": "2026-10-28T03:00:00.123456+00:00"}'

Headers = Callable[..., dict[str, str]]


@pytest.fixture
def leaving() -> str:
    """탈퇴하는 사람."""
    return new_user_id()


@pytest.fixture
def staying() -> str:
    """남는 사람."""
    return new_user_id()


def write_post(client: httpx.Client, headers_for: Headers, user_id: str) -> str:
    """그 사람이 자유 게시판에 글을 써서 그 번호를 돌려준다. 닉네임이 적힌다."""
    response = client.post(
        board_posts('free'),
        headers=headers_for(user_id, nickname=f'이름{user_id[:4]}'),
        json={'title': '첫 모험', 'content': '본문입니다.'},
    )
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def write_comment(
    client: httpx.Client, headers_for: Headers, user_id: str, post_id: str, parent_id: str | None = None
) -> str:
    """그 사람이 글에 댓글을 달아 그 번호를 돌려준다. parent_id 를 주면 답글이다."""
    body: dict[str, str] = {'content': '댓글입니다.'}
    if parent_id is not None:
        body['parent_id'] = parent_id
    response = client.post(post_comments(post_id), headers=headers_for(user_id), json=body)
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def report_post(client: httpx.Client, headers_for: Headers, user_id: str, post_id: str) -> httpx.Response:
    """그 사람이 글을 신고한다."""
    return client.post(post_reports(post_id), headers=headers_for(user_id), json={'reason': 'spam'})


def withdraw(
    client: httpx.Client,
    user_id: str,
    *,
    body: str = BODY,
    secret: str = AUTH_SERVER_SECRET,
    signed_path: str | None = None,
) -> httpx.Response:
    """인증 서버처럼 서명해 그 사람의 탈퇴를 알린다. secret 과 signed_path 로 한 가지씩 틀리게 바꾼다."""
    path = withdrawal(user_id)
    content = body.encode()
    signature = sign(secret, 'POST', signed_path or path, content)
    return client.post(
        path,
        content=content,
        headers={SIGNATURE_HEADER: signature, 'Content-Type': 'application/json'},
    )


def outgoing_users(database: Database) -> list[str]:
    """발송함의 모든 줄의 받는 사람. 적은 차례다."""
    rows = database.execute('SELECT user_id FROM outgoing_notifications ORDER BY id')
    return [str(row['user_id']) for row in rows]


def author_of(database: Database, table: str, row_id: str) -> str | None:
    """글이나 댓글의 글쓴이. 비었으면 None."""
    row = database.row(table, 'id', row_id)
    assert row is not None
    value = row['author_id']
    return None if value is None else str(value)


# 정리


def test_keeps_posts_and_comments_but_clears_author_without_touching_updated_at(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str
):
    post_id = write_post(client, headers_for, leaving)
    comment_id = write_comment(client, headers_for, leaving, post_id)
    before = database.row('posts', 'id', post_id)

    response = withdraw(client, leaving)

    assert response.status_code == httpx.codes.OK
    assert response.json() == {'status': 'processed'}
    row = database.row('posts', 'id', post_id)
    assert row is not None and before is not None
    assert [row['author_id'], row['title'], row['content']] == [None, '첫 모험', '본문입니다.']
    assert row['updated_at'] == before['updated_at']
    assert author_of(database, 'comments', comment_id) is None


def test_clears_author_of_deleted_posts_and_comments(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str
):
    post_id = write_post(client, headers_for, leaving)
    comment_id = write_comment(client, headers_for, leaving, post_id)
    assert client.delete(comment(comment_id), headers=headers_for(leaving)).status_code == httpx.codes.NO_CONTENT
    assert client.delete(post(post_id), headers=headers_for(leaving)).status_code == httpx.codes.NO_CONTENT

    assert withdraw(client, leaving).status_code == httpx.codes.OK

    assert author_of(database, 'posts', post_id) is None
    assert author_of(database, 'comments', comment_id) is None


def test_keeps_reports_but_clears_reporter(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str, staying: str
):
    post_id = write_post(client, headers_for, staying)
    report = report_post(client, headers_for, leaving, post_id)
    assert report.status_code == httpx.codes.CREATED
    report_id = report.json()['id']

    assert withdraw(client, leaving).status_code == httpx.codes.OK

    row = database.row('reports', 'id', report_id)
    assert row is not None
    assert [row['reporter_id'], row['reason']] == [None, 'spam']


def test_deletes_nickname_and_pending_notifications_for_the_user(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str, staying: str
):
    post_id = write_post(client, headers_for, leaving)
    write_comment(client, headers_for, staying, post_id)
    assert outgoing_users(database) == [leaving]

    assert withdraw(client, leaving).status_code == httpx.codes.OK

    assert database.row('authors', 'user_id', leaving) is None
    assert outgoing_users(database) == []


def test_leaves_other_users_data_alone(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str, staying: str
):
    mine = write_post(client, headers_for, staying)
    theirs = write_post(client, headers_for, leaving)
    write_comment(client, headers_for, leaving, mine)

    assert withdraw(client, leaving).status_code == httpx.codes.OK

    assert author_of(database, 'posts', mine) == staying
    assert database.row('authors', 'user_id', staying) is not None
    assert outgoing_users(database) == [staying]
    assert author_of(database, 'posts', theirs) is None


# 보이는 것


def test_post_is_shown_as_written_by_withdrawn_user(client: httpx.Client, headers_for: Headers, leaving: str):
    post_id = write_post(client, headers_for, leaving)
    assert withdraw(client, leaving).status_code == httpx.codes.OK

    shown = client.get(post(post_id))
    listed = client.get(board_posts('free'))

    assert shown.status_code == httpx.codes.OK
    assert listed.status_code == httpx.codes.OK
    body = shown.json()
    assert [body['author_id'], body['author_nickname'], body['author_withdrawn']] == [None, None, True]
    item = listed.json()['items'][0]
    assert [item['author_id'], item['author_withdrawn']] == [None, True]


def test_comments_of_withdrawn_user_are_shown_the_same_and_others_are_not_withdrawn(
    client: httpx.Client, headers_for: Headers, leaving: str, staying: str
):
    post_id = write_post(client, headers_for, staying)
    write_comment(client, headers_for, leaving, post_id)
    write_comment(client, headers_for, staying, post_id)
    assert withdraw(client, leaving).status_code == httpx.codes.OK

    response = client.get(post_comments(post_id))

    assert response.status_code == httpx.codes.OK
    items = response.json()['items']
    assert [[item['author_id'], item['author_withdrawn']] for item in items] == [[None, True], [staying, False]]
    assert items[0]['author_nickname'] is None
    assert isinstance(items[1]['author_nickname'], str)


# 그 뒤


def test_replies_on_withdrawn_users_posts_and_comments_are_not_notified(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str, staying: str
):
    post_id = write_post(client, headers_for, leaving)
    comment_id = write_comment(client, headers_for, leaving, post_id)
    assert withdraw(client, leaving).status_code == httpx.codes.OK

    write_comment(client, headers_for, staying, post_id)
    write_comment(client, headers_for, staying, post_id, comment_id)

    assert outgoing_users(database) == []


def test_operator_can_delete_withdrawn_users_post(
    client: httpx.Client, headers_for: Headers, operator: dict[str, str], leaving: str
):
    post_id = write_post(client, headers_for, leaving)
    assert withdraw(client, leaving).status_code == httpx.codes.OK

    response = client.delete(post(post_id), headers=operator)

    assert response.status_code == httpx.codes.NO_CONTENT


def test_anyone_can_report_withdrawn_users_post(client: httpx.Client, headers_for: Headers, leaving: str, staying: str):
    post_id = write_post(client, headers_for, leaving)
    assert withdraw(client, leaving).status_code == httpx.codes.OK

    assert report_post(client, headers_for, staying, post_id).status_code == httpx.codes.CREATED


# 다시 받기


def test_same_withdrawal_again_is_processed(client: httpx.Client, headers_for: Headers, leaving: str):
    write_post(client, headers_for, leaving)
    assert withdraw(client, leaving).status_code == httpx.codes.OK

    again = withdraw(client, leaving)

    assert [again.status_code, again.json()] == [httpx.codes.OK, {'status': 'processed'}]


def test_unknown_user_is_processed(client: httpx.Client):
    response = withdraw(client, new_user_id())

    assert [response.status_code, response.json()] == [httpx.codes.OK, {'status': 'processed'}]


# 서명과 입력


@pytest.mark.parametrize('wrong', ['other_secret', 'other_path'])
def test_wrong_signature_is_401_and_changes_nothing(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str, staying: str, wrong: str
):
    post_id = write_post(client, headers_for, leaving)

    if wrong == 'other_secret':
        response = withdraw(client, leaving, secret='board-someone-else-secret-0123456789')
    else:
        response = withdraw(client, leaving, signed_path=withdrawal(staying))

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert author_of(database, 'posts', post_id) == leaving


def test_query_is_signed_too_and_signature_without_it_is_rejected(client: httpx.Client, leaving: str):
    path = withdrawal(leaving)
    content = BODY.encode()
    signed_without = sign(AUTH_SERVER_SECRET, 'POST', path, content)

    response = client.post(
        f'{path}?retry=1',
        content=content,
        headers={SIGNATURE_HEADER: signed_without, 'Content-Type': 'application/json'},
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_user_token_without_signature_is_401(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str
):
    post_id = write_post(client, headers_for, leaving)

    response = client.post(
        withdrawal(leaving),
        content=BODY.encode(),
        headers={**headers_for(leaving), 'Content-Type': 'application/json'},
    )

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert author_of(database, 'posts', post_id) == leaving


@pytest.mark.parametrize(
    'body',
    [
        pytest.param('{}', id='missing_time'),
        pytest.param('{"withdrawn_at": "2026-10-28T03:00:00"}', id='time_without_zone'),
        pytest.param('{"withdrawn_at": "어제"}', id='not_a_time'),
        pytest.param('{"withdrawn_at": "2026-10-28T03:00:00Z", "email": "a@b.c"}', id='unknown_field'),
    ],
)
def test_bad_body_is_400_and_changes_nothing(
    client: httpx.Client, database: Database, headers_for: Headers, leaving: str, body: str
):
    post_id = write_post(client, headers_for, leaving)

    response = withdraw(client, leaving, body=body)

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert author_of(database, 'posts', post_id) == leaving


def test_user_id_that_is_not_a_uuid_is_400(client: httpx.Client):
    response = withdraw(client, 'not-a-uuid')

    assert response.status_code == httpx.codes.BAD_REQUEST
