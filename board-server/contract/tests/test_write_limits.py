# board-server/contract/tests/test_write_limits.py

"""
글, 댓글, 신고의 횟수 제한.

서버가 쓰는 한도를 그대로 본다: 글 10분에 5개, 댓글 1분에 10개, 신고 1시간에 20건. 사람마다 세고 운영자는 걸리지 않는다.
시간이 흘러 창이 지나가는 것은 기다리지 않는다. 쓴 시각을 DB 에서 과거로 옮겨 놓고 본다(age_writes).
"""

from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest

from harness.database import Database
from harness.tokens import new_user_id
from tests.urls import board_posts, comment, post, post_comments, post_reports


@dataclass(frozen=True)
class Limit:
    window_seconds: int
    max: int


POSTS = Limit(window_seconds=10 * 60, max=5)
COMMENTS = Limit(window_seconds=60, max=10)
REPORTS = Limit(window_seconds=60 * 60, max=20)


def write_post(client: httpx.Client, headers: dict[str, str], board: str = 'free') -> httpx.Response:
    return client.post(board_posts(board), headers=headers, json={'title': '글', 'content': '본문입니다.'})


def write_posts(client: httpx.Client, headers: dict[str, str], n: int) -> str:
    """글을 n 개 쓴다. 모두 써져야 한다. 마지막에 쓴 글의 번호를 돌려준다."""
    post_id = ''
    for _ in range(n):
        response = write_post(client, headers)
        assert response.status_code == httpx.codes.CREATED
        post_id = response.json()['id']
    return post_id


def write_comment(
    client: httpx.Client, headers: dict[str, str], post_id: object, parent_id: str | None = None
) -> httpx.Response:
    """댓글을 단다. parent_id 를 주면 답글이다."""
    body: dict[str, object] = {'content': '댓글입니다.'}
    if parent_id is not None:
        body['parent_id'] = parent_id
    return client.post(post_comments(post_id), headers=headers, json=body)


def write_comments(client: httpx.Client, headers: dict[str, str], post_id: str, n: int) -> str:
    """댓글을 n 개 단다. 모두 달려야 한다. 마지막에 단 댓글의 번호를 돌려준다."""
    comment_id = ''
    for _ in range(n):
        response = write_comment(client, headers, post_id)
        assert response.status_code == httpx.codes.CREATED
        comment_id = response.json()['id']
    return comment_id


def post_count(client: httpx.Client, board: str = 'free') -> int:
    return client.get(board_posts(board)).json()['total']


def assert_limited(response: httpx.Response, detail: str, limit: Limit) -> None:
    """429 이고, 방금 다 썼으니 창의 길이만큼 기다리라고 본문과 머리말로 알려 준다."""
    assert response.status_code == httpx.codes.TOO_MANY_REQUESTS
    body = response.json()
    assert set(body) == {'detail', 'retry_after'}
    assert body['detail'] == detail
    retry_after = body['retry_after']
    assert isinstance(retry_after, int) and not isinstance(retry_after, bool)
    assert limit.window_seconds - 30 < retry_after <= limit.window_seconds
    assert response.headers['retry-after'] == str(retry_after)


@pytest.fixture
def stranger(headers_for: Callable[..., dict[str, str]]) -> dict[str, str]:
    """다른 사람의 머리말."""
    return headers_for(new_user_id(), nickname='낯선이')


# 글 쓰기의 한도


def test_posts_up_to_limit_are_written(client: httpx.Client, me: dict):
    write_posts(client, me, POSTS.max)

    assert post_count(client) == POSTS.max


def test_post_over_limit_is_429_with_retry_after(client: httpx.Client, me: dict):
    write_posts(client, me, POSTS.max)

    response = write_post(client, me)

    assert_limited(response, '글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.', POSTS)


def test_blocked_post_is_not_saved(client: httpx.Client, me: dict):
    write_posts(client, me, POSTS.max)

    write_post(client, me)

    assert post_count(client) == POSTS.max


def test_post_limit_is_per_user(client: httpx.Client, me: dict, stranger: dict):
    write_posts(client, me, POSTS.max)

    assert write_post(client, stranger).status_code == httpx.codes.CREATED


def test_post_allowed_again_after_window(client: httpx.Client, database: Database, me: dict, user_id: str):
    write_posts(client, me, POSTS.max)

    database.age_writes(user_id, POSTS.window_seconds + 1)

    assert write_post(client, me).status_code == httpx.codes.CREATED


def test_retry_after_is_until_oldest_post_leaves_window(
    client: httpx.Client, database: Database, me: dict, user_id: str
):
    write_posts(client, me, 1)
    # 첫 글을 쓴 지 9분이 지났다
    database.age_writes(user_id, POSTS.window_seconds - 60)
    write_posts(client, me, POSTS.max - 1)

    response = write_post(client, me)

    # 1분만 기다리면 첫 글이 창을 벗어나 하나를 더 쓸 수 있다
    assert response.status_code == httpx.codes.TOO_MANY_REQUESTS
    assert 30 < response.json()['retry_after'] <= 60


def test_post_allowed_after_waiting_retry_after(client: httpx.Client, database: Database, me: dict, user_id: str):
    write_posts(client, me, POSTS.max)
    retry_after = write_post(client, me).json()['retry_after']

    database.age_writes(user_id, retry_after)

    assert write_post(client, me).status_code == httpx.codes.CREATED


def test_deleted_posts_still_count(client: httpx.Client, me: dict):
    last = write_posts(client, me, POSTS.max)
    client.delete(post(last), headers=me)

    # 지워서 자리를 낼 수 있으면 "쓰고 지우고 또 쓰기"로 한도를 피한다
    assert write_post(client, me).status_code == httpx.codes.TOO_MANY_REQUESTS


def test_operator_is_exempt_from_post_limit(client: httpx.Client, operator: dict):
    write_posts(client, operator, POSTS.max)

    assert write_post(client, operator).status_code == httpx.codes.CREATED
    assert write_post(client, operator, 'notice').status_code == httpx.codes.CREATED


def test_forbidden_board_is_403_before_limit(client: httpx.Client, me: dict):
    write_posts(client, me, POSTS.max)

    assert write_post(client, me, 'notice').status_code == httpx.codes.FORBIDDEN


def test_comments_do_not_count_toward_post_limit(client: httpx.Client, me: dict):
    post_id = write_posts(client, me, 1)
    write_comments(client, me, post_id, COMMENTS.max)

    assert write_post(client, me).status_code == httpx.codes.CREATED


def test_edits_and_deletes_do_not_count(client: httpx.Client, me: dict):
    last = write_posts(client, me, POSTS.max)

    edited = client.patch(post(last), headers=me, json={'title': '고친 제목'})

    assert edited.status_code == httpx.codes.OK


# 댓글 쓰기의 한도


@pytest.fixture
def target_post(client: httpx.Client, stranger: dict) -> str:
    """댓글을 달 글. 다른 사람이 쓴다."""
    return write_posts(client, stranger, 1)


def test_comments_up_to_limit_then_429(client: httpx.Client, me: dict, target_post: str):
    write_comments(client, me, target_post, COMMENTS.max)

    response = write_comment(client, me, target_post)

    assert_limited(response, '댓글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.', COMMENTS)


def test_replies_count_toward_comment_limit(client: httpx.Client, me: dict, target_post: str):
    parent = write_comments(client, me, target_post, 1)
    for _ in range(1, COMMENTS.max):
        assert write_comment(client, me, target_post, parent).status_code == httpx.codes.CREATED

    assert write_comment(client, me, target_post, parent).status_code == httpx.codes.TOO_MANY_REQUESTS


def test_comments_across_posts_count_together(client: httpx.Client, me: dict, stranger: dict, target_post: str):
    other = write_posts(client, stranger, 1)
    write_comments(client, me, target_post, COMMENTS.max - 1)
    write_comments(client, me, other, 1)

    assert write_comment(client, me, other).status_code == httpx.codes.TOO_MANY_REQUESTS


def test_comment_limit_is_per_user(client: httpx.Client, me: dict, stranger: dict, target_post: str):
    write_comments(client, me, target_post, COMMENTS.max)

    assert write_comment(client, stranger, target_post).status_code == httpx.codes.CREATED


def test_comment_allowed_again_after_window(
    client: httpx.Client, database: Database, me: dict, user_id: str, target_post: str
):
    write_comments(client, me, target_post, COMMENTS.max)

    database.age_writes(user_id, COMMENTS.window_seconds + 1)

    assert write_comment(client, me, target_post).status_code == httpx.codes.CREATED


def test_deleted_comments_still_count(client: httpx.Client, me: dict, target_post: str):
    last = write_comments(client, me, target_post, COMMENTS.max)
    client.delete(comment(last), headers=me)

    assert write_comment(client, me, target_post).status_code == httpx.codes.TOO_MANY_REQUESTS


def test_operator_is_exempt_from_comment_limit(client: httpx.Client, operator: dict, target_post: str):
    write_comments(client, operator, target_post, COMMENTS.max)

    assert write_comment(client, operator, target_post).status_code == httpx.codes.CREATED


def test_missing_post_is_404_before_comment_limit(client: httpx.Client, me: dict, target_post: str):
    write_comments(client, me, target_post, COMMENTS.max)

    assert write_comment(client, me, '999').status_code == httpx.codes.NOT_FOUND


def test_posts_do_not_count_toward_comment_limit(client: httpx.Client, me: dict, target_post: str):
    write_posts(client, me, POSTS.max)

    assert write_comment(client, me, target_post).status_code == httpx.codes.CREATED


# 신고의 한도


@pytest.fixture
def reportable_posts(database: Database) -> None:
    """신고할 글을 넉넉히 넣는다. API 를 거치면 글 쓰기의 한도에 걸린다. 번호는 1 부터다."""
    database.insert_many_posts(REPORTS.max + 2, new_user_id())


def report(client: httpx.Client, headers: dict[str, str], post_id: int) -> httpx.Response:
    return client.post(post_reports(post_id), headers=headers, json={'reason': 'spam'})


def report_many(client: httpx.Client, headers: dict[str, str], n: int) -> None:
    """1 번 글부터 n 개를 신고한다. 모두 접수돼야 한다."""
    for post_id in range(1, n + 1):
        assert report(client, headers, post_id).status_code == httpx.codes.CREATED


@pytest.mark.usefixtures('reportable_posts')
def test_reports_up_to_limit_then_429(client: httpx.Client, me: dict):
    report_many(client, me, REPORTS.max)

    response = report(client, me, REPORTS.max + 1)

    assert_limited(response, '신고를 너무 자주 하고 있습니다. 잠시 후 다시 시도해 주세요.', REPORTS)


@pytest.mark.usefixtures('reportable_posts')
def test_report_allowed_again_after_window(client: httpx.Client, database: Database, me: dict, user_id: str):
    report_many(client, me, REPORTS.max)

    database.age_writes(user_id, REPORTS.window_seconds + 1)

    assert report(client, me, REPORTS.max + 1).status_code == httpx.codes.CREATED


@pytest.mark.usefixtures('reportable_posts')
def test_report_limit_is_per_user(client: httpx.Client, me: dict, stranger: dict):
    report_many(client, me, REPORTS.max)

    assert report(client, stranger, 1).status_code == httpx.codes.CREATED


@pytest.mark.usefixtures('reportable_posts')
def test_operator_is_exempt_from_report_limit(client: httpx.Client, operator: dict):
    report_many(client, operator, REPORTS.max)

    assert report(client, operator, REPORTS.max + 1).status_code == httpx.codes.CREATED


@pytest.mark.usefixtures('reportable_posts')
def test_duplicate_report_is_409_before_limit(client: httpx.Client, me: dict):
    report_many(client, me, REPORTS.max)

    assert report(client, me, 1).status_code == httpx.codes.CONFLICT


@pytest.mark.usefixtures('reportable_posts')
def test_posts_and_comments_do_not_count_toward_report_limit(client: httpx.Client, me: dict):
    post_id = write_posts(client, me, POSTS.max)
    write_comments(client, me, post_id, COMMENTS.max)

    assert report(client, me, 1).status_code == httpx.codes.CREATED
