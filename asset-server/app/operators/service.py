# asset-server/app/operators/service.py

"""
운영자가 신고를 보고 캐릭터를 숨긴다(#678). docs/architecture/operators.md 의 규칙을 따른다.

  - 조치는 감사 기록(operator_actions)과 한 트랜잭션에서 커밋한다. 조치가 되지 않았으면 기록도 없다
  - 숨긴 캐릭터는 공개 목록, 공개 소개, 남의 새 대화(판 내주기), 남이 보는 그림에서 빠진다.
    주인은 계속 쓴다. 이미 시작한 남의 대화는 사본으로 돈다. 주인이 공개로 돌려도 숨김이 앞선다. 운영자만 푼다
  - 신고를 받아들이면(actioned) 숨기고, 받아들이지 않으면(dismissed) 그대로 둔다. 그 캐릭터의 열린 신고를 모두 처리한다
  - 사유와 운영자는 로그에 싣지 않는다(사유는 자유 글이다)
"""

import logging
import uuid
from datetime import datetime

from server_core.observability.context import current_ids
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters.models import Character
from app.characters.service import CharacterNotFoundError
from app.operators import repository
from app.operators.models import ActionKind, OperatorAction
from app.reports import repository as reports
from app.reports.models import CharacterReport, ReportOutcome
from app.reports.repository import OpenGroup

logger = logging.getLogger(__name__)

# 로그의 operation(관측 규격, trpg-server 와 같다)
ACT_OPERATION = 'operator.act'


def build_action(operator_id: uuid.UUID, kind: ActionKind, target_id: uuid.UUID, reason: str, now: datetime):
    """감사 기록 한 줄을 만든다. 아직 저장하지 않는다. 지금 요청의 식별자를 함께 적는다."""
    return OperatorAction(
        operator_id=operator_id,
        acted_at=now,
        action=kind,
        target_id=target_id,
        reason=reason,
        request_id=current_ids().get('request_id'),
    )


def log_action(action: OperatorAction) -> None:
    """감사 기록과 같은 것을 로그에도 남긴다. 사유는 싣지 않는다."""
    logger.info(
        '운영자가 조치했다',
        extra={
            'operation': ACT_OPERATION,
            'operator_id': str(action.operator_id),
            'action': action.action,
            'target_id': str(action.target_id),
        },
    )


async def locked_character(session: AsyncSession, character_id: uuid.UUID) -> Character:
    """잠가 읽은 캐릭터. 없으면 CharacterNotFoundError."""
    character = await repository.lock_character(session, character_id)
    if character is None:
        raise CharacterNotFoundError
    return character


def hide_kind(hidden: bool) -> ActionKind:
    """숨기기와 풀기의 조치 종류."""
    return ActionKind.CHARACTER_HIDE if hidden else ActionKind.CHARACTER_UNHIDE


def set_hidden(character: Character, hidden: bool, now: datetime) -> None:
    """숨긴다(이미 숨겼으면 처음 숨긴 시각을 둔다) 또는 푼다."""
    if not hidden:
        character.hidden_at = None
    elif character.hidden_at is None:
        character.hidden_at = now


async def list_open(session: AsyncSession, limit: int, offset: int) -> tuple[list[OpenGroup], int]:
    """열린 신고의 묶음 한 쪽과 전체 묶음의 수."""
    return await reports.open_groups(session, limit, offset)


async def list_reports(session: AsyncSession, character_id: uuid.UUID) -> list[CharacterReport]:
    """그 캐릭터의 신고 전부. 캐릭터가 없으면 CharacterNotFoundError."""
    if await session.get(Character, character_id) is None:
        raise CharacterNotFoundError
    return await reports.list_for_character(session, character_id)


async def handle_reports(
    session: AsyncSession, operator_id: uuid.UUID, character_id: uuid.UUID, outcome: ReportOutcome, reason: str, now
) -> tuple[int, bool]:
    """그 캐릭터의 열린 신고를 처리한다. actioned 면 숨긴다. (처리한 수, 숨겨져 있는가)."""
    character = await locked_character(session, character_id)
    handled = await reports.handle_open(session, character_id, operator_id, outcome, now)
    kind = ActionKind.CHARACTER_HIDE if outcome == ReportOutcome.ACTIONED else ActionKind.REPORTS_DISMISS
    if outcome == ReportOutcome.ACTIONED:
        set_hidden(character, True, now)
    action = build_action(operator_id, kind, character_id, reason, now)
    repository.add_action(session, action)
    await session.commit()
    log_action(action)
    return handled, character.hidden_at is not None


async def change_hidden(
    session: AsyncSession, operator_id: uuid.UUID, character_id: uuid.UUID, hidden: bool, reason: str, now: datetime
) -> bool:
    """캐릭터를 숨기거나 푼다. 숨겨져 있는가를 돌려준다."""
    character = await locked_character(session, character_id)
    set_hidden(character, hidden, now)
    action = build_action(operator_id, hide_kind(hidden), character_id, reason, now)
    repository.add_action(session, action)
    await session.commit()
    log_action(action)
    return character.hidden_at is not None
