# trpg-server/app/achievements/schemas.py

"""
시나리오 업적의 응답의 모양. 공개된 시나리오의 업적 목록과 달성률이다.

숨긴 업적은 보는 사람이 받기 전에는 이름, 설명, 그림을 싣지 않는다(null). 받은 수는 싣는다.
조건은 어느 업적에도 싣지 않는다. 판의 내용(장소, 몬스터, 퀘스트)이 새지 않게 한다.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ScenarioAchievementOut(BaseModel):
    """업적 하나와 보는 사람이 받았는지, 받은 사람의 수."""

    id: str
    hidden: bool
    # 숨긴 업적을 받기 전이면 null 이다
    name: str | None
    description: str | None
    # 그림. 붙이지 않았거나 숨긴 업적을 받기 전이면 null 이다(/listings/{scenario_id}/portraits/{image_id}/image)
    image_id: uuid.UUID | None
    # 보는 사람이 받은 때. 받지 않았거나 로그인하지 않았으면 null 이다
    earned_at: datetime | None
    # 이 업적을 받은 사람의 수. 달성률은 players 로 나눈다
    earned_count: int


class ScenarioAchievements(BaseModel):
    """공개된 시나리오의 업적들. 판의 차례다. 공개 중인 판의 것이다."""

    items: list[ScenarioAchievementOut]
    # 이 시나리오를 플레이한 사람의 수(캐릭터를 갖고 앉은 테이블에서 라운드가 닫혔다). 달성률의 분모다
    players: int


class MyAchievementOut(BaseModel):
    """
    내가 받은 업적 하나(GET /achievements/mine). 받았으므로 숨긴 업적도 이름과 그림이 보인다.

    이름, 설명, 그림은 받은 테이블의 판의 것이고, 그 테이블이 없으면 지금 공개 중인 판의 것이다.
    두 판 모두에 그 업적이 없으면(판에서 뺐다) null 이다. 받은 기록은 남는다.
    listed 면 지금 공개 중이고 내가 볼 수 있다. 소개와 업적의 그림을 연다
    (/listings/{scenario_id}/portraits/{image_id}/image).
    """

    scenario_id: uuid.UUID
    # 시나리오의 지금 제목이다
    scenario_title: str
    listed: bool
    achievement_id: str
    name: str | None
    description: str | None
    image_id: uuid.UUID | None
    earned_at: datetime


class MyAchievementPage(BaseModel):
    """내가 받은 업적의 한 쪽. 받은 때가 늦은 것부터다. total 은 모든 시나리오에서 받은 수다."""

    items: list[MyAchievementOut]
    total: int
