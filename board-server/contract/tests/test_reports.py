# board-server/contract/tests/test_reports.py

"""
신고하기(로그인한 누구나)와 읽고 처리하기(운영자)(board-server/test/reports.e2e-spec.ts).

횟수 제한은 쓰기 한도의 시험이 본다. 사람은 시험마다 새로 만든다.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import httpx
import psycopg
import pytest

from harness.database import Database
from harness.tokens import new_user_id
from tests.urls import (
    REPORTS,
    board_posts,
    comment,
    comment_outcome,
    comment_reports,
    post,
    post_comments,
    post_outcome,
    post_reports,
)

# 정해 둔 사유. 운영자의 목록이 이 차례로 센다
REPORT_REASONS = ('spam', 'abuse', 'sexual', 'illegal', 'other')
# 설명의 최대 길이(글자)
DESCRIPTION_MAX_LENGTH = 500
# 사유마다 0 건. 운영자의 목록에서 견줄 때 쓴다
NO_REASONS = dict.fromkeys(REPORT_REASONS, 0)
# 같은 신고를 동시에 보내는 수
CONCURRENT_REPORTS = 5

# 주소의 앞부분(posts, comments)마다 신고하는 주소, 처리하는 주소, 지우는 주소
REPORT_URLS = {'posts': post_reports, 'comments': comment_reports}
OUTCOME_URLS = {'posts': post_outcome, 'comments': comment_outcome}
DELETE_URLS = {'posts': post, 'comments': comment}


@dataclass(frozen=True)
class People:
    """시험에 나오는 사람들. 인증 서버의 public_id 다."""

    writer: str
    reader: str
    another: str
    third: str
    operator: str


class Board:
    """한 시험에서 서버를 부르는 손. 사람마다 토큰을 붙인다."""

    def __init__(self, client: httpx.Client, headers_for: Callable[..., dict[str, str]], people: People) -> None:
        self.client = client
        self.headers_for = headers_for
        self.people = people

    def headers(self, user_id: str) -> dict[str, str]:
        return self.headers_for(user_id, operator=user_id == self.people.operator)

    def written_post(self, user_id: str | None = None) -> str:
        """글을 써서 그 번호를 돌려준다."""
        response = self.client.post(
            board_posts('free'),
            headers=self.headers(user_id or self.people.writer),
            json={'title': '글', 'content': '본문입니다.'},
        )
        assert response.status_code == httpx.codes.CREATED
        return response.json()['id']

    def written_comment(self, post_id: str, user_id: str | None = None, parent_id: str | None = None) -> str:
        """댓글을 달아 그 번호를 돌려준다. parent_id 를 주면 답글이다."""
        body: dict[str, Any] = {'content': '댓글입니다.'}
        if parent_id is not None:
            body['parent_id'] = parent_id
        response = self.client.post(
            post_comments(post_id), headers=self.headers(user_id or self.people.writer), json=body
        )
        assert response.status_code == httpx.codes.CREATED
        return response.json()['id']

    def report(self, user_id: str, kind: str, target_id: str, body: object = None) -> httpx.Response:
        """글이나 댓글을 신고한다. kind 는 주소의 앞부분(posts, comments)이다."""
        payload = {'reason': 'spam'} if body is None else body
        return self.client.post(REPORT_URLS[kind](target_id), headers=self.headers(user_id), json=payload)

    def remove(self, user_id: str, kind: str, target_id: str) -> None:
        """글이나 댓글을 지운다."""
        response = self.client.delete(DELETE_URLS[kind](target_id), headers=self.headers(user_id))
        assert response.status_code == httpx.codes.NO_CONTENT

    def open_list(self, user_id: str | None = None, params: dict[str, Any] | None = None) -> httpx.Response:
        """운영자의 목록을 읽는다."""
        return self.client.get(REPORTS, headers=self.headers(user_id or self.people.operator), params=params)

    def reports_of(self, kind: str, target_id: str, user_id: str | None = None) -> httpx.Response:
        """글이나 댓글 하나에 걸린 신고를 읽는다."""
        return self.client.get(REPORT_URLS[kind](target_id), headers=self.headers(user_id or self.people.operator))

    def handle(
        self, kind: str, target_id: str, outcome: object = 'actioned', user_id: str | None = None
    ) -> httpx.Response:
        """글이나 댓글 하나에 걸린 열린 신고를 처리한다."""
        return self.client.put(
            OUTCOME_URLS[kind](target_id),
            headers=self.headers(user_id or self.people.operator),
            json={'outcome': outcome},
        )


@pytest.fixture
def people() -> People:
    return People(
        writer=new_user_id(),
        reader=new_user_id(),
        another=new_user_id(),
        third=new_user_id(),
        operator=new_user_id(),
    )


@pytest.fixture
def board(client: httpx.Client, headers_for: Callable[..., dict[str, str]], people: People) -> Board:
    return Board(client, headers_for, people)


def report_row(database: Database, report_id: int) -> dict[str, Any] | None:
    """신고 한 행을 그대로 읽는다. 사람과 대상의 번호는 문자열로 맞춘다."""
    row = database.row('reports', 'id', report_id)
    if row is None:
        return None
    return {
        key: str(value) if key in ('post_id', 'comment_id', 'reporter_id', 'handled_by') and value else value
        for key, value in row.items()
    }


# POST /posts/:id/reports


def test_reporting_post_returns_201_with_receipt_only(board: Board, people: People, database: Database):
    post_id = board.written_post()

    response = board.report(people.reader, 'posts', post_id, {'reason': 'abuse', 'description': '욕설이 있습니다.'})

    assert response.status_code == httpx.codes.CREATED
    body = response.json()
    assert body == {'id': '1', 'reason': 'abuse', 'created_at': body['created_at']}
    assert isinstance(body['created_at'], str)
    row = report_row(database, 1)
    assert row is not None
    assert row['post_id'] == post_id
    assert row['comment_id'] is None
    assert row['reporter_id'] == people.reader
    assert row['reason'] == 'abuse'
    assert row['description'] == '욕설이 있습니다.'
    assert row['handled_at'] is None
    assert row['handled_by'] is None
    assert row['outcome'] is None


def test_description_is_optional_and_null_when_omitted(board: Board, people: People, database: Database):
    post_id = board.written_post()

    assert board.report(people.reader, 'posts', post_id).status_code == httpx.codes.CREATED
    response = board.report(people.another, 'posts', post_id, {'reason': 'spam', 'description': None})
    assert response.status_code == httpx.codes.CREATED

    assert report_row(database, 1)['description'] is None
    assert report_row(database, 2)['description'] is None


def test_reporting_without_login_is_401(board: Board, client: httpx.Client):
    post_id = board.written_post()

    response = client.post(post_reports(post_id), json={'reason': 'spam'})

    assert response.status_code == httpx.codes.UNAUTHORIZED


def test_same_person_reporting_same_post_twice_is_409_but_others_can(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)

    again = board.report(people.reader, 'posts', post_id, {'reason': 'abuse'})

    assert again.status_code == httpx.codes.CONFLICT
    assert again.json() == {'detail': '이미 신고했습니다.'}
    assert board.report(people.another, 'posts', post_id).status_code == httpx.codes.CREATED


def test_same_person_cannot_report_again_after_report_was_handled(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)
    board.handle('posts', post_id, 'dismissed')

    assert board.report(people.reader, 'posts', post_id).status_code == httpx.codes.CONFLICT


def test_concurrent_identical_reports_accept_only_one(board: Board, people: People, database: Database):
    post_id = board.written_post()
    headers = board.headers(people.reader)
    base_url = board.client.base_url

    def send(_: int) -> int:
        # 연결마다 따로 보내 서버에서 실제로 겹치게 한다
        with httpx.Client(base_url=base_url, timeout=10) as http:
            return http.post(post_reports(post_id), headers=headers, json={'reason': 'spam'}).status_code

    with ThreadPoolExecutor(max_workers=CONCURRENT_REPORTS) as pool:
        statuses = sorted(pool.map(send, range(CONCURRENT_REPORTS)))

    assert statuses == [httpx.codes.CREATED] + [httpx.codes.CONFLICT] * (CONCURRENT_REPORTS - 1)
    assert database.execute('SELECT count(*)::int AS count FROM reports') == [{'count': 1}]


def test_cannot_report_own_post(board: Board, people: People):
    post_id = board.written_post()

    response = board.report(people.writer, 'posts', post_id)

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '자신의 글은 신고할 수 없습니다.'}


def test_deleted_missing_or_malformed_post_is_404(board: Board, people: People):
    post_id = board.written_post()
    board.remove(people.writer, 'posts', post_id)

    for target_id in (post_id, '999', 'abc'):
        response = board.report(people.reader, 'posts', target_id)
        assert response.status_code == httpx.codes.NOT_FOUND
        assert response.json() == {'detail': '글을 찾을 수 없습니다.'}


@pytest.mark.parametrize(
    ('body', 'field'),
    [
        ({}, 'reason'),
        ({'reason': 'boring'}, 'reason'),
        ({'reason': 'other'}, 'description'),
        ({'reason': 'other', 'description': '   '}, 'description'),
        ({'reason': 'spam', 'description': ''}, 'description'),
        ({'reason': 'spam', 'description': 3}, 'description'),
        ({'reason': 'spam', 'description': 'a\u0000b'}, 'description'),
        ({'reason': 'spam', 'description': 'a' * (DESCRIPTION_MAX_LENGTH + 1)}, 'description'),
        ({'reason': 'spam', 'target': 'x'}, 'target'),
    ],
)
def test_invalid_report_input_is_400(board: Board, people: People, body: dict[str, Any], field: str):
    post_id = board.written_post()

    response = board.report(people.reader, 'posts', post_id, body)

    assert response.status_code == httpx.codes.BAD_REQUEST
    assert list(response.json()['errors']) == [field]


def test_other_reason_with_description_up_to_max_length_is_accepted(board: Board, people: People):
    post_id = board.written_post()

    response = board.report(
        people.reader, 'posts', post_id, {'reason': 'other', 'description': 'a' * DESCRIPTION_MAX_LENGTH}
    )

    assert response.status_code == httpx.codes.CREATED


def test_every_defined_reason_is_accepted(board: Board, people: People):
    post_id = board.written_post()
    reporters = [people.reader, people.another, people.third, people.operator, new_user_id()]

    for reporter, reason in zip(reporters, REPORT_REASONS, strict=True):
        response = board.report(reporter, 'posts', post_id, {'reason': reason, 'description': '설명'})
        assert response.status_code == httpx.codes.CREATED


# POST /comments/:id/reports


def test_comments_and_replies_can_be_reported(board: Board, people: People, database: Database):
    post_id = board.written_post(people.reader)
    comment_id = board.written_comment(post_id)
    reply_id = board.written_comment(post_id, people.writer, comment_id)

    assert board.report(people.reader, 'comments', comment_id).status_code == httpx.codes.CREATED
    assert board.report(people.reader, 'comments', reply_id).status_code == httpx.codes.CREATED

    row = report_row(database, 1)
    assert row['post_id'] is None
    assert row['comment_id'] == comment_id


def test_same_person_can_report_a_post_and_a_comment(board: Board, people: People):
    post_id = board.written_post(people.reader)
    comment_id = board.written_comment(post_id)
    other_post = board.written_post(people.writer)

    assert board.report(people.another, 'posts', other_post).status_code == httpx.codes.CREATED
    assert board.report(people.another, 'comments', comment_id).status_code == httpx.codes.CREATED


def test_duplicate_comment_report_is_409_and_own_comment_is_403(board: Board, people: People):
    post_id = board.written_post(people.reader)
    comment_id = board.written_comment(post_id)
    board.report(people.reader, 'comments', comment_id)

    assert board.report(people.reader, 'comments', comment_id).status_code == httpx.codes.CONFLICT
    own = board.report(people.writer, 'comments', comment_id)
    assert own.status_code == httpx.codes.FORBIDDEN
    assert own.json() == {'detail': '자신의 댓글은 신고할 수 없습니다.'}


def test_deleted_placeholder_or_orphaned_comment_is_404(board: Board, people: People):
    post_id = board.written_post(people.reader)
    deleted = board.written_comment(post_id)
    board.remove(people.writer, 'comments', deleted)
    placeholder = board.written_comment(post_id)
    board.written_comment(post_id, people.another, placeholder)
    board.remove(people.writer, 'comments', placeholder)
    orphan = board.written_comment(post_id)
    board.remove(people.reader, 'posts', post_id)

    for target_id in (deleted, placeholder, orphan, '999', 'abc'):
        response = board.report(people.another, 'comments', target_id)
        assert response.status_code == httpx.codes.NOT_FOUND
        assert response.json() == {'detail': '댓글을 찾을 수 없습니다.'}


# GET /reports


def test_report_list_is_403_for_non_operator_and_401_without_login(board: Board, people: People, client: httpx.Client):
    response = board.open_list(people.reader)

    assert response.status_code == httpx.codes.FORBIDDEN
    assert response.json() == {'detail': '운영자만 신고를 볼 수 있습니다.'}
    assert client.get(REPORTS).status_code == httpx.codes.UNAUTHORIZED


def test_report_list_is_empty_without_reports(board: Board):
    response = board.open_list()

    assert response.status_code == httpx.codes.OK
    assert response.json() == {'items': [], 'page': 1, 'size': 20, 'total': 0}


def test_report_list_groups_by_target_and_counts_reasons(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id, {'reason': 'spam'})
    board.report(people.another, 'posts', post_id, {'reason': 'spam'})
    board.report(people.third, 'posts', post_id, {'reason': 'other', 'description': '설명'})

    response = board.open_list()

    assert response.status_code == httpx.codes.OK
    body = response.json()
    assert body['total'] == 1
    [group] = body['items']
    assert isinstance(group['first_reported_at'], str)
    assert isinstance(group['last_reported_at'], str)
    assert body['items'] == [
        {
            'target': {'type': 'post', 'id': post_id, 'post_id': post_id, 'deleted': False},
            'open_count': 3,
            'reasons': {**NO_REASONS, 'spam': 2, 'other': 1},
            'first_reported_at': group['first_reported_at'],
            'last_reported_at': group['last_reported_at'],
        }
    ]
    assert group['first_reported_at'] <= group['last_reported_at']


def test_posts_and_comments_are_grouped_separately_with_parent_post(board: Board, people: People):
    post_id = board.written_post()
    comment_id = board.written_comment(post_id)
    board.report(people.reader, 'posts', post_id)
    board.report(people.reader, 'comments', comment_id, {'reason': 'abuse'})

    body = board.open_list().json()

    assert body['total'] == 2
    assert [item['target'] for item in body['items']] == [
        {'type': 'post', 'id': post_id, 'post_id': post_id, 'deleted': False},
        {'type': 'comment', 'id': comment_id, 'post_id': post_id, 'deleted': False},
    ]


def test_post_and_comment_with_same_id_are_counted_separately(board: Board, people: People):
    post_id = board.written_post()
    comment_id = board.written_comment(post_id)
    assert comment_id == post_id
    board.report(people.reader, 'posts', post_id)
    board.report(people.reader, 'comments', comment_id)

    assert board.open_list().json()['total'] == 2


def test_report_list_orders_by_first_report_and_keeps_position(board: Board, people: People):
    first = board.written_post()
    second = board.written_post()
    board.report(people.reader, 'posts', first)
    board.report(people.reader, 'posts', second)
    board.report(people.another, 'posts', first)

    body = board.open_list().json()

    assert [item['target']['id'] for item in body['items']] == [first, second]


def test_report_list_is_paginated(board: Board, people: People):
    ids = []
    for _ in range(3):
        ids.append(board.written_post())
        board.report(people.reader, 'posts', ids[-1])

    body = board.open_list(params={'page': 2, 'size': 2}).json()

    assert body['total'] == 3
    assert body['page'] == 2
    assert [item['target']['id'] for item in body['items']] == [ids[2]]


def test_reports_stay_open_after_target_deleted_and_show_deleted(board: Board, people: People):
    post_id = board.written_post()
    comment_id = board.written_comment(post_id)
    board.report(people.reader, 'posts', post_id)
    board.report(people.reader, 'comments', comment_id)
    board.remove(people.operator, 'comments', comment_id)
    board.remove(people.operator, 'posts', post_id)

    body = board.open_list().json()

    assert [item['target']['deleted'] for item in body['items']] == [True, True]


def test_handled_reports_leave_the_list(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)
    board.handle('posts', post_id)

    assert board.open_list().json()['total'] == 0


# GET /posts/:id/reports, GET /comments/:id/reports


def test_post_reports_are_listed_newest_first_with_description_and_reporter(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id, {'reason': 'spam', 'description': '광고'})
    board.report(people.another, 'posts', post_id, {'reason': 'abuse'})

    response = board.reports_of('posts', post_id)

    assert response.status_code == httpx.codes.OK
    body = response.json()
    assert body['total'] == 2
    expected = [
        {'id': '2', 'reason': 'abuse', 'description': None, 'reporter_id': people.another, 'outcome': None},
        {'id': '1', 'reason': 'spam', 'description': '광고', 'reporter_id': people.reader, 'outcome': None},
    ]
    assert len(body['items']) == len(expected)
    for item, fields in zip(body['items'], expected, strict=True):
        assert {key: item[key] for key in fields} == fields


def test_reports_of_other_targets_are_not_mixed(board: Board, people: People):
    post_id = board.written_post()
    other_post = board.written_post()
    comment_id = board.written_comment(post_id)
    board.report(people.reader, 'posts', post_id)
    board.report(people.reader, 'posts', other_post)
    board.report(people.reader, 'comments', comment_id)

    for_post = board.reports_of('posts', post_id).json()
    for_comment = board.reports_of('comments', comment_id).json()

    assert [item['id'] for item in for_post['items']] == ['1']
    assert [item['id'] for item in for_comment['items']] == ['3']


def test_reports_of_deleted_post_are_readable_and_empty_when_none(board: Board, people: People):
    post_id = board.written_post()
    quiet = board.written_post()
    board.report(people.reader, 'posts', post_id)
    board.remove(people.writer, 'posts', post_id)

    assert board.reports_of('posts', post_id).json()['total'] == 1
    assert board.reports_of('posts', quiet).json() == {'items': [], 'page': 1, 'size': 20, 'total': 0}


def test_target_reports_are_403_for_non_operators_including_author(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)

    assert board.reports_of('posts', post_id, people.writer).status_code == httpx.codes.FORBIDDEN
    assert board.reports_of('posts', post_id, people.reader).status_code == httpx.codes.FORBIDDEN


def test_missing_target_reports_are_403_for_non_operator_and_404_for_operator(board: Board, people: People):
    assert board.reports_of('posts', '999', people.reader).status_code == httpx.codes.FORBIDDEN
    assert board.reports_of('posts', '999').status_code == httpx.codes.NOT_FOUND
    assert board.reports_of('comments', '999').status_code == httpx.codes.NOT_FOUND


# PUT /posts/:id/reports/outcome, PUT /comments/:id/reports/outcome


def test_handling_closes_all_open_reports_at_once_with_operator_and_outcome(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)
    board.report(people.another, 'posts', post_id)

    response = board.handle('posts', post_id, 'actioned')

    assert response.status_code == httpx.codes.NO_CONTENT
    items = board.reports_of('posts', post_id).json()['items']
    assert len(items) == 2
    for item in items:
        assert item['handled_by'] == people.operator
        assert item['outcome'] == 'actioned'
        assert isinstance(item['handled_at'], str)
    # 한 문장으로 닫으므로 처리한 시각이 같다
    assert items[0]['handled_at'] == items[1]['handled_at']


def test_new_report_after_handling_reopens_and_keeps_previous_outcome(board: Board, people: People, database: Database):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)
    board.handle('posts', post_id, 'dismissed')

    board.report(people.another, 'posts', post_id)

    group = board.open_list().json()['items'][0]
    assert group['open_count'] == 1
    assert report_row(database, 1)['outcome'] == 'dismissed'
    assert report_row(database, 2)['outcome'] is None


def test_handling_without_open_reports_is_404_including_second_time(board: Board, people: People):
    post_id = board.written_post()
    assert board.handle('posts', post_id).status_code == httpx.codes.NOT_FOUND

    board.report(people.reader, 'posts', post_id)
    assert board.handle('posts', post_id).status_code == httpx.codes.NO_CONTENT

    again = board.handle('posts', post_id)
    assert again.status_code == httpx.codes.NOT_FOUND
    assert again.json() == {'detail': '처리할 신고가 없습니다.'}


def test_handling_comment_reports_leaves_post_reports_open(board: Board, people: People):
    post_id = board.written_post()
    comment_id = board.written_comment(post_id)
    board.report(people.reader, 'posts', post_id)
    board.report(people.reader, 'comments', comment_id)

    assert board.handle('comments', comment_id).status_code == httpx.codes.NO_CONTENT

    body = board.open_list().json()
    assert [item['target']['type'] for item in body['items']] == ['post']


def test_reports_of_deleted_post_can_be_handled(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)
    board.remove(people.operator, 'posts', post_id)

    assert board.handle('posts', post_id).status_code == httpx.codes.NO_CONTENT


def test_handling_by_non_operator_is_403_and_does_not_close(board: Board, people: People):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)

    assert board.handle('posts', post_id, 'dismissed', people.writer).status_code == httpx.codes.FORBIDDEN
    assert board.open_list().json()['total'] == 1


@pytest.mark.parametrize('body', [{}, {'outcome': 'deleted'}, {'outcome': 3}])
def test_invalid_outcome_is_400(board: Board, people: People, client: httpx.Client, body: dict[str, Any]):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)

    response = client.put(post_outcome(post_id), headers=board.headers(people.operator), json=body)

    assert response.status_code == httpx.codes.BAD_REQUEST


def test_handling_missing_post_or_comment_is_404(board: Board):
    assert board.handle('posts', '999').status_code == httpx.codes.NOT_FOUND
    assert board.handle('comments', '999').status_code == httpx.codes.NOT_FOUND
    assert board.handle('posts', 'abc').status_code == httpx.codes.NOT_FOUND


# DB 가 지키는 약속


def test_report_must_target_exactly_one_of_post_or_comment(board: Board, people: People, database: Database):
    post_id = board.written_post()
    comment_id = board.written_comment(post_id)

    def insert(post_value: str | None, comment_value: str | None) -> None:
        database.execute(
            "INSERT INTO reports (post_id, comment_id, reporter_id, reason) VALUES (%s, %s, %s, 'spam')",
            (post_value, comment_value, people.reader),
        )

    with pytest.raises(psycopg.errors.CheckViolation, match='ck_reports_one_target'):
        insert(None, None)
    with pytest.raises(psycopg.errors.CheckViolation, match='ck_reports_one_target'):
        insert(post_id, comment_id)


def test_handled_at_handled_by_and_outcome_must_be_set_together(board: Board, people: People, database: Database):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)

    with pytest.raises(psycopg.errors.CheckViolation, match='ck_reports_handled_together'):
        database.execute("UPDATE reports SET outcome = 'actioned'")


def test_post_row_with_reports_cannot_be_deleted(board: Board, people: People, database: Database):
    post_id = board.written_post()
    board.report(people.reader, 'posts', post_id)

    with pytest.raises(psycopg.errors.ForeignKeyViolation, match='fk_reports_post'):
        database.execute('DELETE FROM posts WHERE id = %s', (post_id,))
