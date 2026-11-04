# trpg-server/app/creator_stats/schemas.py

"""제작자 숫자의 응답 모양(#991). asset 서버의 캐릭터와 세계관의 것과 같은 모양이다."""

import uuid

from pydantic import BaseModel


class WorkStarts(BaseModel):
    """작품 하나의 수. total 은 모든 기간에, recent 는 최근 recent_days 일 동안 연 테이블의 수다."""

    id: uuid.UUID
    title: str
    total: int
    recent: int


class ScenarioStats(BaseModel):
    """
    내 시나리오의 숫자. total 과 recent 는 내 시나리오 모두를 더한 것이다.

    items 는 최근의 수가 많은 것부터 MAX_STATS_ITEMS 개까지다. 더한 수는 잘린 것까지 센다.
    테이블을 열 때마다 바로 바뀐다.
    """

    recent_days: int
    total: int
    recent: int
    items: list[WorkStarts]
