# board-server/app/reports/reviews.py

"""
운영자가 신고를 읽고 처리한다. 신고하는 쪽은 service.py 다.

모두 운영자만 한다. 운영자인지를 가장 먼저 본다(403). 무엇이 얼마나 신고됐는지는 운영자만 알 일이다.
그다음이 "없는 것인가(404)"다.

처리는 신고 한 건이 아니라 신고당한 것 단위다. 한 글에 일곱 명이 신고해도 운영자는 한 번 처리한다.

지운 글과 지운 댓글에 걸린 신고도 읽고 처리한다. 신고당한 것을 운영자가 지운 뒤에도 신고는 열려 있다.
처리해서 닫아야 목록에서 빠진다. 지우는 일과 처리하는 일을 묶지 않았다. 지우지 않고 "문제없음"으로
닫는 일도 있고, 글쓴이가 스스로 지우는 일도 있다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Actor
from app.posts.policy import offset_of
from app.posts.service import post_not_found
from app.reports import repository
from app.reports.errors import comment_not_found, no_open_reports, operator_only_reports
from app.reports.policy import can_review
from app.reports.schemas import (
    OpenReportGroupPageResponse,
    ReportPageResponse,
    to_open_report_group_response,
    to_report_response,
)
from app.reports.targets import COMMENT, POST, ReportTarget, TargetState

# 신고당한 것의 상태를 찾는 열쇠. 종류와 번호다
TargetKey = tuple[str, int]


def ensure_operator(actor: Actor) -> None:
    """운영자인지 확인한다. 아니면 403 을 낸다."""
    if not can_review(actor.is_operator):
        raise operator_only_reports()


async def ensure_exists(session: AsyncSession, target: ReportTarget) -> None:
    """글이나 댓글이 있는지 확인한다. 지운 것도 있는 것이다. 없으면 404 를 낸다."""
    if not await repository.target_exists(session, target):
        raise post_not_found() if target.type == POST else comment_not_found()


def key_of(target: ReportTarget) -> TargetKey:
    return (target.type, target.id)


async def states_of(session: AsyncSession, targets: Sequence[ReportTarget]) -> dict[TargetKey, TargetState]:
    """신고당한 것들의 지금 상태(어느 글인가, 지웠는가)를 한 번에 읽는다. 글과 댓글을 한 번씩 묻는다."""
    posts = await repository.post_states(session, [target.id for target in targets if target.type == POST])
    comments = await repository.comment_states(session, [target.id for target in targets if target.type == COMMENT])
    states: dict[TargetKey, TargetState] = {(POST, post_id): state for post_id, state in posts.items()}
    states.update({(COMMENT, comment_id): state for comment_id, state in comments.items()})
    return states


def state_from(states: dict[TargetKey, TargetState], target: ReportTarget) -> TargetState:
    """
    목록의 한 줄에 맞는 상태를 꺼낸다. 글과 댓글은 행을 없애지 않고 외래 키가 신고를 지키므로 늘 있다.
    없으면 DB 가 약속을 어긴 것이다.
    """
    state = states.get(key_of(target))
    if state is None:
        raise LookupError('신고당한 것을 찾지 못했다')
    return state


async def list_open(session: AsyncSession, actor: Actor, page: int, size: int) -> OpenReportGroupPageResponse:
    """열린 신고를 신고당한 것마다 묶어 한 쪽 돌려준다. 가장 오래 기다린 것부터다. 운영자가 아니면 403 이다."""
    ensure_operator(actor)
    groups = await repository.find_open_groups(session, offset_of(page, size), size)
    total = await repository.count_open_targets(session)
    states = await states_of(session, [group.target for group in groups])
    items = [to_open_report_group_response(group, state_from(states, group.target)) for group in groups]
    return OpenReportGroupPageResponse(items=items, page=page, size=size, total=total)


async def list_reports_of(
    session: AsyncSession, target: ReportTarget, actor: Actor, page: int, size: int
) -> ReportPageResponse:
    """
    글이나 댓글 하나에 걸린 신고를 모두(처리한 것도) 한 쪽 돌려준다. 최근 것부터다.
    운영자가 아니면 403, 그런 것이 없으면 404 다. 지운 것이어도 읽는다.
    """
    ensure_operator(actor)
    await ensure_exists(session, target)
    reports = await repository.list_reports_of(session, target, offset_of(page, size), size)
    total = await repository.count_reports_of(session, target)
    return ReportPageResponse(
        items=[to_report_response(report) for report in reports], page=page, size=size, total=total
    )


async def handle(session: AsyncSession, target: ReportTarget, actor: Actor, outcome: str) -> None:
    """
    글이나 댓글 하나에 걸린 열린 신고를 모두 처리해서 닫는다.
    운영자가 아니면 403, 그런 것이 없거나 열린 신고가 없으면 404 다. 닫은 뒤에 새 신고가 오면 다시 열린다.
    """
    ensure_operator(actor)
    await ensure_exists(session, target)
    closed = await repository.close_open_reports(session, target, actor.user_id, outcome)
    if closed == 0:
        raise no_open_reports()
    await session.commit()
