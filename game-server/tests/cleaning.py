# game-server/tests/cleaning.py

"""
테스트가 시작할 때 테이블을 비우는 법. conftest.py 의 clean_tables 가 쓰고, tests/test_clean_tables.py 가 검증한다.

conftest.py 에 두지 않고 따로 둔다. 테스트 파일이 conftest.py 를 직접 불러오지 않게 하려는 것이다.
"""

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import Base


def clearing_order() -> list[Table]:
    """
    비울 테이블들을 비울 순서대로 돌려준다. 앱의 모델이 아는 테이블 전부다.

    가리키는 테이블이 먼저, 가리켜지는 테이블이 나중이다. 반대로 지우면 외래 키가 막는다.
    sorted_tables 는 가리켜지는 쪽부터 늘어놓으므로 뒤집는다.
    손으로 적지 않는다. 테이블이 새로 생겨도 모델에 있으면 저절로 들어간다.
    마이그레이션의 기록 테이블(alembic_version)은 모델이 아니라서 들어가지 않는다. 지우면 안 되는 테이블이다.
    """
    return list(reversed(Base.metadata.sorted_tables))


async def clear_tables(engine: AsyncEngine) -> None:
    """
    모든 테이블의 행을 지운다. 한 트랜잭션이다.

    TRUNCATE 를 쓰지 않고 DELETE 를 쓴다. TRUNCATE 는 테이블과 색인의 파일을 새로 만들어 바꿔 끼운다.
    테스트마다 수십 개의 파일이 생기고 버려져서, 디스크에 확정하는 일이 느린 곳(Windows 의 Docker)에서 크게 느려진다.
    테스트의 테이블에는 행이 몇 개뿐이라, 행을 지우는 DELETE 가 훨씬 싸다.
    """
    async with engine.begin() as connection:
        for table in clearing_order():
            await connection.execute(table.delete())
