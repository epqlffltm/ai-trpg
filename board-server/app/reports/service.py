# board-server/app/reports/service.py

"""
글과 댓글을 신고한다. 신고한 사람의 쪽이다. 운영자가 읽고 처리하는 쪽은 reviews.py 다.

규칙은 여기에 없다(app/reports/policy.py). 여기서는 필요한 것을 DB 에서 읽어 그 규칙에 묻고,
안 되면 거절하고, 되면 저장한다.

거절하는 차례는 "없는 것인가(404)", "자기 것인가(403)", "이미 신고했는가(409)", "너무 자주 하는가(429)"다.
이미 신고한 것은 행을 만들지 않으므로 횟수를 세기 전에 거절한다.

지운 글과 지운 댓글은 신고하지 못한다. 읽을 수 없는 것이다. 지운 글에 달린 댓글도 같다.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Actor
from app.core.write_limits import REPORT_LIMIT, ensure_within
from app.posts.service import post_not_found
from app.reports import repository
from app.reports.errors import already_reported, cannot_report_own, comment_not_found, is_unique_violation
from app.reports.policy import can_report
from app.reports.schemas import CreateReportDto, ReportReceiptResponse, to_report_receipt_response
from app.reports.targets import POST, ReportTarget


async def author_of(session: AsyncSession, target: ReportTarget) -> uuid.UUID | None:
    """신고하는 것을 쓴 사람. 없거나 지운 것이면 404 를 낸다. 글쓴이가 탈퇴했으면 None 이다."""
    if target.type == POST:
        row = await repository.find_live_post_author(session, target.id)
        if row is None:
            raise post_not_found()
    else:
        row = await repository.find_live_comment_author(session, target.id)
        if row is None:
            raise comment_not_found()
    return row.author_id


async def save(
    session: AsyncSession, target: ReportTarget, reporter_id: uuid.UUID, data: CreateReportDto
) -> ReportReceiptResponse:
    """
    신고를 저장하고 접수를 돌려준다. 같은 신고가 동시에 둘 들어오면 앞의 확인을 함께 지나칠 수 있다.
    그때는 DB 의 유일 제약이 늦은 쪽을 막는다. 그것도 409 로 돌려준다.
    """
    try:
        row = await repository.insert_report(session, target, reporter_id, data.reason, data.description)
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if is_unique_violation(error):
            raise already_reported() from error
        raise
    return to_report_receipt_response(row.id, row.reason, row.created_at)


async def file_report(
    session: AsyncSession, target: ReportTarget, reporter: Actor, data: CreateReportDto
) -> ReportReceiptResponse:
    """
    글이나 댓글을 신고한다. 없거나 지운 것이면 404, 자기 것이면 403, 이미 신고했으면 409,
    너무 자주 하면 429 다.
    """
    author_id = await author_of(session, target)
    if not can_report(author_id, reporter.user_id):
        raise cannot_report_own(target.type)
    if await repository.has_reported(session, target, reporter.user_id):
        raise already_reported()
    await ensure_within(session, REPORT_LIMIT, reporter)
    return await save(session, target, reporter.user_id, data)
