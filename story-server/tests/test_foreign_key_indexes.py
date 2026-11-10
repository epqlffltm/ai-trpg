# story-server/tests/test_foreign_key_indexes.py

"""
외래 키마다 그 칸으로 찾을 색인이 있는지 본다(#1259). 실제 DB 의 테스트 스키마를 읽는다.

외래 키가 가리키는 줄을 지우면 PostgreSQL 이 가리키던 쪽을 그 칸으로 찾는다(CASCADE, SET NULL, RESTRICT 모두).
색인이 없으면 지우는 줄마다 표 전체를 훑는다. 관계로 읽을 때도 같은 칸으로 찾는다.

보는 것: 외래 키의 칸들이 어느 색인의 앞 칸들과 같은가. 조건이 붙은 색인(부분 색인)은 치지 않는다.
일부러 색인을 두지 않는 키가 생기면 WITHOUT_INDEX 에 까닭과 함께 적는다.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 색인 없이 두기로 한 외래 키. '표.제약 이름' 과 까닭이다
WITHOUT_INDEX: dict[str, str] = {}

UNINDEXED = text(
    """
    SELECT c.conrelid::regclass::text || '.' || c.conname
      FROM pg_constraint c
     WHERE c.contype = 'f'
       AND c.connamespace = current_schema()::regnamespace
       AND NOT EXISTS (
           SELECT 1
             FROM pg_index i
            WHERE i.indrelid = c.conrelid
              AND i.indisvalid
              AND i.indpred IS NULL
              AND i.indnkeyatts >= cardinality(c.conkey)
              AND (i.indkey::int2[])[0:cardinality(c.conkey) - 1] @> c.conkey
       )
     ORDER BY 1
    """
)


async def test_every_foreign_key_has_an_index_to_find_it_by(session: AsyncSession):
    unindexed = [name for name in await session.scalars(UNINDEXED) if name.split('.', 1)[-1] not in WITHOUT_INDEX]

    assert unindexed == []
