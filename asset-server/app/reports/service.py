# asset-server/app/reports/service.py

"""
공개 캐릭터를 신고한다(#678). 운영자의 처리는 app/operators/service.py 다.

지키는 것.
  - 신고할 수 있는 것은 그 사람이 볼 수 있는 공개 캐릭터다(공개 목록과 같다). 볼 수 없거나 숨긴 것은 404 다
  - 자기 캐릭터는 신고하지 못한다(403 own_character). 같은 캐릭터를 두 번 신고하지 못한다(409 already_reported)
  - 두 번째 신고는 유일 제약이 막는다(동시에 보내도 하나만 남는다). DB 가 정한다
"""

import uuid

from server_core.auth.tokens import AccessClaims
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.characters import service as characters
from app.reports import repository
from app.reports.models import CharacterReport
from app.reports.schemas import ReportCreate


class OwnCharacterReportError(Exception):
    """자기 캐릭터를 신고했다. 403 이다."""


class AlreadyReportedError(Exception):
    """이미 신고한 캐릭터다. 409 다."""


async def file_report(
    session: AsyncSession, viewer: AccessClaims, character_id: uuid.UUID, data: ReportCreate
) -> CharacterReport:
    """신고를 접수한다. 볼 수 없으면 CharacterNotFoundError, 자기 것이면 OwnCharacterReportError."""
    character, version = await characters.get_public(session, viewer, character_id)
    if characters.is_owner(character, viewer):
        raise OwnCharacterReportError
    report = CharacterReport(
        character_id=character_id,
        reporter_id=viewer.user_id,
        version=version.number,
        reason=data.reason,
        description=data.description,
    )
    repository.add(session, report)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise AlreadyReportedError from error
    await session.refresh(report)
    return report
