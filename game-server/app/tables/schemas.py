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

from app.assets.models import PLAYER_MADE_MODES, TABLE_MAX_PLAYERS, CharacterMode, Rating
from app.assets.scenarios.schemas import (
    CharacterDescription,
    CharacterModes,
    CharacterName,
    PlayerMadeHp,
    RecommendedPlayers,
)
from app.engine.ruleset import RULESET_MAX_ABILITIES, Key, Ruleset
from app.engine.sheet import Score, Sheet
from app.tables.models import TABLE_PASSWORD_MAX_LENGTH, TABLE_PASSWORD_MIN_LENGTH, TableStatus

# 테이블의 비밀번호. 앞뒤 공백을 떼지 않는다. 적은 그대로가 비밀번호다
TablePassword = Annotated[
    str, StringConstraints(min_length=TABLE_PASSWORD_MIN_LENGTH, max_length=TABLE_PASSWORD_MAX_LENGTH)
]


class TableCreate(BaseModel):
    """
    테이블을 만들 때 받는 값. 어느 시나리오의 어느 판으로, 어느 스타팅으로, 몇 명이서 할지 고른다.

    version 을 비우면 그 시나리오의 공개 중인 판을 쓴다. 번호를 적는 것은 자기 시나리오일 때만 된다.
    is_public 을 켜면 로비에 보인다. 만든 뒤에는 바꿀 수 없다. 비밀번호는 로비에 보이는 테이블에만 건다.
    character_modes 로 캐릭터 방식을 좁힌다. 판이 허용한 것 중에서만 고른다. 비우면 판이 허용한 그대로다.
    """

    model_config = ConfigDict(extra='forbid')

    scenario_id: uuid.UUID
    version: int | None = Field(default=None, ge=1)
    # 고른 스타팅. 판의 openings 에서 몇 번째인가(0 부터)
    opening_index: int = Field(default=0, ge=0)
    # 정원. 방장을 포함한다
    capacity: int = Field(ge=1, le=TABLE_MAX_PLAYERS)
    is_public: bool = False
    password: TablePassword | None = None
    # 이 테이블에서 허용할 캐릭터 방식. 만든 뒤에는 바꿀 수 없다
    character_modes: CharacterModes | None = None

    @model_validator(mode='after')
    def require_public_for_password(self) -> 'TableCreate':
        """로비에 보이지 않는 테이블에는 비밀번호를 걸 수 없다. 초대 코드가 그 일을 한다."""
        if self.password is not None and not self.is_public:
            raise ValueError('비밀번호는 로비에 보이는 테이블에만 걸 수 있습니다.')
        return self


# 초대 코드. 길이는 넉넉히 받는다. 틀린 코드는 "없는 테이블"로 답한다
InviteCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class JoinRequest(BaseModel):
    """초대 코드로 테이블에 들어갈 때 받는 값."""

    model_config = ConfigDict(extra='forbid')

    invite_code: InviteCode


class LobbyJoinRequest(BaseModel):
    """
    로비에서 테이블에 들어갈 때 받는 값. 비밀번호가 걸린 테이블이면 비밀번호를 적는다.

    길이를 검사하지 않는다(위쪽 끝만 막는다). 틀린 비밀번호는 모양이 어떻든 "틀렸다"로 답한다.
    """

    model_config = ConfigDict(extra='forbid')

    password: str | None = Field(default=None, max_length=TABLE_PASSWORD_MAX_LENGTH)


# 플레이어가 직접 정하는 능력치의 점수. 능력치의 이름표에서 점수로 간다. 여기서는 모양만 본다.
# 이 테이블의 규칙에 맞는지(능력치가 빠짐없이 있는지, 점수가 범위 안인지)는 서비스가 본다
ChosenAbilities = Annotated[dict[Key, Score], Field(max_length=RULESET_MAX_ABILITIES)]


class CharacterUpdate(BaseModel):
    """
    캐릭터를 정할 때 받는 값. 보낸 것으로 캐릭터를 통째로 바꾼다.

    방식(mode)에 따라 적는 칸이 다르다.
      - pregen: pregen_index 를 적는다. 이름이나 설명을 함께 보내면 그 칸은 보낸 것으로 고쳐 쓴다.
      - custom: 이름을 적는다. 숫자는 시나리오의 기본 시트를 받는다.
      - manual: 이름과 능력치의 점수(abilities)를 적는다. 최대 HP 는 적지 않는다. 규칙으로 구한다.
      - point_buy: manual 과 같은 칸을 적는다. 점수는 규칙의 총점 안에서 살 수 있는 것이어야 한다.
      - rolled: manual 과 같은 칸을 적는다. 점수는 먼저 굴려 둔 것을 남김없이 한 번씩 쓴 것이어야 한다.
        굴리는 것은 다른 주소다(POST .../character/roll). 굴린 점수를 여기에 적어 보내는 것이 아니다.

    mode 를 비우면 pregen_index 가 있으면 pregen, 없으면 custom 으로 본다.
    능력치를 적는 방식은 여럿이라, 능력치를 보낼 때는 mode 를 반드시 적는다.
    """

    model_config = ConfigDict(extra='forbid')

    mode: CharacterMode | None = None
    pregen_index: int | None = Field(default=None, ge=0)
    name: CharacterName | None = None
    description: CharacterDescription | None = None
    abilities: ChosenAbilities | None = None

    @property
    def chosen_mode(self) -> CharacterMode:
        """이 요청의 방식. 적지 않았으면 프리젠을 골랐는지로 정한다."""
        if self.mode is not None:
            return self.mode
        return CharacterMode.PREGEN if self.pregen_index is not None else CharacterMode.CUSTOM

    @model_validator(mode='after')
    def require_a_name_without_pregen(self) -> 'CharacterUpdate':
        """프리젠을 고르지 않았으면 이름이 있어야 한다."""
        if self.pregen_index is None and self.name is None:
            raise ValueError('프리젠을 고르지 않았으면 이름을 적어야 합니다.')
        return self

    @model_validator(mode='after')
    def require_fields_of_the_mode(self) -> 'CharacterUpdate':
        """방식에 맞는 칸만 적었는지 본다. 프리젠은 프리젠 방식에만, 능력치는 능력치를 적는 방식에만 적는다."""
        mode = self.chosen_mode
        if (mode == CharacterMode.PREGEN) != (self.pregen_index is not None):
            raise ValueError('pregen_index 는 pregen 방식에서만, 그리고 반드시 적습니다.')
        if (mode in PLAYER_MADE_MODES) != (self.abilities is not None):
            raise ValueError('abilities 는 플레이어가 능력치를 정하는 방식에서만, 그리고 반드시 적습니다.')
        return self


class HostTransfer(BaseModel):
    """방장을 넘길 때 받는 값."""

    model_config = ConfigDict(extra='forbid')

    user_id: uuid.UUID


class CharacterOut(BaseModel):
    """캐릭터."""

    name: str
    description: str


class SheetOut(BaseModel):
    """앉은 사람의 캐릭터 시트. 앉은 사람은 서로의 시트를 본다."""

    # 능력치의 점수. 이름표가 무슨 능력치인지는 테이블의 rules 에 있다
    abilities: dict[str, int]
    max_hp: int
    # 지금의 HP
    hp: int


class RollOut(BaseModel):
    """주사위로 굴린 능력치의 점수들. 앉은 사람은 서로의 굴림을 본다."""

    # 굴린 눈. 점수 하나마다 눈의 목록이 하나다. 버린 눈도 들어 있다
    dice: list[list[int]]
    # 굴려서 나온 점수들. 이것을 능력치에 놓는다
    scores: list[int]
    # 이 테이블에서 몇 번 굴렸는가
    times_rolled: int
    # 방장이 "한 번 더"를 줬는가. 켜져 있으면 다시 굴릴 수 있다
    reroll_granted: bool


class MemberOut(BaseModel):
    """테이블에 앉은 사람 하나."""

    # 인증 서버의 public_id 다. 이름은 인증 서버가 안다
    user_id: uuid.UUID
    is_host: bool
    # 아직 만들지 않았으면 None 이다
    character: CharacterOut | None
    # 캐릭터를 얻은 방식. 숫자가 어디서 왔는지 알려 준다. 아직 만들지 않았으면 None 이다
    character_mode: CharacterMode | None
    # 프리젠에서 가져왔으면 몇 번째 프리젠인가
    pregen_index: int | None
    # 주사위로 굴린 점수들. 이 테이블에서 굴린 적이 있으면 있다. 다른 방식으로 캐릭터를 만들었어도 남아 있다
    roll: RollOut | None
    # 플레이어가 정한 능력치의 점수. 그런 방식(manual, point_buy, rolled)으로 만들었을 때만 있다.
    # 시작하면 이것으로 시트가 만들어진다
    abilities: dict[str, int] | None
    # 게임을 시작하기 전에는 None 이다. 시작할 때 받는다
    sheet: SheetOut | None
    joined_at: datetime


class PregenChoice(BaseModel):
    """고를 수 있는 프리젠 하나. 누가 이미 가져갔는지 함께 알려 준다."""

    name: str
    description: str
    # 이 프리젠을 고르면 받는 숫자
    sheet: Sheet
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
    # 로비에 보이는가, 로비에서 들어올 때 비밀번호를 묻는가
    is_public: bool
    has_password: bool
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
    # 이 테이블의 규칙. 능력치의 이름과 난이도의 단계가 있다. 시트를 읽고 행동을 고르는 데 필요하다
    rules: Ruleset
    # 이 테이블에서 허용하는 캐릭터 방식
    character_modes: list[CharacterMode]
    # 캐릭터를 직접 만들면 받는 숫자. 직접 만들기를 허용하지 않는 테이블이면 None 이다
    default_sheet: Sheet | None
    # 플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 그런 방식을 허용하지 않는 테이블이면 None 이다.
    # 최대 HP = 기준값 + 능력치의 보정, 상한을 넘지 않는다. 어느 능력치인지는 rules 의 hp_ability 다
    player_made_hp: PlayerMadeHp | None
    # 방장이 "한 번 더 굴리기"를 줄 수 있는 테이블인가. 제작자가 허락했고, 주사위로 정하는 방식을 쓰는 테이블일 때다
    reroll_allowed: bool
    pregens: list[PregenChoice]
    members: list[MemberOut]
    # 초대 코드. 방장에게만 보인다
    invite_code: str | None
    started_at: datetime | None
    ended_at: datetime | None
