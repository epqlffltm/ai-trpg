# board-server/contract/tests/test_pins.py

"""
글 고정(PUT, DELETE /posts/{id}/pin)과 글 목록의 고정한 글(board-server/test/pins.e2e-spec.ts).

시간이 흘러 고정이 끝나는 것은 기다리지 않는다. 끝나는 시각을 DB 에서 지난 시각으로 바꿔 놓고 본다(expire_pin).
글 쓰기의 한도(10분에 5개)가 실제 값이라, 글을 여섯 개 넘게 쓰는 시험은 글마다 새 사람을 쓴다.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
import pytest

from harness.database import Database
from harness.tokens import new_user_id
from tests.urls import board_posts, post, post_comments, post_pin

# 서버가 정해 둔 고정의 규칙
MAX_PINS_PER_BOARD = 5
DEFAULT_PIN_DAYS = 7
MAX_PIN_DAYS = 365
DAY = timedelta(days=1)


def now() -> datetime:
    return datetime.now().astimezone()


def written_id(client: httpx.Client, headers: dict[str, str], board: str = 'free') -> str:
    """글을 써서 그 번호를 돌려준다."""
    response = client.post(board_posts(board), headers=headers, json={'title': '글', 'content': '본문입니다.'})
    assert response.status_code == httpx.codes.CREATED
    return response.json()['id']


def pin(client: httpx.Client, headers: dict[str, str], post_id: object, body: object = None) -> httpx.Response:
    """글을 고정한다. body 를 주지 않으면 본문 없이 부른다."""
    if body is None:
        return client.put(post_pin(post_id), headers=headers)
    return client.put(post_pin(post_id), headers=headers, json=body)


def pinned(client: httpx.Client, operator: dict[str, str], post_id: str, body: object = None) -> None:
    """운영자로 글을 고정한다. 준비 단계에서 쓴다."""
    assert pin(client, operator, post_id, body).status_code == httpx.codes.NO_CONTENT


def unpin(client: httpx.Client, headers: dict[str, str], post_id: object) -> httpx.Response:
    return client.delete(post_pin(post_id), headers=headers)


def read(client: httpx.Client, post_id: str) -> dict:
    response = client.get(post(post_id))
    assert response.status_code == httpx.codes.OK
    return response.json()


def listing(client: httpx.Client, board: str = 'free', params: dict | None = None) -> dict:
    response = client.get(board_posts(board), params=params)
    assert response.status_code == httpx.codes.OK
    return response.json()


def ids(posts: list[dict]) -> list[str]:
    return [item['id'] for item in posts]


def pinned_until(client: httpx.Client, post_id: str) -> datetime:
    return datetime.fromisoformat(read(client, post_id)['pinned_until'])


@pytest.fixture
def fresh_writer(headers_for: Callable[..., dict[str, str]]) -> Callable[[], dict[str, str]]:
    """부를 때마다 새 사람의 머리말. 글 쓰기의 한도에 걸리지 않게 글마다 다른 사람이 쓴다."""

    def make() -> dict[str, str]:
        return headers_for(new_user_id(), nickname='글쓴이')

    return make


@pytest.fixture
def pin_many(
    client: httpx.Client, operator: dict[str, str], fresh_writer: Callable[[], dict[str, str]]
) -> Callable[..., list[str]]:
    """글을 n 개 써서 모두 고정한다."""

    def make(n: int, board: str = 'free') -> list[str]:
        written = []
        for _ in range(n):
            post_id = written_id(client, fresh_writer(), board)
            pinned(client, operator, post_id)
            written.append(post_id)
        return written

    return make


# 글 고정하기


def test_operator_pin_returns_204_without_body(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)

    response = pin(client, operator, post_id)

    assert response.status_code == httpx.codes.NO_CONTENT
    assert response.text == ''
    assert read(client, post_id)['pinned'] is True


def test_pin_without_days_uses_default_period(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)
    before = now()

    pinned(client, operator, post_id)

    until = pinned_until(client, post_id)
    # 응답의 시각은 밀리초까지라 앞쪽에 1초의 여유를 둔다
    assert until >= before + DEFAULT_PIN_DAYS * DAY - timedelta(seconds=1)
    assert until <= now() + DEFAULT_PIN_DAYS * DAY


def test_pin_uses_given_days(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)
    before = now()

    pinned(client, operator, post_id, {'days': 30})

    until = pinned_until(client, post_id)
    assert until >= before + 30 * DAY - timedelta(seconds=1)
    assert until <= now() + 30 * DAY


@pytest.mark.parametrize('days', [0, -1, 1.5, MAX_PIN_DAYS + 1, '7', None])
def test_invalid_days_is_400_and_not_pinned(client: httpx.Client, me: dict, operator: dict, days: object):
    post_id = written_id(client, me)

    response = client.put(post_pin(post_id), headers=operator, json={'days': days})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert 'days' in response.json()['errors']
    assert read(client, post_id)['pinned'] is False


def test_unknown_field_is_400(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)

    response = pin(client, operator, post_id, {'until': '2099-01-01'})

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert read(client, post_id)['pinned'] is False


def test_longest_period_is_accepted(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)

    assert pin(client, operator, post_id, {'days': MAX_PIN_DAYS}).status_code == httpx.codes.NO_CONTENT


def test_non_operator_cannot_pin_even_own_post(client: httpx.Client, me: dict):
    post_id = written_id(client, me)

    response = pin(client, me, post_id)

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '운영자만 글을 고정할 수 있습니다.'}
    assert read(client, post_id)['pinned'] is False


def test_pin_without_login_is_401(client: httpx.Client, me: dict):
    post_id = written_id(client, me)

    response = client.put(post_pin(post_id))

    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert read(client, post_id)['pinned'] is False


def test_pin_missing_post_is_404_even_for_non_operator(client: httpx.Client, me: dict, operator: dict):
    assert pin(client, operator, '999').status_code == httpx.codes.NOT_FOUND
    assert pin(client, me, '999').status_code == httpx.codes.NOT_FOUND
    assert pin(client, operator, 'abc').status_code == httpx.codes.NOT_FOUND


def test_deleted_post_cannot_be_pinned(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)
    client.delete(post(post_id), headers=me)

    assert pin(client, operator, post_id).status_code == httpx.codes.NOT_FOUND


def test_pinning_again_resets_period(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)
    pinned(client, operator, post_id, {'days': 1})
    first = pinned_until(client, post_id)

    pinned(client, operator, post_id, {'days': 10})

    second = pinned_until(client, post_id)
    assert second - first >= 9 * DAY


def test_pin_does_not_change_updated_at(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)
    before = read(client, post_id)['updated_at']

    pinned(client, operator, post_id)
    unpin(client, operator, post_id)

    # 고정은 글을 고치는 것이 아니다. "수정됨" 표시가 붙으면 안 된다
    assert read(client, post_id)['updated_at'] == before


def test_posts_on_any_board_can_be_pinned(client: httpx.Client, me: dict, operator: dict):
    notice = written_id(client, operator, 'notice')
    free = written_id(client, me, 'free')

    pinned(client, operator, notice)
    pinned(client, operator, free)

    assert ids(listing(client, 'notice')['pinned']) == [notice]
    assert ids(listing(client, 'free')['pinned']) == [free]


# 고정할 수 있는 글의 수


def test_pinning_over_board_limit_is_409(client: httpx.Client, me: dict, operator: dict, pin_many):
    pin_many(MAX_PINS_PER_BOARD)
    extra = written_id(client, me)

    response = pin(client, operator, extra)

    assert response.status_code == httpx.codes.CONFLICT
    assert response.json() == {'detail': '이 게시판에는 글을 더 고정할 수 없습니다.'}
    assert read(client, extra)['pinned'] is False


def test_already_pinned_post_can_be_pinned_again_when_full(client: httpx.Client, operator: dict, pin_many):
    first = pin_many(MAX_PINS_PER_BOARD)[0]

    assert pin(client, operator, first, {'days': 30}).status_code == httpx.codes.NO_CONTENT


def test_unpinning_one_makes_room(client: httpx.Client, me: dict, operator: dict, pin_many):
    first = pin_many(MAX_PINS_PER_BOARD)[0]
    extra = written_id(client, me)

    unpin(client, operator, first)

    assert pin(client, operator, extra).status_code == httpx.codes.NO_CONTENT


def test_expired_pin_does_not_take_a_slot(client: httpx.Client, database: Database, me: dict, operator: dict, pin_many):
    first = pin_many(MAX_PINS_PER_BOARD)[0]
    extra = written_id(client, me)

    database.expire_pin(first)

    assert pin(client, operator, extra).status_code == httpx.codes.NO_CONTENT


def test_deleted_post_does_not_take_a_slot(client: httpx.Client, me: dict, operator: dict, pin_many):
    first = pin_many(MAX_PINS_PER_BOARD)[0]
    extra = written_id(client, me)

    client.delete(post(first), headers=operator)

    assert pin(client, operator, extra).status_code == httpx.codes.NO_CONTENT


def test_pin_limit_is_counted_per_board(client: httpx.Client, me: dict, operator: dict, pin_many):
    pin_many(MAX_PINS_PER_BOARD, 'free')
    elsewhere = written_id(client, me, 'scenario')

    assert pin(client, operator, elsewhere).status_code == httpx.codes.NO_CONTENT


# 고정 풀기


def test_operator_unpin_returns_204_and_clears_pin(client: httpx.Client, database: Database, me: dict, operator: dict):
    post_id = written_id(client, me)
    pinned(client, operator, post_id)

    response = unpin(client, operator, post_id)

    assert response.status_code == httpx.codes.NO_CONTENT
    body = read(client, post_id)
    assert body['pinned'] is False
    assert body['pinned_until'] is None
    row = database.row('posts', 'id', post_id)
    assert row is not None
    assert row['pinned_at'] is None
    assert row['pinned_until'] is None


def test_unpinning_unpinned_post_is_not_an_error(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)

    assert unpin(client, operator, post_id).status_code == httpx.codes.NO_CONTENT
    assert unpin(client, operator, post_id).status_code == httpx.codes.NO_CONTENT


def test_non_operator_unpin_is_403_and_pin_stays(client: httpx.Client, me: dict, operator: dict):
    post_id = written_id(client, me)
    pinned(client, operator, post_id)

    response = unpin(client, me, post_id)

    assert response.status_code == httpx.codes.FORBIDDEN
    assert read(client, post_id)['pinned'] is True


def test_unpin_without_login_is_401(client: httpx.Client, me: dict):
    post_id = written_id(client, me)

    response = client.delete(post_pin(post_id))

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_unpin_missing_post_is_404(client: httpx.Client, operator: dict):
    assert unpin(client, operator, '999').status_code == httpx.codes.NOT_FOUND


# 글 목록의 고정한 글


def test_pinned_posts_are_listed_separately_and_not_in_items_or_total(client: httpx.Client, me: dict, operator: dict):
    first = written_id(client, me)
    notice = written_id(client, me)
    last = written_id(client, me)
    pinned(client, operator, notice)

    body = listing(client)

    assert ids(body['pinned']) == [notice]
    assert ids(body['items']) == [last, first]
    assert body['total'] == 2
    assert body['pinned'][0]['pinned'] is True
    assert all(not item['pinned'] for item in body['items'])


def test_pinned_is_empty_list_when_nothing_pinned(client: httpx.Client, me: dict):
    written_id(client, me)

    assert listing(client)['pinned'] == []


def test_later_pinned_post_comes_first(client: httpx.Client, me: dict, operator: dict):
    older = written_id(client, me)
    newer = written_id(client, me)
    pinned(client, operator, newer)
    pinned(client, operator, older)

    # 글을 쓴 차례가 아니라 고정한 차례다
    assert ids(listing(client)['pinned']) == [older, newer]


def test_repinned_post_moves_to_top(client: httpx.Client, me: dict, operator: dict):
    first = written_id(client, me)
    second = written_id(client, me)
    pinned(client, operator, first)
    pinned(client, operator, second)

    pinned(client, operator, first)

    assert ids(listing(client)['pinned']) == [first, second]


def test_pinned_posts_only_on_first_page(client: httpx.Client, me: dict, operator: dict):
    notice = written_id(client, me)
    written_id(client, me)
    written_id(client, me)
    written_id(client, me)
    pinned(client, operator, notice)

    first_page = listing(client, 'free', {'size': 2, 'page': 1})
    second_page = listing(client, 'free', {'size': 2, 'page': 2})

    assert ids(first_page['pinned']) == [notice]
    assert second_page['pinned'] == []


def test_pinned_posts_do_not_count_toward_page_size(client: httpx.Client, me: dict, operator: dict):
    notice = written_id(client, me)
    a = written_id(client, me)
    b = written_id(client, me)
    c = written_id(client, me)
    pinned(client, operator, notice)

    first_page = listing(client, 'free', {'size': 2, 'page': 1})
    second_page = listing(client, 'free', {'size': 2, 'page': 2})

    # 고정한 글 하나에 더해 글 둘이 온다. 고정했다고 다른 글이 다음 쪽으로 밀리지 않는다
    assert ids(first_page['items']) == [c, b]
    assert ids(second_page['items']) == [a]
    assert first_page['total'] == 3


def test_unpinned_post_returns_to_its_place(client: httpx.Client, me: dict, operator: dict):
    first = written_id(client, me)
    notice = written_id(client, me)
    last = written_id(client, me)
    pinned(client, operator, notice)

    unpin(client, operator, notice)

    body = listing(client)
    assert body['pinned'] == []
    assert ids(body['items']) == [last, notice, first]
    assert body['total'] == 3


def test_pinned_posts_of_other_boards_are_not_mixed(client: httpx.Client, me: dict, operator: dict):
    elsewhere = written_id(client, me, 'scenario')
    written_id(client, me, 'free')
    pinned(client, operator, elsewhere)

    assert listing(client, 'free')['pinned'] == []
    assert ids(listing(client, 'scenario')['pinned']) == [elsewhere]


def test_deleted_pinned_post_leaves_listing(client: httpx.Client, me: dict, operator: dict):
    notice = written_id(client, me)
    pinned(client, operator, notice)

    client.delete(post(notice), headers=me)

    body = listing(client)
    assert body['pinned'] == []
    assert body['items'] == []


def test_pinned_post_has_comment_count(client: httpx.Client, me: dict, operator: dict):
    notice = written_id(client, me)
    pinned(client, operator, notice)
    client.post(post_comments(notice), headers=me, json={'content': '댓글입니다.'})

    assert listing(client)['pinned'][0]['comment_count'] == 1


# 고정이 끝난 글


def test_expired_pin_drops_automatically(client: httpx.Client, database: Database, me: dict, operator: dict):
    first = written_id(client, me)
    notice = written_id(client, me)
    last = written_id(client, me)
    pinned(client, operator, notice)

    database.expire_pin(notice)

    # 아무도 풀지 않았다. 읽을 때 고정하지 않은 글로 읽는다
    body = listing(client)
    assert body['pinned'] == []
    assert ids(body['items']) == [last, notice, first]
    assert body['total'] == 3


def test_expired_pin_reads_as_unpinned_without_past_time(
    client: httpx.Client, database: Database, me: dict, operator: dict
):
    notice = written_id(client, me)
    pinned(client, operator, notice)

    database.expire_pin(notice)

    body = read(client, notice)
    assert body['pinned'] is False
    assert body['pinned_until'] is None


def test_expired_post_can_be_pinned_again(client: httpx.Client, database: Database, me: dict, operator: dict):
    notice = written_id(client, me)
    pinned(client, operator, notice)
    database.expire_pin(notice)

    pinned(client, operator, notice)

    assert ids(listing(client)['pinned']) == [notice]
