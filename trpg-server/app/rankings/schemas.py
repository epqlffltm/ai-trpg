# trpg-server/app/rankings/schemas.py

"""시나리오 랭킹의 응답 모양(#985). 시나리오는 공개 목록의 한 줄과 같다."""

from pydantic import BaseModel

from app.listings.schemas import PublicListing


class RankedScenario(BaseModel):
    """랭킹의 시나리오 하나. rank 는 1 부터다. starts 는 최근 recent_days 일 동안 이 시나리오로 연 테이블의 수다."""

    rank: int
    starts: int
    listing: PublicListing


class ScenarioRanking(BaseModel):
    """시나리오의 랭킹. 테이블을 열 때마다 바로 바뀐다."""

    recent_days: int
    items: list[RankedScenario]
