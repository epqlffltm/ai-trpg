# trpg-server/app/assets/scenarios/schemas.py

"""
시나리오 API 가 받는 입력과 내보내는 응답의 모양. 공통 모양(app/assets/schemas.py)에 시나리오의 칸을 더한다.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, ClassVar, Literal

from ai_core.catalog_file import Slug
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
    CARRIED_MAX_EQUIPMENT,
    CARRIED_MAX_INVENTORY,
    CHARACTER_DESCRIPTION_MAX_LENGTH,
    CHARACTER_NAME_MAX_LENGTH,
    CLOCK_MAX_DAY,
    COMBAT_NUMBER_MAX,
    COUNTED_CONDITIONS,
    CURRENCY_NAME_MAX_LENGTH,
    CURRENCY_UNIT_MAX_LENGTH,
    DEFAULT_CHARACTER_MODES,
    DEFAULT_NARRATION_STYLE,
    DEFAULT_ROUND_MINUTES,
    DEFAULT_SELL_PERCENT,
    DEFAULT_START_DAY,
    DEFAULT_START_HOUR,
    DROP_CHANCE_MAX,
    ENCOUNTER_MAX_COUNT,
    FAIL_ONLY_CONDITIONS,
    HAPPENING_MAX_EFFECTS,
    ITEM_STACK_MAX,
    MONEY_MAX,
    MONSTER_MAX_ATTACKS,
    PLAYER_MADE_HP_MAX,
    QUEST_CONDITION_MAX_COUNT,
    QUEST_LINK_CONDITIONS,
    QUEST_MAX_CONDITIONS,
    QUEST_MAX_TIME_LIMIT_MINUTES,
    ROUND_MAX_MINUTES,
    SCENARIO_MAX_BESTIARIES,
    SCENARIO_MAX_COVERS,
    SCENARIO_MAX_ENCOUNTERS,
    SCENARIO_MAX_HAPPENINGS,
    SCENARIO_MAX_ITEM_RULES,
    SCENARIO_MAX_LANDMARKS,
    SCENARIO_MAX_LOREBOOKS,
    SCENARIO_MAX_MONSTER_SHEETS,
    SCENARIO_MAX_NPC_PLACES,
    SCENARIO_MAX_NPC_SHEETS,
    SCENARIO_MAX_OPENINGS,
    SCENARIO_MAX_PLACE_ITEMS,
    SCENARIO_MAX_PREGENS,
    SCENARIO_MAX_QUEST_RULES,
    SCENARIO_MAX_ROUTES,
    SCENARIO_MAX_STARTING_ITEMS,
    SCENARIO_MAX_WANDERS,
    SCENARIO_OPENING_MAX_LENGTH,
    TABLE_MAX_PLAYERS,
    VERSION_NOTE_MAX_LENGTH,
    WANDER_MAX_MONSTERS,
    WANDER_MAX_WEIGHT,
    CharacterMode,
    HappeningEffectKind,
    ItemKind,
    ItemRarity,
    NarrationStyle,
    NpcAttitude,
    NpcCaught,
    PlaceItemVisibility,
    QuestConditionKind,
    QuestMatch,
    QuestStart,
    Rating,
    RouteVisibility,
    Surprise,
)
from app.assets.scenarios.recommended_model import ModelState
from app.assets.scenarios.snapshot import Snapshot
from app.assets.schemas import AssetCreate, AssetSummary, AssetUpdate
from app.calendar.clock import TimeOfDay
from app.engine.action import DoorDevice
from app.engine.item_aids import Aids
from app.engine.item_effects import AttackEffects, Effects
from app.engine.ruleset import RULESET_MAX_EQUIPMENT_SLOTS, InjuryNature, Key, SkillCost
from app.engine.sheet import CharacterSheet, Sheet

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

# 돈의 양(#278). 시작 돈, 프리젠이 더 받는 돈, 퀘스트의 보상이다. 0 은 주지 않는 것이다
Money = Annotated[int, Field(ge=0, le=MONEY_MAX)]
# 물건 하나의 값. 0 으로 팔지 않는다. 사고팔 수 없는 물건은 값을 비운다
Price = Annotated[int, Field(ge=1, le=MONEY_MAX)]


class Currency(BaseModel):
    """
    시나리오의 화폐(#278). 이름(금화)과 단위(닢), 캐릭터 모두가 시작할 때 받는 돈, 상인이 사 주는 값의 백분율이다.

    결제의 크레딧과 상관없다. 게임 안의 돈이고 엔진만 바꾼다. 서술(AI)은 돈을 주거나 빼앗지 못한다.
    sell_percent 는 상인이 물건을 사 줄 때 물건의 값에 곱한다(내림). 0 이면 상인이 사 주지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CURRENCY_NAME_MAX_LENGTH)]
    # 단위는 비워도 된다(금화 30)
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=CURRENCY_UNIT_MAX_LENGTH)] = ''
    starting: Money = 0
    sell_percent: int = Field(default=DEFAULT_SELL_PERCENT, ge=0, le=100)


def reject_duplicate_slots(slots: list[str]) -> list[str]:
    """같은 칸을 두 번 적으면 거부한다."""
    if len(set(slots)) != len(slots):
        raise ValueError('같은 장비의 칸을 두 번 적었습니다.')
    return slots


# 장비의 칸들(#276). 룰북의 equipment_slots 의 이름표다. 룰북에 있는지는 게시할 때 본다
Slots = Annotated[list[Key], Field(max_length=RULESET_MAX_EQUIPMENT_SLOTS), AfterValidator(reject_duplicate_slots)]
# 무기의 공격 보정, 방어구의 방어, 몬스터의 타고난 방어(#276). 어떻게 쓰는지는 룰북의 방어 규칙(armor)이 정한다
CombatNumber = Annotated[int, Field(ge=1, le=COMBAT_NUMBER_MAX)]


class ItemStack(BaseModel):
    """
    물건 몇 개. 붙인 로어북의 물건 항목 하나(entry_id)를 count 개다. 시작 소지품에 쓴다.

    wear 는 그중 하나를 시작할 때 착용하는 칸들이다(#276). 비우면 착용하지 않고 시작한다.
    그 물건의 아이템 규칙이 정한 칸 중에서, 차지하는 칸의 수만큼 적는다. 퀘스트의 보상에는 적지 않는다.
    가리키는 항목이 붙인 로어북에 있는지, 물건인지, 칸이 맞는지는 게시할 때 본다. 로어북은 나중에 바꿀 수 있다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    count: int = Field(ge=1, le=ITEM_STACK_MAX)
    wear: Slots = []

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
    sheet: CharacterSheet | None = None
    # 이 프리젠을 고른 사람이 시작할 때 더 받는 소지품. 시나리오의 시작 소지품은 따로 받는다
    items: StartingItems = []
    # 이 프리젠을 고른 사람이 시작할 때 더 받는 돈(#278). 시나리오의 시작 돈(currency.starting)은 따로 받는다
    money: Money = 0


def reject_duplicate_names(pregens: list[Pregen]) -> list[Pregen]:
    """같은 이름의 프리젠이 두 번 있으면 거부한다. 고르는 화면에서 구별할 수 없다. 대소문자만 다른 것도 같은 것이다."""
    names = [pregen.name.casefold() for pregen in pregens]
    if len(set(names)) != len(names):
        raise ValueError('같은 이름의 프리젠이 두 번 있습니다.')
    return pregens


Pregens = Annotated[list[Pregen], Field(max_length=SCENARIO_MAX_PREGENS), AfterValidator(reject_duplicate_names)]


class CarriedItem(BaseModel):
    """
    몬스터나 NPC 가 지닌 물건 한 줄. 붙인 로어북의 물건 항목(entry_id)을 count 개 지녔다. 몬스터는 마리마다다.

    chance 는 살아 있던 몬스터나 NPC 가 처음 쓰러졌을 때 이 줄이 떨어질 확률(%)이다. 비우면 늘 떨어진다(100).
    줄마다 따로 굴린다. 떨어지지 않은 것은 그대로 지닌다.
    wear 는 그 물건 하나를 착용한 칸들이다(#276). 한 개라도 지니고 있는 동안 착용한 것이다.
    떨어뜨리거나 빼앗겨 남은 것이 없으면 그 부위는 빈다. 칸이 맞는지는 게시할 때 본다(carried_wear_invalid).
    항목이 붙인 로어북의 물건인지는 게시할 때 본다. 소지품과 같은 문제로 알린다(item_entry_missing, item_not_item).
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    count: int = Field(default=1, ge=1, le=ITEM_STACK_MAX)
    chance: int = Field(default=DROP_CHANCE_MAX, ge=1, le=DROP_CHANCE_MAX)
    # 착용한 칸들(#276). 장비(equipment)의 줄에만 적는다. 앉은 사람의 시작 착용과 같은 규칙이다
    wear: Slots = []

    @field_serializer('entry_id')
    def entry_id_as_text(self, entry_id: uuid.UUID) -> str:
        """항목의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(entry_id)


def reject_duplicate_items(lines: list[CarriedItem]) -> list[CarriedItem]:
    """같은 물건이 두 줄이면 거부한다. 한 줄에 개수와 확률로 적는다."""
    entry_ids = [line.entry_id for line in lines]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 물건이 두 줄 있습니다. 한 줄에 개수와 확률로 적습니다.')
    return lines


def reject_wear_in_inventory(inventory: list[CarriedItem]) -> None:
    """소지품(품에 넣은 것)에는 착용을 적지 않는다. 착용은 장비의 줄에만 있다."""
    if any(line.wear for line in inventory):
        raise ValueError('착용(wear)은 장비(equipment)의 줄에만 적습니다.')


def reject_unknown_weapons(attacks: list['MonsterAttack'], equipment: list[CarriedItem]) -> None:
    """공격의 무기는 그 시트의 장비 줄에 있는 물건이어야 한다."""
    carried = {line.entry_id for line in equipment}
    if any(attack.weapon is not None and attack.weapon not in carried for attack in attacks):
        raise ValueError('공격의 무기(weapon)는 장비(equipment)에 적은 물건이어야 합니다.')


def reject_items_in_both(equipment: list[CarriedItem], inventory: list[CarriedItem]) -> None:
    """같은 물건을 장비와 소지품에 함께 적었으면 거부한다. 지닌 것을 셀 때 어느 줄인지 갈리지 않게."""
    entry_ids = [line.entry_id for line in [*equipment, *inventory]]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 물건을 장비와 소지품에 함께 적었습니다.')


CarriedEquipment = Annotated[
    list[CarriedItem], Field(max_length=CARRIED_MAX_EQUIPMENT), AfterValidator(reject_duplicate_items)
]
CarriedInventory = Annotated[
    list[CarriedItem], Field(max_length=CARRIED_MAX_INVENTORY), AfterValidator(reject_duplicate_items)
]


class MonsterAttack(BaseModel):
    """
    몬스터의 공격(스킬) 하나. 몬스터의 차례에 이 능력치로 이 난이도에 판정하고, 맞으면 대상이 이 등급만큼 피해를 입는다.
    effects 가 있으면(#805 ③-b) 맞혔을 때 대상에게 그 효과들(부상, 수치의 맞추기)이 더 든다.
    방어와 세이브는 피해만 막는다.
    피해 등급(harm)은 비울 수 있다. 그때는 효과만 있는 공격이다(독 뿜기). 피해도 효과도 없는 공격은 받지 않는다.

    이름표(능력치, 난이도, 양의 등급)는 룰북의 것이다. 규칙에 있는지는 게시할 때 본다(monster_attack_invalid).
    NPC 시트의 공격도 이 모양이다(#487). 그때 게시의 문제는 npc_attack_invalid 다.
    cost 는 쓸 때 내는 비용이다(#805 ③-a). 그 몬스터나 인물이 가진 수치(rules.resources 의 holders) 하나를 그만큼 낸다.
    비우면 공짜다. 차례에 이 공격을 골랐는데 모자라면 그 차례에 아무것도 하지 못한다. 빗나가도 낸다.
    """

    model_config = ConfigDict(extra='forbid')

    # 공격의 이름. 서술과 기록에 쓴다(물어뜯기)
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ATTACK_NAME_MAX_LENGTH)]
    ability: Key
    difficulty: Key
    # 맞혔을 때의 피해의 양의 등급. 비우면 피해가 없다(#805 ③-b)
    harm: Key | None = None
    # 이 공격에 쓰는 무기(#276). 시트의 장비 줄의 물건이다. 착용하고 있고 공격 보정이 있으면 판정에 더한다.
    # 빼앗기거나 떨어뜨려 지니지 않으면 보정도 없다. 비우면 맨몸의 공격이다(물어뜯기)
    weapon: uuid.UUID | None = None
    # 쓸 때 내는 비용(#805 ③-a). 비우면 공짜다
    cost: SkillCost | None = None
    # 맞혔을 때 더 드는 효과들(#805 ③-b). 부상(injure)과 수치의 맞추기(adjust)다. 대상은 맞은 캐릭터다
    effects: AttackEffects = []

    @model_validator(mode='after')
    def require_something(self) -> 'MonsterAttack':
        """피해도 효과도 없는 공격은 아무 일도 하지 않는다. 받지 않는다."""
        if self.harm is None and not self.effects:
            raise ValueError('공격에는 피해 등급(harm)이나 효과(effects)가 있어야 합니다.')
        return self

    @field_serializer('weapon')
    def weapon_as_text(self, weapon: uuid.UUID | None) -> str | None:
        """무기의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return None if weapon is None else str(weapon)


def reject_duplicate_attacks(attacks: list[MonsterAttack]) -> list[MonsterAttack]:
    """같은 이름의 공격이 둘이면 거부한다. 기록에서 어느 공격인지 알 수 없다."""
    names = [attack.name for attack in attacks]
    if len(set(names)) != len(names):
        raise ValueError('같은 이름의 공격이 두 번 있습니다.')
    return attacks


MonsterAttacks = Annotated[
    list[MonsterAttack], Field(max_length=MONSTER_MAX_ATTACKS), AfterValidator(reject_duplicate_attacks)
]


class NpcSheet(BaseModel):
    """
    NPC 시트 하나. 붙인 로어북의 인물 항목 하나(entry_id)에 숫자와 처음 태도와 지닌 물건을 준다.

    attitude 는 일행을 처음 어떻게 대하는가다(우호, 중립(기본), 적대). 테이블에서는 엔진이 바꾼다(#474).
    지닌 물건(장비와 소지품)과 둔한지는 몬스터 시트와 같은 모양이다(#457). 숨긴 소지품은 없다. 몬스터처럼 보인다.
    on_caught 는 훔치다 들켰을 때다. 늘 적대가 되고, fight 면 싸움도 붙는다(기본 hostile, 적대만).
    attacks 는 공격들이다. 몬스터 시트와 같은 모양이다(#487). 싸움이 붙은 적대 인물이 라운드의 차례에 쓴다(#487 2/2).
    merchant 는 상인인지다(#278). 상인은 소지품(inventory) 중 값이 있는 물건을 팔고, 값이 있는 물건을 사 준다.
    소지품의 개수가 곧 재고다. 장비는 팔지 않는다.

    프리젠과 달리 시트를 비워 둘 수 없다. 숫자를 줄 생각이 없으면 이 칸을 만들지 않으면 된다(기본 NPC 시트를 쓴다).
    가리키는 항목이 붙인 로어북에 있는지, 인물인지, 시트가 규칙에 맞는지는 게시할 때 본다.
    로어북도 룰북도 나중에 바꿀 수 있어서 지금 정할 수 없다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    sheet: Sheet
    attitude: NpcAttitude = NpcAttitude.NEUTRAL
    # 지닌 물건. 처음 쓰러졌을 때의 드롭은 여기서만 나온다. 비우면 아무것도 지니지 않는다
    equipment: CarriedEquipment = []
    inventory: CarriedInventory = []
    # 둔한가. 둔하면 훔치기가 쉽다(룰북 규칙의 steal.dull 만큼). 눈치 능력치와는 따로 더한다
    dull: bool = False
    # 훔치다 들켰을 때. 적대만(hostile) 하는가, 싸움도 붙는가(fight)
    on_caught: NpcCaught = NpcCaught.HOSTILE
    # 공격들. 비우면 싸움이 붙어도 치지 않는다. 이름표가 룰북에 있는지는 게시할 때 본다(npc_attack_invalid)
    attacks: MonsterAttacks = []
    # 상인인가(#278). 화폐가 없는 시나리오에는 상인을 두지 못한다(게시의 currency_missing)
    merchant: bool = False

    @model_validator(mode='after')
    def one_line_per_item(self) -> 'NpcSheet':
        """같은 물건을 장비와 소지품에 함께 적지 않는다."""
        reject_items_in_both(self.equipment, self.inventory)
        return self

    @model_validator(mode='after')
    def wear_and_weapons_in_equipment(self) -> 'NpcSheet':
        """착용은 장비의 줄에만 적고, 공격의 무기는 장비에 적은 물건이다(#276)."""
        reject_wear_in_inventory(self.inventory)
        reject_unknown_weapons(self.attacks, self.equipment)
        return self

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


class NaturalArmor(BaseModel):
    """몬스터의 한 부위의 타고난 방어(#276). 칸(slot)은 룰북의 장비의 칸이다. 룰북에 있는지는 게시할 때 본다."""

    model_config = ConfigDict(extra='forbid')

    slot: Key
    defense: CombatNumber


def reject_duplicate_natural_armor(natural: list[NaturalArmor]) -> list[NaturalArmor]:
    """한 부위를 두 번 적으면 거부한다. 한 줄에 그 부위의 방어를 적는다."""
    slots = [one.slot for one in natural]
    if len(set(slots)) != len(slots):
        raise ValueError('같은 부위의 타고난 방어가 두 번 있습니다.')
    return natural


NaturalArmors = Annotated[
    list[NaturalArmor],
    Field(max_length=RULESET_MAX_EQUIPMENT_SLOTS),
    AfterValidator(reject_duplicate_natural_armor),
]


def reject_repeated_natures(natures: list[InjuryNature]) -> list[InjuryNature]:
    """같은 성질을 두 번 적으면 거부한다."""
    if len(set(natures)) != len(natures):
        raise ValueError('같은 성질을 두 번 적었습니다.')
    return natures


Natures = Annotated[list[InjuryNature], Field(max_length=len(InjuryNature)), AfterValidator(reject_repeated_natures)]


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
    # 지닌 물건. 장비(equipment)는 몸에 걸치거나 쥔 것, 소지품(inventory)은 품에 넣은 것이다.
    # 쓰러뜨렸을 때의 드롭은 여기서만 나온다(#372, #456). 비우면 아무것도 지니지 않고 드롭도 없다
    equipment: CarriedEquipment = []
    inventory: CarriedInventory = []
    # 둔한가. 둔하면 훔치기가 쉽다(룰북 규칙의 steal.dull 만큼). 눈치 능력치와 타입과는 따로 더한다
    dull: bool = False
    # 부위마다 타고난 방어(#276). 가죽, 비늘, 껍데기. 착용한 방어구의 방어에 더한다. 칸은 룰북의 것이다
    natural_armor: NaturalArmors = []
    # 타고난 불굴 세이브(#276). 세이브 방식에서 관통을 무시하고 막는다. 비우면 없다
    ward: CombatNumber | None = None
    # 타입의 면역(app/tables/monsters.py 의 Traits)에 더하는 부상의 성질과, 타입의 면역에서 빼는 성질(#799).
    # 독을 먹는 골렘(빼기), 정신이 없는 짐승(더하기)처럼 그 몬스터만 다를 때 적는다
    immune: Natures = []
    vulnerable: Natures = []

    @model_validator(mode='after')
    def one_line_per_item(self) -> 'MonsterSheet':
        """같은 물건을 장비와 소지품에 함께 적지 않는다. 마리가 지닌 것을 셀 때 어느 줄인지 갈리지 않게."""
        reject_items_in_both(self.equipment, self.inventory)
        return self

    @model_validator(mode='after')
    def immune_or_vulnerable(self) -> 'MonsterSheet':
        """한 성질을 더하면서 빼지 않는다."""
        if set(self.immune) & set(self.vulnerable):
            raise ValueError('같은 성질을 면역(immune)과 약함(vulnerable)에 함께 적었습니다.')
        return self

    @model_validator(mode='after')
    def wear_and_weapons_in_equipment(self) -> 'MonsterSheet':
        """착용은 장비의 줄에만 적고, 공격의 무기는 장비에 적은 물건이다(#276)."""
        reject_wear_in_inventory(self.inventory)
        reject_unknown_weapons(self.attacks, self.equipment)
        return self

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


class NpcPlace(BaseModel):
    """
    인물의 자리 하나(#282). 붙인 로어북의 인물 항목 하나(entry_id)가 처음에 맵의 장소 하나(place_id)에 있다.

    자리가 있는 인물은 캐릭터가 그 장소에 서 있을 때 장면에 나오고, 같은 장소에서만 겨눈다. 서술이 불러내지 못한다.
    NPC 시트가 없는 인물도 자리를 적을 수 있다. 인물이 인물 항목인지, 장소가 맵의 장소인지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    place_id: uuid.UUID

    @field_serializer('entry_id', 'place_id')
    def id_as_text(self, value: uuid.UUID) -> str:
        """ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(value)


def reject_duplicate_npc_places(places: list[NpcPlace]) -> list[NpcPlace]:
    """같은 인물의 자리가 두 번 있으면 거부한다. 인물 하나는 한 곳에만 있다."""
    entry_ids = [place.entry_id for place in places]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 인물의 자리가 두 번 있습니다.')
    return places


NpcPlaces = Annotated[
    list[NpcPlace], Field(max_length=SCENARIO_MAX_NPC_PLACES), AfterValidator(reject_duplicate_npc_places)
]


class PickCheck(BaseModel):
    """
    자물쇠를 따는 판정(#281). 행동 '따기'가 이 능력과 난이도로 굴린다. 성공하면 자물쇠가 열린다.

    needs_tool 이면 도구가 있어야 딴다(#802). 도구는 그 행동을 거드는 물건(아이템 규칙의 aids)이면 어느 것이든 된다.
    플레이어가 행동에 붙인다. 보정과 없어지는 방식은 물건이 정한다.
    예전의 특정 도구(tool)는 이것과 그 물건의 거들기가 됐다.
    능력치와 난이도가 룰북에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    ability: Key
    difficulty: Key | None = None
    needs_tool: bool = False


class ItemLock(BaseModel):
    """
    물건이 새 자물쇠일 때 그 자물쇠(#281). 행동 '바꾸기'로 판에 자물쇠가 있던 문에 단다.

    단 자물쇠는 판의 자물쇠 대신 쓰인다. 여는 열쇠(key)는 새 것이다. 옛 열쇠로는 더 열지 못한다.
    열쇠는 붙인 로어북의 물건 항목 하나다. 길의 자물쇠의 열쇠, 다른 자물쇠 물건의 열쇠와 겹치지 못한다
    (게시의 route_key_repeated). 자물쇠 물건 자신을 열쇠로 적지 못한다.
    pick 을 적었으면 단 자물쇠를 따기로 열 수 있다. 적지 않으면 따지 못한다. 단 자물쇠는 열린 채다.
    한 테이블에서 자물쇠 물건 하나는 한 번만 단다. 달면 소지품에서 없어진다.
    """

    model_config = ConfigDict(extra='forbid')

    key: uuid.UUID
    pick: PickCheck | None = None

    @field_serializer('key')
    def key_as_text(self, key: uuid.UUID) -> str:
        """열쇠의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(key)


class ItemThrow(BaseModel):
    """
    물건을 던지는 판정(#277). 투척 단검처럼 던지기에 맞춘 물건에 적는다. 적지 않은 물건도 던질 수 있다(#801).
    그때는 룰북의 맞히는 판정(rules.item_check)으로 던진다.

    ability 와 difficulty 는 룰북의 능력치와 난이도의 이름이다. 난이도를 비우면 룰북의 기본 난이도다.
    룰북의 규칙에 있는지는 게시할 때 본다(item_throw_invalid). 맞으면 그 물건의 효과(effects)가 든다.
    예전의 맞았을 때의 피해(harm)는 효과의 damage 가 됐다. 던지면 맞든 빗나가든 하나 없어진다.
    """

    model_config = ConfigDict(extra='forbid')

    ability: Key
    difficulty: Key | None = None


class ItemRule(BaseModel):
    """
    아이템 규칙 하나. 붙인 로어북의 물건 항목 하나(entry_id)가 엔진에서 무엇인지 정한다.

    규칙이 없는 물건 항목은 장비(gear)이고 노말이다. 소모품만 효과 목록(effects)을 적을 수 있다(#800).
    효과는 쓰면 대상에게 일어나는 일들이다(회복, 풀기, 피해, 부상, app/engine/item_effects.py). 차례대로 실행한다.
    등급과 부상이 룰북에 있는지는 게시할 때 본다. 예전의 heals(회복의 양)와 cures(푸는 부상)는 효과가 됐다.
    rarity 는 물건의 등급이다(노말, 레어, 유니크, 에픽, 레전드). 높을수록 훔치기 어렵다.
    price 는 상인이 파는 값이다(#278). 사 줄 때는 화폐의 백분율(currency.sell_percent)을 곱한다.
    비우면 사고팔 수 없는 물건이다. 화폐가 없는 시나리오에는 값을 적지 못한다(게시의 currency_missing).
    slots 는 착용할 때 들어갈 수 있는 룰북의 칸들, slot_count 는 그중 몇 칸을 함께 차지하는가다(#276).
    두 손 검은 주손과 보조손을 함께(2), 단검은 둘 중 하나(1)다. slots 를 비우면 착용하지 않는 물건이다.
    장비에만 적는다. 칸이 룰북에 있는지는 게시할 때 본다(item_slot_invalid).
    attack 은 무기의 공격 보정이다. 이 물건을 착용하고 공격할 때 판정에 더한다(#276).
    defense 는 차지한 칸(부위)의 방어, guard 는 모든 부위의 방어다(방패). 착용하면 공격을 막는다.
    어떻게 막는지는 룰북의 방어 규칙(armor.mode)이 정한다. 셋 다 착용하는 물건에만 적는다.
    ap 는 무기의 관통력이다. 관통하면 방어구로는 막지 못한다. ward 는 불굴 세이브의 값이다(부적, 역장).
    세이브 방식에서 관통을 무시하고 막는다. 여러 개를 착용하면 가장 큰 것을 쓴다.
    lock 은 이 물건이 문에 다는 새 자물쇠일 때의 그 자물쇠다(#281). 장비에만 적는다.
    throw 는 던지는 판정이다(#277). 장비에도 적을 수 있다(#801, 투척 도끼). 적지 않으면 룰북의 맞히는 판정으로 던진다.
    행동 '던지기'로 같은 장소의 몬스터나 인물에게 던지고, 맞으면 그 물건의 효과가 든다.
    aids 는 이 물건이 거드는 행동들이다(#802, app/engine/item_aids.py). 치료, 따기, 고치기, 부수기, 넘기에 붙여 쓰면
    판정에 보정을 더하고, 굴린 뒤 정한 대로 없어진다(늘, 실패하면, 안 없어짐). 장비와 소모품 모두 적는다.
    예전의 치료 보정(treat_bonus)은 치료의 거들기(늘 없어짐)가 됐다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    kind: ItemKind = ItemKind.GEAR
    effects: Effects = []
    rarity: ItemRarity = ItemRarity.NORMAL
    price: Price | None = None
    slots: Slots = []
    slot_count: int = Field(default=1, ge=1, le=RULESET_MAX_EQUIPMENT_SLOTS)
    attack: CombatNumber | None = None
    defense: CombatNumber | None = None
    guard: CombatNumber | None = None
    ap: CombatNumber | None = None
    ward: CombatNumber | None = None
    lock: ItemLock | None = None
    throw: ItemThrow | None = None
    aids: Aids = []

    @model_validator(mode='after')
    def combat_only_when_worn(self) -> 'ItemRule':
        """공격 보정과 방어는 착용하는 물건(칸이 있다)에만 적는다. 착용해야 쓰인다."""
        numbers = (self.attack, self.defense, self.guard, self.ap, self.ward)
        if not self.slots and any(number is not None for number in numbers):
            raise ValueError('공격 보정(attack, ap)과 방어(defense, guard, ward)는 칸(slots)이 있는 물건에만 적습니다.')
        return self

    @model_validator(mode='after')
    def pierce_only_with_attack(self) -> 'ItemRule':
        """관통력은 무기(공격 보정이 있다)에만 적는다. 타격에 적을 수 있는 것은 무기뿐이다."""
        if self.ap is not None and self.attack is None:
            raise ValueError('관통력(ap)은 공격 보정(attack)이 있는 무기에만 적습니다.')
        return self

    @model_validator(mode='after')
    def slots_only_on_gear(self) -> 'ItemRule':
        """소모품은 착용하지 않는다. 쓰면 없어지는 물건이다."""
        if self.slots and self.kind != ItemKind.GEAR:
            raise ValueError('장비의 칸(slots)은 장비(gear)에만 적습니다.')
        return self

    @model_validator(mode='after')
    def slot_count_within_slots(self) -> 'ItemRule':
        """차지하는 칸의 수는 들어갈 수 있는 칸보다 많지 않다."""
        if self.slots and self.slot_count > len(self.slots):
            raise ValueError('차지하는 칸의 수(slot_count)가 들어갈 수 있는 칸(slots)보다 많습니다.')
        return self

    @model_validator(mode='after')
    def effects_only_with_consumables(self) -> 'ItemRule':
        """효과는 소모품에만 적는다. 장비는 쓰지 않는 물건이다."""
        if self.effects and self.kind != ItemKind.CONSUMABLE:
            raise ValueError('효과(effects)는 소모품(consumable)에만 적습니다.')
        return self

    @model_validator(mode='after')
    def lock_only_on_gear(self) -> 'ItemRule':
        """자물쇠는 장비에만 적는다. 다는 것은 쓰는 것이 아니다."""
        if self.lock is not None and self.kind != ItemKind.GEAR:
            raise ValueError('자물쇠(lock)는 장비(gear)에만 적습니다.')
        return self

    @model_validator(mode='after')
    def lock_key_not_itself(self) -> 'ItemRule':
        """자물쇠 물건 자신은 그 자물쇠의 열쇠가 아니다. 달면 없어지니 열 열쇠가 남지 않는다."""
        if self.lock is not None and self.lock.key == self.entry_id:
            raise ValueError('자물쇠 물건 자신을 그 자물쇠의 열쇠(lock.key)로 적지 못합니다.')
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


class QuestCondition(BaseModel):
    """
    퀘스트의 조건 하나. 종류(kind)마다 target 이 가리키는 것이 다르다(QuestConditionKind).

    reach_place 는 장소 항목, defeat_monster 는 붙인 도감의 몬스터(시트를 적은 것),
    hold_item 과 lose_item 은 물건 항목,
    defeat_npc 와 npc_dead 는 인물 항목, quest_succeeded 와 quest_failed 는 다른 퀘스트(사건 항목)다.
    count 는 defeat_monster, hold_item, lose_item 만 쓴다. 나머지는 1 로 둔다.
    consume 은 hold_item 에만 쓴다. 참이면 이룰 때 그 물건을 count 개 일행의 소지품에서 가져간다(배달).
    일행이 고르게 나눠 낸다(app/rounds/quest_handover.py). 이루는 조건(conditions)에만 적는다.
    가리키는 것이 있는지, 맞는 종류인지, 이룰 수 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: QuestConditionKind
    target: uuid.UUID
    count: int = Field(default=1, ge=1, le=QUEST_CONDITION_MAX_COUNT)
    consume: bool = False

    @model_validator(mode='after')
    def count_only_when_counted(self) -> 'QuestCondition':
        """세지 않는 조건(장소에 닿기, 인물 쓰러뜨리기)에는 count 를 적지 않는다."""
        if self.count != 1 and self.kind not in COUNTED_CONDITIONS:
            raise ValueError('count 는 defeat_monster, hold_item, lose_item 에만 적습니다.')
        return self

    @model_validator(mode='after')
    def consume_only_items(self) -> 'QuestCondition':
        """가져가는 것은 물건뿐이다. 장소나 몬스터를 가져갈 수 없다."""
        if self.consume and self.kind != QuestConditionKind.HOLD_ITEM:
            raise ValueError('consume 은 hold_item 에만 적습니다.')
        return self

    @field_serializer('target')
    def target_as_text(self, target: uuid.UUID) -> str:
        """가리키는 것의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(target)


def reject_duplicate_conditions(conditions: list[QuestCondition]) -> list[QuestCondition]:
    """같은 종류의 같은 대상이 두 줄이면 거부한다. 한 줄에 count 로 적는다."""
    pairs = [(condition.kind, condition.target) for condition in conditions]
    if len(set(pairs)) != len(pairs):
        raise ValueError('같은 조건이 두 번 있습니다.')
    return conditions


QuestConditions = Annotated[
    list[QuestCondition], Field(max_length=QUEST_MAX_CONDITIONS), AfterValidator(reject_duplicate_conditions)
]


class QuestRule(BaseModel):
    """
    퀘스트 규칙 하나. 붙인 로어북의 사건 항목 하나(entry_id)가 퀘스트로서 어떤지 정한다.

    start 는 테이블이 시작할 때의 상태다(숨김, 진행 중). reward 는 성공했을 때 받는 물건이다.
    reward_money 는 성공했을 때 받는 돈이다(#278). 살아 있는 캐릭터마다 이만큼 받는다. 0 이면 돈은 없다.
    time_limit_minutes 는 기한이다. 퀘스트가 드러난(진행 중이 된) 때부터 게임 안의 시간으로 센다.
    비우면 기한이 없다. 지나면 서버가 실패로 바꾼다(app/rounds/deadlines.py).
    conditions 는 이루는 조건이다. 라운드가 닫힐 때 엔진이 보고 채워졌으면 성공으로 바꾼다(app/rounds/quest_goals.py).
    match 는 조건이 여럿일 때 모두(all) 채워야 하는지, 하나라도(any) 채우면 되는지다.
    조건이 없으면 성공하지 않는다. 사람(방장, 장부 초안)은 퀘스트를 성공으로 바꾸지 못한다.
    reveal 은 숨긴 퀘스트가 드러나는 조건, reveal_match 는 그것을 맞추는 법이다. 엔진이 보고 드러낸다.
    숨긴 채로 시작하는 퀘스트에만 적는다. 다른 퀘스트를 보는 조건(퀘스트 잇기)은 여기와 실패하는 조건에 쓴다.
    자기 자신을 보면 거부한다. 드러나는 조건이 없는 숨긴 퀘스트는 이루어야만 드러난다(드러내며 바로 성공).
    사람(방장, 장부 초안)은 퀘스트를 드러내지 못한다.
    fail 은 실패하는 조건, fail_match 는 그것을 맞추는 법이다(#367).
    진행 중인 퀘스트의 조건이 채워지면 엔진이 실패로 바꾼다.
    같은 라운드에 이루는 조건도 채워졌으면 성공이 먼저다. 물건을 잃는 것(lose_item)은 여기에만 쓴다.
    조건이 없으면 기한으로만 실패한다. 사람(방장)은 퀘스트를 실패로 바꾸지 못한다.
    규칙이 없는 사건 항목은 숨긴 채로 시작하고 보상과 기한과 조건이 없다.
    가리키는 사건과 보상의 물건이 붙인 로어북에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    start: QuestStart = QuestStart.HIDDEN
    # 시작 소지품과 모양이 같다. 같은 물건은 한 줄에 개수로 적는다
    reward: StartingItems = []
    reward_money: Money = 0
    time_limit_minutes: int | None = Field(default=None, ge=1, le=QUEST_MAX_TIME_LIMIT_MINUTES)
    conditions: QuestConditions = []
    match: QuestMatch = QuestMatch.ALL
    reveal: QuestConditions = []
    reveal_match: QuestMatch = QuestMatch.ALL
    fail: QuestConditions = []
    fail_match: QuestMatch = QuestMatch.ALL

    @model_validator(mode='after')
    def no_wear_in_rewards(self) -> 'QuestRule':
        """보상은 소지품으로 받는다. 착용하는 칸을 적지 않는다."""
        if any(stack.wear for stack in self.reward):
            raise ValueError('보상에는 착용하는 칸(wear)을 적지 않습니다.')
        return self

    @model_validator(mode='after')
    def no_links_in_conditions(self) -> 'QuestRule':
        """다른 퀘스트를 보는 조건은 이루는 조건에 쓰지 않는다. 이루는 것은 이 퀘스트의 일로 정한다."""
        if any(condition.kind in QUEST_LINK_CONDITIONS for condition in self.conditions):
            raise ValueError(
                'quest_succeeded 와 quest_failed 는 드러나는 조건(reveal)과 실패하는 조건(fail)에만 적습니다.'
            )
        return self

    @model_validator(mode='after')
    def losses_only_in_fail(self) -> 'QuestRule':
        """물건을 잃어서 이루거나 드러나는 퀘스트는 없다. 잃는 것은 실패하는 조건이다."""
        if any(condition.kind in FAIL_ONLY_CONDITIONS for condition in [*self.conditions, *self.reveal]):
            raise ValueError('lose_item 은 실패하는 조건(fail)에만 적습니다.')
        return self

    @model_validator(mode='after')
    def consume_only_on_success(self) -> 'QuestRule':
        """드러나거나 실패할 때는 아무것도 가져가지 않는다. 가져가는 것은 이룰 때다."""
        if any(condition.consume for condition in [*self.reveal, *self.fail]):
            raise ValueError('consume 은 이루는 조건(conditions)에만 적습니다.')
        return self

    @model_validator(mode='after')
    def fail_not_on_itself(self) -> 'QuestRule':
        """자기 자신이 끝나야 실패하는 조건은 뜻이 없다. 끝난 퀘스트는 더 실패하지 않는다."""
        if any(condition.target == self.entry_id for condition in self.fail):
            raise ValueError('실패하는 조건이 자기 자신을 가리킵니다.')
        return self

    @model_validator(mode='after')
    def reveal_only_when_hidden(self) -> 'QuestRule':
        """처음부터 진행 중인 퀘스트는 드러날 일이 없다."""
        if self.reveal and self.start != QuestStart.HIDDEN:
            raise ValueError('드러나는 조건(reveal)은 숨긴 채로 시작하는 퀘스트에만 적습니다.')
        return self

    @model_validator(mode='after')
    def reveal_not_on_itself(self) -> 'QuestRule':
        """자기 자신이 끝나야 드러나는 조건은 뜻이 없다. 숨긴 채로 끝나면 그때 드러난다."""
        if any(condition.target == self.entry_id for condition in self.reveal):
            raise ValueError('드러나는 조건이 자기 자신을 가리킵니다.')
        return self

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


class CrossCheck(BaseModel):
    """
    길을 넘는 판정(#281). 절벽 오르기, 급류 헤엄치기처럼 지날 때마다 가는 사람이 굴린다.

    ability 와 difficulty 는 찾는 판정(FindCheck)과 같다. 실패하면 가지 못하고 그 자리에 남는다.
    harm 을 적었으면 실패한 사람이 그 양의 등급(룰북의 magnitudes 의 이름)만큼 다친다(떨어짐, 휩쓸림).
    셋 다 룰북의 규칙에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    ability: Key
    difficulty: Key | None = None
    harm: Key | None = None


class RouteLock(BaseModel):
    """
    길의 자물쇠(#281). 잠겨 있으면 그 열쇠(key)를 지닌 사람만 지나간다. 지나가면서 연다.

    열쇠는 붙인 로어북의 물건 항목 하나다. 열쇠 하나는 자물쇠 하나만 연다. 같은 열쇠를 두 길에 적으면 게시하지 못한다.
    locked 는 테이블이 시작할 때 잠겨 있는가다(기본은 잠김). 연 문은 누가 다시 잠그기 전까지 열린 채다.
    열쇠를 지닌 사람은 길의 어느 끝에서든 잠그고 연다(행동 '잠그기', '열기'). 열쇠는 쓰여도 없어지지 않는다.
    pick 을 적었으면 열쇠 없이 따기로 열 수 있다. 적지 않으면 따지 못한다.
    """

    model_config = ConfigDict(extra='forbid')

    key: uuid.UUID
    locked: bool = True
    pick: PickCheck | None = None

    @field_serializer('key')
    def key_as_text(self, key: uuid.UUID) -> str:
        """열쇠의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(key)


class RouteBar(BaseModel):
    """
    길의 빗장(#281). 길의 한쪽 끝(side)에만 있다. 그쪽에 선 사람만 열쇠 없이 걸고 푼다(행동 '잠그기', '열기').

    걸려 있으면 빗장 쪽에서는 지나가며 풀고, 반대쪽에서는 지나가지 못한다. 반대쪽에서는 부수기로만 연다.
    barred 는 테이블이 시작할 때 걸려 있는가다(기본은 안 걸림). side 는 길의 두 끝 중 하나여야 한다.
    """

    model_config = ConfigDict(extra='forbid')

    side: uuid.UUID
    barred: bool = False

    @field_serializer('side')
    def side_as_text(self, side: uuid.UUID) -> str:
        """장소의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(side)


class ForceCheck(BaseModel):
    """
    문을 부수는 판정(#281). 행동 '부수기'가 이 능력과 난이도로 굴린다. 적지 않으면 부수지 못한다.

    성공하면 자물쇠와 빗장이 부서져 열린다. 부서진 것은 고치기 전까지 다시 잠그거나 걸지 못한다.
    """

    model_config = ConfigDict(extra='forbid')

    ability: Key
    difficulty: Key | None = None


class RepairCheck(PickCheck):
    """
    부서진 문을 고치는 판정(#281). 행동 '고치기'가 이 능력과 난이도로 굴린다. 적지 않으면 고치지 못한다.

    성공하면 문이 고쳐진다. 고친 문은 열린 채다. 다시 잠그려면 잠그기를 한다.
    needs_tool 이면 고치기를 거드는 물건(공구 같은 것)이 있어야 고친다(#802). 따기와 같다.
    """


class RouteRule(BaseModel):
    """
    길 하나. 붙인 로어북의 장소 항목 둘(from_place, to_place)을 잇는다.

    two_way 면 양쪽으로 다닌다(기본). 아니면 from 에서 to 로만 간다(떨어지는 구멍, 한쪽에서만 열리는 문).
    visibility 는 플레이어가 길을 언제 아는가다(기본은 처음부터, RouteVisibility).
    숨긴 길(hidden)은 플레이어도 방장도 모른다. 숨긴 길에는 찾는 판정(find)이 있어야 하고, 다른 길에는 없다.
    travel_minutes 는 이 길로 한 칸 가는 데 걸리는 게임 안의 시간(분)이다. 양쪽이 같다. 비우면 라운드의 걸음 안에서 간다
    (옆방). 누가 이 길로 가면 다음 라운드가 열릴 때 그만큼은 흐른다(app/calendar/state.py 의 stretch_next_step).
    길의 조건(#281): cross 는 지날 때마다 굴리는 넘기 판정, lock 은 열쇠로 여는 자물쇠, bar 는 한쪽의 빗장,
    force 는 문(자물쇠와 빗장)을 부수는 판정, repair 는 부서진 문을 고치는 판정이다. 자물쇠와 넘기는 양쪽에서 같다.
    빗장, 자물쇠, 넘기 판정의 차례로 본다. force 와 repair 는 자물쇠나 빗장이 있는 길에만 적는다.
    가리키는 장소가 붙인 로어북에 있는지, 장소인지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    from_place: uuid.UUID
    to_place: uuid.UUID
    two_way: bool = True
    visibility: RouteVisibility = RouteVisibility.OPEN
    find: FindCheck | None = None
    travel_minutes: int | None = Field(default=None, ge=1, le=ROUND_MAX_MINUTES)
    cross: CrossCheck | None = None
    lock: RouteLock | None = None
    bar: RouteBar | None = None
    force: ForceCheck | None = None
    repair: RepairCheck | None = None

    @model_validator(mode='after')
    def leads_somewhere_else(self) -> 'RouteRule':
        """제자리로 돌아오는 길은 받지 않는다."""
        if self.from_place == self.to_place:
            raise ValueError('길의 두 끝이 같은 장소입니다.')
        return self

    @model_validator(mode='after')
    def bar_on_an_end(self) -> 'RouteRule':
        """빗장은 길의 두 끝 중 한쪽에 있다."""
        if self.bar is not None and self.bar.side not in (self.from_place, self.to_place):
            raise ValueError('빗장은 길의 두 끝 중 한쪽(side)에 있어야 합니다.')
        return self

    @model_validator(mode='after')
    def force_only_with_a_door(self) -> 'RouteRule':
        """부술 것(자물쇠나 빗장)이 있는 길에만 부수는 판정을 적는다."""
        if self.force is not None and self.lock is None and self.bar is None:
            raise ValueError('부수는 판정(force)은 자물쇠나 빗장이 있는 길에만 적습니다.')
        return self

    @model_validator(mode='after')
    def repair_only_with_a_door(self) -> 'RouteRule':
        """고칠 것(자물쇠나 빗장)이 있는 길에만 고치는 판정을 적는다."""
        if self.repair is not None and self.lock is None and self.bar is None:
            raise ValueError('고치는 판정(repair)은 자물쇠나 빗장이 있는 길에만 적습니다.')
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


class PlaceItem(BaseModel):
    """
    장소에 놓인 물건 한 줄. 맵의 장소 하나(place_id)에 물건 하나(entry_id)가 count 개 있다(#279).

    visibility 는 플레이어가 언제 아는가다(기본은 보임, PlaceItemVisibility). 보이는 물건은 줍기(take)로 가져간다.
    숨긴 물건에는 찾는 판정(find)이 있어야 하고, 보이는 물건에는 없다. 숨긴 길과 같다.
    장소가 맵의 장소인지, 물건이 붙인 로어북의 물건 항목인지, 판정이 룰북의 규칙에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    place_id: uuid.UUID
    entry_id: uuid.UUID
    count: int = Field(default=1, ge=1, le=ITEM_STACK_MAX)
    visibility: PlaceItemVisibility = PlaceItemVisibility.OPEN
    find: FindCheck | None = None

    @model_validator(mode='after')
    def find_only_when_hidden(self) -> 'PlaceItem':
        """숨긴 물건에만 찾는 판정이 있다. 숨긴 물건에 없으면, 보이는 물건에 있으면 거부한다."""
        hidden = self.visibility == PlaceItemVisibility.HIDDEN
        if hidden and self.find is None:
            raise ValueError('숨긴 물건에는 찾는 판정(find)이 있어야 합니다.')
        if not hidden and self.find is not None:
            raise ValueError('찾는 판정(find)은 숨긴 물건에만 적습니다.')
        return self

    @field_serializer('place_id', 'entry_id')
    def id_as_text(self, value: uuid.UUID) -> str:
        """ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(value)


def reject_duplicate_place_items(rules: list[PlaceItem]) -> list[PlaceItem]:
    """같은 장소의 같은 물건이 같은 보이기로 두 줄이면 거부한다. 한 줄에 개수로 적는다."""
    keys = [(rule.place_id, rule.entry_id, rule.visibility) for rule in rules]
    if len(set(keys)) != len(keys):
        raise ValueError('같은 장소에 같은 물건이 두 번 있습니다. 한 줄에 개수로 적습니다.')
    return rules


PlaceItems = Annotated[
    list[PlaceItem], Field(max_length=SCENARIO_MAX_PLACE_ITEMS), AfterValidator(reject_duplicate_place_items)
]


class CoverRule(BaseModel):
    """
    장소 하나의 커버(#276 의 커버 세이브). 그 장소(place_id)에 숨을 곳이 얼마나 좋은지(cover, 1~10)다.

    그 장소에서 엄폐한(cover 행동) 앉은 사람은 그 라운드에 이 값으로 커버 세이브를 받는다(app/rounds/covers.py).
    세이브 방식의 룰북에서만 쓰인다. 장소가 맵의 장소인지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    place_id: uuid.UUID
    cover: CombatNumber

    @field_serializer('place_id')
    def id_as_text(self, value: uuid.UUID) -> str:
        """ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(value)


def reject_duplicate_covers(rules: list[CoverRule]) -> list[CoverRule]:
    """같은 장소의 커버가 둘이면 거부한다. 어느 값으로 숨는지 가를 수 없다."""
    places = [rule.place_id for rule in rules]
    if len(set(places)) != len(places):
        raise ValueError('같은 장소의 커버가 두 번 있습니다.')
    return rules


Covers = Annotated[list[CoverRule], Field(max_length=SCENARIO_MAX_COVERS), AfterValidator(reject_duplicate_covers)]


class WanderMonster(BaseModel):
    """
    무작위 조우 표의 한 줄(#283). 붙인 도감의 몬스터 하나(monster_id)가 count 마리 나온다.

    weight 는 이 줄이 뽑힐 몫이다. 표의 몫을 모두 더한 것 가운데 이 줄의 몫만큼 뽑힌다.
    surprise 는 조우와 같다. 쉬는 중에 나오면 적은 것과 상관없이 몬스터가 기습한다.
    몬스터가 시트를 적은 몬스터인지는 게시할 때 본다(조우와 같다).
    """

    model_config = ConfigDict(extra='forbid')

    monster_id: uuid.UUID
    count: int = Field(default=1, ge=1, le=ENCOUNTER_MAX_COUNT)
    weight: int = Field(default=1, ge=1, le=WANDER_MAX_WEIGHT)
    surprise: Surprise = Surprise.NONE

    @field_serializer('monster_id')
    def id_as_text(self, value: uuid.UUID) -> str:
        """ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(value)


def reject_duplicate_wander_monsters(monsters: list[WanderMonster]) -> list[WanderMonster]:
    """한 표에 같은 몬스터가 두 줄이면 거부한다. 한 줄에 마리 수와 몫으로 적는다."""
    ids = [monster.monster_id for monster in monsters]
    if len(set(ids)) != len(ids):
        raise ValueError('한 조우 표에 같은 몬스터가 두 번 있습니다.')
    return monsters


def reject_duplicate_times(times: list[TimeOfDay]) -> list[TimeOfDay]:
    """같은 때를 두 번 적으면 거부한다."""
    if len(set(times)) != len(times):
        raise ValueError('같은 때가 두 번 있습니다.')
    return times


WanderMonsters = Annotated[
    list[WanderMonster], Field(max_length=WANDER_MAX_MONSTERS), AfterValidator(reject_duplicate_wander_monsters)
]
TimesOfDay = Annotated[list[TimeOfDay], Field(max_length=len(TimeOfDay)), AfterValidator(reject_duplicate_times)]


class WanderTable(BaseModel):
    """
    무작위 조우 표 하나(#283). 장소(place_id)에서 하루의 때(times)에 쓰는 표다.

    걸리는 시간이 있는 길을 한 칸 와서 그 장소에 닿거나, 그 장소에서 길게 쉬면 엔진이 한 번 굴린다.
    chance(0~100)% 로 조우가 나고, 나면 몬스터의 줄 하나를 몫(weight)대로 뽑아 그 장소에 놓는다.
    place_id 를 비우면 판의 기본 표다. 표를 하나도 적지 않은 장소에서 쓴다. 기본 표도 없으면 조우가 없다.
    times 를 비우면 언제나 쓴다. 한 장소(또는 기본 표)의 표들은 때가 겹치지 않는다. 때가 맞는 표가 없으면 조우가 없다.
    chance 가 0 이면 조우가 나지 않는 표다(마을처럼 안전한 곳). 그때는 몬스터를 적지 않는다.
    장소가 맵의 장소인지, 몬스터가 시트를 적은 몬스터인지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    place_id: uuid.UUID | None = None
    times: TimesOfDay = []
    chance: int = Field(ge=0, le=100)
    monsters: WanderMonsters = []

    @model_validator(mode='after')
    def monsters_only_with_a_chance(self) -> 'WanderTable':
        """조우가 날 수 있으면 나올 몬스터가 있어야 하고, 나지 않으면 몬스터를 적지 않는다."""
        if self.chance > 0 and not self.monsters:
            raise ValueError('조우가 날 확률(chance)이 있으면 나올 몬스터(monsters)를 적습니다.')
        if self.chance == 0 and self.monsters:
            raise ValueError('조우가 나지 않는 표(chance 0)에는 몬스터를 적지 않습니다.')
        return self

    @field_serializer('place_id')
    def place_as_text(self, value: uuid.UUID | None) -> str | None:
        """장소의 ID 를 글자로 꺼낸다. 기본 표면 None 이다."""
        return None if value is None else str(value)


def times_overlap(one: WanderTable, other: WanderTable) -> bool:
    """두 표의 때가 겹치는가. 비운 때는 언제나라서 무엇과도 겹친다."""
    return not one.times or not other.times or bool(set(one.times) & set(other.times))


def reject_overlapping_wanders(tables: list[WanderTable]) -> list[WanderTable]:
    """같은 장소(또는 기본 표)의 두 표가 같은 때를 가지면 거부한다. 어느 표로 굴릴지 가를 수 없다."""
    for index, one in enumerate(tables):
        rest = tables[index + 1 :]
        if any(other.place_id == one.place_id and times_overlap(one, other) for other in rest):
            raise ValueError('같은 장소의 조우 표 둘이 같은 때를 씁니다.')
    return tables


Wanders = Annotated[
    list[WanderTable], Field(max_length=SCENARIO_MAX_WANDERS), AfterValidator(reject_overlapping_wanders)
]


QuestRules = Annotated[
    list[QuestRule], Field(max_length=SCENARIO_MAX_QUEST_RULES), AfterValidator(reject_duplicate_quests)
]


class MoveEffect(BaseModel):
    """
    사건의 효과 하나: 캐릭터들을 맵의 한 장소(to_place)로 옮긴다(#367).

    from_place 가 없으면 죽지 않은 캐릭터 모두를, 있으면 그 장소에 서 있던 죽지 않은 캐릭터만 옮긴다.
    쓰러진 캐릭터도 옮겨진다(끌려간다). 두 장소가 맵의 장소인지는 게시할 때 본다. 길로 이어져 있지 않아도 된다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[HappeningEffectKind.MOVE]
    to_place: uuid.UUID
    from_place: uuid.UUID | None = None

    @model_validator(mode='after')
    def leads_somewhere_else(self) -> 'MoveEffect':
        """그 자리로 옮기는 것은 뜻이 없다."""
        if self.from_place == self.to_place:
            raise ValueError('옮기는 곳과 옮겨지는 사람이 선 곳이 같습니다.')
        return self

    @field_serializer('to_place', 'from_place')
    def place_as_text(self, place: uuid.UUID | None) -> str | None:
        """장소의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return None if place is None else str(place)


class MoveNpcEffect(BaseModel):
    """
    사건의 효과 하나: 인물(NPC) 하나(npc)를 맵의 한 장소(to_place)로 옮긴다(#282).

    인물은 붙인 로어북의 인물 항목이다. 자리를 적지 않은 인물이면 그 뒤로 자리가 있는 인물이 된다.
    쓰러진 인물도 옮겨진다. 죽은 인물은 그 자리에 남는다. 길로 이어져 있지 않아도 된다.
    인물이 인물 항목인지, 장소가 맵의 장소인지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    kind: Literal[HappeningEffectKind.MOVE_NPC]
    npc: uuid.UUID
    to_place: uuid.UUID

    @field_serializer('npc', 'to_place')
    def id_as_text(self, value: uuid.UUID) -> str:
        """ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(value)


class RouteEnds(BaseModel):
    """
    사건의 효과가 다루는 길 하나(#281). 길의 두 끝이다. 방향은 보지 않는다(문은 길의 어느 끝에서든 같다).

    판의 길 중 두 끝이 같은 것이 그 길이다. 그런 길이 있고 문(자물쇠나 빗장)이 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    from_place: uuid.UUID
    to_place: uuid.UUID

    @model_validator(mode='after')
    def two_ends(self) -> 'RouteEnds':
        """제자리로 오는 길은 없다."""
        if self.from_place == self.to_place:
            raise ValueError('길의 두 끝이 같습니다.')
        return self

    @field_serializer('from_place', 'to_place')
    def end_as_text(self, place: uuid.UUID) -> str:
        """장소의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(place)


class RouteDoorEffect(RouteEnds):
    """
    사건의 효과 하나: 길 하나의 문을 잠그거나(lock_route) 연다(unlock_route, #281).

    판이 하는 일이라 열쇠도 서 있는 쪽도 보지 않는다. NPC 나 몬스터가 문을 잠그고 여는 것을 이것으로 적는다.
    device 를 적으면 그 장치만, 비우면 그 문의 장치 모두(자물쇠, 빗장)다. 적은 장치가 그 길에 있는지는 게시할 때 본다.
    부서진 문은 잠그지 못한다(고치는 효과를 먼저 적는다). 이미 그렇게 되어 있는 장치는 그대로다.
    """

    kind: Literal[HappeningEffectKind.LOCK_ROUTE, HappeningEffectKind.UNLOCK_ROUTE]
    device: DoorDevice | None = None


class RepairRouteEffect(RouteEnds):
    """
    사건의 효과 하나: 길 하나의 부서진 문을 고친다(repair_route, #281).

    고친 문은 열린 채다. 다시 잠그려면 뒤에 잠그는 효과(lock_route)를 잇는다. 부서지지 않은 문은 그대로다.
    """

    kind: Literal[HappeningEffectKind.REPAIR_ROUTE]


HappeningEffect = Annotated[
    MoveEffect | MoveNpcEffect | RouteDoorEffect | RepairRouteEffect, Field(discriminator='kind')
]
HappeningEffects = Annotated[list[HappeningEffect], Field(min_length=1, max_length=HAPPENING_MAX_EFFECTS)]


class HappeningRule(BaseModel):
    """
    사건 규칙 하나(#367). 조건(when)이 채워지면 한 번 일어나 효과(effects)를 낸다. 붙인 로어북의 사건 항목 하나다.

    조건의 모양과 종류는 퀘스트의 것과 같다(QuestCondition). 하나 이상 적는다.
    match 는 모두(all)인지 하나라도(any)인지다.
    가져가기(consume)는 쓰지 않는다. 사건은 물건을 받지 않는다. 다른 퀘스트를 보는 조건(퀘스트 잇기)과
    물건을 잃는 조건(lose_item)도 쓸 수 있다. 같은 사건 항목이 퀘스트이기도 해도 된다(이름만 함께 쓴다).
    라운드가 닫힐 때 퀘스트를 본 뒤에 엔진이 본다. 일어난 것은 테이블에 적어 다시 일어나지 않는다
    (app/rounds/happenings.py).
    효과는 캐릭터 옮기기(MoveEffect)와 인물 옮기기(MoveNpcEffect, #282)다. kind 로 가른다.
    가리키는 사건과 장소, 옮기는 인물이 붙인 로어북에 있는지는 게시할 때 본다.
    """

    model_config = ConfigDict(extra='forbid')

    entry_id: uuid.UUID
    when: Annotated[QuestConditions, Field(min_length=1)]
    match: QuestMatch = QuestMatch.ALL
    effects: HappeningEffects

    @model_validator(mode='after')
    def nothing_consumed(self) -> 'HappeningRule':
        """사건은 물건을 가져가지 않는다. 가져가는 것은 퀘스트를 이룰 때다."""
        if any(condition.consume for condition in self.when):
            raise ValueError('consume 은 퀘스트의 이루는 조건(conditions)에만 적습니다.')
        return self

    @field_serializer('entry_id')
    def entry_id_as_text(self, entry_id: uuid.UUID) -> str:
        """항목의 ID 를 글자로 꺼낸다. 시나리오의 문서 칸(JSONB)에 그대로 적을 수 있어야 한다."""
        return str(entry_id)


def reject_duplicate_happenings(rules: list[HappeningRule]) -> list[HappeningRule]:
    """같은 사건의 규칙이 두 번 있으면 거부한다. 일어났다고 적는 것이 사건 항목 하나마다다."""
    entry_ids = [rule.entry_id for rule in rules]
    if len(set(entry_ids)) != len(entry_ids):
        raise ValueError('같은 사건의 사건 규칙이 두 번 있습니다.')
    return rules


Happenings = Annotated[
    list[HappeningRule], Field(max_length=SCENARIO_MAX_HAPPENINGS), AfterValidator(reject_duplicate_happenings)
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
    default_sheet: CharacterSheet | None = None
    npc_sheets: NpcSheets = []
    default_npc_sheet: Sheet | None = None
    monster_sheets: MonsterSheets = []
    encounters: Encounters = []
    items: ItemRules = []
    starting_items: StartingItems = []
    # 화폐(#278). 비우면 돈이 없는 시나리오다
    currency: Currency | None = None
    quests: QuestRules = []
    start_place: uuid.UUID | None = None
    routes: Routes = []
    landmarks: Landmarks = []
    place_items: PlaceItems = []
    # 장소마다의 커버(#276). 세이브 방식의 룰북에서 엄폐할 때 쓴다
    covers: Covers = []
    # 무작위 조우 표(#283). 길을 오거나 길게 쉬면 엔진이 굴린다
    wanders: Wanders = []
    happenings: Happenings = []
    npc_places: NpcPlaces = []
    player_made_hp: PlayerMadeHp | None = None
    # 주사위로 정한 점수를 방장이 다시 굴리게 해 줄 수 있는가. 안 보내면 안 된다
    reroll_allowed: bool = False
    # 추천 문체. 테이블의 방장이 고르지 않으면 이것으로 서술한다. 안 보내면 정통이다
    narration_style: NarrationStyle = DEFAULT_NARRATION_STYLE
    # 추천 서술 모델의 이름표. 반드시 보낸다. 서비스 중인 모델이어야 한다(app/assets/scenarios/recommended_model.py)
    narration_model: Slug
    # 게임 안의 시계. 안 보내면 1일째 8시에 시작하고 라운드 하나에 10분이 흐른다
    clock: Clock = DEFAULT_CLOCK


class ScenarioUpdate(AssetUpdate):
    """
    시나리오를 고칠 때 받는 값. 보낸 칸만 바꾼다.

    rulebook_id, world_id, default_sheet, default_npc_sheet, player_made_hp, start_place, currency 는
    null 을 보내면 비운다.
    보내지 않으면 그대로 둔다.
    lorebook_ids, bestiary_ids, openings, pregens, npc_sheets, monster_sheets, encounters, items, starting_items,
    quests, routes, landmarks, place_items, covers, wanders, happenings, npc_places, character_modes 는
    보낸 목록으로 통째로 바꾼다.
    character_modes 말고는 전부 없애려면 빈 목록을 보낸다. character_modes 는 비울 수 없다.
    recommended_players 는 최소와 최대를 함께 보낸다. clock 은 셋을 함께 보낸다.
    """

    clearable: ClassVar[frozenset[str]] = frozenset(
        {'rulebook_id', 'world_id', 'default_sheet', 'default_npc_sheet', 'player_made_hp', 'start_place', 'currency'}
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
    default_sheet: CharacterSheet | None = None
    npc_sheets: NpcSheets | None = None
    default_npc_sheet: Sheet | None = None
    monster_sheets: MonsterSheets | None = None
    encounters: Encounters | None = None
    items: ItemRules | None = None
    starting_items: StartingItems | None = None
    currency: Currency | None = None
    quests: QuestRules | None = None
    start_place: uuid.UUID | None = None
    routes: Routes | None = None
    landmarks: Landmarks | None = None
    place_items: PlaceItems | None = None
    covers: Covers | None = None
    wanders: Wanders | None = None
    happenings: Happenings | None = None
    npc_places: NpcPlaces | None = None
    player_made_hp: PlayerMadeHp | None = None
    reroll_allowed: bool | None = None
    narration_style: NarrationStyle | None = None
    # 비울 수 없다. 보내면 서비스 중인 모델이어야 한다
    narration_model: Slug | None = None
    clock: Clock | None = None


class ModelStatusOut(BaseModel):
    """
    작성자 화면에 보이는 추천 서술 모델의 상태(app/assets/scenarios/recommended_model.py).

    state 가 ok 가 아니면 화면이 작성자에게 알린다. replacement 는 지금 테이블을 만들면 대신 쓸 모델이다.
    가격 목록을 받지 못했거나 같은 회사에 대신할 모델이 없으면 null 이다. 그때는 방장이 모델을 고른다.
    """

    state: ModelState
    retires_on: date | None
    replacement: str | None


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
    default_sheet: CharacterSheet | None
    npc_sheets: list[NpcSheet]
    default_npc_sheet: Sheet | None
    monster_sheets: list[MonsterSheet]
    encounters: list[Encounter]
    items: list[ItemRule]
    starting_items: list[ItemStack]
    currency: Currency | None
    quests: list[QuestRule]
    start_place: uuid.UUID | None
    routes: list[RouteRule]
    landmarks: list[uuid.UUID]
    place_items: list[PlaceItem]
    covers: list[CoverRule]
    wanders: list[WanderTable]
    happenings: list[HappeningRule]
    npc_places: list[NpcPlace]
    player_made_hp: PlayerMadeHp | None
    reroll_allowed: bool
    narration_style: NarrationStyle
    # 이 규칙 전에 만든 시나리오만 비어 있다
    narration_model: str | None
    # 추천 서술 모델의 상태. 추천 모델이 없으면 null
    narration_model_status: ModelStatusOut | None
    clock: Clock


VersionNote = Annotated[str, StringConstraints(max_length=VERSION_NOTE_MAX_LENGTH)]


class VersionCreate(BaseModel):
    """
    게시할 때 받는 값. 변경 내용만 적는다. 비워도 된다.

    판의 내용은 받지 않는다. 서버가 초안에서 직접 읽어 굳힌다.
    """

    model_config = ConfigDict(extra='forbid')

    note: VersionNote = ''


class PublishCheck(BaseModel):
    """
    지금 게시하면 막히는 이유(#428). 게시하지 않고 미리 본다. 판을 만들지 않는다.

    problems 는 게시가 409 로 돌려주는 것과 같은 이름들이다. 비어 있으면 지금 게시할 수 있다(ready).
    """

    ready: bool
    problems: list[str]


class VersionSummary(BaseModel):
    """판의 목록에 싣는 값. 굳힌 내용은 싣지 않는다."""

    id: uuid.UUID
    number: int
    note: str
    created_at: datetime


class VersionDetail(VersionSummary):
    """만든 사람이 자기 판을 볼 때의 값. 굳힌 내용까지 싣는다. GM 전용 글이 들어 있다."""

    snapshot: Snapshot
