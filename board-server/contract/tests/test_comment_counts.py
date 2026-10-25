# board-server/contract/tests/test_comment_counts.py

"""
글에 실리는 댓글 수(comment_count)(board-server/test/comment-counts.e2e-spec.ts).

세는 것은 살아 있는 댓글과 답글이다. 지운 것은 세지 않는다.
"""

from collections.abc import Callable

import httpx
import pytest

from harness.tokens import new_user_id
from tests.urls import board_posts, comment, post, post_comments

Headers = dict[str, str]


@pytest.fixture
def writer(headers_for: Callable[..., Headers]) -> Headers:
    """글을 쓰는 사람."""
    return headers_for(new_user_id())


@pytest.fixture
def stranger(headers_for: Callable[..., Headers]) -> Headers:
    """댓글을 다는 사람."""
    return headers_for(new_user_id())


def write(client: httpx.Client, headers: Headers, board: str = 'free') -> httpx.Response:
    """글을 쓴다."""
    return client.post(board_posts(board), headers=headers, json={'title': '글', 'content': '본문입니다.'})


def written_post_id(client: httpx.Client, headers: Headers, board: str = 'free') -> str:
    """글을 써서 그 번호를 돌려준다."""
    response = write(client, headers, board)
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def comment_id(client: httpx.Client, headers: Headers, post_id: str, parent_id: str | None = None) -> str:
    """댓글을 달아 그 번호를 돌려준다. parent_id 를 주면 답글이다."""
    body: dict[str, str] = {'content': '댓글입니다.'}
    if parent_id is not None:
        body['parent_id'] = parent_id
    response = client.post(post_comments(post_id), headers=headers, json=body)
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def remove_comment(client: httpx.Client, headers: Headers, target: str) -> None:
    """댓글을 지운다."""
    assert client.delete(comment(target), headers=headers).status_code == httpx.codes.NO_CONTENT


def count_on_post(client: httpx.Client, post_id: str) -> int:
    """글 하나를 읽어 그 댓글 수를 돌려준다."""
    response = client.get(post(post_id))
    assert response.status_code == httpx.codes.OK
    return response.json()['comment_count']


def counts_on_list(client: httpx.Client, board: str = 'free', query: str = '') -> dict[str, int]:
    """글 목록을 읽어 글 번호마다의 댓글 수를 돌려준다."""
    response = client.get(f'{board_posts(board)}{query}')
    assert response.status_code == httpx.codes.OK
    return {item['id']: item['comment_count'] for item in response.json()['items']}


# 글 하나의 댓글 수


def test_new_post_has_zero(client: httpx.Client, writer: Headers):
    response = write(client, writer)

    assert response.json()['comment_count'] == 0


def test_post_without_comments_has_zero(client: httpx.Client, writer: Headers):
    post_id = written_post_id(client, writer)

    assert count_on_post(client, post_id) == 0


def test_comments_and_replies_are_counted_together(client: httpx.Client, writer: Headers, stranger: Headers):
    post_id = written_post_id(client, writer)
    first = comment_id(client, stranger, post_id)
    comment_id(client, stranger, post_id)
    comment_id(client, stranger, post_id, first)

    assert count_on_post(client, post_id) == 3


def test_deleted_comment_is_not_counted(client: httpx.Client, writer: Headers, stranger: Headers):
    post_id = written_post_id(client, writer)
    comment_id(client, stranger, post_id)
    remove_comment(client, stranger, comment_id(client, stranger, post_id))

    assert count_on_post(client, post_id) == 1


def test_deleted_reply_is_not_counted(client: httpx.Client, writer: Headers, stranger: Headers):
    post_id = written_post_id(client, writer)
    parent = comment_id(client, stranger, post_id)
    remove_comment(client, stranger, comment_id(client, stranger, post_id, parent))

    assert count_on_post(client, post_id) == 1


def test_placeholder_is_not_counted_but_its_replies_are(client: httpx.Client, writer: Headers, stranger: Headers):
    post_id = written_post_id(client, writer)
    parent = comment_id(client, stranger, post_id)
    comment_id(client, stranger, post_id, parent)
    comment_id(client, stranger, post_id, parent)
    remove_comment(client, stranger, parent)

    # 화면에는 "삭제된 댓글입니다" 아래에 답글 둘이 보인다. 읽을 수 있는 글은 둘이다
    assert count_on_post(client, post_id) == 2


def test_comments_of_other_posts_are_not_counted(client: httpx.Client, writer: Headers, stranger: Headers):
    post_id = written_post_id(client, writer)
    other = written_post_id(client, writer)
    comment_id(client, stranger, other)
    comment_id(client, stranger, other)

    assert count_on_post(client, post_id) == 0


def test_edit_response_carries_count(client: httpx.Client, writer: Headers, stranger: Headers):
    post_id = written_post_id(client, writer)
    comment_id(client, stranger, post_id)

    response = client.patch(post(post_id), headers=writer, json={'title': '고친 제목'})

    assert response.status_code == httpx.codes.OK
    assert response.json()['comment_count'] == 1


# 글 목록의 댓글 수


def test_each_post_in_list_has_its_own_count(client: httpx.Client, writer: Headers, stranger: Headers):
    quiet = written_post_id(client, writer)
    busy = written_post_id(client, writer)
    removed_only = written_post_id(client, writer)
    parent = comment_id(client, stranger, busy)
    comment_id(client, stranger, busy, parent)
    comment_id(client, stranger, busy)
    remove_comment(client, stranger, comment_id(client, stranger, removed_only))

    assert counts_on_list(client) == {
        quiet: 0,
        busy: 3,
        # 달렸다가 지워진 댓글뿐인 글도 0 이다
        removed_only: 0,
    }


def test_counts_are_not_mixed_across_boards(client: httpx.Client, writer: Headers, stranger: Headers):
    free = written_post_id(client, writer, 'free')
    scenario = written_post_id(client, writer, 'scenario')
    comment_id(client, stranger, scenario)

    assert counts_on_list(client, 'free') == {free: 0}
    assert counts_on_list(client, 'scenario') == {scenario: 1}


def test_board_without_posts_is_empty(client: httpx.Client):
    assert counts_on_list(client) == {}


def test_each_page_carries_counts_for_its_posts(client: httpx.Client, writer: Headers, stranger: Headers):
    first = written_post_id(client, writer)
    second = written_post_id(client, writer)
    third = written_post_id(client, writer)
    comment_id(client, stranger, first)
    comment_id(client, stranger, third)
    comment_id(client, stranger, third)

    # 새 글부터다. 1쪽에 third 와 second, 2쪽에 first 가 온다
    assert counts_on_list(client, 'free', '?size=2&page=1') == {third: 2, second: 0}
    assert counts_on_list(client, 'free', '?size=2&page=2') == {first: 1}
