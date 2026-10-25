# board-server/tests/cleaning.py

"""
테스트가 시작할 때 테이블을 비우는 법. conftest.py 의 clean_tables 가 쓴다.

게시판(boards)은 비우지 않는다. 마이그레이션이 넣은 것이라 다시 넣을 길이 없다.
"""

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine

import app.authors.models  # noqa: F401  # 모델을 불러와야 Base.metadata 에 테이블이 들어간다
import app.boards.models  # noqa: F401
import app.comments.models  # noqa: F401
import app.notifications.models  # noqa: F401
import app.posts.models  # noqa: F401
import app.reports.models  # noqa: F401
from app.core.database import Base

# 비우지 않는 표
KEPT_TABLES = frozenset({'boards'})


def clearing_order() -> list[Table]:
    """비울 테이블들을 비울 순서대로. 가리키는 테이블이 먼저다(반대로 지우면 외래 키가 막는다)."""
    return [table for table in reversed(Base.metadata.sorted_tables) if table.name not in KEPT_TABLES]


async def clear_tables(engine: AsyncEngine) -> None:
    """데이터의 행을 모두 지운다. 한 트랜잭션이다."""
    async with engine.begin() as connection:
        for table in clearing_order():
            await connection.execute(table.delete())
