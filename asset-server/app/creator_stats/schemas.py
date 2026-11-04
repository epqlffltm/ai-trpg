# asset-server/app/creator_stats/schemas.py

"""제작자 숫자의 응답 모양(#991). trpg-server 의 시나리오의 것과 같은 모양에 받아 온 시각을 더한다."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class WorkStarts(BaseModel):
    """작품 하나의 수. total 은 모든 기간에, recent 는 최근 recent_days 일 동안 시작한 수다."""

    id: uuid.UUID
    title: str
    total: int
    recent: int


class WorkStats(BaseModel):
    """
    내 캐릭터(또는 세계관)의 숫자. total 과 recent 는 내 작품 모두를 더한 것이다.

    items 는 최근의 수가 많은 것부터 MAX_STATS_ITEMS 개까지다. 더한 수는 잘린 것까지 센다.
    수는 chat 과 story 서버에서 한 시간마다 받아 온 것이다. refreshed_at 은 그 시각이고, 받은 적이 없으면 null 이다.
    """

    recent_days: int
    refreshed_at: datetime | None
    total: int
    recent: int
    items: list[WorkStarts]
