# asset-server/app/images/models.py

"""
그림의 테이블 모델(#566). 그림의 바이트는 저장소(SeaweedFS, S3)에 그림의 id 로 있고, 여기에는 그 그림의 행이 있다.

  - 그림은 바뀌지 않는다. 고치면 새 id 다. 그래서 nginx 가 그림의 id 로 캐시해도 틀어지지 않는다.
  - 형식, 크기(바이트), 너비와 높이는 다시 인코딩한 뒤의 것이다(app/images/decoder.py).
  - 누가 볼 수 있는지: 주인, 그리고 그 그림이 쓰인 판(image_uses)이 공개 캐릭터의 것이고 그 판의 등급을 볼 수 있는 사람.

표 둘이다.
  - images: 그림 하나에 한 줄.
  - image_uses: 그림이 쓰인 판. 게시할 때 판의 대표 그림과 소개 글의 그림을 적는다
    (app/images/service.py 의 record_uses).
    판이 지워지면(캐릭터를 지웠다) 함께 지워진다. 쓰인 그림은 지우지 못한다(RESTRICT). 탈퇴할 때 남이 쓰는
    공개 캐릭터의 그림이 지워지지 않게 하려는 것이다.
    판마다 적는 까닭: 대화(chat)는 옛 판을 사본으로 갖고 있다. 대표 그림을 바꿔 새로 게시해도
    옛 판의 그림이 보여야 한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.images.formats import ImageFormat

# 받는 형식들. CHECK 에 쓴다
FORMATS_SQL = ', '.join(f"'{image_format}'" for image_format in ImageFormat)


class Image(Base):
    """그림 하나."""

    __tablename__ = 'images'
    __table_args__ = (
        CheckConstraint(f'format IN ({FORMATS_SQL})', name='format_allowed'),
        CheckConstraint('byte_size > 0 AND width > 0 AND height > 0', name='size_positive'),
    )

    # 그림의 id. 저장소의 키이고, nginx 의 캐시 키다
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 주인. 인증 서버의 public_id 다. 탈퇴할 때 "이 사람의 그림들"을 찾는다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    format: Mapped[str] = mapped_column(String(10))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImageUse(Base):
    """그림이 쓰인 판 하나. 바뀌지 않는다."""

    __tablename__ = 'image_uses'

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('character_versions.id', ondelete='CASCADE'), primary_key=True
    )
    # "이 그림이 공개된 판에 쓰였나"를 그림의 id 로 찾는다
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('images.id', ondelete='RESTRICT'), primary_key=True, index=True
    )
