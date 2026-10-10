# game-server/tests/test_database.py

"""
DB 연결을 검증한다. 테스트가 정말로 테스트용 스키마에서 도는가.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import ping_database
from tests.conftest import TEST_SCHEMA


async def test_database_answers(session: AsyncSession):
    await ping_database(session)


async def test_tests_run_in_the_test_schema(session: AsyncSession):
    schema = await session.scalar(text('SELECT current_schema()'))

    # 개발용 데이터(game 스키마)를 건드리지 않는다
    assert schema == TEST_SCHEMA


async def test_connects_as_the_game_account(session: AsyncSession):
    user = await session.scalar(text('SELECT current_user'))

    # 관리용 슈퍼유저로 접속하면, 권한 때문에 실패해야 할 코드가 통과한다
    assert user == 'game'


async def test_cannot_read_the_auth_schema(session: AsyncSession):
    can_use = await session.scalar(text("SELECT has_schema_privilege(current_user, 'auth', 'USAGE')"))

    # 인증 서버의 테이블을 직접 읽지 않는다는 것을 약속이 아니라 DB 권한으로 지킨다
    assert can_use is False


async def test_the_extension_schema_comes_after_the_test_schema(session: AsyncSession):
    path = await session.scalar(text('SHOW search_path'))

    # 테이블은 앞의 스키마에 놓이고, 벡터 타입은 뒤의 확장 스키마에서 찾는다
    assert path == f'{TEST_SCHEMA}, extensions'


async def test_the_vector_type_can_be_used(session: AsyncSession):
    distance = await session.scalar(text("SELECT '[1, 0]'::vector <=> '[0, 1]'::vector"))

    # pgvector 가 켜져 있고 게임 계정이 쓸 수 있다. 직각인 두 벡터의 코사인 거리는 1 이다
    assert distance == 1.0
