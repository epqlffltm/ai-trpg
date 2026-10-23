# chat-server/app/operators/service.py

"""
운영자가 대화 속 답의 신고를 보고 처리한다(#678). docs/architecture/operators.md 의 규칙을 따른다.

  - 신고에 굳힌 대화의 글을 볼 때마다 감사 기록(operator_reads)을 먼저 저장한다. 없는 신고를 본 시도도 남긴다
  - 처리는 감사 기록(operator_actions)과 한 트랜잭션에서 커밋한다.
    이미 처리한 신고면 409 already_handled 이고 기록도 없다
  - 신고의 목록은 대화의 글을 싣지 않는다. 그래서 보는 기록을 남기지 않는다
  - 사유와 본 내용은 로그에 싣지 않는다
"""

import logging
import uuid
from datetime import datetime

from server_core.observability.context import current_ids
from sqlalchemy.ext.asyncio import AsyncSession

from app.operators import repository
from app.operators.models import ActionKind, OperatorAction, OperatorRead, ReadKind
from app.reports import repository as reports
from app.reports.models import MessageReport, ReportOutcome

logger = logging.getLogger(__name__)

# 로그의 operation(관측 규격, trpg-server 와 같다)
READ_OPERATION = 'operator.read'
ACT_OPERATION = 'operator.act'


class ReportNotFoundError(Exception):
    """그런 신고가 없다. 404 다."""


class AlreadyHandledError(Exception):
    """이미 처리한 신고다. 409 다."""


def build_read(operator_id: uuid.UUID, report_id: uuid.UUID, reason: str, now: datetime) -> OperatorRead:
    """보는 기록 한 줄. 아직 저장하지 않는다."""
    return OperatorRead(
        operator_id=operator_id,
        read_at=now,
        target_kind=ReadKind.MESSAGE_REPORT,
        target_id=report_id,
        reason=reason,
        request_id=current_ids().get('request_id'),
    )


def build_action(operator_id: uuid.UUID, kind: ActionKind, report_id: uuid.UUID, reason: str, now: datetime):
    """처리 기록 한 줄. 아직 저장하지 않는다."""
    return OperatorAction(
        operator_id=operator_id,
        acted_at=now,
        action=kind,
        target_id=report_id,
        reason=reason,
        request_id=current_ids().get('request_id'),
    )


def log_record(operation: str, operator_id: uuid.UUID, kind: str, target_id: uuid.UUID) -> None:
    """감사 기록과 같은 것을 로그에도 남긴다. 사유와 본 내용은 싣지 않는다."""
    logger.info(
        '운영자가 신고를 보거나 처리했다',
        extra={'operation': operation, 'operator_id': str(operator_id), 'kind': kind, 'target_id': str(target_id)},
    )


async def list_open(session: AsyncSession, limit: int, offset: int) -> tuple[list[MessageReport], int]:
    """열린 신고의 한 쪽과 전체 수."""
    return await reports.list_open(session, limit, offset)


async def read_report(
    session: AsyncSession, operator_id: uuid.UUID, report_id: uuid.UUID, reason: str, now: datetime
) -> MessageReport:
    """신고 하나와 굳힌 글. 보기 전에 감사 기록을 저장한다. 없으면 ReportNotFoundError(기록은 남는다)."""
    record = build_read(operator_id, report_id, reason, now)
    repository.add_record(session, record)
    await session.commit()
    log_record(READ_OPERATION, operator_id, record.target_kind, report_id)
    report = await reports.get(session, report_id)
    if report is None:
        raise ReportNotFoundError
    return report


def action_kind(outcome: ReportOutcome) -> ActionKind:
    """처리의 결과에 맞는 기록의 종류."""
    return ActionKind.REPORT_ACTION if outcome == ReportOutcome.ACTIONED else ActionKind.REPORT_DISMISS


async def handle_report(
    session: AsyncSession, operator_id: uuid.UUID, report_id: uuid.UUID, outcome: ReportOutcome, reason: str, now
) -> None:
    """신고를 처리한다. 없으면 ReportNotFoundError, 이미 처리했으면 AlreadyHandledError."""
    if not await reports.handle(session, report_id, operator_id, outcome, now):
        await session.rollback()
        raise ReportNotFoundError if await reports.get(session, report_id) is None else AlreadyHandledError
    action = build_action(operator_id, action_kind(outcome), report_id, reason, now)
    repository.add_record(session, action)
    await session.commit()
    log_record(ACT_OPERATION, operator_id, action.action, report_id)
