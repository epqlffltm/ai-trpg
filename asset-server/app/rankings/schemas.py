# asset-server/app/rankings/schemas.py

"""랭킹의 응답 모양(#985). 작품은 공개 목록의 한 줄과 같다."""

from datetime import datetime

from pydantic import BaseModel

from app.characters.schemas import PublicCharacterSummary
from app.worlds.schemas import PublicWorldSummary


class RankedCharacter(BaseModel):
    """랭킹의 캐릭터 하나. rank 는 1 부터다. starts 는 최근 recent_days 일 동안 대화를 시작한 수다."""

    rank: int
    starts: int
    character: PublicCharacterSummary


class RankedWorld(BaseModel):
    """랭킹의 세계관 하나. starts 는 최근 recent_days 일 동안 세션을 시작한 수다."""

    rank: int
    starts: int
    world: PublicWorldSummary


class CharacterRanking(BaseModel):
    """
    캐릭터의 랭킹. refreshed_at 은 수를 받아 온 시각이다(몇 분마다 받는다). 한 번도 받지 못했으면 null 이고 비어 있다.
    """

    recent_days: int
    refreshed_at: datetime | None
    items: list[RankedCharacter]


class WorldRanking(BaseModel):
    """세계관의 랭킹. 모양은 캐릭터의 것과 같다."""

    recent_days: int
    refreshed_at: datetime | None
    items: list[RankedWorld]
