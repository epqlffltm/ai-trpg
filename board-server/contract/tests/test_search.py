# board-server/contract/tests/test_search.py

"""
글 검색(GET /posts?q=).

notice 의 글은 운영자가, 나머지는 글쓴이가 쓴다. 한 사람이 10분에 쓰는 글은 다섯 개까지라
그보다 많이 쓰는 시험은 여러 사람이 나눠 쓴다.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from harness.tokens import new_user_id
from tests.urls import POSTS, board_posts, post, post_comments, post_pin

# 한 사람이 10분에 쓰는 글의 한도
POSTS_PER_WRITER = 5

Headers = Callable[..., dict[str, str]]


class Writers:
    """글을 쓰는 사람들. 글쓴이는 다섯 개마다 새 사람으로 바뀐다. notice 는 운영자가 쓴다."""

    def __init__(self, client: httpx.Client, headers_for: Headers) -> None:
        self.client = client
        self.headers_for = headers_for
        self.writer = new_user_id()
        self.operator = headers_for(new_user_id(), operator=True)
        self._written = 0

    def writer_headers(self) -> dict[str, str]:
        return self.headers_for(self.writer)

    def _next_writer(self) -> dict[str, str]:
        if self._written and self._written % POSTS_PER_WRITER == 0:
            self.writer = new_user_id()
        self._written += 1
        return self.writer_headers()

    def write(self, title: str, content: str = '본문입니다.', board: str = 'free') -> str:
        """글을 써서 그 번호를 돌려준다."""
        headers = self.operator if board == 'notice' else self._next_writer()
        response = self.client.post(board_posts(board), headers=headers, json={'title': title, 'content': content})
        assert response.status_code == httpx.codes.CREATED
        return response.json()['id']


@pytest.fixture
def writers(client: httpx.Client, headers_for: Headers) -> Writers:
    return Writers(client, headers_for)


def search(client: httpx.Client, params: Any) -> httpx.Response:
    """글을 검색한다. 로그인하지 않는다."""
    return client.get(POSTS, params=params)


def found_ids(client: httpx.Client, q: str, **more: str) -> list[str]:
    """검색해서 찾은 글의 번호들."""
    response = search(client, {'q': q, **more})
    assert response.status_code == httpx.codes.OK
    return [item['id'] for item in response.json()['items']]


# 글 검색


def test_search_without_login_returns_list_shape(client: httpx.Client, writers: Writers):
    post_id = writers.write('고정 버그를 찾았습니다', '본문에는 없는 말')

    response = search(client, {'q': '버그'})

    assert response.status_code == httpx.codes.OK
    body = response.json()
    item = body['items'][0]
    assert isinstance(item.pop('created_at'), str)
    assert isinstance(item.pop('updated_at'), str)
    assert body == {
        'items': [
            {
                'id': post_id,
                'board': 'free',
                'author_id': writers.writer,
                'author_nickname': None,
                'author_withdrawn': False,
                'title': '고정 버그를 찾았습니다',
                'comment_count': 0,
                'pinned': False,
                'pinned_until': None,
            }
        ],
        'page': 1,
        'size': 20,
        'total': 1,
    }


def test_search_matches_title_and_content(client: httpx.Client, writers: Writers):
    in_title = writers.write('주사위 이야기', '본문입니다.')
    in_content = writers.write('제목', '어제 주사위를 굴렸다.')
    writers.write('상관없는 글', '상관없는 본문')

    assert found_ids(client, '주사위') == [in_content, in_title]


def test_search_matches_anywhere_in_a_word(client: httpx.Client, writers: Writers):
    post_id = writers.write('공지사항을 읽어 주세요')

    assert found_ids(client, '공지') == [post_id]
    assert found_ids(client, '지사') == [post_id]


def test_search_requires_all_words(client: httpx.Client, writers: Writers):
    both = writers.write('고정 기능', '버그가 있습니다')
    writers.write('고정 기능', '잘 됩니다')
    writers.write('다른 글', '버그가 있습니다')

    # 한 낱말은 제목에, 다른 낱말은 본문에 있어도 된다
    assert found_ids(client, '고정 버그') == [both]
    assert found_ids(client, '버그   고정') == [both]


def test_search_is_case_insensitive(client: httpx.Client, writers: Writers):
    post_id = writers.write('NestJS 질문')

    assert found_ids(client, 'nestjs') == [post_id]
    assert found_ids(client, 'NESTJS') == [post_id]


def test_search_returns_newest_first(client: httpx.Client, writers: Writers):
    first = writers.write('주사위 하나')
    second = writers.write('주사위 둘')
    third = writers.write('주사위 셋')

    assert found_ids(client, '주사위') == [third, second, first]


def test_search_with_no_match_is_empty(client: httpx.Client, writers: Writers):
    writers.write('주사위 이야기')

    response = search(client, {'q': '없는낱말'})

    assert response.status_code == httpx.codes.OK
    assert response.json() == {'items': [], 'page': 1, 'size': 20, 'total': 0}


def test_search_results_have_no_content(client: httpx.Client, writers: Writers):
    writers.write('주사위 이야기', '길고 긴 본문')

    response = search(client, {'q': '주사위'})

    assert 'content' not in response.json()['items'][0]


# 검색어의 기호


def test_percent_is_literal(client: httpx.Client, writers: Writers):
    percent = writers.write('확률은 50%입니다')
    writers.write('확률은 500입니다')

    assert found_ids(client, '50%') == [percent]


def test_underscore_is_literal(client: httpx.Client, writers: Writers):
    underscore = writers.write('snake_case 로 적는다')
    writers.write('snakeXcase 로 적는다')

    assert found_ids(client, 'snake_case') == [underscore]


def test_backslash_is_literal(client: httpx.Client, writers: Writers):
    backslash = writers.write('경로는 C:\\temp 입니다')
    writers.write('경로는 C:temp 입니다')

    assert found_ids(client, 'C:\\temp') == [backslash]


def test_sql_like_text_is_literal(client: httpx.Client, writers: Writers):
    quoted = writers.write("제목에 '; DROP TABLE posts; -- 이 있다")
    writers.write('평범한 글')

    assert found_ids(client, "'; DROP TABLE posts; --") == [quoted]
    # 글이 지워지지도 않았다
    assert len(found_ids(client, '평범한')) == 1


# 검색의 범위


def test_search_without_board_covers_all_boards(client: httpx.Client, writers: Writers):
    in_free = writers.write('주사위 이야기', '본문', 'free')
    in_scenario = writers.write('주사위 시나리오', '본문', 'scenario')
    in_notice = writers.write('주사위 공지', '본문', 'notice')

    body = search(client, {'q': '주사위'}).json()

    assert body['total'] == 3
    # 글마다 어느 게시판의 글인지 실린다
    assert [[item['id'], item['board']] for item in body['items']] == [
        [in_notice, 'notice'],
        [in_scenario, 'scenario'],
        [in_free, 'free'],
    ]


def test_search_with_board_covers_only_that_board(client: httpx.Client, writers: Writers):
    in_free = writers.write('주사위 이야기', '본문', 'free')
    writers.write('주사위 시나리오', '본문', 'scenario')

    assert found_ids(client, '주사위', board='free') == [in_free]


def test_search_in_unknown_board_is_404(client: httpx.Client):
    response = search(client, {'q': '주사위', 'board': 'no-such-board'})

    assert response.status_code == httpx.codes.NOT_FOUND
    assert response.json() == {'detail': '게시판을 찾을 수 없습니다.'}


def test_deleted_posts_are_not_found(client: httpx.Client, writers: Writers):
    kept = writers.write('주사위 하나')
    removed = writers.write('주사위 둘')
    assert client.delete(post(removed), headers=writers.writer_headers()).status_code == httpx.codes.NO_CONTENT

    body = search(client, {'q': '주사위'}).json()

    assert body['total'] == 1
    assert body['items'][0]['id'] == kept


def test_pinned_post_appears_in_its_own_place(client: httpx.Client, writers: Writers):
    first = writers.write('주사위 하나')
    pinned = writers.write('주사위 둘')
    last = writers.write('주사위 셋')
    assert client.put(post_pin(pinned), headers=writers.operator).is_success

    body = search(client, {'q': '주사위'}).json()

    # 글 목록처럼 따로 싣지 않는다. 찾은 글을 새 글부터 보여 줄 뿐이다
    assert 'pinned' not in body
    assert [[item['id'], item['pinned']] for item in body['items']] == [
        [last, False],
        [pinned, True],
        [first, False],
    ]


def test_search_results_carry_comment_count(client: httpx.Client, writers: Writers):
    post_id = writers.write('주사위 이야기')
    response = client.post(post_comments(post_id), headers=writers.writer_headers(), json={'content': '댓글입니다.'})
    assert response.status_code == httpx.codes.CREATED

    body = search(client, {'q': '주사위'}).json()

    assert body['items'][0]['comment_count'] == 1


def test_comments_are_not_searched(client: httpx.Client, writers: Writers):
    post_id = writers.write('제목')
    response = client.post(
        post_comments(post_id), headers=writers.writer_headers(), json={'content': '댓글에만 있는 낱말 주사위'}
    )
    assert response.status_code == httpx.codes.CREATED

    assert found_ids(client, '주사위') == []


# 검색 결과의 쪽


def test_search_is_paginated_with_total(client: httpx.Client, writers: Writers):
    ids = [writers.write(f'주사위 {number}') for number in range(1, 6)]
    writers.write('상관없는 글')

    first = search(client, {'q': '주사위', 'size': '2', 'page': '1'}).json()
    third = search(client, {'q': '주사위', 'size': '2', 'page': '3'}).json()

    assert {key: first[key] for key in ('page', 'size', 'total')} == {'page': 1, 'size': 2, 'total': 5}
    assert [item['id'] for item in first['items']] == [ids[4], ids[3]]
    assert [item['id'] for item in third['items']] == [ids[0]]


# 틀린 검색어


@pytest.mark.parametrize(
    'params',
    [
        pytest.param({}, id='missing'),
        pytest.param({'q': ''}, id='empty'),
        pytest.param({'q': '가'}, id='one_character'),
        pytest.param({'q': '주사위 가'}, id='one_character_word'),
        pytest.param({'q': '하나 두울 세엣 네엣 다섯 여섯'}, id='too_many_words'),
        pytest.param({'q': '가' * 51}, id='too_long'),
        pytest.param([('q', '주사위'), ('q', '버그')], id='repeated'),
    ],
)
def test_invalid_query_is_400(client: httpx.Client, params: Any):
    response = search(client, params)

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'q' in response.json()['errors']


def test_query_with_nul_is_400(client: httpx.Client):
    # DB 에 그대로 물으면 DB 가 오류를 낸다. DB 까지 가지 않는다
    response = client.get(f'{POSTS}?q=%EC%A3%BC%EC%82%AC%EC%9C%84%00')

    assert response.status_code == httpx.codes.BAD_REQUEST


def test_malformed_board_slug_is_400(client: httpx.Client):
    response = search(client, {'q': '주사위', 'board': "free'--"})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'board' in response.json()['errors']


def test_unknown_parameter_is_400(client: httpx.Client):
    response = search(client, {'q': '주사위', 'sort': 'old'})

    assert response.status_code == httpx.codes.BAD_REQUEST


# 글 하나를 읽는 주소와 섞이지 않는다


def test_post_path_reads_and_query_searches(client: httpx.Client, writers: Writers):
    post_id = writers.write('주사위 이야기')

    read = client.get(post(post_id))
    found = search(client, {'q': '주사위'})

    assert 'content' in read.json()
    assert 'items' in found.json()
