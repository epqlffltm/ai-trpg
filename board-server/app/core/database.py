# board-server/app/core/database.py

"""
이 서버의 테이블 모델의 부모(Base). 엔진과 세션을 만드는 일은 공용 코드(server_core.database)가 한다.

Base 는 서버마다 둔다. 이 서버의 모델만 Base.metadata 에 등록되고,
Alembic 이 그 목록과 실제 DB 를 비교해 이 서버의 마이그레이션을 만든다.
"""

from server_core.database import NAMING_CONVENTION
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    모든 테이블 모델의 부모.

    이 클래스를 물려받은 모델은 Base.metadata 에 등록된다.
    제약과 색인의 이름은 서버들이 함께 쓰는 규칙(NAMING_CONVENTION)으로 짓는다.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
