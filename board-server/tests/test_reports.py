# board-server/tests/test_reports.py

"""
신고하기와 운영자의 신고 처리(app/reports/). 계약 시험이 보지 못하는 것을 본다.

  - 신고의 메트릭(board_reports_total)이 결과마다 센다
  - 입력 오류의 칸과 문장, 검사의 차례(토큰 -> 주소 -> 본문 -> 운영자인가)가 NestJS 때와 같다
  - 줄을 모델로 직접 넣고 본다(탈퇴한 글쓴이, 지운 댓글, 처리한 신고, 같은 시각의 묶음)
  - 동시에 들어온 같은 신고가 DB 의 유일 제약에 걸렸을 때와 그 밖의 DB 오류
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from server_core.testing.metrics import MetricsRecorder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.boards.models import Board
from app.comments.models import Comment
from app.posts.models import Post
from app.reports import repository, reviews
from app.reports.models import Report
from app.reports.schemas import CreateReportDto, description_problem
from app.reports.targets import TargetState, comment_target, post_target, target_of

pytestmark = pytest.mark.usefixtures('clean_tables')

Headers = Callable[..., dict[str, str]]

API = '/api/v1/board'
WRITER = uuid.uuid4()
READER = uuid.uuid4()
OPERATOR = uuid.uuid4()
REPORTED_AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
NO_REASONS = {'spam': 0, 'abuse': 0, 'sexual': 0, 'illegal': 0, 'other': 0}


def as_user(headers_for: Headers, user_id: uuid.UUID) -> dict[str, str]:
    return headers_for(str(user_id))


def as_operator(headers_for: Headers) -> dict[str, str]:
    return headers_for(str(OPERATOR), roles=['operator'])


async def add_post(session: AsyncSession, author_id: uuid.UUID | None = WRITER, deleted: bool = False) -> Post:
    board_id = await session.scalar(select(Board.id).where(Board.slug == 'free'))
    post = Post(
        board_id=board_id,
        author_id=author_id,
        title='글',
        content='본문입니다.',
        deleted_at=REPORTED_AT if deleted else None,
    )
    session.add(post)
    await session.flush()
    return post


async def add_comment(
    session: AsyncSession, post: Post, author_id: uuid.UUID | None = WRITER, deleted: bool = False
) -> Comment:
    comment = Comment(post_id=post.id, author_id=author_id, content='댓글', deleted_at=REPORTED_AT if deleted else None)
    session.add(comment)
    await session.flush()
    return comment


async def add_report(
    session: AsyncSession,
    *,
    post: Post | None = None,
    comment: Comment | None = None,
    reporter_id: uuid.UUID | None = READER,
    reason: str = 'spam',
    created_at: datetime = REPORTED_AT,
) -> Report:
    report = Report(
        post_id=None if post is None else post.id,
        comment_id=None if comment is None else comment.id,
        reporter_id=reporter_id,
        reason=reason,
        created_at=created_at,
    )
    session.add(report)
    await session.flush()
    return report


# 신고하기


async def test_reporting_counts_success_and_rejection(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, metrics: MetricsRecorder
):
    post = await add_post(session)
    await session.commit()
    url = f'{API}/posts/{post.id}/reports'

    assert (await client.post(url, headers=as_user(headers_for, READER), json={'reason': 'spam'})).status_code == 201
    assert (await client.post(url, headers=as_user(headers_for, READER), json={'reason': 'spam'})).status_code == 409

    assert metrics.value('board_reports', target='post', result='success') == 1
    assert metrics.value('board_reports', target='post', result='rejected') == 1


async def test_comment_report_counts_under_comment(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, metrics: MetricsRecorder
):
    comment = await add_comment(session, await add_post(session))
    await session.commit()

    response = await client.post(
        f'{API}/comments/{comment.id}/reports', headers=as_user(headers_for, WRITER), json={'reason': 'spam'}
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert metrics.value('board_reports', target='comment', result='rejected') == 1


async def test_rate_limited_report_counts_as_rate_limited(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, metrics: MetricsRecorder
):
    posts = [await add_post(session) for _ in range(21)]
    for post in posts[:20]:
        await add_report(session, post=post, created_at=datetime.now(UTC))
    await session.commit()

    response = await client.post(
        f'{API}/posts/{posts[20].id}/reports', headers=as_user(headers_for, READER), json={'reason': 'spam'}
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert metrics.value('board_reports', target='post', result='rate_limited') == 1


async def test_withdrawn_authors_post_and_comment_can_be_reported(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post = await add_post(session, author_id=None)
    comment = await add_comment(session, post, author_id=None)
    await session.commit()
    headers = as_user(headers_for, READER)

    post_response = await client.post(f'{API}/posts/{post.id}/reports', headers=headers, json={'reason': 'spam'})
    comment_response = await client.post(
        f'{API}/comments/{comment.id}/reports',
        headers=headers,
        json={'reason': 'other', 'description': '  앞뒤 빈칸\n줄바꿈 '},
    )

    assert post_response.status_code == status.HTTP_201_CREATED
    assert comment_response.status_code == status.HTTP_201_CREATED
    body = comment_response.json()
    assert body['reason'] == 'other'
    assert body['created_at'].endswith('Z')
    saved = await session.get(Report, int(body['id']))
    assert saved.description == '  앞뒤 빈칸\n줄바꿈 '
    assert saved.comment_id == comment.id
    assert saved.post_id is None


async def test_malformed_id_is_404_before_body_is_checked(client: AsyncClient, headers_for: Headers):
    headers = as_user(headers_for, READER)

    post_response = await client.post(f'{API}/posts/abc/reports', headers=headers, json={})
    comment_response = await client.post(f'{API}/comments/0/reports', headers=headers, json={})

    assert post_response.status_code == status.HTTP_404_NOT_FOUND
    assert post_response.json() == {'detail': '글을 찾을 수 없습니다.'}
    assert comment_response.status_code == status.HTTP_404_NOT_FOUND
    assert comment_response.json() == {'detail': '댓글을 찾을 수 없습니다.'}


async def test_input_errors_list_unknown_fields_then_reason_then_description(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post = await add_post(session)
    await session.commit()

    response = await client.post(
        f'{API}/posts/{post.id}/reports',
        headers=as_user(headers_for, READER),
        json={'description': 3, 'reporter_id': 'x', 'reason': 1},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        'detail': '입력이 올바르지 않습니다.',
        'errors': {
            'reporter_id': ['property reporter_id should not exist'],
            'reason': ['reason 은 spam, abuse, sexual, illegal, other 가운데 하나여야 합니다.'],
            'description': ['설명은 글자여야 합니다.'],
        },
    }


async def test_other_without_description_names_the_one_problem(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post = await add_post(session)
    await session.commit()

    response = await client.post(
        f'{API}/posts/{post.id}/reports', headers=as_user(headers_for, READER), json={'reason': 'other'}
    )

    assert response.json()['errors'] == {'description': ['기타(other)를 고르면 설명을 적어야 합니다.']}


@pytest.mark.parametrize(
    ('reason', 'description', 'problem'),
    [
        ('spam', None, None),
        ('other', '설명', None),
        ('other', None, '기타(other)를 고르면 설명을 적어야 합니다.'),
        ('spam', 3, '설명은 글자여야 합니다.'),
        ('spam', ' \n', '설명을 적어야 합니다.'),
        ('spam', 'a\x00', '설명에 쓸 수 없는 글자가 있습니다.'),
        ('spam', 'a' * 501, '설명은 500자를 넘을 수 없습니다.'),
        ('spam', '😀' * 500, None),
    ],
)
def test_description_problem(reason: str, description: object, problem: str | None):
    assert description_problem(reason, description) == problem


def test_report_dto_keeps_description_and_defaults_to_none():
    assert CreateReportDto.model_validate({'reason': 'spam'}).description is None
    assert CreateReportDto.model_validate({'reason': 'spam', 'description': ' a '}).description == ' a '


async def test_unique_violation_on_insert_is_409(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, monkeypatch: pytest.MonkeyPatch
):
    """앞의 확인을 함께 지나친 늦은 신고는 DB 의 유일 제약이 막는다."""
    post = await add_post(session)
    await add_report(session, post=post)
    await session.commit()

    async def not_yet(*_: object) -> bool:
        return False

    monkeypatch.setattr(repository, 'has_reported', not_yet)
    response = await client.post(
        f'{API}/posts/{post.id}/reports', headers=as_user(headers_for, READER), json={'reason': 'abuse'}
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {'detail': '이미 신고했습니다.'}


async def test_other_integrity_errors_are_not_turned_into_409(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, monkeypatch: pytest.MonkeyPatch
):
    post = await add_post(session)
    await session.commit()

    class Broken(Exception):
        sqlstate = '23514'

    async def fails(*_: object) -> None:
        raise IntegrityError('INSERT', {}, Broken())

    monkeypatch.setattr(repository, 'insert_report', fails)

    with pytest.raises(IntegrityError):
        await client.post(
            f'{API}/posts/{post.id}/reports', headers=as_user(headers_for, READER), json={'reason': 'spam'}
        )


# 운영자의 목록과 처리


async def test_non_operator_gets_400_for_bad_input_before_403(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post = await add_post(session)
    await session.commit()
    headers = as_user(headers_for, READER)

    bad_body = await client.put(f'{API}/posts/{post.id}/reports/outcome', headers=headers, json={'outcome': None})
    bad_query = await client.get(f'{API}/reports?size=0', headers=headers)
    good = await client.put(f'{API}/posts/{post.id}/reports/outcome', headers=headers, json={'outcome': 'dismissed'})

    assert bad_body.status_code == status.HTTP_400_BAD_REQUEST
    assert bad_body.json()['errors'] == {'outcome': ['outcome 은 actioned, dismissed 가운데 하나여야 합니다.']}
    assert bad_query.json()['errors'] == {'size': ['size 는 1 이상이어야 합니다.']}
    assert good.status_code == status.HTTP_403_FORBIDDEN
    assert good.json() == {'detail': '운영자만 신고를 볼 수 있습니다.'}


async def test_repeated_page_in_query_is_400(client: AsyncClient, headers_for: Headers):
    response = await client.get(f'{API}/reports?page=1&page=2', headers=as_operator(headers_for))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert list(response.json()['errors']) == ['page']


async def test_open_list_shows_groups_with_parent_post_and_deleted_state(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post = await add_post(session)
    comment = await add_comment(session, post, deleted=True)
    later = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    await add_report(session, comment=comment, reason='abuse', created_at=REPORTED_AT)
    await add_report(session, comment=comment, reporter_id=OPERATOR, reason='other', created_at=later)
    await add_report(session, post=post, reason='sexual', created_at=later)
    await session.commit()

    response = await client.get(f'{API}/reports', headers=as_operator(headers_for))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        'items': [
            {
                'target': {'type': 'comment', 'id': str(comment.id), 'post_id': str(post.id), 'deleted': True},
                'open_count': 2,
                'reasons': {**NO_REASONS, 'abuse': 1, 'other': 1},
                'first_reported_at': '2026-10-01T09:00:00.000Z',
                'last_reported_at': '2026-10-02T09:00:00.000Z',
            },
            {
                'target': {'type': 'post', 'id': str(post.id), 'post_id': str(post.id), 'deleted': False},
                'open_count': 1,
                'reasons': {**NO_REASONS, 'sexual': 1},
                'first_reported_at': '2026-10-02T09:00:00.000Z',
                'last_reported_at': '2026-10-02T09:00:00.000Z',
            },
        ],
        'page': 1,
        'size': 20,
        'total': 2,
    }


async def test_same_first_report_time_is_ordered_by_post_then_comment(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    first = await add_post(session)
    second = await add_post(session)
    comment = await add_comment(session, first)
    await add_report(session, comment=comment)
    await add_report(session, post=second)
    await add_report(session, post=first)
    await session.commit()

    body = (await client.get(f'{API}/reports', headers=as_operator(headers_for))).json()

    assert [(item['target']['type'], item['target']['id']) for item in body['items']] == [
        ('post', str(first.id)),
        ('post', str(second.id)),
        ('comment', str(comment.id)),
    ]


async def test_reports_of_comment_show_handling_and_page(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    comment = await add_comment(session, await add_post(session))
    older = await add_report(session, comment=comment, reporter_id=None)
    newer = await add_report(session, comment=comment, reporter_id=OPERATOR, reason='abuse')
    await session.commit()
    headers = as_operator(headers_for)

    handled = await client.put(
        f'{API}/comments/{comment.id}/reports/outcome', headers=headers, json={'outcome': 'actioned'}
    )
    page = await client.get(f'{API}/comments/{comment.id}/reports?page=2&size=1', headers=headers)

    assert handled.status_code == status.HTTP_204_NO_CONTENT
    body = page.json()
    assert body['total'] == 2
    assert body['page'] == 2
    [item] = body['items']
    assert item['id'] == str(older.id) != str(newer.id)
    assert item['reporter_id'] is None
    assert item['handled_by'] == str(OPERATOR)
    assert item['outcome'] == 'actioned'
    assert item['handled_at'].endswith('Z')
    assert item['created_at'] == '2026-10-01T09:00:00.000Z'


async def test_missing_or_malformed_comment_is_404_for_operator(client: AsyncClient, headers_for: Headers):
    headers = as_operator(headers_for)

    listed = await client.get(f'{API}/comments/999/reports', headers=headers)
    handled = await client.put(f'{API}/comments/abc/reports/outcome', headers=headers, json={'outcome': 'actioned'})

    assert listed.json() == {'detail': '댓글을 찾을 수 없습니다.'}
    assert handled.status_code == status.HTTP_404_NOT_FOUND
    assert handled.json() == {'detail': '댓글을 찾을 수 없습니다.'}


async def test_operator_is_not_counted_as_reporting_when_handling(
    client: AsyncClient, session: AsyncSession, headers_for: Headers, metrics: MetricsRecorder
):
    post = await add_post(session)
    await add_report(session, post=post)
    await session.commit()

    await client.put(
        f'{API}/posts/{post.id}/reports/outcome', headers=as_operator(headers_for), json={'outcome': 'dismissed'}
    )

    assert metrics.points('board_reports') == []


# 순수한 함수들


def test_missing_state_is_an_error():
    with pytest.raises(LookupError):
        reviews.state_from({}, post_target(1))


def test_state_is_found_by_type_and_id():
    state = TargetState(post_id=1, deleted=False)

    assert reviews.state_from({('comment', 1): state}, comment_target(1)) is state


def test_target_of_reads_the_filled_column():
    assert target_of(3, None) == post_target(3)
    assert target_of(None, 4) == comment_target(4)
    with pytest.raises(ValueError, match='가리키지 않는다'):
        target_of(None, None)


def test_report_dto_rejects_a_body_that_is_not_an_object():
    with pytest.raises(ValidationError):
        CreateReportDto.model_validate(['spam'])


async def test_deleted_post_and_comment_on_deleted_post_cannot_be_reported(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post = await add_post(session, deleted=True)
    comment = await add_comment(session, post)
    await session.commit()
    headers = as_user(headers_for, READER)

    post_response = await client.post(f'{API}/posts/{post.id}/reports', headers=headers, json={'reason': 'spam'})
    comment_response = await client.post(
        f'{API}/comments/{comment.id}/reports', headers=headers, json={'reason': 'spam'}
    )

    assert post_response.json() == {'detail': '글을 찾을 수 없습니다.'}
    assert comment_response.json() == {'detail': '댓글을 찾을 수 없습니다.'}


async def test_empty_open_list_and_post_without_open_reports(
    client: AsyncClient, session: AsyncSession, headers_for: Headers
):
    post = await add_post(session)
    await session.commit()
    headers = as_operator(headers_for)

    listed = await client.get(f'{API}/reports', headers=headers)
    of_post = await client.get(f'{API}/posts/{post.id}/reports', headers=headers)
    handled = await client.put(f'{API}/posts/{post.id}/reports/outcome', headers=headers, json={'outcome': 'actioned'})

    assert listed.json() == {'items': [], 'page': 1, 'size': 20, 'total': 0}
    assert of_post.json() == {'items': [], 'page': 1, 'size': 20, 'total': 0}
    assert handled.status_code == status.HTTP_404_NOT_FOUND
    assert handled.json() == {'detail': '처리할 신고가 없습니다.'}
