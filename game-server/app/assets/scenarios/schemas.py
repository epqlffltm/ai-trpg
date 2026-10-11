# game-server/app/assets/scenarios/schemas.py

"""
시나리오 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 시나리오의 칸을 더한다.
"""

import uuid
from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)

from app.assets.models import (
    CHARACTER_DESCRIPTION_MAX_LENGTH,
    CHARACTER_NAME_MAX_LENGTH,
    DEFAULT_CHARACTER_MODES,
    DEFAULT_NARRATION_STYLE,
    PLAYER_MADE_HP_MAX,
    SCENARIO_MAX_LOREBOOKS,
    SCENARIO_MAX_NPC_SHEETS,
    SCENARIO_MAX_OPENINGS,
    SCENARIO_MAX_PREGENS,
    SCENARIO_OPENING_MAX_LENGTH,
    TABLE_MAX_PLAYERS,
    VERSION_NOTE_MAX_LENGTH,
    CharacterMode,
    NarrationStyle,
    Rating,
)
from app.assets.scenarios.snapshot import Snapshot
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate
from app.engine.sheet import Sheet

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

    이름과 설명은 플레이어가 만드는 캐릭터와 칸이 같다. 그래서 골라서 그대로 자기 캐릭터로 가져갈 수 있다.
    시트는 그 캐릭터의 숫자다. 초안일 때는 비워 둘 수 있다. 게시할 때 있는지, 룰북의 규칙에 맞는지 검사한다.
    여기서는 시트의 모양만 본다. 룰북은 나중에 붙이거나 바꿀 수 있어서, 규칙에 맞는지는 지금 정할 수 없다.
    """

    model_config = ConfigDict(extra='forbid')

    name: CharacterName
    description: CharacterDescription = ''
    sheet: Sheet | None = None


def reject_duplicate_names(pregens: list[Pregen]) -> list[Pregen]:
    """같은 이름의 프리젠이 두 번 있으면 거부한다. 고르는 화면에서 구별할 수 없다. 대소문자만 다른 것도 같은 것이다."""
    names = [pregen.name.casefold() for pregen in pregens]
    if len(set(names)) != len(names):
        raise ValueError('같은 이름의 프리젠이 두 번 있습니다.')
    return pregens


Pregens = Annotated[list[Pregen], Field(max_length=SCENARIO_MAX_PREGENS), AfterValidator(reject_duplicate_names)]


class NpcSheet(BaseModel):
    """
    NPC 시트 하나. 붙인 로어북의 인물 항목 하나(entry_id)에 숫자를 준다.

    프리젠과 달리 시트를 비워 둘 수 없다. 숫자를 줄 생각이 없으면 이 칸을 만들지 않으면 된다(기본 NPC 시트를 쓴다).
    가리키는 항목이 붙인 로어북에 있는지, 인물인지, 시트가 규칙에 맞는지는 게시할 때 본다.
    로어북도 룰북도 나중에 바꿀 수 있어서 지금 정할 수 없다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    sheet: Sheet

    @field_serializer('entry_id')
    def entry_id_as_text(self, entry_id: uuid.UUID) -> str:
        """항목의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(entry_id)


def reject_duplicate_entries(npc_sheets: list[NpcSheet]) -> list[NpcSheet]:
    """같은 항목의 시트가 두 번 있으면 거부한다. 어느 숫자를 쓸지 정할 수 없다."""
    entry_ids = [npc_sheet.entry_id for npc_sheet in npc_sheets]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 인물의 시트가 두 번 있습니다.')
    return npc_sheets


NpcSheets = Annotated[
    list[NpcSheet], Field(max_length=SCENARIO_MAX_NPC_SHEETS), AfterValidator(reject_duplicate_entries)
]


def in_fixed_order(modes: list[CharacterMode]) -> list[CharacterMode]:
    """
    방식의 목록을 정해진 순서로 놓는다. 같은 것이 두 번 있으면 거부한다.

    순서에 뜻이 없는 목록이다. 보낸 순서와 상관없이 늘 같은 순서로 저장하고 돌려준다.
    """
    if len(set(modes)) != len(modes):
        raise ValueError('같은 방식이 두 번 있습니다.')
    return [mode for mode in CharacterMode if mode in modes]


# 허용하는 캐릭터 방식들. 하나는 있어야 한다. 하나도 없으면 아무도 앉을 수 없다
CharacterModes = Annotated[list[CharacterMode], Field(min_length=1), AfterValidator(in_fixed_order)]


class PlayerMadeHp(BaseModel):
    """
    플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 기준값과 상한을 함께 보낸다.

    최대 HP = 기준값 + 능력치의 보정. 상한을 넘지 않는다. 어느 능력치의 보정인지는 룰북의 규칙이 정한다.
    상한을 기준값과 같게 두면 보정은 깎기만 한다.
    """

    model_config = ConfigDict(extra='forbid')

    base: int = Field(ge=1, le=PLAYER_MADE_HP_MAX)
    cap: int = Field(ge=1, le=PLAYER_MADE_HP_MAX)

    @model_validator(mode='after')
    def reject_base_over_cap(self) -> 'PlayerMadeHp':
        """기준값이 상한보다 크면 거부한다."""
        if self.base > self.cap:
            raise ValueError('기준값이 상한보다 큽니다.')
        return self


class ScenarioCreate(AssetCreate):
    """
    시나리오를 만들 때 받는 값. 제목만 필수다.

    룰북과 스타팅 없이도 만들 수 있다(임시 저장). 게시할 때 둘 다 있는지 검사한다.
    시트도 비워 둘 수 있다. 게시할 때 룰북의 규칙과 견주어 검사한다.
    """

    # 이용 등급. 시나리오를 조립할 때 제작자가 고른다. 성인용으로 올리는 것은 직접 골라야 한다
    rating: Rating = Rating.ALL
    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    lorebook_ids: LorebookIds = []
    openings: Openings = []
    recommended_players: RecommendedPlayers = RecommendedPlayers(min=1, max=TABLE_MAX_PLAYERS)
    pregens: Pregens = []
    # 안 보내면 프리젠과 기본 시트를 허용한다. 플레이어가 숫자를 정하는 방식은 직접 적어야 켜진다
    character_modes: CharacterModes = list(DEFAULT_CHARACTER_MODES)
    default_sheet: Sheet | None = None
    npc_sheets: NpcSheets = []
    default_npc_sheet: Sheet | None = None
    player_made_hp: PlayerMadeHp | None = None
    # 주사위로 정한 점수를 방장이 다시 굴리게 해 줄 수 있는가. 안 보내면 안 된다
    reroll_allowed: bool = False
    # 추천 문체. 테이블의 방장이 고르지 않으면 이것으로 서술한다. 안 보내면 정통이다
    narration_style: NarrationStyle = DEFAULT_NARRATION_STYLE


class ScenarioUpdate(AssetUpdate):
    """
    시나리오를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    rulebook_id, world_id, default_sheet, default_npc_sheet, player_made_hp 는 null 을 보내면 비운다.
    보내지 않으면 그대로 둔다.
    lorebook_ids, openings, pregens, npc_sheets, character_modes 는 보낸 목록으로 통째로 바꾼다.
    character_modes 말고는 전부 없애려면 빈 목록을 보낸다. character_modes 는 비울 수 없다.
    recommended_players 는 최소와 최대를 함께 보낸다.
    """

    clearable: ClassVar[frozenset[str]] = frozenset(
        {'rulebook_id', 'world_id', 'default_sheet', 'default_npc_sheet', 'player_made_hp'}
    )

    rating: Rating | None = None
    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    lorebook_ids: LorebookIds | None = None
    openings: Openings | None = None
    recommended_players: RecommendedPlayers | None = None
    pregens: Pregens | None = None
    character_modes: CharacterModes | None = None
    default_sheet: Sheet | None = None
    npc_sheets: NpcSheets | None = None
    default_npc_sheet: Sheet | None = None
    player_made_hp: PlayerMadeHp | None = None
    reroll_allowed: bool | None = None
    narration_style: NarrationStyle | None = None


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
    character_modes: list[CharacterMode]
    default_sheet: Sheet | None
    npc_sheets: list[NpcSheet]
    default_npc_sheet: Sheet | None
    player_made_hp: PlayerMadeHp | None
    reroll_allowed: bool
    narration_style: NarrationStyle


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
