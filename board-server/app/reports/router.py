# board-server/app/reports/router.py

"""
신고의 API. 주소를 받아 서비스를 부르고, 결과를 돌려준다.

신고하기(로그인한 누구나)
    POST /posts/{id}/reports                 글을 신고한다
    POST /comments/{id}/reports              댓글(답글 포함)을 신고한다

읽고 처리하기(운영자)
    GET  /reports                            열린 신고를 신고당한 것마다 묶은 목록. 오래 기다린 것부터
    GET  /posts/{id}/reports                 한 글에 걸린 신고 모두(처리한 것도). 설명과 신고한 사람이 나온다
    GET  /comments/{id}/reports              한 댓글에 걸린 신고 모두
    PUT  /posts/{id}/reports/outcome         한 글에 걸린 열린 신고를 모두 처리해서 닫는다
    PUT  /comments/{id}/reports/outcome      한 댓글에 걸린 열린 신고를 모두 처리해서 닫는다

토큰을 먼저 본다(401). 그다음이 주소의 번호(모양이 아니면 DB 에 묻지 않고 404), 주소의 값과 본문의 검사(400) 차례다.
본문이 JSON 이 아니면 그 모든 것보다 먼저 400 이다(본문을 읽는 단계다. NestJS 로 쓰던 때도 같았다).
글을 지우는 것은 이미 있는 지우기 API 로 따로 한다(DELETE /posts/{id}).
신고는 결과마다 센다(board_reports_total).
"""

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.core.auth import FOR_OPERATORS, Member
from app.core.dependencies import Session
from app.core.ids import parse_record_id
from app.core.metrics import counted, record_report
from app.core.query_params import query_model, query_parameters
from app.posts.service import post_not_found
from app.reports import reviews, service
from app.reports.errors import comment_not_found
from app.reports.schemas import (
    CreateReportDto,
    HandleReportsDto,
    ListReportsQuery,
    OpenReportGroupPageResponse,
    ReportPageResponse,
    ReportReceiptResponse,
)
from app.reports.targets import ReportTarget, comment_target, post_target

router = APIRouter(tags=['reports'])


def post_in_path(post_id: Annotated[str, Path(alias='id')]) -> ReportTarget:
    """주소의 글. 번호의 모양이 아니면 그런 글이 없는 것이다(404)."""
    parsed = parse_record_id(post_id)
    if parsed is None:
        raise post_not_found()
    return post_target(parsed)


def comment_in_path(comment_id: Annotated[str, Path(alias='id')]) -> ReportTarget:
    """주소의 댓글. 번호의 모양이 아니면 그런 댓글이 없는 것이다(404)."""
    parsed = parse_record_id(comment_id)
    if parsed is None:
        raise comment_not_found()
    return comment_target(parsed)


PostTarget = Annotated[ReportTarget, Depends(post_in_path)]
CommentTarget = Annotated[ReportTarget, Depends(comment_in_path)]
ListQuery = Annotated[ListReportsQuery, Depends(query_model(ListReportsQuery))]


@router.post('/posts/{id}/reports', response_model=ReportReceiptResponse, status_code=status.HTTP_201_CREATED)
async def report_post(
    actor: Member, target: PostTarget, data: CreateReportDto, session: Session
) -> ReportReceiptResponse:
    """글을 신고한다. 접수했다는 것만 돌려준다."""
    with counted(partial(record_report, 'post')):
        return await service.file_report(session, target, actor, data)


@router.post('/comments/{id}/reports', response_model=ReportReceiptResponse, status_code=status.HTTP_201_CREATED)
async def report_comment(
    actor: Member, target: CommentTarget, data: CreateReportDto, session: Session
) -> ReportReceiptResponse:
    """댓글을 신고한다. 답글도 같다."""
    with counted(partial(record_report, 'comment')):
        return await service.file_report(session, target, actor, data)


@router.get(
    '/reports',
    response_model=OpenReportGroupPageResponse,
    status_code=status.HTTP_200_OK,
    openapi_extra={**query_parameters(ListReportsQuery), **FOR_OPERATORS},
)
async def list_open_reports(actor: Member, query: ListQuery, session: Session) -> OpenReportGroupPageResponse:
    """열린 신고의 목록. 신고당한 것마다 한 줄이다."""
    return await reviews.list_open(session, actor, query.page, query.size)


@router.get(
    '/posts/{id}/reports',
    response_model=ReportPageResponse,
    status_code=status.HTTP_200_OK,
    openapi_extra={**query_parameters(ListReportsQuery), **FOR_OPERATORS},
)
async def list_post_reports(
    actor: Member, target: PostTarget, query: ListQuery, session: Session
) -> ReportPageResponse:
    """한 글에 걸린 신고들."""
    return await reviews.list_reports_of(session, target, actor, query.page, query.size)


@router.get(
    '/comments/{id}/reports',
    response_model=ReportPageResponse,
    status_code=status.HTTP_200_OK,
    openapi_extra={**query_parameters(ListReportsQuery), **FOR_OPERATORS},
)
async def list_comment_reports(
    actor: Member, target: CommentTarget, query: ListQuery, session: Session
) -> ReportPageResponse:
    """한 댓글에 걸린 신고들."""
    return await reviews.list_reports_of(session, target, actor, query.page, query.size)


@router.put('/posts/{id}/reports/outcome', status_code=status.HTTP_204_NO_CONTENT, openapi_extra=FOR_OPERATORS)
async def handle_post_reports(actor: Member, target: PostTarget, data: HandleReportsDto, session: Session) -> None:
    """한 글에 걸린 열린 신고를 모두 처리한다."""
    await reviews.handle(session, target, actor, data.outcome)


@router.put('/comments/{id}/reports/outcome', status_code=status.HTTP_204_NO_CONTENT, openapi_extra=FOR_OPERATORS)
async def handle_comment_reports(
    actor: Member, target: CommentTarget, data: HandleReportsDto, session: Session
) -> None:
    """한 댓글에 걸린 열린 신고를 모두 처리한다."""
    await reviews.handle(session, target, actor, data.outcome)
