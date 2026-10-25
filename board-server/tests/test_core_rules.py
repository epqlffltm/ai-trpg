# board-server/tests/test_core_rules.py

"""
DB 와 HTTP 없이 보는 작은 규칙들. 닉네임의 모양, 최근 닉네임의 기억, 기다릴 초, 시각의 모양, 알림을 받을 사람, 메트릭.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from functools import partial

import pytest
from fastapi import status
from server_core.testing.metrics import MetricsRecorder
from starlette.exceptions import HTTPException

from app.authors.service import RecentNicknames, read_nickname
from app.core import metrics as board_metrics
from app.core.errors import ApiError
from app.core.ids import parse_record_id, record_id
from app.core.times import format_timestamp
from app.core.write_limits import retry_after_seconds
from app.notifications.outbox import COMMENT_REPLIED, POST_COMMENTED, CommentContext, payload_of, recipient_of

WRITER = uuid.uuid4()
COMMENTER = uuid.uuid4()


@pytest.mark.parametrize(('value', 'read'), [('모험가', '모험가'), (' 이름 ', ' 이름 '), ('가' * 50, '가' * 50)])
def test_acceptable_nicknames_are_read_as_they_are(value: str, read: str):
    assert read_nickname(value) == read


@pytest.mark.parametrize('value', [None, 3, '', '  \n', '줄\n바꿈', '보이지​않음', '가' * 51])
def test_unacceptable_nicknames_are_not_read(value: object):
    assert read_nickname(value) is None


def test_recent_nicknames_forget_everyone_when_full():
    recent = RecentNicknames(max_size=2)
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    recent.remember(first, 'a')
    recent.remember(second, 'b')

    recent.remember(third, 'c')

    assert not recent.has(first, 'a')
    assert recent.has(third, 'c')
    recent.clear()
    assert not recent.has(third, 'c')


def test_recent_nicknames_keep_the_last_one_per_person():
    recent = RecentNicknames(max_size=1)
    person = uuid.uuid4()
    recent.remember(person, 'a')
    recent.remember(person, 'b')

    assert recent.has(person, 'b')
    assert not recent.has(person, 'a')


@pytest.mark.parametrize(('remaining', 'seconds'), [(0.2, 1), (141.3, 142), ('59.9', 60), (0, 1), (-3, 1), ('x', 1)])
def test_retry_after_is_a_rounded_up_positive_integer(remaining: object, seconds: int):
    assert retry_after_seconds(remaining) == seconds


@pytest.mark.parametrize(('value', 'parsed'), [('1', 1), ('123456789012345678', 123456789012345678)])
def test_record_ids_are_parsed(value: str, parsed: int):
    assert parse_record_id(value) == parsed
    assert record_id(parsed) == value


@pytest.mark.parametrize('value', ['0', '01', '-1', 'abc', '1.5', '1234567890123456789', '1\x00', '1\u0661', '1\n'])
def test_malformed_record_ids_are_not_parsed(value: str):
    assert parse_record_id(value) is None


def test_record_id_of_nothing_is_nothing():
    assert record_id(None) is None


def test_timestamps_are_utc_milliseconds_with_z():
    seoul = timezone(timedelta(hours=9))

    assert format_timestamp(datetime(2026, 10, 25, 17, 0, 0, 123456, tzinfo=seoul)) == '2026-10-25T08:00:00.123Z'
    assert format_timestamp(datetime(2026, 10, 25, 8, 0, 0)) == '2026-10-25T08:00:00.000Z'
    assert format_timestamp(datetime(2026, 10, 25, 8, 0, 0, 999, tzinfo=UTC)) == '2026-10-25T08:00:00.000Z'


def context(**overrides) -> CommentContext:
    values = {
        'board_slug': 'free',
        'post_id': 7,
        'post_title': '첫 모험',
        'post_author_id': WRITER,
        'comment_id': 9,
        'comment_author_id': COMMENTER,
    }
    values.update(overrides)
    return CommentContext(**values)


def test_a_comment_notifies_the_post_writer():
    assert recipient_of(context()) == (WRITER, POST_COMMENTED)
    assert payload_of(context()) == {'board_slug': 'free', 'post_id': '7', 'post_title': '첫 모험', 'comment_id': '9'}


def test_a_reply_notifies_the_comment_writer():
    other = uuid.uuid4()
    reply = context(parent_id=3, parent_author_id=other)

    assert recipient_of(reply) == (other, COMMENT_REPLIED)
    assert payload_of(reply)['parent_id'] == '3'


@pytest.mark.parametrize(
    'overrides',
    [{'post_author_id': COMMENTER}, {'post_author_id': None}, {'parent_id': 3, 'parent_author_id': COMMENTER}],
)
def test_nobody_is_notified_of_their_own_or_a_withdrawn_writers_post(overrides: dict):
    assert recipient_of(context(**overrides)) is None


def counted_results(recorder: MetricsRecorder) -> list[str]:
    return [point.labels['result'] for point in recorder.points('board_writes')]


def count_post_create(error: Exception | None) -> None:
    """글 쓰기 하나를 센다. error 가 있으면 그 거절로 끝난다."""
    with board_metrics.counted(partial(board_metrics.record_write, 'post', 'create')):
        if error is not None:
            raise error


def test_a_finished_write_is_success(metrics: MetricsRecorder):
    count_post_create(None)

    assert counted_results(metrics) == [board_metrics.SUCCESS]


@pytest.mark.parametrize(
    ('error', 'result'),
    [
        (ApiError(status.HTTP_403_FORBIDDEN, '권한이 없습니다.'), board_metrics.REJECTED),
        (ApiError(status.HTTP_429_TOO_MANY_REQUESTS, '너무 자주', retry_after=3), board_metrics.RATE_LIMITED),
        (HTTPException(status.HTTP_404_NOT_FOUND), board_metrics.REJECTED),
    ],
)
def test_a_refused_write_is_counted_by_its_status(metrics: MetricsRecorder, error: Exception, result: str):
    with pytest.raises(type(error)):
        count_post_create(error)

    assert counted_results(metrics) == [result]


def test_server_errors_are_not_counted(metrics: MetricsRecorder):
    with pytest.raises(ApiError):
        count_post_create(ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, '지금은 안 된다'))

    assert counted_results(metrics) == []


def test_searches_and_reports_are_counted(metrics: MetricsRecorder):
    board_metrics.record_search(board_metrics.SEARCH_TIMEOUT, 3.2)
    board_metrics.record_report('comment', board_metrics.SUCCESS)

    assert metrics.value('board_searches', result='timeout') == 1
    assert metrics.value('board_search_duration') == 1
    assert [point.labels for point in metrics.points('board_reports')] == [{'target': 'comment', 'result': 'success'}]
