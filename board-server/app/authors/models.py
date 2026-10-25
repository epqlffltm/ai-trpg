# board-server/app/authors/models.py

"""
글쓴이의 닉네임. 토큰에 실린 닉네임을 사람마다 하나 기억한다(app/authors/service.py).

글과 댓글의 응답에 실을 이름을 여기서 찾는다. 인증 서버를 요청마다 부르지 않는다.
탈퇴하면 그 줄을 지운다(app/withdrawal/).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

NICKNAME_MAX_LENGTH = 50


class Author(Base):
    """한 사람의 닉네임."""

    __tablename__ = 'authors'

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(NICKNAME_MAX_LENGTH))
    # 닉네임이 바뀐 시각. 같은 닉네임이면 고치지 않는다
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
