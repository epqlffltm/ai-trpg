# story-server/app/records/schemas.py

"""
계정의 기록 API 가 내보내는 모양.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.records.illustrations import SceneKind


class EndingRecordOut(BaseModel):
    """본 엔딩 하나. ending_id 는 판의 엔딩의 id 다. 이름과 힌트는 판의 문서에 있다."""

    ending_id: str
    first_seen_at: datetime
    # 처음 본 세션. 그 세션이 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class EndingRecordList(BaseModel):
    """한 세계관에서 본 엔딩들. 처음 본 차례다."""

    items: list[EndingRecordOut]


class IllustrationOut(BaseModel):
    """
    연 일러스트 하나. 장면은 종류(event, ending)와 판의 id 다. image_id 는 연 때의 그림이다.
    cast 는 그 장면이 부르는 인물들이다. 갤러리는 인물마다 묶고, 비었으면 세계관 칸에 둔다.
    """

    kind: SceneKind
    scene_id: str
    image_id: uuid.UUID
    cast: list[str]
    first_seen_at: datetime
    # 처음 연 세션. 그 세션이 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class IllustrationList(BaseModel):
    """한 세계관에서 연 일러스트들. 처음 연 차례다."""

    items: list[IllustrationOut]


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
    # 처음 받은 세션. 그 세션이 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class AchievementRecordList(BaseModel):
    """한 세계관에서 받은 업적들. 받은 차례다."""

    items: list[AchievementRecordOut]


class AchievementRate(BaseModel):
    """업적 하나를 받은 사람의 수."""

    achievement_id: str
    earned_count: int


class AchievementRates(BaseModel):
    """
    한 세계관의 업적마다 받은 사람의 수와, 그 세계관을 플레이한 사람의 수. 달성률은 화면이 나눈다.
    아무도 받지 않은 업적은 items 에 없다. 업적의 이름과 차례는 세계관의 소개(asset 서버)에 있다.
    """

    players: int
    items: list[AchievementRate]


class MyAchievementOut(BaseModel):
    """
    내가 받은 업적 하나(GET /achievements/mine). 이름, 받는 법, 그림은 받은 때의 판의 것이다(숨긴 업적도 보인다).
    world_name 은 내가 가져온 그 세계관의 마지막 판의 이름이다. 가져온 판이 없으면 null 이다.
    """

    world_id: uuid.UUID
    world_name: str | None
    achievement_id: str
    name: str
    description: str
    image_id: uuid.UUID | None
    earned_at: datetime
    # 처음 받은 세션. 그 세션이 지워졌으면 null 이다
    conversation_id: uuid.UUID | None


class MyAchievementPage(BaseModel):
    """내가 받은 업적의 한 쪽. 받은 때가 늦은 것부터다. total 은 모든 세계관에서 받은 수다."""

    items: list[MyAchievementOut]
    total: int
