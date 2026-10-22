# asset-server/app/images/models.py

"""
그림의 테이블 모델(#566). 그림의 바이트는 저장소(SeaweedFS, S3)에 그림의 id 로 있고, 여기에는 그 그림의 행이 있다.

  - 그림은 바뀌지 않는다. 고치면 새 id 다. 그래서 nginx 가 그림의 id 로 캐시해도 틀어지지 않는다.
  - 형식, 크기(바이트), 너비와 높이는 다시 인코딩한 뒤의 것이다(app/images/decoder.py).
  - 누가 볼 수 있는지는 지금은 주인뿐이다. 페르소나와 캐릭터, 소개 글에 붙은 그림을 남이 보는 규칙은
    다음 PR 에서 더한다(그림이 쓰인 곳을 판마다 적는다).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Uuid, func
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
