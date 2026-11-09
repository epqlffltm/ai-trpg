# chat-server/app/achievements/schemas.py

"""
업적 API 가 내보내는 모양(docs/architecture/achievements.md 의 "chat").
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AchievementRecordOut(BaseModel):
    """
    받은 업적 하나. achievement_id 는 판의 업적의 id 다. 이름, 받는 법, 그림은 받은 때의 판의 것이다
    (숨긴 업적도 받은 사람에게는 보인다).
    """

    achievement_id: str
    name: str
    description: str
    image_id: uuid.UUID | None
    earned_at: datetime
    # 처음 받은 대화. 그 대화가 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class AchievementRecordList(BaseModel):
    """한 캐릭터에서 받은 업적들. 받은 차례다."""

    items: list[AchievementRecordOut]


class AchievementRate(BaseModel):
    """업적 하나를 받은 사람의 수."""

    achievement_id: str
    earned_count: int


class AchievementRates(BaseModel):
    """
    한 캐릭터의 업적마다 받은 사람의 수와, 그 캐릭터와 대화한 사람의 수. 달성률은 화면이 나눈다.
    아무도 받지 않은 업적은 items 에 없다. 업적의 이름과 차례는 캐릭터의 소개(asset 서버)에 있다.
    """

    players: int
    items: list[AchievementRate]


class EarnedAchievementOut(BaseModel):
    """
    이번 답으로 처음 받은 업적 하나. 판의 업적의 이름, 받는 법, 그림이다.
    숨긴 업적도 받았으므로 보인다. 받은 기록은 GET /achievements 가 다시 준다.
    """

    id: str
    name: str
    description: str
    image_id: uuid.UUID | None
