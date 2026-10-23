# trpg-server/app/core/database.py

"""
게임 서버의 DB 연결. 테이블 모델의 부모(Base)와, 확장(pgvector)의 스키마를 함께 보는 엔진이다.

엔진, 세션, 요청마다의 세션, DB 가 응답하는지 보는 것은 공용 코드(server_core/database.py)다(#589).
풀의 크기는 설정(DB_POOL_SIZE, DB_MAX_OVERFLOW)에서 읽는다. 적지 않으면 5 와 10 이다(SQLAlchemy 의 기본값).
"""

from server_core import database
from server_core.database import NAMING_CONVENTION
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings

# 확장(pgvector)이 놓인 스키마. 슈퍼유저가 만들어 두고 게임 계정에게 읽기만 준다
# (docker/postgres/init/03-extensions.sql).
# 확장은 데이터베이스마다 한 번, 스키마 하나에만 놓인다. game 과 game_test 가 함께 쓴다
EXTENSIONS_SCHEMA = 'extensions'


class Base(DeclarativeBase):
    """
    게임 서버의 모든 테이블 모델의 부모.

    이 클래스를 물려받은 모델은 Base.metadata 에 등록된다.
    Alembic 이 그 목록과 실제 DB 를 비교해 마이그레이션을 만든다. 제약과 색인의 이름은 공용 규칙으로 짓는다.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine(settings: Settings) -> AsyncEngine:
    """
    설정으로 엔진을 만든다. 공용 코드의 엔진에 확장의 스키마를 search_path 뒤에 더한다.

    벡터 타입(vector)과 거리 연산자를 스키마 이름 없이 쓸 수 있다.
    """
    return database.create_engine(settings, extra_schemas=(EXTENSIONS_SCHEMA,))
