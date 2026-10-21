# chat-server/tests/test_schema_isolation.py

"""
chat 계정이 다른 서비스의 스키마에 닿지 못하는지 DB 권한으로 확인한다.

서비스마다 계정과 스키마를 따로 둔다(docker/postgres/init/). 서로의 테이블을 직접 읽지 않고 API 로만 묻는다는 약속을
코드 리뷰가 아니라 DB 가 지키게 한다.
누군가 편하자고 `GRANT USAGE ON SCHEMA auth TO chat` 을 실행하면 여기서 실패한다.

목록은 이름을 하나씩 적지 않고 DB 에서 읽는다. 새 서비스가 스키마를 만들면 따로 고치지 않아도 검사에 들어간다.
허용할 것만 적는다(공용 스키마와 확장 스키마). 그 밖의 남의 스키마는 모두 막혀 있어야 한다.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

# 시스템 스키마(pg_catalog, information_schema 등)는 누구나 읽는다. 서비스의 데이터가 아니라서 검사에서 뺀다
NON_SYSTEM = "nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema'"

# chat 계정이 읽어도 되는 남의 스키마. public 은 PostgreSQL 기본 스키마,
# extensions 는 pgvector 가 놓인 곳이다(게임 서버만 쓴다)
SHARED_SCHEMAS = {'public', 'extensions'}

# 권한이 없을 때의 SQLSTATE(insufficient_privilege)
INSUFFICIENT_PRIVILEGE = '42501'


async def foreign_schemas(session: AsyncSession) -> set[str]:
    """chat 계정이 주인이 아닌 서비스 스키마의 이름."""
    rows = await session.scalars(
        text(f'SELECT nspname FROM pg_namespace WHERE {NON_SYSTEM} AND nspowner <> current_user::regrole')
    )
    return set(rows) - SHARED_SCHEMAS


async def schemas_with(session: AsyncSession, privilege: str) -> set[str]:
    """chat 계정이 이 권한(USAGE, CREATE)을 가진 스키마의 이름."""
    rows = await session.scalars(
        text(f'SELECT nspname FROM pg_namespace WHERE {NON_SYSTEM} AND has_schema_privilege(current_user, oid, :p)'),
        {'p': privilege},
    )
    return set(rows)


async def own_schemas(session: AsyncSession) -> set[str]:
    """chat 계정이 주인인 스키마의 이름(chat, chat_test)."""
    rows = await session.scalars(text('SELECT nspname FROM pg_namespace WHERE nspowner = current_user::regrole'))
    return set(rows)


async def refusal_code(session: AsyncSession, statement: str) -> str | None:
    """
    문장을 실행해 DB 가 거절한 SQLSTATE 를 돌려준다. 통과하면 None.
    세이브포인트 안에서 실행해, 거절된 뒤에도 같은 세션으로 다음 문장을 실행할 수 있게 한다.
    """
    try:
        async with session.begin_nested():
            await session.execute(text(statement))
    except DBAPIError as error:
        return getattr(error.orig, 'sqlstate', None)
    return None


async def test_the_other_services_schemas_are_in_this_database(session: AsyncSession):
    others = await foreign_schemas(session)

    # 검사할 대상이 없으면 아래 테스트가 아무것도 확인하지 않고 통과한다. 인증 서버의 스키마는 어느 환경에나 있다
    assert 'auth' in others


async def test_cannot_use_any_schema_of_another_service(session: AsyncSession):
    readable = await schemas_with(session, 'USAGE')
    others = await foreign_schemas(session)

    # USAGE 가 없으면 그 스키마 안의 어떤 테이블도 이름으로 찾지 못한다
    assert readable & others == set()


async def test_can_create_only_in_its_own_schemas(session: AsyncSession):
    writable = await schemas_with(session, 'CREATE')

    # 공용 스키마(public, extensions)에도 만들지 못한다. 만들 수 있으면 다른 서비스의 이름을 가로챌 수 있다
    assert writable == await own_schemas(session)


async def test_cannot_create_new_schemas(session: AsyncSession):
    can_create = await session.scalar(text("SELECT has_database_privilege(current_user, current_database(), 'CREATE')"))

    # 스키마는 초기화 스크립트(슈퍼유저)만 만든다. chat 계정이 새 스키마를 만들어 권한 경계를 넓히지 못한다
    assert can_create is False


async def test_reading_by_full_name_is_refused(session: AsyncSession):
    others = sorted(await foreign_schemas(session))

    # search_path 와 상관없이 `auth.표이름` 처럼 스키마까지 적어도 막힌다.
    # 표가 있는지 보기 전에 스키마의 USAGE 를 먼저 검사하므로, 없는 표 이름으로도 권한 오류가 난다
    codes = {name: await refusal_code(session, f'SELECT 1 FROM {name}.any_table') for name in others}

    assert codes == dict.fromkeys(others, INSUFFICIENT_PRIVILEGE)


async def test_creating_a_table_there_is_refused(session: AsyncSession):
    others = sorted(await foreign_schemas(session))

    codes = {name: await refusal_code(session, f'CREATE TABLE {name}.planted (id int)') for name in others}

    assert codes == dict.fromkeys(others, INSUFFICIENT_PRIVILEGE)


@pytest.mark.parametrize('privilege', ['USAGE', 'CREATE'])
async def test_no_other_account_can_reach_the_chat_schemas(session: AsyncSession, privilege: str):
    # 반대 방향. chat 서버가 자기 스키마를 남에게 열지 않았는지 본다(마이그레이션의 GRANT 실수 등).
    # 슈퍼유저는 권한 검사를 받지 않으므로 뺀다. 로그인할 수 없는 기본 역할(pg_read_all_data 등)도 뺀다
    rows = await session.execute(
        text(
            'SELECT r.rolname, n.nspname FROM pg_roles r CROSS JOIN pg_namespace n '
            'WHERE r.rolcanlogin AND NOT r.rolsuper AND r.oid <> current_user::regrole '
            'AND n.nspowner = current_user::regrole AND has_schema_privilege(r.oid, n.oid, :p)'
        ),
        {'p': privilege},
    )

    assert rows.all() == []
