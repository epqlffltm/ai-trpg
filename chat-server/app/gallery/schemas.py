# chat-server/app/gallery/schemas.py

"""
연 이벤트 씬 API 의 응답의 모양.
이벤트 씬의 그림과 제목은 asset 서버의 판(공개 캐릭터의 문서)에 있다. 여기는 id 와 연 시각만 싣는다.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class UnlockOut(BaseModel):
    """연 이벤트 씬 하나. character_id 는 asset 서버의 캐릭터 id 다."""

    character_id: uuid.UUID
    scene_id: str
    unlocked_at: datetime


class UnlockPage(BaseModel):
    """목록의 한 쪽과 전체 개수. 대화 목록과 같은 모양이다."""

    items: list[UnlockOut]
    total: int
