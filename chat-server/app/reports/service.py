# chat-server/app/reports/service.py

"""
대화 속 캐릭터의 답을 신고한다(#678). 운영자가 보는 것은 app/operators/service.py 다.

지키는 것.
  - 자기가 볼 수 있는 대화의 캐릭터의 답만 신고한다(아니면 404 message_not_found, 사람의 말이면 422 not_reportable)
  - 같은 답을 두 번 신고하지 못한다(유일 제약, 409 already_reported)
  - 신고한 답과 그 앞의 말 몇 개(지금 가지의 것)를 굳혀 둔다. 운영자는 대화를 열지 않고 이것만 본다
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations import repository as conversations
from app.conversations.models import Conversation, ImportedCharacter, Message, Role
from app.conversations.service import MessageNotFoundError
from app.core.dependencies import Viewer
from app.ratings import allowed_ratings
from app.reports import repository
from app.reports.models import CONTEXT_MESSAGES, MessageReport
from app.reports.schemas import ReportCreate


class NotReportableError(Exception):
    """신고할 수 없는 말이다(사람의 말). 422 다."""


class AlreadyReportedError(Exception):
    """이미 신고한 답이다. 409 다."""


def context_of(before: Sequence[Message]) -> list[dict]:
    """신고한 답 앞의 말들 가운데 마지막 CONTEXT_MESSAGES 개(오래된 것부터)."""
    return [{'role': message.role, 'content': message.content} for message in before[-CONTEXT_MESSAGES:]]


def build_report(
    reporter_id: uuid.UUID,
    conversation: Conversation,
    character: ImportedCharacter,
    message: Message,
    before: Sequence[Message],
    data: ReportCreate,
) -> MessageReport:
    """신고와 굳힌 글을 만든다. 아직 저장하지 않는다."""
    return MessageReport(
        reporter_id=reporter_id,
        conversation_id=conversation.id,
        message_id=message.id,
        character_id=character.source_id,
        character_version=character.version,
        character_name=character.name,
        model_slug=conversation.model_slug,
        reason=data.reason,
        description=data.description,
        content=message.content,
        context=context_of(before),
    )


async def file_report(
    session: AsyncSession, viewer: Viewer, message_id: uuid.UUID, data: ReportCreate
) -> MessageReport:
    """신고를 접수한다."""
    found = await conversations.find_visible_message(
        session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
    )
    if found is None:
        raise MessageNotFoundError
    message, (conversation, character, _) = found
    if message.role != Role.ASSISTANT:
        raise NotReportableError
    path = await conversations.active_path(session, message.id)
    report = build_report(viewer.claims.user_id, conversation, character, message, path[:-1], data)
    repository.add(session, report)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise AlreadyReportedError from error
    await session.refresh(report)
    return report
