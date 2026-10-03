# game-server/migrations/env.py

"""
Alembic 이 마이그레이션을 실행할 때 부르는 파일.

    uv run alembic upgrade head                          # 마이그레이션 적용
    uv run alembic revision --autogenerate -m "설명"      # 모델과 DB 를 비교해 새 마이그레이션 만들기
    uv run alembic check                                 # 모델을 바꾸고 마이그레이션을 안 만들었는지 검사

DB 주소와 스키마는 앱과 같은 설정(app.core.config)에서 읽는다. alembic.ini 에 따로 적지 않는다.
두 곳에 적으면 한쪽만 고쳤을 때 서로 다른 DB 를 보게 된다.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.database import Base, create_engine

config = context.config

# alembic.ini 의 로그 설정을 적용한다
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

# 모델들이 등록된 목록. Alembic 이 이것과 실제 DB 를 비교한다.
# 모델 파일을 새로 만들면 여기서 불러와야 목록에 들어간다
target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    """주어진 연결로 마이그레이션을 실행한다."""
    # 스키마를 따로 지정하지 않는다. 연결의 search_path 가 이미 설정의 스키마를 가리킨다.
    # 어디까지 적용했는지 적는 표(alembic_version)도 그 스키마에 만들어진다.
    # 스키마마다 따로 있으므로, 개발용과 테스트용의 적용 상태가 섞이지 않는다
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_with_app_engine() -> None:
    """
    앱과 같은 방법으로 만든 엔진으로 DB 에 연결해 마이그레이션을 실행한다.

    같은 엔진이므로 search_path 도 같다. 마이그레이션이 만드는 테이블이 앱이 찾는 스키마에 놓인다.
    """
    engine = create_engine(settings)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    # DB 에 연결하지 않고 SQL 만 출력하는 방식(--sql). 쓰지 않는다
    raise SystemExit('이 프로젝트는 --sql(오프라인) 방식을 쓰지 않습니다.')

asyncio.run(run_migrations_with_app_engine())
