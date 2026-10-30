# story-server/app/reports/repository.py

"""
세션 속 답의 신고를 DB 에 쓴다. 커밋하지 않는다. 운영자가 읽고 처리하는 것은 운영자 API 가 더한다.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.models import MessageReport


def add(session: AsyncSession, report: MessageReport) -> None:
    """새 신고를 세션에 올린다."""
    session.add(report)
