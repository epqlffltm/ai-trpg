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
    ATTACK_NAME_MAX_LENGTH,
    CHARACTER_DESCRIPTION_MAX_LENGTH,
    CHARACTER_NAME_MAX_LENGTH,
    CLOCK_MAX_DAY,
    DEFAULT_CHARACTER_MODES,
    DEFAULT_NARRATION_STYLE,
    DEFAULT_ROUND_MINUTES,
    DEFAULT_START_DAY,
    DEFAULT_START_HOUR,
    ENCOUNTER_MAX_COUNT,
    ITEM_STACK_MAX,
    MONSTER_MAX_ATTACKS,
    PLAYER_MADE_HP_MAX,
    ROUND_MAX_MINUTES,
    SCENARIO_MAX_BESTIARIES,
    SCENARIO_MAX_ENCOUNTERS,
    SCENARIO_MAX_ITEM_RULES,
    SCENARIO_MAX_LANDMARKS,
    SCENARIO_MAX_LOREBOOKS,
    SCENARIO_MAX_MONSTER_SHEETS,
    SCENARIO_MAX_NPC_SHEETS,
    SCENARIO_MAX_OPENINGS,
    SCENARIO_MAX_PREGENS,
    SCENARIO_MAX_QUEST_RULES,
    SCENARIO_MAX_ROUTES,
    SCENARIO_MAX_STARTING_ITEMS,
    SCENARIO_OPENING_MAX_LENGTH,
    TABLE_MAX_PLAYERS,
    VERSION_NOTE_MAX_LENGTH,
    CharacterMode,
    ItemKind,
    NarrationStyle,
    QuestStart,
    Rating,
    RouteVisibility,
    Surprise,
)
from app.assets.scenarios.snapshot import Snapshot
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate
from app.engine.ruleset import Key
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


def reject_duplicate_bestiaries(bestiary_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """같은 몬스터 도감이 두 번 있으면 거부한다."""
    if len(set(bestiary_ids)) != len(bestiary_ids):
        raise ValueError('같은 도감이 두 번 있습니다.')
    return bestiary_ids


BestiaryIds = Annotated[
    list[uuid.UUID], Field(max_length=SCENARIO_MAX_BESTIARIES), AfterValidator(reject_duplicate_bestiaries)
]


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


class Clock(BaseModel):
    """
    게임 안의 시계. 테이블이 시작할 때의 시각(며칠째, 몇 시)과 라운드 하나에 흐르는 기본 시간(분).

    시각은 1일째 0시부터 센다. 달 이름 같은 달력은 아직 없다. 셋을 함께 보낸다.
    라운드 하나에 흐르는 시간은 방장이 라운드마다 바꿀 수 있다. 여기 적는 것은 바꾸지 않았을 때의 값이다.
    """

    model_config = ConfigDict(extra='forbid')

    start_day: int = Field(ge=1, le=CLOCK_MAX_DAY)
    start_hour: int = Field(ge=0, le=23)
    round_minutes: int = Field(ge=1, le=ROUND_MAX_MINUTES)


# 시계를 보내지 않은 시나리오의 시계. 1일째 8시에 시작하고 라운드 하나에 10분이 흐른다
DEFAULT_CLOCK = Clock(start_day=DEFAULT_START_DAY, start_hour=DEFAULT_START_HOUR, round_minutes=DEFAULT_ROUND_MINUTES)


class ItemStack(BaseModel):
    """
    물건 몇 개. 붙인 로어북의 물건 항목 하나(entry_id)를 count 개다. 시작 소지품에 쓴다.

    가리키는 항목이 붙인 로어북에 있는지, 물건인지는 게시할 때 본다. 로어북은 나중에 바꿀 수 있다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    count: int = Field(ge=1, le=ITEM_STACK_MAX)

    @field_serializer('entry_id')
    def entry_id_as_text(self, entry_id: uuid.UUID) -> str:
        """항목의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(entry_id)


def reject_duplicate_stacks(stacks: list[ItemStack]) -> list[ItemStack]:
    """같은 물건이 두 줄에 나뉘어 있으면 거부한다. 한 줄에 개수를 적는다."""
    entry_ids = [stack.entry_id for stack in stacks]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 물건이 두 번 있습니다. 한 줄에 개수를 적습니다.')
    return stacks


# 시작 소지품. 시나리오의 것(모두가 받는다)과 프리젠 하나의 것이 같은 모양이다
StartingItems = Annotated[
    list[ItemStack], Field(max_length=SCENARIO_MAX_STARTING_ITEMS), AfterValidator(reject_duplicate_stacks)
]


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
    # 이 프리젠을 고른 사람이 시작할 때 더 받는 소지품. 시나리오의 시작 소지품은 따로 받는다
    items: StartingItems = []


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


class MonsterAttack(BaseModel):
    """
    몬스터의 공격(스킬) 하나. 몬스터의 차례에 이 능력치로 이 난이도에 판정하고, 맞으면 대상이 이 등급만큼 피해를 입는다.

    이름표(능력치, 난이도, 양의 등급)는 룰북의 것이다. 규칙에 있는지는 게시할 때 본다(monster_attack_invalid).
    """

    model_config = ConfigDict(extra='forbid')

    # 공격의 이름. 서술과 기록에 쓴다(물어뜯기)
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ATTACK_NAME_MAX_LENGTH)]
    ability: Key
    difficulty: Key
    harm: Key


def reject_duplicate_attacks(attacks: list[MonsterAttack]) -> list[MonsterAttack]:
    """같은 이름의 공격이 둘이면 거부한다. 기록에서 어느 공격인지 알 수 없다."""
    names = [attack.name for attack in attacks]
    if len(set(names)) != len(names):
        raise ValueError('같은 이름의 공격이 두 번 있습니다.')
    return attacks


MonsterAttacks = Annotated[
    list[MonsterAttack], Field(max_length=MONSTER_MAX_ATTACKS), AfterValidator(reject_duplicate_attacks)
]


class MonsterSheet(BaseModel):
    """
    몬스터 시트 하나. 붙인 도감의 몬스터 하나(monster_id)에 숫자를 준다.

    시트를 적은 몬스터만 이 시나리오가 쓴다. 판에는 시트가 있는 몬스터만 들어간다.
    가리키는 몬스터가 붙인 도감에 있는지, 시트가 규칙에 맞는지는 게시할 때 본다. NPC 시트와 같은 까닭이다.
    """

    model_config = ConfigDict(extra='forbid')

    monster_id: uuid.UUID
    sheet: Sheet
    # 공격들. 비우면 공격하지 않는 몬스터다(겁먹은 짐승). 숫자와 같은 까닭으로 시나리오에 적는다(룰북의 이름표다)
    attacks: MonsterAttacks = []

    @field_serializer('monster_id')
    def monster_id_as_text(self, monster_id: uuid.UUID) -> str:
        """몬스터의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(monster_id)


def reject_duplicate_monsters(monster_sheets: list[MonsterSheet]) -> list[MonsterSheet]:
    """같은 몬스터의 시트가 두 번 있으면 거부한다. 어느 숫자를 쓸지 정할 수 없다."""
    monster_ids = [monster_sheet.monster_id for monster_sheet in monster_sheets]
    if len(set(monster_ids)) != len(monster_ids):
        raise ValueError('같은 몬스터의 시트가 두 번 있습니다.')
    return monster_sheets


MonsterSheets = Annotated[
    list[MonsterSheet], Field(max_length=SCENARIO_MAX_MONSTER_SHEETS), AfterValidator(reject_duplicate_monsters)
]


class Encounter(BaseModel):
    """
    조우 하나. 맵의 장소 하나(place_id)에 몬스터 하나(monster_id)가 count 마리 있다.

    장소가 붙인 로어북의 장소 항목인지, 몬스터가 시트를 적은 몬스터인지는 게시할 때 본다.
    로어북도 몬스터 시트도 나중에 바꿀 수 있어서 지금 정할 수 없다.
    """

    model_config = ConfigDict(extra='forbid')

    place_id: uuid.UUID
    monster_id: uuid.UUID
    count: int = Field(ge=1, le=ENCOUNTER_MAX_COUNT)
    # 누가 기습하는가. 적지 않으면 기습이 없다
    surprise: Surprise = Surprise.NONE

    @field_serializer('place_id', 'monster_id')
    def id_as_text(self, value: uuid.UUID) -> str:
        """ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(value)


def reject_duplicate_encounters(encounters: list[Encounter]) -> list[Encounter]:
    """같은 장소의 같은 몬스터가 두 줄이면 거부한다. 한 줄에 마리 수로 적는다."""
    pairs = [(encounter.place_id, encounter.monster_id) for encounter in encounters]
    if len(set(pairs)) != len(pairs):
        raise ValueError('같은 장소의 같은 몬스터가 두 번 있습니다. 한 줄에 마리 수로 적습니다.')
    return encounters


Encounters = Annotated[
    list[Encounter], Field(max_length=SCENARIO_MAX_ENCOUNTERS), AfterValidator(reject_duplicate_encounters)
]


class ItemRule(BaseModel):
    """
    아이템 규칙 하나. 붙인 로어북의 물건 항목 하나(entry_id)가 엔진에서 무엇인지 정한다.

    규칙이 없는 물건 항목은 장비(gear)다. 소모품만 회복의 양(heals)을 적을 수 있다.
    heals 는 룰북의 등급(magnitudes)의 이름이다(예: light). 그 등급이 룰북에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    kind: ItemKind
    heals: Key | None = None

    @model_validator(mode='after')
    def heal_only_with_consumables(self) -> 'ItemRule':
        """장비에는 회복의 양을 적지 않는다. 쓰지 않는 물건이다."""
        if self.heals is not None and self.kind != ItemKind.CONSUMABLE:
            raise ValueError('회복의 양(heals)은 소모품(consumable)에만 적습니다.')
        return self

    @field_serializer('entry_id')
    def entry_id_as_text(self, entry_id: uuid.UUID) -> str:
        """항목의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(entry_id)


def reject_duplicate_rules(rules: list[ItemRule]) -> list[ItemRule]:
    """같은 물건의 규칙이 두 번 있으면 거부한다. 어느 규칙을 쓸지 정할 수 없다."""
    entry_ids = [rule.entry_id for rule in rules]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 물건의 규칙이 두 번 있습니다.')
    return rules


ItemRules = Annotated[list[ItemRule], Field(max_length=SCENARIO_MAX_ITEM_RULES), AfterValidator(reject_duplicate_rules)]


class QuestRule(BaseModel):
    """
    퀘스트 규칙 하나. 붙인 로어북의 사건 항목 하나(entry_id)가 퀘스트로서 어떤지 정한다.

    start 는 테이블이 시작할 때의 상태다(숨김, 진행 중). reward 는 성공했을 때 받는 물건이다.
    규칙이 없는 사건 항목은 숨긴 채로 시작하고 보상이 없다.
    가리키는 사건과 보상의 물건이 붙인 로어북에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    start: QuestStart = QuestStart.HIDDEN
    # 시작 소지품과 모양이 같다. 같은 물건은 한 줄에 개수로 적는다
    reward: StartingItems = []

    @field_serializer('entry_id')
    def entry_id_as_text(self, entry_id: uuid.UUID) -> str:
        """항목의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(entry_id)


def reject_duplicate_quests(rules: list[QuestRule]) -> list[QuestRule]:
    """같은 사건의 규칙이 두 번 있으면 거부한다. 어느 규칙을 쓸지 정할 수 없다."""
    entry_ids = [rule.entry_id for rule in rules]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 사건의 퀘스트 규칙이 두 번 있습니다.')
    return rules


class FindCheck(BaseModel):
    """
    숨긴 길을 찾는 판정. 어느 능력치(ability)로, 어느 난이도(difficulty)로 굴리는가.

    둘 다 룰북의 규칙에 있는 이름이다. 난이도를 적지 않으면 규칙의 기본 난이도다. 규칙에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    ability: Key
    difficulty: Key | None = None


class RouteRule(BaseModel):
    """
    길 하나. 붙인 로어북의 장소 항목 둘(from_place, to_place)을 잇는다.

    two_way 면 양쪽으로 다닌다(기본). 아니면 from 에서 to 로만 간다(떨어지는 구멍, 한쪽에서만 열리는 문).
    visibility 는 플레이어가 길을 언제 아는가다(기본은 처음부터, RouteVisibility).
    숨긴 길(hidden)은 플레이어도 방장도 모른다. 숨긴 길에는 찾는 판정(find)이 있어야 하고, 다른 길에는 없다.
    가리키는 장소가 붙인 로어북에 있는지, 장소인지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    from_place: uuid.UUID
    to_place: uuid.UUID
    two_way: bool = True
    visibility: RouteVisibility = RouteVisibility.OPEN
    find: FindCheck | None = None

    @model_validator(mode='after')
    def leads_somewhere_else(self) -> 'RouteRule':
        """제자리로 돌아오는 길은 받지 않는다."""
        if self.from_place == self.to_place:
            raise ValueError('길의 두 끝이 같은 장소입니다.')
        return self

    @model_validator(mode='after')
    def find_only_when_hidden(self) -> 'RouteRule':
        """숨긴 길만 찾는 판정이 있다. 숨기고 판정이 없으면 영영 드러나지 않는다."""
        hidden = self.visibility == RouteVisibility.HIDDEN
        if hidden and self.find is None:
            raise ValueError('숨긴 길에는 찾는 판정(find)이 있어야 합니다.')
        if not hidden and self.find is not None:
            raise ValueError('찾는 판정(find)은 숨긴 길에만 적습니다.')
        return self

    @field_serializer('from_place', 'to_place')
    def place_as_text(self, place: uuid.UUID) -> str:
        """장소의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(place)


def reject_duplicate_routes(routes: list[RouteRule]) -> list[RouteRule]:
    """같은 두 장소를 잇는 길이 둘이면 거부한다. 방향이 달라도 같은 두 장소다. 어느 길로 가는지 가를 수 없다."""
    pairs = [frozenset((route.from_place, route.to_place)) for route in routes]
    if len(set(pairs)) != len(pairs):
        raise ValueError('같은 두 장소를 잇는 길이 두 번 있습니다.')
    return routes


Routes = Annotated[list[RouteRule], Field(max_length=SCENARIO_MAX_ROUTES), AfterValidator(reject_duplicate_routes)]


def reject_duplicate_landmarks(landmarks: list[uuid.UUID]) -> list[uuid.UUID]:
    """같은 장소가 명소에 두 번 있으면 거부한다."""
    if len(set(landmarks)) != len(landmarks):
        raise ValueError('같은 장소가 명소에 두 번 있습니다.')
    return landmarks


Landmarks = Annotated[
    list[uuid.UUID], Field(max_length=SCENARIO_MAX_LANDMARKS), AfterValidator(reject_duplicate_landmarks)
]


QuestRules = Annotated[
    list[QuestRule], Field(max_length=SCENARIO_MAX_QUEST_RULES), AfterValidator(reject_duplicate_quests)
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
    bestiary_ids: BestiaryIds = []
    openings: Openings = []
    recommended_players: RecommendedPlayers = RecommendedPlayers(min=1, max=TABLE_MAX_PLAYERS)
    pregens: Pregens = []
    # 안 보내면 프리젠과 기본 시트를 허용한다. 플레이어가 숫자를 정하는 방식은 직접 적어야 켜진다
    character_modes: CharacterModes = list(DEFAULT_CHARACTER_MODES)
    default_sheet: Sheet | None = None
    npc_sheets: NpcSheets = []
    default_npc_sheet: Sheet | None = None
    monster_sheets: MonsterSheets = []
    encounters: Encounters = []
    items: ItemRules = []
    starting_items: StartingItems = []
    quests: QuestRules = []
    start_place: uuid.UUID | None = None
    routes: Routes = []
    landmarks: Landmarks = []
    player_made_hp: PlayerMadeHp | None = None
    # 주사위로 정한 점수를 방장이 다시 굴리게 해 줄 수 있는가. 안 보내면 안 된다
    reroll_allowed: bool = False
    # 추천 문체. 테이블의 방장이 고르지 않으면 이것으로 서술한다. 안 보내면 정통이다
    narration_style: NarrationStyle = DEFAULT_NARRATION_STYLE
    # 게임 안의 시계. 안 보내면 1일째 8시에 시작하고 라운드 하나에 10분이 흐른다
    clock: Clock = DEFAULT_CLOCK


class ScenarioUpdate(AssetUpdate):
    """
    시나리오를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    rulebook_id, world_id, default_sheet, default_npc_sheet, player_made_hp, start_place 는 null 을 보내면 비운다.
    보내지 않으면 그대로 둔다.
    lorebook_ids, bestiary_ids, openings, pregens, npc_sheets, monster_sheets, encounters, items, starting_items,
    quests, routes, landmarks, character_modes 는
    보낸 목록으로 통째로 바꾼다.
    character_modes 말고는 전부 없애려면 빈 목록을 보낸다. character_modes 는 비울 수 없다.
    recommended_players 는 최소와 최대를 함께 보낸다. clock 은 셋을 함께 보낸다.
    """

    clearable: ClassVar[frozenset[str]] = frozenset(
        {'rulebook_id', 'world_id', 'default_sheet', 'default_npc_sheet', 'player_made_hp', 'start_place'}
    )

    rating: Rating | None = None
    rulebook_id: uuid.UUID | None = None
    world_id: uuid.UUID | None = None
    lorebook_ids: LorebookIds | None = None
    bestiary_ids: BestiaryIds | None = None
    openings: Openings | None = None
    recommended_players: RecommendedPlayers | None = None
    pregens: Pregens | None = None
    character_modes: CharacterModes | None = None
    default_sheet: Sheet | None = None
    npc_sheets: NpcSheets | None = None
    default_npc_sheet: Sheet | None = None
    monster_sheets: MonsterSheets | None = None
    encounters: Encounters | None = None
    items: ItemRules | None = None
    starting_items: StartingItems | None = None
    quests: QuestRules | None = None
    start_place: uuid.UUID | None = None
    routes: Routes | None = None
    landmarks: Landmarks | None = None
    player_made_hp: PlayerMadeHp | None = None
    reroll_allowed: bool | None = None
    narration_style: NarrationStyle | None = None
    clock: Clock | None = None


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
    bestiary_ids: list[uuid.UUID]
    openings: list[str]
    recommended_players: RecommendedPlayers
    pregens: list[Pregen]
    character_modes: list[CharacterMode]
    default_sheet: Sheet | None
    npc_sheets: list[NpcSheet]
    default_npc_sheet: Sheet | None
    monster_sheets: list[MonsterSheet]
    encounters: list[Encounter]
    items: list[ItemRule]
    starting_items: list[ItemStack]
    quests: list[QuestRule]
    start_place: uuid.UUID | None
    routes: list[RouteRule]
    landmarks: list[uuid.UUID]
    player_made_hp: PlayerMadeHp | None
    reroll_allowed: bool
    narration_style: NarrationStyle
    clock: Clock


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
