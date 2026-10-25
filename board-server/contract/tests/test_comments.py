# board-server/contract/tests/test_comments.py

"""
댓글과 답글의 쓰기, 목록, 고치기, 지우기(board-server/test/comments.e2e-spec.ts).

시험마다 글쓴이가 자유 게시판(free)에 글 하나를 써 두고 시작한다. 토큰에 닉네임을 싣지 않는다.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest

from harness.database import Database
from harness.tokens import new_user_id
from tests.urls import board_posts, comment, post, post_comments

# 한 댓글에 달 수 있는 답글의 수
MAX_REPLIES_PER_COMMENT = 100
# 한 사람이 1분에 달 수 있는 댓글의 수. 이보다 많이 달 때는 시각을 옮긴다
COMMENT_LIMIT = 10
# 쓰기 한도의 창(초). 이만큼 시각을 옮기면 한도가 비워진다
COMMENT_WINDOW_SECONDS = 60

Headers = dict[str, str]


@pytest.fixture
def writer_id() -> str:
    """글을 써 둔 사람."""
    return new_user_id()


@pytest.fixture
def stranger_id() -> str:
    """글쓴이가 아닌 사람."""
    return new_user_id()


@pytest.fixture
def writer(headers_for: Callable[..., Headers], writer_id: str) -> Headers:
    return headers_for(writer_id)


@pytest.fixture
def stranger(headers_for: Callable[..., Headers], stranger_id: str) -> Headers:
    return headers_for(stranger_id)


@pytest.fixture
def post_id(client: httpx.Client, writer: Headers) -> str:
    """시험마다 새로 써 두는 글의 번호."""
    return written_post_id(client, writer)


def written_post_id(client: httpx.Client, headers: Headers, board: str = 'free') -> str:
    """글을 써서 그 번호를 돌려준다."""
    response = client.post(board_posts(board), headers=headers, json={'title': '글', 'content': '본문입니다.'})
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def add_comment(
    client: httpx.Client, headers: Headers, post_id: str, body: dict[str, Any] | None = None
) -> httpx.Response:
    """글에 댓글을 단다. 본문에 parent_id 를 주면 답글이다."""
    return client.post(post_comments(post_id), headers=headers, json=body or {'content': '댓글입니다.'})


def comment_id(
    client: httpx.Client, headers: Headers, post_id: str, content: str = '댓글입니다.', parent_id: str | None = None
) -> str:
    """댓글을 달아 그 번호를 돌려준다. 준비 단계에서 쓴다."""
    body: dict[str, Any] = {'content': content}
    if parent_id is not None:
        body['parent_id'] = parent_id
    response = add_comment(client, headers, post_id, body)
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def threads(client: httpx.Client, post_id: str, query: str = '') -> list[dict[str, Any]]:
    """댓글 목록의 줄들을 읽는다. 로그인하지 않는다."""
    response = client.get(f'{post_comments(post_id)}{query}')
    assert response.status_code == httpx.codes.OK
    return response.json()['items']


def contents(items: list[dict[str, Any]]) -> list[str | None]:
    return [item['content'] for item in items]


def ids(items: list[dict[str, Any]]) -> list[str]:
    return [item['id'] for item in items]


# 댓글 쓰기


def test_logged_in_user_comments_and_gets_201_with_the_comment(
    client: httpx.Client, stranger: Headers, stranger_id: str, post_id: str
):
    response = add_comment(client, stranger, post_id)

    assert response.status_code == httpx.codes.CREATED
    body = response.json()
    assert isinstance(body['created_at'], str)
    assert isinstance(body['updated_at'], str)
    assert {key: value for key, value in body.items() if key not in ('created_at', 'updated_at')} == {
        'id': '1',
        'post_id': post_id,
        'parent_id': None,
        'author_id': stranger_id,
        'author_nickname': None,
        'author_withdrawn': False,
        'content': '댓글입니다.',
        'deleted': False,
    }
    assert set(body) == {
        'id',
        'post_id',
        'parent_id',
        'author_id',
        'author_nickname',
        'author_withdrawn',
        'content',
        'deleted',
        'created_at',
        'updated_at',
    }


def test_null_parent_id_comments_on_the_post(client: httpx.Client, writer: Headers, post_id: str):
    response = add_comment(client, writer, post_id, {'content': '댓글', 'parent_id': None})

    assert response.status_code == httpx.codes.CREATED
    assert response.json()['parent_id'] is None


def test_commenting_without_login_is_401(client: httpx.Client, post_id: str):
    response = client.post(post_comments(post_id), json={'content': '댓글입니다.'})

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_commenting_on_missing_post_is_404(client: httpx.Client, writer: Headers):
    response = add_comment(client, writer, '999', {'content': '댓글'})

    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '글을 찾을 수 없습니다.'}


def test_cannot_comment_on_deleted_post(client: httpx.Client, writer: Headers, stranger: Headers, post_id: str):
    assert client.delete(post(post_id), headers=writer).status_code == httpx.codes.NO_CONTENT

    response = add_comment(client, stranger, post_id)

    assert response.status_code == httpx.codes.NOT_FOUND


def test_invalid_input_is_400_and_nothing_is_stored(client: httpx.Client, writer: Headers, post_id: str):
    response = add_comment(client, writer, post_id, {'content': '   '})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'content' in response.json()['errors']
    assert threads(client, post_id) == []


def test_author_comes_from_token_not_body(client: httpx.Client, writer: Headers, stranger_id: str, post_id: str):
    response = add_comment(client, writer, post_id, {'content': '댓글', 'author_id': stranger_id})

    assert response.status_code == httpx.codes.BAD_REQUEST


def test_anyone_comments_on_post_in_operator_only_board(client: httpx.Client, operator: Headers, stranger: Headers):
    notice = written_post_id(client, operator, 'notice')

    response = add_comment(client, stranger, notice, {'content': '확인했습니다.'})

    assert response.status_code == httpx.codes.CREATED


# 답글 쓰기


def test_reply_to_comment(client: httpx.Client, writer: Headers, stranger: Headers, stranger_id: str, post_id: str):
    parent = comment_id(client, writer, post_id)

    response = add_comment(client, stranger, post_id, {'content': '답글입니다.', 'parent_id': parent})

    assert response.status_code == httpx.codes.CREATED
    body = response.json()
    assert body['post_id'] == post_id
    assert body['parent_id'] == parent
    assert body['author_id'] == stranger_id
    assert body['content'] == '답글입니다.'


def test_cannot_reply_to_reply(client: httpx.Client, writer: Headers, stranger: Headers, post_id: str):
    parent = comment_id(client, writer, post_id)
    reply = comment_id(client, stranger, post_id, '답글', parent)

    response = add_comment(client, writer, post_id, {'content': '답글의 답글', 'parent_id': reply})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {'detail': '답글에는 답글을 달 수 없습니다.'}


def test_cannot_reply_to_missing_comment(client: httpx.Client, writer: Headers, post_id: str):
    response = add_comment(client, writer, post_id, {'content': '답글', 'parent_id': '999'})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {'detail': '답글을 달 댓글을 찾을 수 없습니다.'}


def test_cannot_reply_to_deleted_comment(client: httpx.Client, writer: Headers, stranger: Headers, post_id: str):
    parent = comment_id(client, writer, post_id)
    assert client.delete(comment(parent), headers=writer).status_code == httpx.codes.NO_CONTENT

    response = add_comment(client, stranger, post_id, {'content': '답글', 'parent_id': parent})

    assert response.status_code == httpx.codes.BAD_REQUEST


def test_cannot_reply_to_comment_of_another_post(client: httpx.Client, writer: Headers, post_id: str):
    parent = comment_id(client, writer, post_id)
    other_post = written_post_id(client, writer)

    response = add_comment(client, writer, other_post, {'content': '답글', 'parent_id': parent})

    # 이 글의 주소로 다른 글의 댓글 아래에 답글을 끼워 넣을 수 없다
    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {'detail': '답글을 달 댓글을 찾을 수 없습니다.'}


def test_malformed_parent_id_is_400(client: httpx.Client, writer: Headers, post_id: str):
    response = add_comment(client, writer, post_id, {'content': '답글', 'parent_id': 'abc'})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'parent_id' in response.json()['errors']


def test_full_replies_on_comment_is_409(client: httpx.Client, writer: Headers, operator: Headers, post_id: str):
    # 답글을 많이 달아야 하므로 쓰기 한도가 없는 운영자가 단다
    parent = comment_id(client, writer, post_id)
    for number in range(1, MAX_REPLIES_PER_COMMENT + 1):
        comment_id(client, operator, post_id, f'답글 {number}', parent)

    response = add_comment(client, operator, post_id, {'content': '하나 더', 'parent_id': parent})

    assert response.status_code == httpx.codes.CONFLICT
    assert response.json() == {'detail': '이 댓글에는 답글을 더 달 수 없습니다.'}


def test_deleted_reply_does_not_count_toward_reply_limit(
    client: httpx.Client, writer: Headers, operator: Headers, post_id: str
):
    parent = comment_id(client, writer, post_id)
    replies = [
        comment_id(client, operator, post_id, f'답글 {n}', parent) for n in range(1, MAX_REPLIES_PER_COMMENT + 1)
    ]
    assert client.delete(comment(replies[0]), headers=operator).status_code == httpx.codes.NO_CONTENT

    response = add_comment(client, operator, post_id, {'content': '빈자리에 하나 더', 'parent_id': parent})

    assert response.status_code == httpx.codes.CREATED


# 댓글 목록


def test_list_without_login_oldest_first_with_replies(
    client: httpx.Client,
    writer: Headers,
    writer_id: str,
    stranger: Headers,
    stranger_id: str,
    post_id: str,
):
    first = comment_id(client, writer, post_id, '첫 댓글')
    second = comment_id(client, stranger, post_id, '둘째 댓글')
    reply = comment_id(client, stranger, post_id, '첫 댓글의 답글', first)

    response = client.get(post_comments(post_id))

    assert response.status_code == httpx.codes.OK
    body = response.json()
    assert body['next'] is None
    assert len(body['items']) == 2
    head, tail = body['items']
    head_reply = head['replies'][0]
    for row in (head, head_reply):
        assert isinstance(row.pop('created_at'), str)
        assert isinstance(row.pop('updated_at'), str)
    assert head == {
        'id': first,
        'post_id': post_id,
        'parent_id': None,
        'author_id': writer_id,
        'author_nickname': None,
        'author_withdrawn': False,
        'content': '첫 댓글',
        'deleted': False,
        'replies': [
            {
                'id': reply,
                'post_id': post_id,
                'parent_id': first,
                'author_id': stranger_id,
                'author_nickname': None,
                'author_withdrawn': False,
                'content': '첫 댓글의 답글',
                'deleted': False,
            }
        ],
    }
    assert tail['id'] == second
    assert tail['content'] == '둘째 댓글'
    assert tail['replies'] == []


def test_list_without_comments_is_empty(client: httpx.Client, post_id: str):
    response = client.get(post_comments(post_id))

    assert response.json() == {'items': [], 'next': None}


def test_replies_are_grouped_per_comment_oldest_first(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    first = comment_id(client, writer, post_id, '첫 댓글')
    second = comment_id(client, writer, post_id, '둘째 댓글')
    comment_id(client, stranger, post_id, '둘째의 답글 1', second)
    comment_id(client, stranger, post_id, '첫째의 답글 1', first)
    comment_id(client, stranger, post_id, '둘째의 답글 2', second)

    one, two = threads(client, post_id)

    assert contents(one['replies']) == ['첫째의 답글 1']
    assert contents(two['replies']) == ['둘째의 답글 1', '둘째의 답글 2']


def test_list_has_only_that_posts_comments(client: httpx.Client, writer: Headers, post_id: str):
    comment_id(client, writer, post_id, '이 글의 댓글')
    other_post = written_post_id(client, writer)
    add_comment(client, writer, other_post, {'content': '다른 글의 댓글'})

    assert contents(threads(client, post_id)) == ['이 글의 댓글']


def test_cursor_pagination_does_not_count_replies(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    comment_ids = [comment_id(client, writer, post_id, f'댓글 {number}') for number in range(1, 6)]
    comment_id(client, stranger, post_id, '답글', comment_ids[0])

    first = client.get(f'{post_comments(post_id)}?size=2').json()
    second = client.get(f'{post_comments(post_id)}?size=2&after={first["next"]}').json()
    third = client.get(f'{post_comments(post_id)}?size=2&after={second["next"]}').json()

    assert contents(first['items']) == ['댓글 1', '댓글 2']
    assert len(first['items'][0]['replies']) == 1
    assert first['next'] == comment_ids[1]
    assert contents(second['items']) == ['댓글 3', '댓글 4']
    assert contents(third['items']) == ['댓글 5']
    # 뒤에 더 없으면 next 가 비어 있다
    assert third['next'] is None


def test_next_is_null_when_page_ends_exactly(client: httpx.Client, writer: Headers, post_id: str):
    comment_id(client, writer, post_id, '댓글 1')
    comment_id(client, writer, post_id, '댓글 2')

    body = client.get(f'{post_comments(post_id)}?size=2').json()

    assert len(body['items']) == 2
    assert body['next'] is None


def test_new_comment_between_pages_is_neither_duplicated_nor_skipped(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    comment_id(client, writer, post_id, '댓글 1')
    comment_id(client, writer, post_id, '댓글 2')
    comment_id(client, writer, post_id, '댓글 3')
    first = client.get(f'{post_comments(post_id)}?size=2').json()

    comment_id(client, stranger, post_id, '그사이에 달린 댓글')
    second = client.get(f'{post_comments(post_id)}?size=2&after={first["next"]}').json()

    assert contents(second['items']) == ['댓글 3', '그사이에 달린 댓글']


def test_ids_past_ten_are_ordered_numerically(
    client: httpx.Client, database: Database, writer: Headers, writer_id: str, post_id: str
):
    # 글자로 줄 세우면 '10' 이 '9' 보다 앞에 온다. 숫자로 줄 세우는지 본다
    for number in range(1, 12):
        if number == COMMENT_LIMIT + 1:
            # 1분에 열 개까지다. 시간이 흐른 것처럼 옮겨 한도를 비운다
            database.age_writes(writer_id, COMMENT_WINDOW_SECONDS + 1)
        comment_id(client, writer, post_id, f'댓글 {number}')

    response = client.get(f'{post_comments(post_id)}?size=3&after=8')

    assert ids(response.json()['items']) == ['9', '10', '11']


@pytest.mark.parametrize('query', ['?after=abc', '?after=0', '?size=0', '?size=51', '?page=2'])
def test_invalid_query_is_400(client: httpx.Client, post_id: str, query: str):
    response = client.get(f'{post_comments(post_id)}{query}')

    assert response.status_code == httpx.codes.BAD_REQUEST


def test_listing_missing_post_is_404(client: httpx.Client):
    response = client.get(post_comments('999'))

    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '글을 찾을 수 없습니다.'}


def test_comments_of_deleted_post_cannot_be_listed(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    comment_id(client, stranger, post_id)
    assert client.delete(post(post_id), headers=writer).status_code == httpx.codes.NO_CONTENT

    response = client.get(post_comments(post_id))

    assert response.status_code == httpx.codes.NOT_FOUND


# 댓글 고치기


def test_author_edits_and_gets_edited_comment(client: httpx.Client, writer: Headers, post_id: str):
    target = comment_id(client, writer, post_id)

    response = client.patch(comment(target), headers=writer, json={'content': '고친 댓글'})

    assert response.status_code == httpx.codes.OK
    assert response.json()['id'] == target
    assert response.json()['content'] == '고친 댓글'
    assert threads(client, post_id)[0]['content'] == '고친 댓글'


def test_edit_changes_updated_at_but_keeps_created_at(client: httpx.Client, writer: Headers, post_id: str):
    created = add_comment(client, writer, post_id).json()

    edited = client.patch(comment(created['id']), headers=writer, json={'content': '고친 댓글'}).json()

    assert edited['created_at'] == created['created_at']
    assert datetime.fromisoformat(edited['updated_at']) > datetime.fromisoformat(created['updated_at'])


def test_reply_can_be_edited_and_keeps_its_parent(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    parent = comment_id(client, writer, post_id)
    reply = comment_id(client, stranger, post_id, '답글', parent)

    response = client.patch(comment(reply), headers=stranger, json={'content': '고친 답글'})

    assert response.json()['parent_id'] == parent
    assert response.json()['content'] == '고친 답글'


def test_cannot_edit_someone_elses_comment(client: httpx.Client, writer: Headers, stranger: Headers, post_id: str):
    target = comment_id(client, writer, post_id)

    response = client.patch(comment(target), headers=stranger, json={'content': '남이 고친 댓글'})

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '자신의 댓글만 고칠 수 있습니다.'}
    assert threads(client, post_id)[0]['content'] == '댓글입니다.'


def test_operator_cannot_edit_someone_elses_comment(
    client: httpx.Client, writer: Headers, operator: Headers, post_id: str
):
    target = comment_id(client, writer, post_id)

    response = client.patch(comment(target), headers=operator, json={'content': '운영자가 고친 댓글'})

    assert response.status_code == httpx.codes.FORBIDDEN


def test_editing_without_login_is_401(client: httpx.Client, writer: Headers, post_id: str):
    target = comment_id(client, writer, post_id)

    response = client.patch(comment(target), json={'content': '고친 댓글'})

    assert response.status_code == httpx.codes.UNAUTHORIZED


@pytest.mark.parametrize('missing', ['999', 'abc', '0'])
def test_editing_missing_comment_is_404(client: httpx.Client, writer: Headers, missing: str):
    response = client.patch(comment(missing), headers=writer, json={'content': '고친 댓글'})

    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '댓글을 찾을 수 없습니다.'}


def test_editing_without_content_is_400(client: httpx.Client, writer: Headers, post_id: str):
    target = comment_id(client, writer, post_id)

    response = client.patch(comment(target), headers=writer, json={})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'content' in response.json()['errors']


# 댓글 지우기


def test_author_deletes_with_204_and_it_leaves_the_list(client: httpx.Client, writer: Headers, post_id: str):
    kept = comment_id(client, writer, post_id, '남는 댓글')
    removed = comment_id(client, writer, post_id, '지울 댓글')

    response = client.delete(comment(removed), headers=writer)

    assert response.status_code == httpx.codes.NO_CONTENT
    assert ids(threads(client, post_id)) == [kept]


def test_delete_keeps_row_and_records_deleted_at(
    client: httpx.Client, database: Database, writer: Headers, post_id: str
):
    target = comment_id(client, writer, post_id)

    client.delete(comment(target), headers=writer)
    row = database.row('comments', 'id', target)

    assert row is not None
    assert str(row['id']) == target
    assert row['content'] == '댓글입니다.'
    assert isinstance(row['deleted_at'], datetime)


def test_deleted_comment_with_replies_stays_as_placeholder_without_author_or_content(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    parent = comment_id(client, writer, post_id, '지울 댓글')
    reply = comment_id(client, stranger, post_id, '남는 답글', parent)

    client.delete(comment(parent), headers=writer)
    items = threads(client, post_id)

    assert len(items) == 1
    assert items[0]['id'] == parent
    assert items[0]['author_id'] is None
    assert items[0]['content'] is None
    assert items[0]['deleted'] is True
    assert ids(items[0]['replies']) == [reply]


def test_placeholder_disappears_when_all_its_replies_are_deleted(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    parent = comment_id(client, writer, post_id, '지울 댓글')
    reply = comment_id(client, stranger, post_id, '지울 답글', parent)
    client.delete(comment(parent), headers=writer)

    client.delete(comment(reply), headers=stranger)

    assert threads(client, post_id) == []


def test_deleted_reply_leaves_the_list_and_comment_stays(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    parent = comment_id(client, writer, post_id, '댓글')
    kept = comment_id(client, stranger, post_id, '남는 답글', parent)
    removed = comment_id(client, stranger, post_id, '지울 답글', parent)

    client.delete(comment(removed), headers=stranger)
    [item] = threads(client, post_id)

    assert item['id'] == parent
    assert item['deleted'] is False
    assert ids(item['replies']) == [kept]


def test_placeholder_takes_its_turn_in_cursor_pagination(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    first = comment_id(client, writer, post_id, '지울 댓글')
    comment_id(client, stranger, post_id, '답글', first)
    comment_id(client, writer, post_id, '둘째 댓글')
    comment_id(client, writer, post_id, '셋째 댓글')
    client.delete(comment(first), headers=writer)

    head = client.get(f'{post_comments(post_id)}?size=1').json()
    rest = client.get(f'{post_comments(post_id)}?size=5&after={head["next"]}').json()

    assert head['items'][0]['id'] == first
    assert head['items'][0]['deleted'] is True
    assert contents(rest['items']) == ['둘째 댓글', '셋째 댓글']


def test_cannot_delete_someone_elses_comment(client: httpx.Client, writer: Headers, stranger: Headers, post_id: str):
    target = comment_id(client, writer, post_id)

    response = client.delete(comment(target), headers=stranger)

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '자신의 댓글만 지울 수 있습니다.'}
    assert len(threads(client, post_id)) == 1


def test_post_author_cannot_delete_someone_elses_comment(
    client: httpx.Client, writer: Headers, stranger: Headers, post_id: str
):
    # 글은 writer 가 썼다. 댓글은 stranger 의 것이다
    target = comment_id(client, stranger, post_id)

    response = client.delete(comment(target), headers=writer)

    assert response.status_code == httpx.codes.FORBIDDEN


def test_operator_deletes_someone_elses_comment(client: httpx.Client, writer: Headers, operator: Headers, post_id: str):
    target = comment_id(client, writer, post_id)

    response = client.delete(comment(target), headers=operator)

    assert response.status_code == httpx.codes.NO_CONTENT
    assert threads(client, post_id) == []


def test_deleting_without_login_is_401(client: httpx.Client, writer: Headers, post_id: str):
    target = comment_id(client, writer, post_id)

    response = client.delete(comment(target))

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert len(threads(client, post_id)) == 1


def test_deleting_missing_comment_is_404(client: httpx.Client, writer: Headers):
    response = client.delete(comment('999'), headers=writer)

    assert response.status_code == httpx.codes.NOT_FOUND


def test_deleted_comment_cannot_be_deleted_or_edited_again(client: httpx.Client, writer: Headers, post_id: str):
    target = comment_id(client, writer, post_id)
    client.delete(comment(target), headers=writer)

    again = client.delete(comment(target), headers=writer)
    edited = client.patch(comment(target), headers=writer, json={'content': '되살린 댓글'})

    assert again.status_code == httpx.codes.NOT_FOUND
    assert edited.status_code == httpx.codes.NOT_FOUND
