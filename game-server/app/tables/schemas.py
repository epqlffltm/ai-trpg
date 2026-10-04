# game-server/app/tables/schemas.py

"""
테이블 API 가 받는 입력과 내보내는 응답의 모양.

응답에 테이블의 복사본(content)을 통째로 싣지 않는다. GM 전용 글이 들어 있다.
참가자에게 필요한 것(고른 스타팅, 프리젠, 추천 인원)만 꺼내 싣는다.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.assets.models import TABLE_MAX_PLAYERS, Rating
from app.assets.scenarios.schemas import CharacterDescription, CharacterName, RecommendedPlayers
from app.tables.models import TableStatus


class TableCreate(BaseModel):
    """
    테이블을 만들 때 받는 값. 어느 시나리오의 어느 판으로, 어느 스타팅으로, 몇 명이서 할지 고른다.

    version 을 비우면 그 시나리오의 공개 중인 판을 쓴다. 번호를 적는 것은 자기 시나리오일 때만 된다.
    """

    model_config = ConfigDict(extra='forbid')

    scenario_id: uuid.UUID
    version: int | None = Field(default=None, ge=1)
    # 고른 스타팅. 판의 openings 에서 몇 번째인가(0 부터)
    opening_index: int = Field(default=0, ge=0)
    # 정원. 방장을 포함한다
    capacity: int = Field(ge=1, le=TABLE_MAX_PLAYERS)


# 초대 코드. 길이는 넉넉히 받는다. 틀린 코드는 "없는 테이블"로 답한다
InviteCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class JoinRequest(BaseModel):
    """테이블에 들어갈 때 받는 값."""

    model_config = ConfigDict(extra='forbid')

    invite_code: InviteCode


class CharacterUpdate(BaseModel):
    """
    캐릭터를 정할 때 받는 값. 보낸 것으로 캐릭터를 통째로 바꾼다.

    직접 만들 때는 이름을 적는다. 프리젠을 가져올 때는 pregen_index 를 적는다.
    프리젠을 가져오면서 이름이나 설명을 함께 보내면, 그 칸은 보낸 것으로 고쳐 쓴다.
    """

    model_config = ConfigDict(extra='forbid')

    pregen_index: int | None = Field(default=None, ge=0)
    name: CharacterName | None = None
    description: CharacterDescription | None = None

    @model_validator(mode='after')
    def require_a_name_without_pregen(self) -> 'CharacterUpdate':
        """프리젠을 고르지 않았으면 이름이 있어야 한다."""
        if self.pregen_index is None and self.name is None:
            raise ValueError('프리젠을 고르지 않았으면 이름을 적어야 합니다.')
        return self


class HostTransfer(BaseModel):
    """방장을 넘길 때 받는 값."""

    model_config = ConfigDict(extra='forbid')

    user_id: uuid.UUID


class CharacterOut(BaseModel):
    """캐릭터."""

    name: str
    description: str


class MemberOut(BaseModel):
    """테이블에 앉은 사람 하나."""

    # 인증 서버의 public_id 다. 이름은 인증 서버가 안다
    user_id: uuid.UUID
    is_host: bool
    # 아직 만들지 않았으면 None 이다
    character: CharacterOut | None
    # 프리젠에서 가져왔으면 몇 번째 프리젠인가
    pregen_index: int | None
    joined_at: datetime


class PregenChoice(BaseModel):
    """고를 수 있는 프리젠 하나. 누가 이미 가져갔는지 함께 알려 준다."""

    name: str
    description: str
    # 가져간 사람. 아무도 가져가지 않았으면 None 이다
    taken_by: uuid.UUID | None


class TableSummary(BaseModel):
    """테이블의 목록에 싣는 값."""

    id: uuid.UUID
    title: str
    status: TableStatus
    rating: Rating
    capacity: int
    member_count: int
    host_id: uuid.UUID
    created_at: datetime


class TablePage(BaseModel):
    """테이블 목록의 한 쪽."""

    items: list[TableSummary]
    # 조건에 맞는 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)


class TableDetail(TableSummary):
    """
    참가자가 테이블을 볼 때의 값. 여기 적힌 칸만 나간다.

    GM 전용 글(룰북의 진행 지침, 세계관의 GM 전용 설정, 로어북)은 싣지 않는다. 방장에게도 싣지 않는다.
    """

    # 고른 스타팅의 글. 테이블이 시작될 때 AI 가 읽어 줄 장면이다
    opening: str
    recommended_players: RecommendedPlayers
    pregens: list[PregenChoice]
    members: list[MemberOut]
    # 초대 코드. 방장에게만 보인다
    invite_code: str | None
    started_at: datetime | None
    ended_at: datetime | None
