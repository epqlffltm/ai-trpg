# story-server/app/references/setup.py

"""
말 한 번에 참고 자료를 찾는 것을 만든다(#1338). 앱을 만들 때 한 번 부른다(app/main.py).
"""

from ai_core.embedder import Embedder
from reference_core.finder import ReferenceFinder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.references.models import TABLES

# 로그의 operation. 찾지 못하면(시간이 다 되거나 실패) 이것으로 남고 대화는 참고 자료 없이 돈다
FIND_OPERATION = 'story.reference_find'


def build_reference_finder(
    session_factory: async_sessionmaker[AsyncSession], embedder: Embedder | None
) -> ReferenceFinder | None:
    """임베더가 있으면 이 서버의 표로 찾는 것을 만든다. 없으면(EMBEDDER=off) None 이다."""
    if embedder is None:
        return None
    return ReferenceFinder(TABLES, session_factory, embedder, operation=FIND_OPERATION)
