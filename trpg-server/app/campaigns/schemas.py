# trpg-server/app/campaigns/schemas.py

"""
캠페인의 플레이 API 의 입력과 응답의 모양(#481 B).

플레이를 시작할 때는 첫 편의 테이블을 여는 값(TableCreate 의 칸)을 함께 받는다. 시나리오와 판은 캠페인의 판이 정한다.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.campaigns.carrying import Carry
from app.campaigns.models import QuestResult, RunStatus
from app.tables.schemas import TableCreate


class RunTable(TableCreate):
    """편의 테이블을 여는 값. TableCreate 와 같되, 시나리오와 판은 받지 않는다(보내면 422)."""

    scenario_id: None = None
    version: None = None


class RunCreate(BaseModel):
    """플레이를 시작할 때 받는 값. 캠페인과 그 판의 번호(비우면 마지막 판), 첫 편의 테이블을 여는 값."""

    model_config = ConfigDict(extra='forbid')

    campaign_id: uuid.UUID
    version: int | None = Field(default=None, ge=1)
    table: RunTable


class RunEpisodeOut(BaseModel):
    """플레이의 편 하나. 편의 이름과 시나리오의 판, 그 편의 테이블(아직 열지 않았으면 None)."""

    position: int
    title: str
    scenario_id: uuid.UUID
    version: int
    table_id: uuid.UUID | None


class QuestResultOut(BaseModel):
    """편이 끝날 때의 퀘스트 결과 하나."""

    position: int
    entry_id: uuid.UUID
    result: QuestResult


class RunDetail(BaseModel):
    """
    플레이 하나. 편들과 지금 편, 편마다 끝난 퀘스트의 결과, 보는 사람이 가장 나중에 넘긴 것(없으면 None).

    넘긴 것은 본인의 것만 싣는다. 다른 사람의 캐릭터는 그 편의 테이블에서 본다.
    """

    id: uuid.UUID
    campaign_id: uuid.UUID
    title: str
    version: int
    host_id: uuid.UUID
    status: RunStatus
    position: int
    episodes: list[RunEpisodeOut]
    quest_results: list[QuestResultOut]
    my_carry: Carry | None
    created_at: datetime
    ended_at: datetime | None


class RunSummary(BaseModel):
    """플레이의 목록에 싣는 값. 캠페인의 제목, 지금 편과 편의 수, 지금 편의 테이블(아직 열지 않았으면 None)."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    title: str
    host_id: uuid.UUID
    status: RunStatus
    position: int
    episode_count: int
    episode_title: str
    table_id: uuid.UUID | None
    created_at: datetime
    ended_at: datetime | None


class RunPage(BaseModel):
    """내 플레이 목록의 한 쪽."""

    items: list[RunSummary]
    total: int = Field(ge=0)
