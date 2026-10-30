# story-server/app/operators/repository.py

"""
운영자의 감사 기록을 적는다. 덧붙이기만 한다. 커밋하지 않는다.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.operators.models import OperatorAction, OperatorRead


def add_record(session: AsyncSession, record: OperatorRead | OperatorAction) -> None:
    """감사 기록 한 줄을 세션에 올린다."""
    session.add(record)
