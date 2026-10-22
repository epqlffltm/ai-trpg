# asset-server/app/images/schemas.py

"""
그림 API 의 응답 모양(#566). 올리기의 요청은 본문이 그림의 바이트 그대로라 모양이 없다(app/images/router.py).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.images.formats import ImageFormat


class ImageDetail(BaseModel):
    """올린 그림. url 은 그 그림을 내주는 주소다(소개 글의 img 에 그대로 쓴다)."""

    id: uuid.UUID
    format: ImageFormat
    byte_size: int
    width: int
    height: int
    url: str
    created_at: datetime
