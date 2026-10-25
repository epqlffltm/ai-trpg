# board-server/app/reports/repository.py

"""
신고와 신고당한 것(글, 댓글)을 DB 에서 읽고 쓴다. 커밋하지 않는다. 언제 커밋할지는 서비스가 안다.

  - 글과 댓글을 찾는 데 글 모듈과 댓글 모듈의 서비스를 쓰지 않고 테이블을 바로 읽는다.
    댓글 모듈은 글 모듈을 쓰므로, 둘을 함께 가져다 쓰는 것보다 테이블을 읽는 편이 모듈 사이의 고리를 만들지 않는다
  - 신고하기는 지우지 않은 것만 본다. 운영자가 읽고 처리할 때는 지운 것도 있는 것이다(행은 남는다)
  - 열린 신고의 묶음은 DB 가 센다(GROUP BY, 사유마다 FILTER). 한 글에 일곱 명이 신고해도 한 줄이다
  - 신고당한 것들의 상태는 글과 댓글을 한 번씩 묻는다. 한 줄마다 물으면 한 쪽에 스무 번이 나간다
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Row, distinct, exists, func, insert, nulls_last, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.comments.models import Comment
from app.posts.models import Post
from app.reports.models import Report
from app.reports.policy import REPORT_REASONS
from app.reports.schemas import OpenReportGroup
from app.reports.targets import POST, ReportTarget, TargetState, target_of


def of_target(target: ReportTarget) -> ColumnElement[bool]:
    """이것을 가리키는 신고의 조건."""
    return Report.post_id == target.id if target.type == POST else Report.comment_id == target.id


def is_open() -> ColumnElement[bool]:
    """처리하지 않은 신고."""
    return Report.handled_at.is_(None)


def reason_column(reason: str) -> str:
    """사유 하나의 건수를 담는 칸의 이름. 쿼리와 읽는 곳이 같은 이름을 쓴다."""
    return f'reason_{reason}'


async def find_live_post_author(session: AsyncSession, post_id: int) -> Row | None:
    """지우지 않은 글의 글쓴이(author_id 한 칸의 줄). 없거나 지운 글이면 None 이다."""
    query = select(Post.author_id).where(Post.id == post_id, Post.deleted_at.is_(None))
    return (await session.execute(query)).first()


async def find_live_comment_author(session: AsyncSession, comment_id: int) -> Row | None:
    """지우지 않은 댓글의 글쓴이. 없거나 지운 댓글, 지운 글에 달린 댓글이면 None 이다."""
    query = (
        select(Comment.author_id)
        .join(Post, Post.id == Comment.post_id)
        .where(Comment.id == comment_id, Comment.deleted_at.is_(None), Post.deleted_at.is_(None))
    )
    return (await session.execute(query)).first()


async def has_reported(session: AsyncSession, target: ReportTarget, reporter_id: uuid.UUID) -> bool:
    """이 사람이 이것을 이미 신고했는가. 처리한 신고도 센다."""
    query = select(exists().where(Report.reporter_id == reporter_id, of_target(target)))
    return bool(await session.scalar(query))


async def insert_report(
    session: AsyncSession, target: ReportTarget, reporter_id: uuid.UUID, reason: str, description: str | None
) -> Row:
    """신고를 넣고 접수에 쓸 칸(id, reason, created_at)을 돌려준다."""
    query = (
        insert(Report)
        .values(
            post_id=target.id if target.type == POST else None,
            comment_id=None if target.type == POST else target.id,
            reporter_id=reporter_id,
            reason=reason,
            description=description,
        )
        .returning(Report.id, Report.reason, Report.created_at)
    )
    return (await session.execute(query)).one()


async def target_exists(session: AsyncSession, target: ReportTarget) -> bool:
    """글이나 댓글이 있는가. 지운 것도 있는 것이다."""
    model = Post if target.type == POST else Comment
    return bool(await session.scalar(select(exists().where(model.id == target.id))))


async def list_reports_of(session: AsyncSession, target: ReportTarget, offset: int, limit: int) -> Sequence[Report]:
    """이것에 걸린 신고 한 쪽(처리한 것도). 최근 것(번호가 큰 것)부터다."""
    query = select(Report).where(of_target(target)).order_by(Report.id.desc()).offset(offset).limit(limit)
    return (await session.scalars(query)).all()


async def count_reports_of(session: AsyncSession, target: ReportTarget) -> int:
    """이것에 걸린 신고의 수(처리한 것도)."""
    return await session.scalar(select(func.count()).select_from(Report).where(of_target(target))) or 0


async def close_open_reports(session: AsyncSession, target: ReportTarget, handled_by: uuid.UUID, outcome: str) -> int:
    """이것에 걸린 열린 신고를 모두 닫고 닫은 수를 돌려준다. 한 문장이라 처리한 시각이 같다."""
    query = (
        update(Report)
        .where(of_target(target), is_open())
        .values(handled_at=func.now(), handled_by=handled_by, outcome=outcome)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(query)
    return result.rowcount  # type: ignore[attr-defined]


def open_group_of(row: Row) -> OpenReportGroup:
    """DB 가 준 한 줄을 묶음으로."""
    mapping = row._mapping
    return OpenReportGroup(
        target=target_of(mapping['post_id'], mapping['comment_id']),
        open_count=mapping['open_count'],
        reasons={reason: mapping[reason_column(reason)] for reason in REPORT_REASONS},
        first_reported_at=mapping['first_reported_at'],
        last_reported_at=mapping['last_reported_at'],
    )


async def find_open_groups(session: AsyncSession, offset: int, limit: int) -> list[OpenReportGroup]:
    """
    열린 신고를 신고당한 것마다 묶어 읽는다. 처음 신고가 이른 것부터다.
    처음 신고의 시각이 같으면 번호로 줄을 세운다. 쪽을 넘겨도 순서가 흔들리지 않게 한다.
    """
    first_reported_at = func.min(Report.created_at).label('first_reported_at')
    reason_counts = [
        func.count().filter(Report.reason == reason).label(reason_column(reason)) for reason in REPORT_REASONS
    ]
    query = (
        select(
            Report.post_id,
            Report.comment_id,
            func.count().label('open_count'),
            first_reported_at,
            func.max(Report.created_at).label('last_reported_at'),
            *reason_counts,
        )
        .where(is_open())
        .group_by(Report.post_id, Report.comment_id)
        .order_by(first_reported_at.asc(), nulls_last(Report.post_id.asc()), nulls_last(Report.comment_id.asc()))
        .offset(offset)
        .limit(limit)
    )
    return [open_group_of(row) for row in (await session.execute(query)).all()]


async def count_open_targets(session: AsyncSession) -> int:
    """
    열린 신고가 걸린 것의 수. 글과 댓글을 따로 세어 더한다.
    한 신고는 둘 가운데 하나만 가리키고, 글의 번호와 댓글의 번호는 서로 다른 것을 센다.
    """
    query = select(func.count(distinct(Report.post_id)) + func.count(distinct(Report.comment_id))).where(is_open())
    return await session.scalar(query) or 0


async def post_states(session: AsyncSession, post_ids: Sequence[int]) -> dict[int, TargetState]:
    """글들의 지금 상태. 지운 글도 읽는다."""
    if not post_ids:
        return {}
    rows = (await session.execute(select(Post.id, Post.deleted_at).where(Post.id.in_(post_ids)))).all()
    return {row.id: TargetState(post_id=row.id, deleted=row.deleted_at is not None) for row in rows}


async def comment_states(session: AsyncSession, comment_ids: Sequence[int]) -> dict[int, TargetState]:
    """댓글들의 지금 상태(달린 글, 지웠는가). 지운 댓글도 읽는다."""
    if not comment_ids:
        return {}
    query = select(Comment.id, Comment.post_id, Comment.deleted_at).where(Comment.id.in_(comment_ids))
    rows = (await session.execute(query)).all()
    return {row.id: TargetState(post_id=row.post_id, deleted=row.deleted_at is not None) for row in rows}
