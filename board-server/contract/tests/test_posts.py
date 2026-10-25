# board-server/contract/tests/test_posts.py

"""
글 쓰기, 읽기, 목록, 고치기, 지우기.

notice 는 운영자만 쓰고, free 는 로그인한 누구나 쓴다. 운영자는 토큰의 역할(roles)로 정한다.
토큰에 닉네임을 싣지 않는다. 그래서 글쓴이의 닉네임은 null 이다.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import pytest

from harness.database import Database
from harness.tokens import new_user_id
from tests.urls import board_posts, post

POST = {'title': '첫 글', 'content': '본문입니다.'}
# 한 사람이 10분에 쓰는 글의 한도. 넘게 써야 하는 시험은 여러 사람이 나눠 쓴다
POSTS_PER_WRITER = 5

Headers = Callable[..., dict[str, str]]


@pytest.fixture
def writer() -> str:
    return new_user_id()


@pytest.fixture
def stranger() -> str:
    return new_user_id()


@pytest.fixture
def operator_id() -> str:
    return new_user_id()


def write(
    client: httpx.Client, headers: dict[str, str], board: str = 'free', body: dict[str, Any] | None = None
) -> httpx.Response:
    """게시판에 글을 쓴다."""
    return client.post(board_posts(board), headers=headers, json=POST if body is None else body)


def written_id(client: httpx.Client, headers: dict[str, str], board: str = 'free', title: str = POST['title']) -> str:
    """글을 써서 그 번호를 돌려준다. 준비 단계에서 쓴다."""
    response = write(client, headers, board, {**POST, 'title': title})
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def write_many(client: httpx.Client, headers_for: Headers, titles: list[str]) -> list[str]:
    """글을 차례로 많이 쓴다. 쓰기 한도에 걸리지 않게 다섯 개마다 사람을 바꾼다."""
    ids: list[str] = []
    headers = headers_for(new_user_id())
    for index, title in enumerate(titles):
        if index and index % POSTS_PER_WRITER == 0:
            headers = headers_for(new_user_id())
        ids.append(written_id(client, headers, title=title))
    return ids


def list_posts(client: httpx.Client, board: str = 'free', params: dict[str, str] | None = None) -> httpx.Response:
    """글 목록을 읽는다. 로그인하지 않는다."""
    return client.get(board_posts(board), params=params)


def total(client: httpx.Client, board: str = 'free') -> int:
    return list_posts(client, board).json()['total']


def summary(post_id: str, author_id: str, title: str) -> dict[str, Any]:
    """목록의 한 줄. 시각은 실린 것만 본다."""
    return {
        'id': post_id,
        'board': 'free',
        'author_id': author_id,
        'author_nickname': None,
        'author_withdrawn': False,
        'title': title,
        'comment_count': 0,
        'pinned': False,
        'pinned_until': None,
    }


def without_times(item: dict[str, Any]) -> dict[str, Any]:
    assert isinstance(item.pop('created_at'), str)
    assert isinstance(item.pop('updated_at'), str)
    return item


# 글 쓰기


def test_writing_returns_201_and_the_post(client: httpx.Client, headers_for: Headers, writer: str):
    response = write(client, headers_for(writer))

    assert response.status_code == httpx.codes.CREATED
    body = response.json()
    assert body['updated_at'] == body['created_at']
    assert without_times(dict(body)) == {**summary('1', writer, '첫 글'), 'content': '본문입니다.'}


def test_post_ids_are_sequential_strings(client: httpx.Client, headers_for: Headers, writer: str):
    first = written_id(client, headers_for(writer))
    second = written_id(client, headers_for(writer), 'scenario')

    # 게시판마다 따로 세지 않는다
    assert [first, second] == ['1', '2']


def test_author_comes_from_token_not_body(client: httpx.Client, headers_for: Headers, writer: str, stranger: str):
    response = write(
        client,
        headers_for(writer),
        body={**POST, 'author_id': stranger, 'author_nickname': None, 'author_withdrawn': False},
    )

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'author_id' in response.json()['errors']


def test_writing_without_login_is_401(client: httpx.Client):
    response = client.post(board_posts('free'), json=POST)

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.json() == {'detail': '인증이 필요합니다.'}


def test_writing_to_unknown_board_is_404(client: httpx.Client, headers_for: Headers, writer: str):
    response = write(client, headers_for(writer), 'no-such-board')

    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '게시판을 찾을 수 없습니다.'}


def test_invalid_input_is_400_and_not_saved(client: httpx.Client, headers_for: Headers, writer: str):
    response = write(client, headers_for(writer), body={'title': '', 'content': ''})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert list(response.json()['errors']) == ['title', 'content']
    assert total(client) == 0


def test_title_is_trimmed_and_content_kept_as_is(client: httpx.Client, headers_for: Headers, writer: str):
    content = '  들여쓴 첫 줄\n\n<script>alert(1)</script>\n'

    response = write(client, headers_for(writer), body={'title': '  제목  ', 'content': content})

    # 서버는 HTML 로 해석하지도 지우지도 않는다. 받은 글자 그대로다
    assert response.json()['title'] == '제목'
    assert response.json()['content'] == content


def test_non_operator_cannot_write_to_operator_board(client: httpx.Client, headers_for: Headers, writer: str):
    response = write(client, headers_for(writer), 'notice')

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '이 게시판에는 운영자만 글을 쓸 수 있습니다.'}
    assert total(client, 'notice') == 0


def test_operator_writes_to_operator_board(client: httpx.Client, headers_for: Headers, operator_id: str):
    response = write(client, headers_for(operator_id, operator=True), 'notice')

    assert response.status_code == httpx.codes.CREATED
    body = response.json()
    assert body['board'] == 'notice'
    assert body['author_id'] == operator_id
    assert body['author_nickname'] is None
    assert body['author_withdrawn'] is False


# 글 읽기


def test_reading_returns_post_with_content_without_login(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = client.get(post(post_id))

    assert response.status_code == httpx.codes.OK
    assert without_times(response.json()) == {**summary(post_id, writer, '첫 글'), 'content': '본문입니다.'}


def test_reading_unknown_post_is_404(client: httpx.Client):
    response = client.get(post('999'))

    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '글을 찾을 수 없습니다.'}


@pytest.mark.parametrize('post_id', ['abc', '0', '-1', '1.5', '99999999999999999999999'])
def test_reading_malformed_post_id_is_404(client: httpx.Client, post_id: str):
    response = client.get(post(post_id))

    # DB 까지 가지 않는다. 숫자가 아닌 값을 bigint 칸에 물으면 DB 가 오류를 낸다
    assert response.status_code == httpx.codes.NOT_FOUND


# 글 목록


def test_list_is_newest_first_without_content(client: httpx.Client, headers_for: Headers, writer: str, stranger: str):
    written_id(client, headers_for(writer), title='먼저 쓴 글')
    written_id(client, headers_for(stranger), title='나중에 쓴 글')

    response = list_posts(client)

    assert response.status_code == httpx.codes.OK
    body = response.json()
    items = [without_times(item) for item in body.pop('items')]
    assert items == [summary('2', stranger, '나중에 쓴 글'), summary('1', writer, '먼저 쓴 글')]
    assert body == {'page': 1, 'size': 20, 'total': 2, 'pinned': []}


def test_empty_list(client: httpx.Client):
    response = list_posts(client)

    assert response.json() == {'pinned': [], 'items': [], 'page': 1, 'size': 20, 'total': 0}


def test_list_only_has_that_boards_posts(client: httpx.Client, headers_for: Headers, writer: str):
    written_id(client, headers_for(writer), title='자유')
    written_id(client, headers_for(writer), 'scenario', '시나리오')

    body = list_posts(client, 'scenario').json()

    assert body['total'] == 1
    assert body['items'][0]['title'] == '시나리오'


def test_list_is_paginated(client: httpx.Client, headers_for: Headers, writer: str):
    headers = headers_for(writer)
    for number in range(1, 6):
        written_id(client, headers, title=f'글 {number}')

    def titles(response: httpx.Response) -> list[str]:
        return [item['title'] for item in response.json()['items']]

    first = list_posts(client, params={'page': '1', 'size': '2'})
    second = list_posts(client, params={'page': '2', 'size': '2'})
    third = list_posts(client, params={'page': '3', 'size': '2'})
    beyond = list_posts(client, params={'page': '4', 'size': '2'})

    assert titles(first) == ['글 5', '글 4']
    assert titles(second) == ['글 3', '글 2']
    assert titles(third) == ['글 1']
    # 끝을 넘은 쪽은 오류가 아니라 빈 목록이다. 전체 개수는 그대로 알려 준다
    assert beyond.json() == {'pinned': [], 'items': [], 'page': 4, 'size': 2, 'total': 5}
    assert {key: second.json()[key] for key in ('page', 'size', 'total')} == {'page': 2, 'size': 2, 'total': 5}


def test_ids_past_ten_are_ordered_numerically(client: httpx.Client, headers_for: Headers):
    # 글자로 줄 세우면 '9' 가 '10' 보다 앞에 온다. 숫자로 줄 세우는지 본다
    write_many(client, headers_for, [f'글 {number}' for number in range(1, 12)])

    response = list_posts(client, params={'size': '3'})

    assert [item['id'] for item in response.json()['items']] == ['11', '10', '9']


@pytest.mark.parametrize('params', [{'page': '0'}, {'page': 'abc'}, {'size': '0'}, {'size': '51'}, {'size': 'all'}])
def test_invalid_page_or_size_is_400(client: httpx.Client, params: dict[str, str]):
    response = list_posts(client, params=params)

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json()['detail'] == '입력이 올바르지 않습니다.'


def test_list_of_unknown_board_is_404(client: httpx.Client):
    response = list_posts(client, 'no-such-board')

    assert response.status_code == httpx.codes.NOT_FOUND


@pytest.mark.parametrize('board', ['%00', 'FREE', "free'--", 'a' * 31])
def test_list_of_malformed_board_slug_is_404(client: httpx.Client, board: str):
    response = list_posts(client, board)

    # DB 까지 가지 않는다. NUL 글자를 DB 에 물으면 DB 가 오류를 낸다
    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '게시판을 찾을 수 없습니다.'}


# 글 고치기


def edit(client: httpx.Client, headers: dict[str, str], post_id: str, body: dict[str, Any]) -> httpx.Response:
    return client.patch(post(post_id), headers=headers, json=body)


def title_of(client: httpx.Client, post_id: str) -> str:
    return client.get(post(post_id)).json()['title']


def test_author_edits_only_sent_fields(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = edit(client, headers_for(writer), post_id, {'title': '고친 제목'})

    assert response.status_code == httpx.codes.OK
    body = response.json()
    assert (body['id'], body['board'], body['title'], body['content']) == (post_id, 'free', '고친 제목', '본문입니다.')
    assert title_of(client, post_id) == '고친 제목'


def test_editing_changes_updated_at_but_not_created_at(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))
    before = client.get(post(post_id)).json()

    response = edit(client, headers_for(writer), post_id, {'content': '고친 본문'})

    assert response.json()['created_at'] == before['created_at']
    assert datetime.fromisoformat(response.json()['updated_at']) > datetime.fromisoformat(before['updated_at'])


def test_cannot_edit_someone_elses_post(client: httpx.Client, headers_for: Headers, writer: str, stranger: str):
    post_id = written_id(client, headers_for(writer))

    response = edit(client, headers_for(stranger), post_id, {'title': '남이 고친 제목'})

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '자신의 글만 고칠 수 있습니다.'}
    assert title_of(client, post_id) == '첫 글'


def test_operator_cannot_edit_someone_elses_post(
    client: httpx.Client, headers_for: Headers, writer: str, operator_id: str
):
    post_id = written_id(client, headers_for(writer))

    response = edit(client, headers_for(operator_id, operator=True), post_id, {'title': '운영자가 고친 제목'})

    assert response.status_code == httpx.codes.FORBIDDEN


def test_current_operator_author_edits_operator_board_post(
    client: httpx.Client, headers_for: Headers, operator_id: str
):
    headers = headers_for(operator_id, operator=True)
    post_id = written_id(client, headers, 'notice')

    response = edit(client, headers, post_id, {'title': '고친 공지'})

    assert response.status_code == httpx.codes.OK
    assert response.json()['title'] == '고친 공지'


def test_demoted_author_cannot_edit_operator_board_post(client: httpx.Client, headers_for: Headers, operator_id: str):
    post_id = written_id(client, headers_for(operator_id, operator=True), 'notice')

    # 운영자에서 내려온 뒤의 토큰에는 역할이 없다
    response = edit(client, headers_for(operator_id), post_id, {'title': '내려온 뒤에 고친 공지'})

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '이 게시판의 글은 지금 운영자인 글쓴이만 고칠 수 있습니다.'}
    assert title_of(client, post_id) == POST['title']


def test_another_operator_cannot_edit_someone_elses_notice(
    client: httpx.Client, headers_for: Headers, operator_id: str
):
    post_id = written_id(client, headers_for(operator_id, operator=True), 'notice')

    response = edit(client, headers_for(new_user_id(), operator=True), post_id, {'title': '남이 고친 공지'})

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '자신의 글만 고칠 수 있습니다.'}


def test_editing_without_login_is_401(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = client.patch(post(post_id), json={'title': '고친 제목'})

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_editing_unknown_post_is_404(client: httpx.Client, headers_for: Headers, writer: str):
    response = edit(client, headers_for(writer), '999', {'title': '고친 제목'})

    assert response.status_code == httpx.codes.NOT_FOUND


def test_editing_with_no_fields_is_400(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = edit(client, headers_for(writer), post_id, {})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {'detail': '고칠 내용을 적어야 합니다.'}


def test_invalid_edit_is_400_and_not_applied(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = edit(client, headers_for(writer), post_id, {'title': '   '})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert title_of(client, post_id) == '첫 글'


def test_board_cannot_be_moved(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = edit(client, headers_for(writer), post_id, {'board': 'notice'})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'board' in response.json()['errors']


# 글 지우기


def remove(client: httpx.Client, headers: dict[str, str], post_id: str) -> httpx.Response:
    return client.delete(post(post_id), headers=headers)


def test_author_deletes_with_204_and_post_is_gone(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = remove(client, headers_for(writer), post_id)

    assert response.status_code == httpx.codes.NO_CONTENT
    assert response.text == ''
    assert client.get(post(post_id)).status_code == httpx.codes.NOT_FOUND


def test_deleted_post_is_not_listed_or_counted(client: httpx.Client, headers_for: Headers, writer: str):
    kept = written_id(client, headers_for(writer), title='남는 글')
    removed = written_id(client, headers_for(writer), title='지울 글')

    remove(client, headers_for(writer), removed)
    body = list_posts(client).json()

    assert body['total'] == 1
    assert [item['id'] for item in body['items']] == [kept]


def test_deleting_keeps_row_with_deleted_at(
    client: httpx.Client, headers_for: Headers, writer: str, database: Database
):
    post_id = written_id(client, headers_for(writer))

    remove(client, headers_for(writer), post_id)
    row = database.row('posts', 'id', int(post_id))

    assert row is not None
    assert (str(row['id']), row['title']) == (post_id, '첫 글')
    assert isinstance(row['deleted_at'], datetime)


def test_cannot_delete_someone_elses_post(client: httpx.Client, headers_for: Headers, writer: str, stranger: str):
    post_id = written_id(client, headers_for(writer))

    response = remove(client, headers_for(stranger), post_id)

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '자신의 글만 지울 수 있습니다.'}
    assert client.get(post(post_id)).status_code == httpx.codes.OK


def test_operator_deletes_someone_elses_post(client: httpx.Client, headers_for: Headers, writer: str, operator_id: str):
    post_id = written_id(client, headers_for(writer))

    response = remove(client, headers_for(operator_id, operator=True), post_id)

    assert response.status_code == httpx.codes.NO_CONTENT
    assert client.get(post(post_id)).status_code == httpx.codes.NOT_FOUND


def test_operator_deletes_operator_board_post(client: httpx.Client, headers_for: Headers, operator_id: str):
    headers = headers_for(operator_id, operator=True)
    post_id = written_id(client, headers, 'notice')

    response = remove(client, headers, post_id)

    assert response.status_code == httpx.codes.NO_CONTENT
    assert client.get(post(post_id)).status_code == httpx.codes.NOT_FOUND


def test_demoted_author_cannot_delete_operator_board_post(client: httpx.Client, headers_for: Headers, operator_id: str):
    post_id = written_id(client, headers_for(operator_id, operator=True), 'notice')

    response = remove(client, headers_for(operator_id), post_id)

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '이 게시판의 글은 운영자만 지울 수 있습니다.'}
    assert client.get(post(post_id)).status_code == httpx.codes.OK


def test_deleting_without_login_is_401(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))

    response = client.delete(post(post_id))

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert client.get(post(post_id)).status_code == httpx.codes.OK


def test_deleting_unknown_post_is_404(client: httpx.Client, headers_for: Headers, writer: str):
    response = remove(client, headers_for(writer), '999')

    assert response.status_code == httpx.codes.NOT_FOUND


def test_deleting_twice_is_404(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))
    remove(client, headers_for(writer), post_id)

    response = remove(client, headers_for(writer), post_id)

    assert response.status_code == httpx.codes.NOT_FOUND


def test_deleted_post_cannot_be_edited(client: httpx.Client, headers_for: Headers, writer: str):
    post_id = written_id(client, headers_for(writer))
    remove(client, headers_for(writer), post_id)

    response = edit(client, headers_for(writer), post_id, {'title': '되살린 제목'})

    assert response.status_code == httpx.codes.NOT_FOUND
