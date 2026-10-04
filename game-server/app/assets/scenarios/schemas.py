# game-server/app/assets/scenarios/schemas.py

"""
시나리오 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 시나리오의 칸을 더한다.
"""

import uuid
from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.assets.models import (
    CHARACTER_DESCRIPTION_MAX_LENGTH,
    CHARACTER_NAME_MAX_LENGTH,
    SCENARIO_MAX_LOREBOOKS,
    SCENARIO_MAX_OPENINGS,
    SCENARIO_MAX_PREGENS,
    SCENARIO_OPENING_MAX_LENGTH,
    TABLE_MAX_PLAYERS,
    VERSION_NOTE_MAX_LENGTH,
    Rating,
)
from app.assets.scenarios.snapshot import Snapshot
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate

# 스타팅 하나. 공백이 아닌 글자가 하나는 있어야 한다. 빈 스타팅은 고를 수 없으니 받지 않는다.
# 앞뒤 공백은 떼지 않는다. 줄바꿈으로 장면을 여는 것도 제작자의 글이다
Opening = Annotated[str, StringConstraints(pattern=r'\S', max_length=SCENARIO_OPENING_MAX_LENGTH)]
# 스타팅의 목록. 같은 글이 두 번 있어도 막지 않는다. 순서에 뜻이 있다
Openings = Annotated[list[Opening], Field(max_length=SCENARIO_MAX_OPENINGS)]


def reject_duplicates(lorebook_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """같은 로어북이 두 번 있으면 거부한다."""
    if len(set(lorebook_ids)) != len(lorebook_ids):
        raise ValueError('같은 로어북이 두 번 있습니다.')
    return lorebook_ids


LorebookIds = Annotated[list[uuid.UUID], Field(max_length=SCENARIO_MAX_LOREBOOKS), AfterValidator(reject_duplicates)]


class RecommendedPlayers(BaseModel):
    """
    추천 인원. 최소와 최대를 함께 보낸다.

    추천일 뿐이다. 테이블의 정원을 막지 않는다. 혼자서도, 넷이서도 할 수 있다.
    """

    model_config = ConfigDict(extra='forbid')

    min: int = Field(ge=1, le=TABLE_MAX_PLAYERS)
    max: int = Field(ge=1, le=TABLE_MAX_PLAYERS)

    @model_validator(mode='after')
    def reject_reversed_range(self) -> 'RecommendedPlayers':
        """최소가 최대보다 크면 거부한다."""
        if self.min > self.max:
            raise ValueError('최소 인원이 최대 인원보다 큽니다.')
        return self


CharacterName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CHARACTER_NAME_MAX_LENGTH)
]
CharacterDescription = Annotated[str, StringConstraints(max_length=CHARACTER_DESCRIPTION_MAX_LENGTH)]


class Pregen(BaseModel):
    """
    프리젠 하나. 제작자가 미리 만들어 둔 캐릭터다.

    플레이어가 만드는 캐릭터와 칸이 같다(이름과 설명). 그래서 골라서 그대로 자기 캐릭터로 가져갈 수 있다.
    """

    model_config = ConfigDict(extra='forbid')

    name: CharacterName
    description: CharacterDescription = ''


def reject_duplicate_names(pregens: list[Pregen]) -> list[Pregen]:
    """같은 이름의 프리젠이 두 번 있으면 거부한다. 고르는 화면에서 구별할 수 없다. 대소문자만 다른 것도 같은 것이다."""
    names = [pregen.name.casefold() for pregen in pregens]
    if len(set(names)) != len(names):
        raise ValueError('같은 이름의 프리젠이 두 번 있습니다.')
    return pregens


Pregens = Annotated[list[Pregen], Field(max_length=SCENARIO_MAX_PREGENS), AfterValidator(reject_duplicate_names)]


class ScenarioCreate(AssetCreate):
    """
    시나리오를 만들 때 받는 값. 제목만 필수다.

    룰북과 스타팅 없이도 만들 수 있다(임시 저장). 게시할 때 둘 다 있는지 검사한다.
    """

    # 이용 등급. 시나리오를 조립할 때 제작자가 고른다. 성인용으로 올리는 것은 직접 골라야 한다
    rating: Rating = Rating.ALL
    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    lorebook_ids: LorebookIds = []
    openings: Openings = []
    recommended_players: RecommendedPlayers = RecommendedPlayers(min=1, max=TABLE_MAX_PLAYERS)
    pregens: Pregens = []


class ScenarioUpdate(AssetUpdate):
    """
    시나리오를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    rulebook_id 와 world_id 는 null 을 보내면 떼어 낸다. 보내지 않으면 그대로 둔다.
    lorebook_ids, openings, pregens 는 보낸 목록으로 통째로 바꾼다. 전부 없애려면 빈 목록을 보낸다.
    recommended_players 는 최소와 최대를 함께 보낸다.
    """

    clearable: ClassVar[frozenset[str]] = frozenset({'rulebook_id', 'world_id'})

    rating: Rating | None = None
    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    lorebook_ids: LorebookIds | None = None
    openings: Openings | None = None
    recommended_players: RecommendedPlayers | None = None
    pregens: Pregens | None = None


class ScenarioSummary(AssetSummary):
    """시나리오의 목록에 싣는 값. 공통 값에 등급을 더한다. 목록에서 등급으로 가려 보여 줄 수 있어야 한다."""

    rating: Rating


class ScenarioPage(BaseModel):
    """시나리오 목록의 한 쪽."""

    items: list[ScenarioSummary]
    # 조건에 맞는 전체 개수. 다음 쪽이 있는지 알 수 있다
    total: int = Field(ge=0)


class ScenarioDetail(ScenarioSummary):
    """만든 사람이 자기 시나리오를 볼 때의 값. 가리키는 자산은 ID 만 싣는다. 내용은 그 자산의 주소에서 읽는다."""

    rulebook_id: uuid.UUID | None
    world_id: uuid.UUID | None
    lorebook_ids: list[uuid.UUID]
    openings: list[str]
    recommended_players: RecommendedPlayers
    pregens: list[Pregen]


VersionNote = Annotated[str, StringConstraints(max_length=VERSION_NOTE_MAX_LENGTH)]


class VersionCreate(BaseModel):
    """
    게시할 때 받는 값. 변경 내용만 적는다. 비워도 된다.

    판의 내용은 받지 않는다. 서버가 초안에서 직접 읽어 굳힌다.
    """

    model_config = ConfigDict(extra='forbid')

    note: VersionNote = ''


class VersionSummary(BaseModel):
    """판의 목록에 싣는 값. 굳힌 내용은 싣지 않는다."""

    id: uuid.UUID
    number: int
    note: str
    created_at: datetime


class VersionDetail(VersionSummary):
    """만든 사람이 자기 판을 볼 때의 값. 굳힌 내용까지 싣는다. GM 전용 글이 들어 있다."""

    snapshot: Snapshot
