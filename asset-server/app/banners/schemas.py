# asset-server/app/banners/schemas.py

"""홍보 배너(#994)의 요청과 응답 모양. trpg-server 의 배너와 같은 규칙이다."""

import uuid
from datetime import datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.banners.models import BANNER_MAX_POSITION, BannerKind
from app.characters.schemas import PublicCharacterSummary
from app.worlds.schemas import PublicWorldSummary


def require_order(starts_at: datetime | None, ends_at: datetime | None) -> None:
    """끝이 시작보다 뒤여야 한다. 둘 중 하나가 없으면 보지 않는다."""
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise ValueError('ends_at 은 starts_at 보다 뒤여야 합니다.')


class BannerCreate(BaseModel):
    """배너를 건다. 시작을 비우면 지금부터, 끝을 비우면 내릴 때까지다."""

    model_config = ConfigDict(extra='forbid')

    kind: BannerKind
    target_id: uuid.UUID
    position: int = Field(default=0, ge=0, le=BANNER_MAX_POSITION)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode='after')
    def period_in_order(self) -> Self:
        require_order(self.starts_at, self.ends_at)
        return self


class BannerUpdate(BaseModel):
    """배너의 차례와 기간을 고친다. 보낸 칸만 바뀐다. ends_at 을 null 로 보내면 내릴 때까지가 된다."""

    model_config = ConfigDict(extra='forbid')

    position: int | None = Field(default=None, ge=0, le=BANNER_MAX_POSITION)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode='after')
    def starts_is_not_null(self) -> Self:
        if 'starts_at' in self.model_fields_set and self.starts_at is None:
            raise ValueError('starts_at 은 비울 수 없습니다.')
        if 'position' in self.model_fields_set and self.position is None:
            raise ValueError('position 은 비울 수 없습니다.')
        return self


class BannerOut(BaseModel):
    """
    운영자가 보는 배너 하나. 이름은 작품의 지금 이름(초안)이다.

    지금 보이는지(shown)는 기간과 공개를 함께 본 것이다.
    """

    id: uuid.UUID
    kind: BannerKind
    target_id: uuid.UUID
    name: str
    position: int
    starts_at: datetime
    ends_at: datetime | None
    created_at: datetime
    shown: bool


class PublicBanner(BaseModel):
    """첫 화면에 보이는 배너 하나. 둘 가운데 kind 의 것 하나만 찬다. 공개 목록의 한 줄과 같은 모양이다."""

    id: uuid.UUID
    kind: BannerKind
    character: PublicCharacterSummary | None = None
    world: PublicWorldSummary | None = None


class PublicBannerList(BaseModel):
    """지금 걸린 배너. 차례대로다(캐릭터와 세계관이 함께 차례를 갖는다)."""

    items: list[PublicBanner]
