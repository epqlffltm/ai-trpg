# board-server/tests/test_withdrawal.py

"""
탈퇴를 받는 주소(app/withdrawal/). 계약 시험이 보지 못하는 것을 본다.

  - 줄을 모델로 직접 넣고 정리한 뒤의 DB 를 본다(지운 글과 댓글, 처리한 운영자, 고친 시각, 다른 사람의 것)
  - 중간에 실패하면 아무것도 바뀌지 않는다(한 트랜잭션)
  - 입력 오류의 칸과 문장, 검사의 차례(서명 -> 주소 -> 본문)가 NestJS 때와 같다
  - 정리한 수를 로그에 남기고 사람의 번호는 남기지 않는다
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.service_auth.signing import SIGNATURE_HEADER, sign
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authors.models import Author
from app.boards.models import Board
from app.comments.models import Comment
from app.notifications.models import OutgoingNotification
from app.posts.models import Post
from app.reports.models import Report
from app.withdrawal import repository
from app.withdrawal.schemas import NO_OFFSET_MESSAGE, NOT_ISO_MESSAGE, WithdrawalDto, is_real_date
from tests.conftest import TEST_AUTH_SECRET

pytestmark = pytest.mark.usefixtures('clean_tables')

BODY = '{"withdrawn_at": "2026-10-28T03:00:00.123456+00:00"}'
LEAVING = uuid.uuid4()
STAYING = uuid.uuid4()
OPERATOR = uuid.uuid4()
WRITTEN_AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def withdrawal_path(user_id: object) -> str:
    return f'/api/v1/board/service/users/{user_id}/withdrawal'


async def withdraw(client: AsyncClient, user_id: object, body: str = BODY):
    """인증 서버처럼 서명해 탈퇴를 알린다."""
    path = withdrawal_path(user_id)
    content = body.encode()
    header = sign(TEST_AUTH_SECRET, int(time.time()), 'POST', path, content)
    return await client.post(
        path, content=content, headers={SIGNATURE_HEADER: header, 'Content-Type': 'application/json'}
    )


async def free_board_id(session: AsyncSession) -> int:
    return await session.scalar(select(Board.id).where(Board.slug == 'free'))


async def add_post(session: AsyncSession, author_id: uuid.UUID, deleted: bool = False) -> Post:
    post = Post(
        board_id=await free_board_id(session),
        author_id=author_id,
        title='첫 모험',
        content='본문입니다.',
        updated_at=WRITTEN_AT,
        deleted_at=WRITTEN_AT if deleted else None,
    )
    session.add(post)
    await session.flush()
    return post


async def add_comment(session: AsyncSession, post: Post, author_id: uuid.UUID, deleted: bool = False) -> Comment:
    comment = Comment(
        post_id=post.id,
        author_id=author_id,
        content='댓글입니다.',
        updated_at=WRITTEN_AT,
        deleted_at=WRITTEN_AT if deleted else None,
    )
    session.add(comment)
    await session.flush()
    return comment


async def add_report(session: AsyncSession, post: Post, reporter_id: uuid.UUID, handled: bool = False) -> Report:
    report = Report(
        post_id=post.id,
        reporter_id=reporter_id,
        reason='spam',
        handled_at=WRITTEN_AT if handled else None,
        handled_by=OPERATOR if handled else None,
        outcome='dismissed' if handled else None,
    )
    session.add(report)
    await session.flush()
    return report


def add_notification(session: AsyncSession, user_id: uuid.UUID, key: str) -> None:
    session.add(OutgoingNotification(user_id=user_id, kind='post.commented', source_key=key, payload={}))


async def seed(session: AsyncSession) -> dict[str, int]:
    """두 사람의 글, 댓글, 신고, 닉네임, 알림을 넣는다. 번호들을 돌려준다."""
    mine = await add_post(session, LEAVING)
    deleted_post = await add_post(session, LEAVING, deleted=True)
    theirs = await add_post(session, STAYING)
    my_comment = await add_comment(session, theirs, LEAVING)
    deleted_comment = await add_comment(session, theirs, LEAVING, deleted=True)
    their_comment = await add_comment(session, mine, STAYING)
    my_report = await add_report(session, theirs, LEAVING, handled=True)
    their_report = await add_report(session, mine, STAYING)
    session.add_all([Author(user_id=LEAVING, nickname='떠나는 이'), Author(user_id=STAYING, nickname='남는 이')])
    add_notification(session, LEAVING, 'a')
    add_notification(session, LEAVING, 'b')
    add_notification(session, STAYING, 'c')
    await session.commit()
    return {
        'mine': mine.id,
        'deleted_post': deleted_post.id,
        'theirs': theirs.id,
        'my_comment': my_comment.id,
        'deleted_comment': deleted_comment.id,
        'their_comment': their_comment.id,
        'my_report': my_report.id,
        'their_report': their_report.id,
    }


async def fresh(session: AsyncSession, model: type, row_id: object):
    """DB 의 지금 값. 세션에 남은 것을 버리고 다시 읽는다."""
    session.expire_all()
    return await session.get(model, row_id)


async def notified_users(session: AsyncSession) -> list[uuid.UUID]:
    session.expire_all()
    return list(await session.scalars(select(OutgoingNotification.user_id).order_by(OutgoingNotification.id)))


# 정리


async def test_erases_everything_of_the_user_and_nothing_else(client: AsyncClient, session: AsyncSession):
    ids = await seed(session)

    response = await withdraw(client, LEAVING)

    assert [response.status_code, response.json()] == [status.HTTP_200_OK, {'status': 'processed'}]
    for key in ('mine', 'deleted_post'):
        post = await fresh(session, Post, ids[key])
        assert [post.author_id, post.title, post.updated_at] == [None, '첫 모험', WRITTEN_AT]
    for key in ('my_comment', 'deleted_comment'):
        comment = await fresh(session, Comment, ids[key])
        assert [comment.author_id, comment.updated_at] == [None, WRITTEN_AT]
    report = await fresh(session, Report, ids['my_report'])
    assert [report.reporter_id, report.handled_by, report.outcome] == [None, OPERATOR, 'dismissed']
    assert await fresh(session, Author, LEAVING) is None
    assert await notified_users(session) == [STAYING]
    assert (await fresh(session, Post, ids['theirs'])).author_id == STAYING
    assert (await fresh(session, Comment, ids['their_comment'])).author_id == STAYING
    assert (await fresh(session, Report, ids['their_report'])).reporter_id == STAYING
    assert (await fresh(session, Author, STAYING)).nickname == '남는 이'


async def test_repeated_and_unknown_withdrawals_are_processed(client: AsyncClient, session: AsyncSession):
    await seed(session)

    first = await withdraw(client, LEAVING)
    again = await withdraw(client, LEAVING)
    unknown = await withdraw(client, uuid.uuid4())

    for response in (first, again, unknown):
        assert [response.status_code, response.json()] == [status.HTTP_200_OK, {'status': 'processed'}]
    assert await notified_users(session) == [STAYING]


async def test_logs_counts_without_the_user_id(
    client: AsyncClient, session: AsyncSession, caplog: pytest.LogCaptureFixture
):
    await seed(session)

    with caplog.at_level(logging.INFO, logger='app.withdrawal.service'):
        await withdraw(client, LEAVING)
        await withdraw(client, LEAVING)

    first, second = [record for record in caplog.records if record.name == 'app.withdrawal.service']
    counts = ('blanked_posts', 'blanked_comments', 'blanked_reports', 'deleted_authors', 'deleted_notifications')
    assert [getattr(first, name) for name in counts] == [2, 2, 1, 1, 2]
    assert [getattr(second, name) for name in counts] == [0, 0, 0, 0, 0]
    assert first.operation == 'board.withdrawal'
    assert str(LEAVING) not in json.dumps(first.__dict__, default=str)


async def test_failure_in_the_middle_changes_nothing(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    ids = await seed(session)

    async def broken(*_args) -> int:
        raise RuntimeError('DB 가 끊겼다')

    monkeypatch.setattr(repository, 'delete_author', broken)

    # 시험의 클라이언트는 앱의 예외를 그대로 올린다(서버라면 500 이다)
    with pytest.raises(RuntimeError):
        await withdraw(client, LEAVING)

    assert (await fresh(session, Post, ids['mine'])).author_id == LEAVING
    assert (await fresh(session, Comment, ids['my_comment'])).author_id == LEAVING
    assert (await fresh(session, Report, ids['my_report'])).reporter_id == LEAVING
    assert await notified_users(session) == [LEAVING, LEAVING, STAYING]


# 입력


@pytest.mark.parametrize(
    ('body', 'errors'),
    [
        ('{}', {'withdrawn_at': [NO_OFFSET_MESSAGE, NOT_ISO_MESSAGE]}),
        ('{"withdrawn_at": null}', {'withdrawn_at': [NO_OFFSET_MESSAGE, NOT_ISO_MESSAGE]}),
        ('{"withdrawn_at": 5}', {'withdrawn_at': [NO_OFFSET_MESSAGE, NOT_ISO_MESSAGE]}),
        ('{"withdrawn_at": "어제"}', {'withdrawn_at': [NO_OFFSET_MESSAGE, NOT_ISO_MESSAGE]}),
        ('{"withdrawn_at": "2026-10-28T03:00:00"}', {'withdrawn_at': [NO_OFFSET_MESSAGE]}),
        ('{"withdrawn_at": "2026-10-28T03:00:00+0900"}', {'withdrawn_at': [NO_OFFSET_MESSAGE]}),
        ('{"withdrawn_at": "2026-02-30T03:00:00Z"}', {'withdrawn_at': [NOT_ISO_MESSAGE]}),
        (
            '{"email": 1, "withdrawn_at": "x", "a": 2}',
            {
                'email': ['property email should not exist'],
                'a': ['property a should not exist'],
                'withdrawn_at': [NO_OFFSET_MESSAGE, NOT_ISO_MESSAGE],
            },
        ),
    ],
)
async def test_bad_body_is_400_with_nest_messages(client: AsyncClient, body: str, errors: dict):
    response = await withdraw(client, uuid.uuid4(), body)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {'detail': '입력이 올바르지 않습니다.', 'errors': errors}
    assert list(response.json()['errors']) == list(errors)


@pytest.mark.parametrize(
    'value',
    [
        '2026-10-28T03:00:00Z',
        '2026-10-28 03:00:00+09:00',
        '2024-02-29T00:00:00-05:30',
        '2026-W05-3T24:00+09:00',
        '20261028T030000Z',
    ],
)
async def test_iso_times_with_offset_are_accepted(client: AsyncClient, value: str):
    response = await withdraw(client, uuid.uuid4(), json.dumps({'withdrawn_at': value}))

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.parametrize(
    'value',
    ['0060-02-29T00:00Z', '2026-366T00:00Z', '2026-04-31T00:00Z', '2026-13-01T00:00Z', '2026-10-28T03:00:00Z\n'],
)
def test_impossible_or_malformed_dates_are_not_iso(value: str):
    with pytest.raises(ValueError, match='ISO 8601'):
        WithdrawalDto.model_validate({'withdrawn_at': value})


def test_ordinal_dates_count_leap_years():
    assert WithdrawalDto.model_validate({'withdrawn_at': '2024-366T00:00Z'}).withdrawn_at == '2024-366T00:00Z'


def test_real_date_check_on_its_own_follows_javascript_date():
    # 모양의 검사를 거치지 않은 글에도 답한다. 날짜가 없으면 따지지 않고, 없는 달은 아니다
    assert is_real_date('날짜 없음')
    assert not is_real_date('2026-13-01')


def test_non_object_body_is_left_to_pydantic():
    with pytest.raises(ValueError):
        WithdrawalDto.model_validate(['2026-10-28T03:00:00Z'])


@pytest.mark.parametrize(
    'user_id', ['not-a-uuid', '6f1e2d3c4b5a4c6d8e7f0a1b2c3d4e5f', '6f1e2d3c-4b5a-4c6d-8e7f-0a1b2c3d4e5']
)
async def test_user_id_that_is_not_a_hyphenated_uuid_is_400_without_fields(client: AsyncClient, user_id: str):
    response = await withdraw(client, user_id, '{"email": 1}')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {'detail': '요청이 올바르지 않습니다.'}


async def test_upper_case_uuid_is_accepted(client: AsyncClient):
    response = await withdraw(client, str(uuid.uuid4()).upper())

    assert response.status_code == status.HTTP_200_OK


async def test_broken_json_is_400(client: AsyncClient):
    response = await withdraw(client, uuid.uuid4(), '{"withdrawn_at": ')

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {'detail': '요청이 올바르지 않습니다.'}
