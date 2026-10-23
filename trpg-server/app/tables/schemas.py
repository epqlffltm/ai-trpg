# trpg-server/app/tables/schemas.py

"""
테이블 API 가 받는 입력과 내보내는 응답의 모양.

응답에 테이블의 복사본(content)을 통째로 싣지 않는다. GM 전용 글이 들어 있다.
참가자에게 필요한 것(고른 스타팅, 프리젠, 추천 인원)만 꺼내 싣는다.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from ai_core.catalog_file import Slug
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.assets.models import (
    PLAYER_MADE_MODES,
    TABLE_MAX_PLAYERS,
    CharacterMode,
    ItemKind,
    ItemRarity,
    NarrationStyle,
    Rating,
)
from app.assets.scenarios.schemas import (
    CharacterDescription,
    CharacterModes,
    CharacterName,
    PlayerMadeHp,
    RecommendedPlayers,
)
from app.billing.prices import Tier
from app.calendar.schemas import ClockOut, ClockTimeOut
from app.catalog.models import Grade
from app.catalog.steps import MAX_STEP
from app.engine.ruleset import RULESET_MAX_ABILITIES, RULESET_MAX_EQUIPMENT_SLOTS, Key, Ruleset
from app.engine.sheet import Score, Sheet
from app.tables.models import (
    CREDIT_WAIT_MAX,
    CREDIT_WAIT_MIN,
    DEFAULT_CREDIT_WAIT,
    DEFAULT_ROUND_TIME_LIMIT,
    ROUND_TIME_LIMIT_MAX,
    ROUND_TIME_LIMIT_MIN,
    TABLE_PASSWORD_MAX_LENGTH,
    TABLE_PASSWORD_MIN_LENGTH,
    DepartureKind,
    QuestStatus,
    TableStatus,
)

# 테이블의 비밀번호. 앞뒤 공백을 떼지 않는다. 적은 그대로가 비밀번호다
TablePassword = Annotated[
    str, StringConstraints(min_length=TABLE_PASSWORD_MIN_LENGTH, max_length=TABLE_PASSWORD_MAX_LENGTH)
]


# 라운드의 시간 제한(초). 라운드가 열린 때부터 센다
RoundTimeLimit = Annotated[int, Field(ge=ROUND_TIME_LIMIT_MIN, le=ROUND_TIME_LIMIT_MAX)]
# 크레딧이 모자란 사람을 기다리는 시간(초). 누가 모자라 서술이 멈춘 때부터 센다
CreditWait = Annotated[int, Field(ge=CREDIT_WAIT_MIN, le=CREDIT_WAIT_MAX)]
# 서술의 입력·출력 단계(#387, app/catalog/steps.py)
Step = Annotated[int, Field(ge=0, le=MAX_STEP)]


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
    # GM 의 서술 문체. 비우면 판의 추천 문체다. 만든 뒤에도 방장이 바꿀 수 있다
    narration_style: NarrationStyle | None = None
    # 라운드의 시간 제한(초). 적지 않으면 5 분이다. null 이면 시간 제한이 없다. 만든 뒤에도 방장이 바꿀 수 있다
    round_time_limit: RoundTimeLimit | None = DEFAULT_ROUND_TIME_LIMIT
    # 서술 모델(모델 목록의 이름표). 적지 않으면 시나리오의 추천 모델이고, 쓸 수 없으면 같은 회사의 대체 모델이다.
    # 고를 수 있는 모델만 된다(GET /tables/narration-models). 만든 뒤에도 방장이 바꿀 수 있다
    narration_model: Slug | None = None
    # 서술의 입력·출력 단계(#387). 적지 않으면 0, 0(i0.o0)이다. 정한 모델이 그 단계를 팔아야 한다(그 모델의 options).
    # 모델과 함께 바꾼다(PUT /tables/{id}/narration-model)
    input_step: Step = 0
    output_step: Step = 0
    # 크레딧이 모자란 사람을 기다리는 시간(초)과, 지나면 그 사람을 빼고 서술하는가. 만든 뒤에도 방장이 바꿀 수 있다
    credit_wait_seconds: CreditWait = DEFAULT_CREDIT_WAIT
    remove_short_payers: bool = True
    # 쪽지를 보낸 사실을 모두에게 알리는가. 적지 않으면 알리지 않는다. 만든 뒤에도 방장이 바꿀 수 있다
    whisper_notice: bool = False
    # 서술에 참고 자료(SRD 같은 바깥 자료)를 넣는가. 판의 세계관이 허용해야 켤 수 있다. 모집 중에만 바꿀 수 있다
    references_enabled: bool = False

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

    진행 중에 새 캐릭터를 들일 때도 같은 값을 받는다(POST .../character). 방식마다 적는 칸은 같다.

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


class NarrationStyleUpdate(BaseModel):
    """서술 문체를 바꿀 때 받는 값. null 을 보내면 판의 추천 문체로 돌린다. 칸을 빼먹으면 거부한다."""

    model_config = ConfigDict(extra='forbid')

    narration_style: NarrationStyle | None


class RoundTimeLimitUpdate(BaseModel):
    """라운드의 시간 제한을 바꿀 때 받는 값. null 이면 시간 제한을 없앤다. 칸을 빼먹으면 거부한다."""

    model_config = ConfigDict(extra='forbid')

    round_time_limit: RoundTimeLimit | None


class CreditWaitUpdate(BaseModel):
    """크레딧이 모자란 사람을 기다리는 규칙을 바꿀 때 받는 값. 둘 다 적는다. 칸을 빼먹으면 거부한다."""

    model_config = ConfigDict(extra='forbid')

    credit_wait_seconds: CreditWait
    remove_short_payers: bool


class WhisperNoticeUpdate(BaseModel):
    """쪽지를 보낸 사실을 알릴지 바꿀 때 받는 값. 칸을 빼먹으면 거부한다."""

    model_config = ConfigDict(extra='forbid')

    whisper_notice: bool


class ReferencesUpdate(BaseModel):
    """참고 자료를 서술에 넣을지 바꿀 때 받는 값. 칸을 빼먹으면 거부한다."""

    model_config = ConfigDict(extra='forbid')

    references_enabled: bool


class NarrationModelUpdate(BaseModel):
    """
    서술 모델과 단계를 바꿀 때 받는 값. 모델을 빼먹으면 거부한다. 비울 수 없다(서버의 기본 모델로 돌아가지 않는다).

    단계(#387)는 모델과 함께 한 가격표를 고르는 것이다. 적지 않으면 0, 0(i0.o0)이다. 그 모델이 그 단계를 팔아야 한다.
    """

    model_config = ConfigDict(extra='forbid')

    narration_model: Slug
    input_step: Step = 0
    output_step: Step = 0


class HostTransfer(BaseModel):
    """방장을 넘길 때 받는 값."""

    model_config = ConfigDict(extra='forbid')

    user_id: uuid.UUID


class NextPriceOut(BaseModel):
    """예약된 값의 바뀜. credits 가 null 이면 effective_at 부터 팔지 않는다."""

    credits: str | None
    tier: Tier | None
    # 그때부터의 값도 행사가인가
    promo: bool
    effective_at: datetime


class StepPriceOut(BaseModel):
    """
    모델의 단계 하나와 1인 1라운드의 값(#387). 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.

    입력 단계마다 입력 +8,000 토큰(12,000, 20,000, 28,000), 출력 단계마다 출력 +1,000 토큰(1,200, 2,200, 3,200)이다.
    입력이 크면 지난 기록, 로어북, 기억이 더 들어가고, 출력이 크면 장면이 길어진다.
    """

    input_step: int
    output_step: int
    input_tokens: int
    output_tokens: int
    credits: str | None
    tier: Tier | None
    promo: bool
    next: NextPriceOut | None


class NarrationModelOut(BaseModel):
    """
    고를 수 있는 서술 모델 하나와 1인 1라운드의 값.

    credits 는 결제 서버가 정한 값(글자, "120")이다. 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.
    tier 가 premium 이면 골드(유료 크레딧)로만 낸다. grade 는 화면의 묶음(basic, standard, premium)이다.
    """

    slug: str
    display_name: str
    vendor: str
    grade: Grade
    credits: str | None
    tier: Tier | None
    # 지금 값이 행사가인가. 행사가면 next 가 행사가 끝나는 때와 그 뒤의 값이다(화면이 "11월 21일까지, 그 뒤 440")
    promo: bool
    next: NextPriceOut | None
    # 이 날부터 쓰지 않는다(공급자가 내리는 날). 이 모델을 쓰는 테이블은 그날 같은 회사의 다른 모델로 바뀐다.
    # 화면이 "12월 1일 종료"를 보여 준다. 정해지지 않았으면 null
    retires_on: date | None
    # 지금 파는 단계들과 그 값(#387). 기본 단계(0, 0)가 맨 앞이고 그 값은 위의 credits 와 같다.
    # 입력, 출력의 차례다. 결제 서버 없이 도는 서버면 모든 단계가 값 없이 나온다
    options: list[StepPriceOut]


class NarrationModelsOut(BaseModel):
    """고를 수 있는 서술 모델들. free 는 결제 서버 없이 도는 서버라 값이 없다는 뜻이다."""

    free: bool
    models: list[NarrationModelOut]


class CharacterOut(BaseModel):
    """캐릭터."""

    name: str
    description: str


class InjuryOut(BaseModel):
    """캐릭터가 입고 있는 부상 하나. 이름과 사실, 효과는 테이블의 rules.injuries 에서 이름표(injury)로 찾는다."""

    # 규칙의 Injury.key
    injury: str
    # 생긴 라운드
    round: int
    # 짧은 부상이면 이 라운드가 닫힐 때 풀린다. 오래 가는 것과 결손은 None 이다
    ends_after_round: int | None
    # 오래 가는 부상이면 이 게임 안의 시각이 지나면 낫는다(그 뒤에 닫히는 라운드에서). 짧은 것과 결손은 None 이다
    heals_at: ClockTimeOut | None = None


class ItemOut(BaseModel):
    """
    캐릭터가 가진 물건 한 가지. 이름은 판의 로어북 물건 항목의 이름이다.

    설명(항목의 글)은 싣지 않는다. 로어북은 AI 가 읽는 설정이라 비밀이 들어 있을 수 있다.
    """

    entry_id: uuid.UUID
    name: str
    kind: ItemKind
    # 물건의 등급(노말, 레어, 유니크, 에픽, 레전드)
    rarity: ItemRarity
    count: int


class CatalogItemOut(BaseModel):
    """
    판에 있는 물건 하나. 로어북의 물건 항목이다.

    kind 가 consumable 이면 쓰면 하나 줄어든다. heals 가 있으면 쓸 때 HP 를 그 등급(rules 의 magnitudes)만큼 되돌린다.
    """

    entry_id: uuid.UUID
    name: str
    kind: ItemKind
    heals: str | None
    # 물건의 등급(노말, 레어, 유니크, 에픽, 레전드). 높을수록 훔치기 어렵다
    rarity: ItemRarity
    # 상인이 파는 값(#278). 사 줄 때는 currency.sell_percent 를 곱해 내림한다. 비어 있으면 사고팔 수 없다
    price: int | None = None
    # 착용할 때 들어갈 수 있는 규칙의 칸(rules.equipment_slots)과 함께 차지하는 칸의 수(#276).
    # 칸이 비어 있으면 착용하지 않는 물건이다
    slots: list[str] = []
    slot_count: int = 1
    # 무기의 공격 보정, 차지한 칸의 방어, 모든 부위의 방어(#276). 없으면 None 이다.
    # 무기는 타격에 적을 수 있는 착용한 물건이다(rounds 의 CheckAction.weapon). 방어가 하는 일은 rules.armor 가 정한다
    attack: int | None = None
    defense: int | None = None
    guard: int | None = None
    # 무기의 관통력과 불굴 세이브의 값(#276). 없으면 None 이다
    ap: int | None = None
    ward: int | None = None


class WornOut(BaseModel):
    """착용한 물건 하나(#276). 무엇을 규칙의 어느 칸들에 끼웠는가. 이름은 판의 로어북 물건 항목의 이름이다."""

    entry_id: uuid.UUID
    name: str
    slots: list[str]


class WearRequest(BaseModel):
    """
    장비를 착용할 때 받는 값(#276). 가진 물건 하나를 규칙의 칸들에 끼운다.

    slots 는 그 물건이 들어갈 수 있는 칸 중에서 차지하는 칸의 수만큼 고른다(CatalogItemOut.slots, slot_count).
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    slots: list[Key] = Field(min_length=1, max_length=RULESET_MAX_EQUIPMENT_SLOTS)


class CurrencyOut(BaseModel):
    """
    테이블의 화폐(#278). 판에 굳은 것이다. 돈은 엔진만 바꾼다. 결제의 크레딧과 상관없다.

    sell_percent 는 상인이 사 주는 값의 백분율이다. 물건 하나의 값에 곱해 내림한다.
    """

    name: str
    unit: str
    sell_percent: int


class QuestOut(BaseModel):
    """
    퀘스트 하나. 이름은 판의 로어북 사건 항목의 이름이다. 판의 순서로 싣는다.

    사건의 글은 싣지 않는다. 로어북은 AI 가 읽는 설정이다. 숨긴(hidden) 것은 방장에게만 싣는다.
    """

    entry_id: uuid.UUID
    name: str
    status: QuestStatus
    # 기한이 끝나는 게임 안의 시각. 판의 규칙에 기한이 있는 퀘스트가 드러날 때 정한다. 없으면 None.
    # 진행 중인데 이 시각이 지나면 그다음에 닫히는 라운드까지 기다렸다가 서버가 실패로 바꾼다
    due_at: ClockTimeOut | None = None


class PlaceItemOut(BaseModel):
    """장소에 보이게 놓인 물건 한 가지. 같은 물건은 합친 개수다. 이름은 판의 로어북 물건 항목의 이름이다."""

    entry_id: uuid.UUID
    name: str
    count: int


class PlaceOut(BaseModel):
    """
    아는 장소 하나. 이름은 판의 로어북 장소 항목의 이름이다.

    장소의 글은 싣지 않는다. 로어북은 AI 가 읽는 설정이다.
    items 는 그곳에 보이게 놓인 물건들이다. 누군가 서 본 장소만 싣는다. 숨긴 물건은 싣지 않는다
    (app/tables/place_items.py). 캐릭터가 내려놓은 것(put_down)도 여기 보인다. 줍기(take)로 가져간다.
    cover 는 그 장소의 숨을 곳이 얼마나 좋은지다(#276). 세이브 방식의 판에서 엄폐하면 이 값으로 커버 세이브를 받는다.
    커버가 없는 곳이면 0 이다.
    """

    entry_id: uuid.UUID
    name: str
    items: list[PlaceItemOut] = []
    cover: int = 0


class RouteCrossOut(BaseModel):
    """
    길에 적힌 판정 하나(#281). 넘기(지날 때마다 가는 사람이 굴린다), 따기, 부수기다.

    룰북의 능력치와 난이도의 이름표다.
    """

    ability: str
    # 판에 비워 뒀으면 규칙의 기본 난이도다
    difficulty: str


class RouteOut(BaseModel):
    """
    아는 길 하나. two_way 가 아니면 from_place 에서 to_place 로만 간다.

    길의 조건(#281)도 싣는다. 잠긴 문과 오를 절벽은 보이는 것이다. 무슨 열쇠로 여는지, 따는 도구,
    실패의 피해는 싣지 않는다.
    """

    from_place: uuid.UUID
    to_place: uuid.UUID
    two_way: bool
    # 한 칸 가는 데 걸리는 게임 안의 시간(분). 비어 있으면 라운드의 걸음 안에서 간다
    travel_minutes: int | None = None
    # 자물쇠가 지금 잠겨 있는가. 자물쇠가 없는 길이면 None 이다. 잠겨 있으면 그 열쇠를 지닌 사람만 지나가며 연다
    locked: bool | None = None
    # 길을 넘는 판정. 없으면 None 이다
    cross: RouteCrossOut | None = None
    # 빗장이 지금 걸려 있는가. 빗장이 없는 길이면 None 이다. 빗장 쪽(bar_side)에서만 걸고 푼다
    barred: bool | None = None
    bar_side: uuid.UUID | None = None
    # 문이 부서졌는가. 부서진 문은 열린 채이고 다시 잠그지 못한다
    broken: bool = False
    # 자물쇠를 따는 판정과 문을 부수는 판정. 없으면 따거나 부수지 못한다
    pick: RouteCrossOut | None = None
    force: RouteCrossOut | None = None


class MapOut(BaseModel):
    """
    테이블이 아는 맵. 앉은 사람 모두가 같은 것을 본다. 방장도 마찬가지다.

    숨긴 길과 숨긴 길로만 닿는 장소, 아직 서 보지 않은 안개 길은 싣지 않는다(app/tables/places.py).
    """

    places: list[PlaceOut]
    routes: list[RouteOut]


class SheetOut(BaseModel):
    """앉은 사람의 캐릭터 시트. 앉은 사람은 서로의 시트를 본다."""

    # 이 사람의 몇 번째 캐릭터인가. 시작할 때 받은 것이 1 이다. 새 캐릭터를 들일 때마다 하나씩 올라간다
    number: int
    # 능력치의 점수. 이름표가 무슨 능력치인지는 테이블의 rules 에 있다
    abilities: dict[str, int]
    max_hp: int
    # 지금의 HP
    hp: int
    # 죽음의 굴림에서 지금까지 센 성공과 실패. 쓰러져 있는 동안만 센다. 일어나면 0 으로 돌아간다.
    # 몇 번이 모이면 죽는지, 고비를 넘기는지는 테이블의 rules.death_save 에 있다
    death_successes: int
    death_failures: int
    # 죽었는가. 죽은 캐릭터는 되살아나지 않는다. 그 플레이어는 새 캐릭터를 들일 수 있다
    dead: bool
    # 입고 있는 부상들. 생긴 순서다. 풀리거나 나은 것은 들어가지 않는다
    injuries: list[InjuryOut] = []
    # 가진 물건들. 판의 물건 순서다(TableDetail.items). 앉은 사람은 서로의 소지품을 본다
    items: list[ItemOut] = []
    # 가진 돈(#278). 테이블의 화폐(TableDetail.currency)로 센다. 화폐가 없는 테이블이면 늘 0 이다
    money: int = 0
    # 착용한 물건들(#276). 규칙의 칸의 차례다. 착용한 것도 소지품(items)에 들어 있다
    worn: list[WornOut] = []
    # 서 있는 맵의 장소. 이름은 TableDetail.map.places 에서 찾는다. 맵이 없는 테이블이면 None 이다
    place_id: uuid.UUID | None = None


class FallenOut(BaseModel):
    """떠난 캐릭터 하나. 죽었고, 그 플레이어가 새 캐릭터를 들였다. 숫자는 죽을 때의 것이다."""

    # 그 사람의 몇 번째 캐릭터였는가
    number: int
    character_name: str
    # 프리젠에서 온 캐릭터였으면 몇 번째 프리젠인가. 그 프리젠은 이 테이블에서 다시 고를 수 없다
    pregen_index: int | None
    abilities: dict[str, int]
    max_hp: int


class RollOut(BaseModel):
    """주사위로 굴린 능력치의 점수들. 앉은 사람은 서로의 굴림을 본다."""

    # 굴린 눈. 점수 하나마다 눈의 목록이 하나다. 버린 눈도 들어 있다
    dice: list[list[int]]
    # 굴려서 나온 점수들. 이것을 능력치에 놓는다
    scores: list[int]
    # 이 테이블에서 몇 번 굴렸는가. 캐릭터가 바뀌어도 이어서 센다
    times_rolled: int
    # 이 사람의 몇 번째 캐릭터를 위해 굴렸는가. 지금 정하는 캐릭터의 번호와 같아야 그 캐릭터에 쓸 수 있다.
    # 지금 정하는 캐릭터의 번호는 시트가 없으면 1, 있으면 sheet.number + 1 이다
    character_number: int
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
    # 지금 캐릭터의 시트. 게임을 시작하기 전에는 None 이다. 시작할 때 받는다.
    # 진행 중에 새 캐릭터를 들이면 새 캐릭터의 것으로 바뀐다
    sheet: SheetOut | None
    # 떠난 캐릭터들. 죽은 순서다. 새 캐릭터를 들인 적이 없으면 비어 있다
    fallen: list[FallenOut]
    joined_at: datetime


class PregenChoice(BaseModel):
    """고를 수 있는 프리젠 하나. 누가 이미 가져갔는지 함께 알려 준다."""

    name: str
    description: str
    # 이 프리젠을 고르면 받는 숫자
    sheet: Sheet
    # 가져간 사람. 아무도 가져가지 않았으면 None 이다. 가져간 사람이 테이블을 떠나면 다시 None 이 된다
    taken_by: uuid.UUID | None
    # 이 프리젠의 캐릭터가 이 테이블에서 죽었는가. 죽은 캐릭터의 프리젠은 아무도 다시 고를 수 없다
    dead: bool


class TableSummary(BaseModel):
    """테이블의 목록에 싣는 값."""

    id: uuid.UUID
    # 이 테이블의 시나리오(#428). 시나리오 소개(GET /listings/{scenario_id})로 돌아갈 때 쓴다.
    # 공개를 내렸거나 남의 비공개 시나리오면 그 주소는 404 다. 그래도 값은 싣는다(어느 시나리오였는지는 참가자가 안다)
    scenario_id: uuid.UUID
    title: str
    status: TableStatus
    rating: Rating
    capacity: int
    member_count: int
    host_id: uuid.UUID
    # 로비에 보이는가, 로비에서 들어올 때 비밀번호를 묻는가
    is_public: bool
    has_password: bool
    # 지금의 서술 문체. 로비에서 들어가기 전에 어떤 글로 진행되는지 안다
    narration_style: NarrationStyle
    # 라운드의 시간 제한(초). 없으면 null 이다. 로비에서 들어가기 전에 얼마나 빨리 진행되는지 안다
    round_time_limit: int | None
    # 지금의 서술 모델(이름표). 로비에서 들어가기 전에 어느 모델로 서술하는지 안다. 바꾸면 보통 다음 라운드부터다.
    # 값은 GET /tables/narration-models 에서 이름표로 찾는다. 이 규칙 전에 만든 테이블만 null 이다(서버의 기본 모델)
    narration_model: str | None
    # 서술의 입력·출력 단계(#387). 값은 그 모델의 options 에서 이 단계로 찾는다. 들어가기 전에 안다
    input_step: int
    output_step: int
    # 크레딧이 모자란 사람을 기다리는 시간(초)과, 지나면 그 사람을 자리에서 빼는가. 들어가기 전에 안다
    credit_wait_seconds: int
    remove_short_payers: bool
    # 쪽지를 보낸 사실을 모두에게 알리는가. 들어가기 전에 안다
    whisper_notice: bool
    # 서술에 참고 자료(SRD 같은 바깥 자료)를 넣는가. 들어가기 전에 안다. 시작하면 바뀌지 않는다
    references_enabled: bool
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
    # 시나리오의 제작자가 추천한 문체. 방장이 문체를 고르는 화면에서 "추천"을 표시한다
    recommended_narration_style: NarrationStyle
    pregens: list[PregenChoice]
    # 이 테이블의 판에 있는 물건들. 소지품의 이름과 종류와 값을 여기서 찾는다
    items: list[CatalogItemOut]
    # 화폐(#278). 돈이 없는 판이면 None 이다. 그때는 사고팔지도 돈을 건네지도 못한다
    currency: CurrencyOut | None = None
    # 이 테이블의 퀘스트들. 숨긴 것은 방장에게만 보인다. 시작 전에는 비어 있다
    quests: list[QuestOut]
    # 이 테이블이 아는 맵. 맵이 없는 판이면 None 이다. 시작 전에도 처음부터 아는 것(열린 길, 명소)이 보인다
    map: MapOut | None
    # 게임 안의 지금 시각과 다음 라운드에 흐를 시간. GET .../clock 과 같은 값이다. 시작 전에는 판의 시작 시각이다
    clock: ClockOut
    members: list[MemberOut]
    # 초대 코드. 방장에게만 보인다
    invite_code: str | None
    started_at: datetime | None
    ended_at: datetime | None


class PastTableOut(BaseModel):
    """
    내가 떠난 테이블 하나(#428). 떠난 때까지의 기록을 읽는 길(GET /tables/past/{table_id}/events)로 간다.

    떠난 뒤의 일은 싣지 않는다. 테이블이 지금 어떤 상태인지, 누가 남았는지도 싣지 않는다.
    """

    table_id: uuid.UUID
    scenario_id: uuid.UUID
    title: str
    # 떠날 때의 캐릭터 이름. 캐릭터를 만들기 전에 떠났으면 None 이다
    character_name: str | None
    # 떠난 길. left(스스로), kicked(방장이 내보냄), dropped(크레딧이 모자라 서버가 뺌)
    kind: DepartureKind
    # 읽을 수 있는 마지막 이벤트의 번호. 떠났다는 이벤트의 번호다
    last_sequence: int = Field(ge=1)
    left_at: datetime


class PastTablePage(BaseModel):
    """내가 떠난 테이블 목록의 한 쪽. 최근에 떠난 것부터다."""

    items: list[PastTableOut]
    total: int = Field(ge=0)
