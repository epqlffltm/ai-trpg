# trpg-server/app/assets/scenarios/publishing.py

"""
시나리오를 게시한다. 초안의 지금 내용을 판으로 굳힌다.

게시는 "굳히기"다. 남에게 보이게 하는 것(공개)은 따로다. 판은 만든 사람만 본다.
SQL 을 모른다. 판을 읽고 쓰는 일은 repository.py 에 맡긴다.
판을 고치거나 지우는 함수는 없다. 고칠 것이 있으면 초안을 고치고 새 판을 낸다.
"""

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.bestiaries import repository as monsters
from app.assets.bestiaries.models import Bestiary, Monster
from app.assets.lorebooks import repository as entries
from app.assets.models import (
    PLAYER_MADE_MODES,
    QUEST_LINK_CONDITIONS,
    CharacterMode,
    Lorebook,
    LoreEntry,
    LoreKind,
    QuestConditionKind,
    Rating,
    Rulebook,
    Scenario,
    ScenarioVersion,
    World,
)
from app.assets.ratings import ALL_AGES_ONLY, require_rating
from app.assets.scenarios import repository
from app.assets.scenarios.schemas import (
    CoverRule,
    CrossCheck,
    Encounter,
    FindCheck,
    ForceCheck,
    HappeningEffect,
    HappeningRule,
    ItemRule,
    ItemStack,
    ItemThrow,
    MonsterAttack,
    MonsterSheet,
    MoveEffect,
    MoveNpcEffect,
    NpcPlace,
    NpcSheet,
    PickCheck,
    PlaceItem,
    Pregen,
    QuestCondition,
    QuestRule,
    RepairRouteEffect,
    RouteDoorEffect,
    RouteRule,
    VersionCreate,
    WanderTable,
)
from app.assets.scenarios.snapshot import (
    AttackSnapshot,
    CarriedItemSnapshot,
    MonsterSnapshot,
    NaturalArmorSnapshot,
    build_snapshot,
    snapshot_monster,
    wear_fault,
)
from app.assets.service import AssetNotFoundError
from app.engine.action import DoorDevice
from app.engine.check import find_ability, find_difficulty
from app.engine.health import find_magnitude
from app.engine.injury import find_injury
from app.engine.item_aids import AidAct
from app.engine.item_effects import EffectKind
from app.engine.resources import find_resource, holds
from app.engine.ruleset import Healing, ResourceHolder, Ruleset
from app.engine.sheet import CharacterSheet, Sheet, fits, knows_only, resists_only_known


class Problem(enum.StrEnum):
    """게시할 수 없는 이유."""

    # 룰북이 없다. 진행 방식이 없으면 테이블이 성립하지 않는다
    RULEBOOK_MISSING = 'rulebook_missing'
    # 스타팅이 하나도 없다. 첫 장면은 제작자가 정한다
    OPENING_MISSING = 'opening_missing'
    # 시트가 없는 프리젠이 있다. 판 안의 프리젠은 모두 숫자를 갖는다
    PREGEN_SHEET_MISSING = 'pregen_sheet_missing'
    # 룰북의 규칙에 맞지 않는 시트를 가진 프리젠이 있다. 능력치가 빠졌거나 남거나, 점수가 범위 밖이다
    PREGEN_SHEET_INVALID = 'pregen_sheet_invalid'
    # 캐릭터를 직접 만들 수 있게 했는데 기본 시트가 없다. 그 사람이 받을 숫자가 없다
    DEFAULT_SHEET_MISSING = 'default_sheet_missing'
    # 기본 시트가 룰북의 규칙에 맞지 않는다
    DEFAULT_SHEET_INVALID = 'default_sheet_invalid'
    # 기본 시트나 프리젠의 시트가 아는 기술(skills)이 룰북의 기술(rules.skills)에 없다(#805)
    SHEET_SKILL_INVALID = 'sheet_skill_invalid'
    # 프리젠만 허용했는데 프리젠이 추천 인원의 최소보다 적다. 그 인원이 앉을 수 없다
    PREGENS_TOO_FEW = 'pregens_too_few'
    # 플레이어가 능력치를 정하는 방식을 허용했는데 최대 HP 를 구하는 값(기준값과 상한)이 없다
    PLAYER_MADE_HP_MISSING = 'player_made_hp_missing'
    # 점수제를 허용했는데 룰북의 규칙에 점수제가 없다. 총점도 값표도 없어서 아무도 캐릭터를 만들 수 없다
    POINT_BUY_MISSING = 'point_buy_missing'
    # 주사위로 정하는 방식을 허용했는데 룰북의 규칙에 굴리는 법이 없다
    SCORE_ROLL_MISSING = 'score_roll_missing'
    # 붙인 로어북에 없는 항목을 가리키는 NPC 시트가 있다. 항목을 지웠거나 로어북을 뗐다
    NPC_SHEET_ENTRY_MISSING = 'npc_sheet_entry_missing'
    # 인물이 아닌 항목(장소, 물건 …)을 가리키는 NPC 시트가 있다
    NPC_SHEET_NOT_PERSON = 'npc_sheet_not_person'
    # 룰북의 규칙에 맞지 않는 NPC 시트가 있다
    NPC_SHEET_INVALID = 'npc_sheet_invalid'
    # NPC 시트의 공격의 능력치, 난이도, 양의 등급이 룰북의 규칙에 없다(#487)
    NPC_ATTACK_INVALID = 'npc_attack_invalid'
    # 시트가 없는 인물 항목이 있는데 기본 NPC 시트가 없다. 그 인물이 받을 숫자가 없다
    DEFAULT_NPC_SHEET_MISSING = 'default_npc_sheet_missing'
    # 기본 NPC 시트가 룰북의 규칙에 맞지 않는다
    DEFAULT_NPC_SHEET_INVALID = 'default_npc_sheet_invalid'
    # 붙인 로어북에 없는 항목을 가리키는 아이템 규칙이나 소지품(시작 소지품, 프리젠의 소지품, 퀘스트의 보상,
    # 몬스터의 드롭)이 있다
    ITEM_ENTRY_MISSING = 'item_entry_missing'
    # 물건이 아닌 항목(인물, 장소 …)을 가리키는 아이템 규칙이나 소지품이 있다
    ITEM_NOT_ITEM = 'item_not_item'
    # 룰북의 규칙에 없는 등급을 회복이나 피해의 효과(effects 의 heal, damage, #800)로 적은 소모품이 있다
    ITEM_MAGNITUDE_MISSING = 'item_magnitude_missing'
    # 자물쇠 물건의 따는 판정의 능력치나 난이도가 룰북의 규칙에 없다(#281)
    ITEM_LOCK_INVALID = 'item_lock_invalid'
    # 소모품이 푸는 부상(effects 의 cure)이 룰북의 규칙에 없거나, 풀 수 없는 결손이다(#277)
    ITEM_CURE_INVALID = 'item_cure_invalid'
    # 소모품이 입히는 부상(effects 의 injure)이 룰북의 규칙에 없다(#800)
    ITEM_INJURE_INVALID = 'item_injure_invalid'
    # 소모품이 맞추는 수치(effects 의 adjust)가 룰북의 수치(resources)에 없다(#804)
    ITEM_RESOURCE_INVALID = 'item_resource_invalid'
    # 던지는 소모품의 판정의 능력치나 난이도나 피해의 등급이 룰북의 규칙에 없다(#277)
    ITEM_THROW_INVALID = 'item_throw_invalid'
    # 붙인 로어북에 없는 항목을 가리키는 퀘스트 규칙이 있다
    QUEST_ENTRY_MISSING = 'quest_entry_missing'
    # 사건이 아닌 항목(인물, 물건 …)을 가리키는 퀘스트 규칙이 있다
    QUEST_NOT_EVENT = 'quest_not_event'
    # 퀘스트의 조건이 가리키는 것이 없다. 붙인 로어북에 없는 항목이거나, 시트를 적지 않은 몬스터다
    QUEST_CONDITION_MISSING = 'quest_condition_missing'
    # 퀘스트의 조건이 맞지 않는 종류를 가리킨다(장소에 닿기인데 물건 항목 …)
    QUEST_CONDITION_INVALID = 'quest_condition_invalid'
    # 퀘스트의 조건을 이룰 수 없다. 맵에 없는 장소이거나, 판에 놓인 마리보다 많이 쓰러뜨려야 하거나,
    # 이루는 조건이 없어 성공하지 않는 퀘스트의 성공을 기다린다
    QUEST_CONDITION_IMPOSSIBLE = 'quest_condition_impossible'
    # 퀘스트의 드러나는 조건이 돌고 돈다(가가 드러나려면 나가 끝나야 하고, 나가 드러나려면 가가 끝나야 한다)
    QUEST_REVEAL_CYCLE = 'quest_reveal_cycle'
    # 붙인 로어북에 없는 항목을 가리키는 시작 장소, 길, 명소가 있다
    MAP_PLACE_MISSING = 'map_place_missing'
    # 장소가 아닌 항목(인물, 물건 …)을 가리키는 시작 장소, 길, 명소가 있다
    MAP_NOT_PLACE = 'map_not_place'
    # 길이나 명소가 있는데 시작 장소가 없다. 캐릭터가 설 곳이 없다
    MAP_START_MISSING = 'map_start_missing'
    # 숨긴 길을 찾는 판정의 능력치나 난이도가 룰북의 규칙에 없다
    ROUTE_FIND_INVALID = 'route_find_invalid'
    # 길을 넘는 판정의 능력치, 난이도, 실패의 피해(양의 등급)가 룰북의 규칙에 없다(#281)
    ROUTE_CROSS_INVALID = 'route_cross_invalid'
    # 열쇠 하나를 두 자물쇠(길의 자물쇠, 자물쇠 물건)에 적었다. 열쇠 하나는 자물쇠 하나만 연다(#281)
    ROUTE_KEY_REPEATED = 'route_key_repeated'
    # 자물쇠를 따는 판정, 문을 부수는 판정, 고치는 판정의 능력치나 난이도가 룰북의 규칙에 없다(#281)
    ROUTE_OPEN_INVALID = 'route_open_invalid'
    # 도구가 있어야 따거나 고치는 문(needs_tool)이 있는데, 그 행동을 거드는 물건(아이템 규칙의 aids)이 없다(#802)
    ROUTE_TOOL_MISSING = 'route_tool_missing'
    # 놓인 물건이 맵에 없는 장소(시작 장소, 길의 끝, 명소가 아닌 곳)에 있다. 아무도 그곳에 설 수 없다
    PLACE_ITEM_OFF_MAP = 'place_item_off_map'
    # 숨긴 물건을 찾는 판정의 능력치나 난이도가 룰북의 규칙에 없다
    PLACE_ITEM_FIND_INVALID = 'place_item_find_invalid'
    # 커버의 장소가 맵의 장소가 아니다(시작 장소, 길의 끝, 명소). 맵에 없는 장소에는 아무도 서지 못한다(#276)
    COVER_OFF_MAP = 'cover_off_map'
    # 무작위 조우 표의 장소가 맵의 장소가 아니거나, 맵(시작 장소)이 없는데 조우 표가 있다(#283)
    WANDER_OFF_MAP = 'wander_off_map'
    # 시트를 적지 않은 몬스터를 가리키는 무작위 조우 표가 있다. 판에 들어가지 않는 몬스터라 숫자가 없다(#283)
    WANDER_MONSTER_MISSING = 'wander_monster_missing'
    # 붙인 로어북에 없는 항목을 가리키는 사건 규칙이 있다(#367)
    HAPPENING_ENTRY_MISSING = 'happening_entry_missing'
    # 사건이 아닌 항목(인물, 물건 …)을 가리키는 사건 규칙이 있다
    HAPPENING_NOT_EVENT = 'happening_not_event'
    # 사건의 조건이 가리키는 것이 없다. 퀘스트의 조건과 같은 까닭이다(quest_condition_missing)
    HAPPENING_CONDITION_MISSING = 'happening_condition_missing'
    # 사건의 조건이 맞지 않는 종류를 가리킨다
    HAPPENING_CONDITION_INVALID = 'happening_condition_invalid'
    # 사건의 조건을 이룰 수 없다. 퀘스트의 조건과 같은 까닭이다(quest_condition_impossible)
    HAPPENING_CONDITION_IMPOSSIBLE = 'happening_condition_impossible'
    # 사건이 맵에 없는 장소(시작 장소, 길의 끝, 명소가 아닌 곳)로 옮기거나 그런 장소에 선 사람을 옮긴다
    HAPPENING_PLACE_OFF_MAP = 'happening_place_off_map'
    # 붙인 로어북의 인물 항목이 아닌 것(없는 항목, 장소, 물건 …)을 옮기는 사건이 있다(move_npc, #282)
    HAPPENING_NPC_NOT_PERSON = 'happening_npc_not_person'
    # 문을 다루는 사건의 효과(#281)가 판에 없는 길, 문(자물쇠나 빗장)이 없는 길, 그 길에 없는 장치를 가리킨다
    HAPPENING_ROUTE_INVALID = 'happening_route_invalid'
    # 붙인 로어북의 인물 항목이 아닌 것(없는 항목, 장소, 물건 …)의 자리가 있다(#282)
    NPC_PLACE_NOT_PERSON = 'npc_place_not_person'
    # 인물의 자리가 맵에 없는 장소(시작 장소, 길의 끝, 명소가 아닌 곳)다. 아무도 그 인물을 만날 수 없다
    NPC_PLACE_OFF_MAP = 'npc_place_off_map'
    # 붙인 도감에 없는 몬스터를 가리키는 몬스터 시트가 있다. 몬스터를 지웠거나 도감을 뗐다
    MONSTER_SHEET_MISSING = 'monster_sheet_missing'
    # 룰북의 규칙에 맞지 않는 몬스터 시트가 있다
    MONSTER_SHEET_INVALID = 'monster_sheet_invalid'
    # 붙인 로어북에 없는 항목을 가리키는 조우가 있다
    ENCOUNTER_PLACE_MISSING = 'encounter_place_missing'
    # 장소가 아닌 항목(인물, 물건 …)을 가리키는 조우가 있다
    ENCOUNTER_NOT_PLACE = 'encounter_not_place'
    # 시트를 적지 않은 몬스터를 가리키는 조우가 있다. 판에 들어가지 않는 몬스터라 숫자가 없다
    ENCOUNTER_MONSTER_MISSING = 'encounter_monster_missing'
    # 조우가 있는데 시작 장소가 없다. 맵이 없는 시나리오에는 몬스터를 둘 곳이 없다
    ENCOUNTER_MAP_MISSING = 'encounter_map_missing'
    # 몬스터의 공격의 능력치, 난이도, 양의 등급이 룰북의 규칙에 없다
    MONSTER_ATTACK_INVALID = 'monster_attack_invalid'
    # 몬스터 시트의 면역이나 약함(immune, vulnerable)의 성질이 룰북의 성질(rules.natures)에 없다(#886)
    MONSTER_NATURE_INVALID = 'monster_nature_invalid'
    # 저항(기본 시트, 프리젠의 시트, NPC 시트, 아이템 규칙의 resistances)이나 수치를 내리는 물건의 효과의 성질이
    # 룰북의 성질(rules.natures)에 없다(#886 ②)
    NATURE_INVALID = 'nature_invalid'
    # 네임드 몹이 두 마리 이상 놓인다. 조우 한 줄에 둘 이상이거나, 두 줄 이상에 나온다
    UNIQUE_MONSTER_REPEATED = 'unique_monster_repeated'
    # 돈을 쓰는 칸(물건의 값, 상인, 프리젠의 돈, 퀘스트의 돈의 보상)이 있는데 화폐가 없다(#278)
    CURRENCY_MISSING = 'currency_missing'
    # 아이템 규칙의 장비의 칸(slots)이 룰북의 규칙에 없다(#276)
    ITEM_SLOT_INVALID = 'item_slot_invalid'
    # 시작할 때의 착용(wear)이 틀렸다. 그 물건의 칸이 아니거나, 차지하는 칸의 수와 다르거나, 두 줄이 한 칸에 겹친다
    STARTING_WEAR_INVALID = 'starting_wear_invalid'
    # NPC 나 몬스터의 장비가 착용한 칸(wear)이 틀렸다. 시작할 때의 착용과 같은 검사다(#276)
    CARRIED_WEAR_INVALID = 'carried_wear_invalid'
    # 몬스터의 타고난 방어(natural_armor)의 부위가 룰북의 칸에 없다(#276)
    NATURAL_ARMOR_INVALID = 'natural_armor_invalid'
    # NPC 나 몬스터의 공격의 무기(weapon)가 착용한 장비가 아니거나 공격 보정이 없는 물건이다(#276)
    ATTACK_WEAPON_INVALID = 'attack_weapon_invalid'


class ScenarioNotReadyError(Exception):
    """
    시나리오가 게시할 조건을 갖추지 못했다.

    problems 는 갖추지 못한 조건 전부다. 하나씩 고치고 다시 시도하지 않게 한 번에 알려 준다.
    """

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__()
        self.problems = problems


@dataclass
class Parts:
    """시나리오가 가리키는 자산들. 게시할 때 한 번 읽어서, 조건을 검사하고 판에 굳히는 데 함께 쓴다."""

    rulebook: Rulebook | None
    world: World | None
    # 로어북과 그 항목들
    lorebooks: list[tuple[Lorebook, list[LoreEntry]]]
    # 몬스터 도감과 그 몬스터들
    bestiaries: list[tuple[Bestiary, list[Monster]]]


async def load_parts(session: AsyncSession, owner_id: uuid.UUID, scenario: Scenario) -> Parts:
    """시나리오가 가리키는 자산들을 읽는다."""
    rulebook = None
    if scenario.rulebook_id is not None:
        rulebook = await assets.get_owned(session, Rulebook, owner_id, scenario.rulebook_id)

    world = None
    if scenario.world_id is not None:
        world = await assets.get_owned(session, World, owner_id, scenario.world_id)

    lorebooks = []
    for lorebook_id in scenario.lorebook_ids:
        lorebook = await assets.get_owned(session, Lorebook, owner_id, lorebook_id)
        lorebooks.append((lorebook, await entries.list_entries(session, lorebook_id)))

    bestiaries = []
    for bestiary_id in scenario.bestiary_ids:
        bestiary = await assets.get_owned(session, Bestiary, owner_id, bestiary_id)
        bestiaries.append((bestiary, await monsters.list_monsters(session, bestiary_id)))

    return Parts(rulebook=rulebook, world=world, lorebooks=lorebooks, bestiaries=bestiaries)


def read_ruleset(rulebook: Rulebook | None) -> Ruleset | None:
    """룰북의 규칙을 읽는다. 룰북이 없으면 None 이다."""
    if rulebook is None:
        return None
    return Ruleset.model_validate(rulebook.rules)


def read_pregen_sheets(scenario: Scenario) -> list[CharacterSheet | None]:
    """프리젠들의 시트를 읽는다. 시트가 없는 프리젠의 자리는 None 이다."""
    documents = [pregen.get('sheet') for pregen in scenario.pregens]
    return [CharacterSheet.model_validate(document) if document else None for document in documents]


def find_sheet_skill_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    기본 시트와 프리젠의 시트가 아는 기술이 룰북의 기술인지 본다(#805). 여럿 틀려도 한 번만 적는다.

    룰북이 없으면 볼 수 없다.
    """
    if ruleset is None:
        return []
    sheets = character_sheets(scenario)
    return [Problem.SHEET_SKILL_INVALID] if any(not knows_only(ruleset, sheet) for sheet in sheets) else []


def find_pregen_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    프리젠의 시트에서 문제를 찾는다. 프리젠이 여럿 틀려도 같은 문제는 한 번만 적는다.

    룰북이 없으면 규칙에 맞는지는 볼 수 없다. 그때는 시트가 있는지만 본다.
    프리젠을 허용하지 않아도 본다. 판 안의 프리젠은 어느 것이든 시트가 있어야 판을 읽는 쪽이 단순하다.
    """
    sheets = read_pregen_sheets(scenario)
    problems = []
    if any(sheet is None for sheet in sheets):
        problems.append(Problem.PREGEN_SHEET_MISSING)
    if ruleset and any(sheet and not fits(ruleset, sheet) for sheet in sheets):
        problems.append(Problem.PREGEN_SHEET_INVALID)
    return problems


def find_default_sheet_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    기본 시트에서 문제를 찾는다.

    직접 만들기를 허용했으면 기본 시트가 있어야 한다. 허용하지 않았으면 없어도 된다.
    있으면 허용했든 안 했든 규칙에 맞아야 한다. 판에 들어가기 때문이다.
    """
    if scenario.default_sheet is None:
        needed = CharacterMode.CUSTOM in scenario.character_modes
        return [Problem.DEFAULT_SHEET_MISSING] if needed else []
    if ruleset and not fits(ruleset, CharacterSheet.model_validate(scenario.default_sheet)):
        return [Problem.DEFAULT_SHEET_INVALID]
    return []


def find_player_made_problems(scenario: Scenario) -> list[Problem]:
    """
    플레이어가 능력치를 정하는 방식에서 문제를 찾는다.

    그런 방식을 하나라도 허용했으면 최대 HP 를 구하는 값이 있어야 한다. 플레이어는 최대 HP 를 직접 적지 못한다.
    허용하지 않았으면 없어도 된다.
    """
    allows_player_made = any(mode in PLAYER_MADE_MODES for mode in scenario.character_modes)
    if allows_player_made and scenario.player_made_hp is None:
        return [Problem.PLAYER_MADE_HP_MISSING]
    return []


def find_point_buy_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    점수제에서 문제를 찾는다.

    점수제를 허용했으면 룰북의 규칙에 점수제(총점과 값표)가 있어야 한다. 허용하지 않았으면 없어도 된다.
    룰북이 없으면 볼 수 없다. 그때는 룰북이 없다는 문제가 따로 적힌다.
    """
    allowed = CharacterMode.POINT_BUY in scenario.character_modes
    if allowed and ruleset is not None and ruleset.point_buy is None:
        return [Problem.POINT_BUY_MISSING]
    return []


def find_score_roll_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    주사위로 정하는 방식에서 문제를 찾는다.

    그 방식을 허용했으면 룰북의 규칙에 굴리는 법이 있어야 한다. 허용하지 않았으면 없어도 된다.
    룰북이 없으면 볼 수 없다. 그때는 룰북이 없다는 문제가 따로 적힌다.
    """
    allowed = CharacterMode.ROLLED in scenario.character_modes
    if allowed and ruleset is not None and ruleset.score_roll is None:
        return [Problem.SCORE_ROLL_MISSING]
    return []


def lore_entries(parts: Parts) -> dict[uuid.UUID, LoreEntry]:
    """붙인 로어북의 항목 전부. 항목의 ID 로 찾는다."""
    return {entry.id: entry for _, entries in parts.lorebooks for entry in entries}


def person_ids(parts: Parts) -> set[uuid.UUID]:
    """붙인 로어북의 인물 항목들의 ID."""
    return {entry_id for entry_id, entry in lore_entries(parts).items() if entry.kind == LoreKind.PERSON}


def read_npc_sheets(scenario: Scenario) -> list[NpcSheet]:
    """NPC 시트들을 읽는다."""
    return [NpcSheet.model_validate(document) for document in scenario.npc_sheets]


def find_npc_sheet_problems(scenario: Scenario, parts: Parts, ruleset: Ruleset | None) -> list[Problem]:
    """
    NPC 시트에서 문제를 찾는다. 시트가 여럿 틀려도 같은 문제는 한 번만 적는다.

    시트는 붙인 로어북의 인물 항목을 가리켜야 한다. 로어북의 항목은 시나리오와 따로 고칠 수 있어서,
    고치는 동안 지운 항목이나 종류를 바꾼 항목을 가리키게 될 수 있다. 굳히기 전에 여기서 막는다.
    공격의 이름표도 룰북의 것이어야 한다(몬스터의 공격과 같은 검사다). 룰북이 없으면 규칙에 맞는지는 볼 수 없다.
    """
    npc_sheets = read_npc_sheets(scenario)
    entries = lore_entries(parts)
    people = person_ids(parts)
    problems = []
    if any(npc_sheet.entry_id not in entries for npc_sheet in npc_sheets):
        problems.append(Problem.NPC_SHEET_ENTRY_MISSING)
    if any(npc_sheet.entry_id in entries and npc_sheet.entry_id not in people for npc_sheet in npc_sheets):
        problems.append(Problem.NPC_SHEET_NOT_PERSON)
    if ruleset and any(not fits(ruleset, npc_sheet.sheet) for npc_sheet in npc_sheets):
        problems.append(Problem.NPC_SHEET_INVALID)
    if ruleset and any(
        attack_fault(ruleset, attack, ResourceHolder.NPCS) for npc_sheet in npc_sheets for attack in npc_sheet.attacks
    ):
        problems.append(Problem.NPC_ATTACK_INVALID)
    return problems


def find_default_npc_sheet_problems(scenario: Scenario, parts: Parts, ruleset: Ruleset | None) -> list[Problem]:
    """
    기본 NPC 시트에서 문제를 찾는다.

    시트가 없는 인물 항목이 있으면 기본 NPC 시트가 있어야 한다. 모든 인물에게 시트가 있으면 없어도 된다.
    있으면 쓰든 안 쓰든 규칙에 맞아야 한다. 판에 들어가기 때문이다.
    """
    if scenario.default_npc_sheet is None:
        covered = {npc_sheet.entry_id for npc_sheet in read_npc_sheets(scenario)}
        return [Problem.DEFAULT_NPC_SHEET_MISSING] if person_ids(parts) - covered else []
    if ruleset and not fits(ruleset, Sheet.model_validate(scenario.default_npc_sheet)):
        return [Problem.DEFAULT_NPC_SHEET_INVALID]
    return []


def bestiary_monsters(parts: Parts) -> dict[uuid.UUID, Monster]:
    """붙인 도감의 몬스터 전부. 몬스터의 ID 로 찾는다."""
    return {monster.id: monster for _, found in parts.bestiaries for monster in found}


def read_monster_sheets(scenario: Scenario) -> list[MonsterSheet]:
    """몬스터 시트들을 읽는다."""
    return [MonsterSheet.model_validate(document) for document in scenario.monster_sheets]


def find_monster_sheet_problems(scenario: Scenario, parts: Parts, ruleset: Ruleset | None) -> list[Problem]:
    """
    몬스터 시트에서 문제를 찾는다. 시트가 여럿 틀려도 같은 문제는 한 번만 적는다.

    시트는 붙인 도감의 몬스터를 가리켜야 한다. 도감의 몬스터는 시나리오와 따로 지울 수 있다. 굳히기 전에 여기서 막는다.
    시트가 없는 몬스터는 문제가 아니다. 이 시나리오가 쓰지 않는 몬스터다.
    룰북이 없으면 규칙에 맞는지는 볼 수 없다.
    """
    monster_sheets = read_monster_sheets(scenario)
    known = bestiary_monsters(parts)
    problems = []
    if any(monster_sheet.monster_id not in known for monster_sheet in monster_sheets):
        problems.append(Problem.MONSTER_SHEET_MISSING)
    if ruleset and any(not fits(ruleset, monster_sheet.sheet) for monster_sheet in monster_sheets):
        problems.append(Problem.MONSTER_SHEET_INVALID)
    if ruleset and any(
        attack_fault(ruleset, attack, ResourceHolder.MONSTERS) for sheet in monster_sheets for attack in sheet.attacks
    ):
        problems.append(Problem.MONSTER_ATTACK_INVALID)
    if ruleset and any(nature_fault(ruleset, sheet) for sheet in monster_sheets):
        problems.append(Problem.MONSTER_NATURE_INVALID)
    return problems


def character_sheets(scenario: Scenario) -> list[CharacterSheet]:
    """기본 시트와 프리젠의 시트들. 없는 것은 뺀다."""
    sheets = [sheet for sheet in read_pregen_sheets(scenario) if sheet is not None]
    if scenario.default_sheet is not None:
        sheets.append(CharacterSheet.model_validate(scenario.default_sheet))
    return sheets


def find_resistance_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    저항과 맞추기의 성질(#886 ②)이 룰북의 성질인지 본다. 여럿 틀려도 한 번만 적는다(nature_invalid).

    기본 시트, 프리젠의 시트, NPC 시트, 아이템 규칙의 저항과, 물건의 효과 중 수치를 내리는 맞추기의 성질이다.
    몬스터와 인물의 공격의 효과의 성질은 공격의 검사가 본다(monster_attack_invalid, npc_attack_invalid).
    룰북이 없으면 볼 수 없다.
    """
    if ruleset is None:
        return []
    rules = read_item_rules(scenario)
    resistances = [
        *(sheet.resistances for sheet in character_sheets(scenario)),
        *(npc_sheet.resistances for npc_sheet in read_npc_sheets(scenario)),
        *(rule.resistances for rule in rules),
    ]
    natures = {nature.key for nature in ruleset.natures}
    drains = [effect.nature for rule in rules for effect in rule.effects if effect_nature(effect) is not None]
    if any(not resists_only_known(ruleset, one) for one in resistances) or not set(drains) <= natures:
        return [Problem.NATURE_INVALID]
    return []


def effect_nature(effect) -> str | None:
    """효과 하나의 성질(#886 ②). 수치의 맞추기에만 있다. 없으면 None."""
    return effect.nature if effect.kind == EffectKind.ADJUST else None


def nature_fault(ruleset: Ruleset, sheet: MonsterSheet) -> bool:
    """몬스터 시트의 면역과 약함이 룰북의 성질(#886)이 아닌 것을 가리키는가."""
    known = {nature.key for nature in ruleset.natures}
    return not set(sheet.immune) <= known or not set(sheet.vulnerable) <= known


def attack_fault(ruleset: Ruleset, attack: MonsterAttack, holder: ResourceHolder) -> bool:
    """
    이 공격의 능력치, 난이도, 양의 등급 중 룰북의 규칙에 없는 것이 있는가. 양의 등급은 비울 수 있다(#805 ③-b).
    비용(#805 ③-a)의 수치는 그 쪽(인물이나 몬스터, holder)이 가지는 규칙의 수치여야 한다.
    효과(#805 ③-b)의 부상은 규칙의 부상이고, 맞추는 수치는 맞을 쪽(캐릭터)이 가지는 규칙의 수치여야 한다.
    """
    return (
        find_ability(ruleset, attack.ability) is None
        or find_difficulty(ruleset, attack.difficulty) is None
        or (attack.harm is not None and find_magnitude(ruleset, attack.harm) is None)
        or cost_fault(ruleset, attack, holder)
        or any(attack_effect_fault(ruleset, effect) for effect in attack.effects)
    )


def attack_effect_fault(ruleset: Ruleset, effect) -> bool:
    """
    공격의 효과 하나가 규칙에 없는 부상이거나, 캐릭터가 가지지 않는 수치를 맞추거나,
    규칙에 없는 성질(#886 ②)을 단 맞추기인가.
    """
    if effect.kind == EffectKind.INJURE:
        return find_injury(ruleset, effect.injury) is None
    resource = find_resource(ruleset, effect.resource)
    unknown = effect.nature is not None and effect.nature not in {nature.key for nature in ruleset.natures}
    return resource is None or not holds(resource, ResourceHolder.CHARACTERS) or unknown


def cost_fault(ruleset: Ruleset, attack: MonsterAttack, holder: ResourceHolder) -> bool:
    """공격의 비용이 규칙에 없는 수치거나 그 쪽이 가지지 않는 수치인가. 비용이 없으면 아니다."""
    if attack.cost is None:
        return False
    resource = find_resource(ruleset, attack.cost.resource)
    return resource is None or not holds(resource, holder)


def find_unique_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """
    네임드 몹이 판 전체에서 한 마리인지 본다. 조우 한 줄에 한 마리, 그런 줄이 하나뿐이어야 한다.

    네임드 몹은 이름과 글이 그 한 마리의 것이라 둘이 있으면 누구인지 가를 수 없다.
    """
    unique = {monster.id for monster in bestiary_monsters(parts).values() if monster.unique}
    lines = [encounter for encounter in read_encounters(scenario) if encounter.monster_id in unique]
    ids = [encounter.monster_id for encounter in lines]
    if any(encounter.count > 1 for encounter in lines) or len(ids) != len(set(ids)):
        return [Problem.UNIQUE_MONSTER_REPEATED]
    return []


def snapshot_monsters(scenario: Scenario, parts: Parts) -> list[MonsterSnapshot]:
    """
    판에 굳힐 몬스터들. 시트를 적은 몬스터만, 시트를 적은 순서대로다.

    문제를 찾은 뒤에 부른다. 시트가 가리키는 몬스터는 모두 붙인 도감에 있다.
    """
    known = bestiary_monsters(parts)
    return [
        snapshot_monster(
            known[monster_sheet.monster_id],
            monster_sheet.sheet,
            [AttackSnapshot(**attack.model_dump()) for attack in monster_sheet.attacks],
            [CarriedItemSnapshot(**line.model_dump()) for line in monster_sheet.equipment],
            [CarriedItemSnapshot(**line.model_dump()) for line in monster_sheet.inventory],
            monster_sheet.dull,
            [NaturalArmorSnapshot(**one.model_dump()) for one in monster_sheet.natural_armor],
            monster_sheet.ward,
            monster_sheet.immune,
            monster_sheet.vulnerable,
        )
        for monster_sheet in read_monster_sheets(scenario)
    ]


def read_encounters(scenario: Scenario) -> list[Encounter]:
    """조우들을 읽는다."""
    return [Encounter.model_validate(document) for document in scenario.encounters]


def find_encounter_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """
    조우에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만 적는다.

    장소는 붙인 로어북의 장소 항목이어야 하고, 몬스터는 시트를 적은 몬스터여야 한다(판에 들어가는 몬스터).
    시트를 적은 몬스터가 도감에서 지워졌으면 그것은 몬스터 시트의 문제로 따로 적는다(find_monster_sheet_problems).
    조우는 맵의 장소에 두므로 시작 장소가 있어야 한다.
    """
    encounters = read_encounters(scenario)
    entries = lore_entries(parts)
    sheeted = {monster_sheet.monster_id for monster_sheet in read_monster_sheets(scenario)}
    places = [encounter.place_id for encounter in encounters]
    problems = []
    if any(place not in entries for place in places):
        problems.append(Problem.ENCOUNTER_PLACE_MISSING)
    if any(place in entries and entries[place].kind != LoreKind.PLACE for place in places):
        problems.append(Problem.ENCOUNTER_NOT_PLACE)
    if any(encounter.monster_id not in sheeted for encounter in encounters):
        problems.append(Problem.ENCOUNTER_MONSTER_MISSING)
    if encounters and scenario.start_place is None:
        problems.append(Problem.ENCOUNTER_MAP_MISSING)
    return problems


def read_item_rules(scenario: Scenario) -> list[ItemRule]:
    """아이템 규칙들을 읽는다."""
    return [ItemRule.model_validate(document) for document in scenario.items]


def read_quest_rules(scenario: Scenario) -> list[QuestRule]:
    """퀘스트 규칙들을 읽는다."""
    return [QuestRule.model_validate(document) for document in scenario.quests]


def item_references(scenario: Scenario) -> list[uuid.UUID]:
    """
    물건 항목을 가리키는 것 전부. 아이템 규칙, 시작 소지품, 프리젠마다의 소지품, 퀘스트마다의 보상,
    몬스터와 NPC 마다 지닌 물건(장비와 소지품), 장소에 놓인 물건, 길의 자물쇠의 열쇠, 자물쇠 물건의 열쇠(#281).
    """
    stacks = [ItemStack.model_validate(document) for document in scenario.starting_items]
    for document in scenario.pregens:
        stacks.extend(Pregen.model_validate(document).items)
    for quest in read_quest_rules(scenario):
        stacks.extend(quest.reward)
    sheets = [*read_monster_sheets(scenario), *read_npc_sheets(scenario)]
    carried = [line.entry_id for sheet in sheets for line in [*sheet.equipment, *sheet.inventory]]
    placed = [rule.entry_id for rule in read_place_items(scenario)]
    item_rules = read_item_rules(scenario)
    rules = [rule.entry_id for rule in item_rules]
    routes = read_routes(scenario)
    keys = lock_keys(routes) + item_lock_keys(item_rules)
    return rules + [stack.entry_id for stack in stacks] + carried + placed + keys


def find_item_problems(scenario: Scenario, parts: Parts, ruleset: Ruleset | None) -> list[Problem]:
    """
    아이템 규칙과 소지품에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만 적는다.

    가리키는 것은 붙인 로어북의 물건 항목이어야 한다. NPC 시트와 같은 까닭으로 굳히기 전에 여기서 막는다.
    소모품의 효과(#800)의 회복과 피해의 등급은 룰북의 등급, 푸는 부상은 룰북의 부상이고 결손이 아니어야 하고(#277),
    입히는 부상은 룰북의 부상, 맞추는 수치는 룰북의 수치여야 한다(#804).
    자물쇠 물건의 따는 판정은 룰북의 능력치와 난이도여야 한다(#281).
    던지는 소모품의 판정은 룰북의 능력치와 난이도와 피해의 등급이어야 한다(#277).
    룰북이 없으면 볼 수 없다(그때는 RULEBOOK_MISSING 이다).
    """
    entries = lore_entries(parts)
    pointed = item_references(scenario)
    problems = []
    if any(entry_id not in entries for entry_id in pointed):
        problems.append(Problem.ITEM_ENTRY_MISSING)
    if any(entry_id in entries and entries[entry_id].kind != LoreKind.ITEM for entry_id in pointed):
        problems.append(Problem.ITEM_NOT_ITEM)
    rules = read_item_rules(scenario)
    effects = [effect for rule in rules for effect in rule.effects]
    if ruleset and any(find_magnitude(ruleset, key) is None for key in effect_magnitudes(effects)):
        problems.append(Problem.ITEM_MAGNITUDE_MISSING)
    if ruleset and any(find_invalid(pick, ruleset) for pick in item_lock_picks(rules)):
        problems.append(Problem.ITEM_LOCK_INVALID)
    if ruleset and any(not curable(ruleset, key) for key in effect_cures(effects)):
        problems.append(Problem.ITEM_CURE_INVALID)
    if ruleset and any(find_injury(ruleset, key) is None for key in effect_injuries(effects)):
        problems.append(Problem.ITEM_INJURE_INVALID)
    if ruleset and any(find_resource(ruleset, key) is None for key in effect_resources(effects)):
        problems.append(Problem.ITEM_RESOURCE_INVALID)
    if ruleset and any(cross_invalid(rule.throw, ruleset) for rule in rules):
        problems.append(Problem.ITEM_THROW_INVALID)
    return problems


def effect_magnitudes(effects: list) -> list[str]:
    """효과들이 적은 회복과 피해의 등급(#800)."""
    return [effect.magnitude for effect in effects if effect.kind in (EffectKind.HEAL, EffectKind.DAMAGE)]


def effect_resources(effects: list) -> list[str]:
    """효과들이 맞추는 수치(#804)."""
    return [effect.resource for effect in effects if effect.kind == EffectKind.ADJUST]


def effect_cures(effects: list) -> list[str]:
    """효과들이 푸는 부상(#800)."""
    return [key for effect in effects if effect.kind == EffectKind.CURE for key in effect.injuries]


def effect_injuries(effects: list) -> list[str]:
    """효과들이 입히는 부상(#800)."""
    return [effect.injury for effect in effects if effect.kind == EffectKind.INJURE]


def curable(ruleset: Ruleset, key: str) -> bool:
    """소모품이 풀 수 있는 부상인가. 룰북에 있고 결손이 아니다(#277). 짧은 것과 오래 가는 것이다."""
    injury = find_injury(ruleset, key)
    return injury is not None and injury.healing != Healing.PERMANENT


def starting_groups(scenario: Scenario) -> list[list[ItemStack]]:
    """한 캐릭터가 시작할 때 받을 줄들의 묶음. 시작 소지품만, 그리고 프리젠마다 시작 소지품에 그 소지품을 더한 것."""
    common = [ItemStack.model_validate(document) for document in scenario.starting_items]
    pregens = [Pregen.model_validate(document) for document in scenario.pregens]
    return [common, *([*common, *pregen.items] for pregen in pregens)]


def find_wear_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    장비의 칸에서 문제를 찾는다(#276). 룰북이 없으면 볼 수 없다(그때는 RULEBOOK_MISSING 이다).

    아이템 규칙의 칸은 룰북의 칸이어야 하고, 시작할 때의 착용은 그 물건의 칸에 맞아야 한다(wear_fault).
    """
    if ruleset is None:
        return []
    slot_keys = {slot.key for slot in ruleset.equipment_slots}
    rules = read_item_rules(scenario)
    problems = []
    if any(slot not in slot_keys for rule in rules for slot in rule.slots):
        problems.append(Problem.ITEM_SLOT_INVALID)
    item_slots = {rule.entry_id: (rule.slots, rule.slot_count) for rule in rules}
    if any(wear_fault(slot_keys, item_slots, group) for group in starting_groups(scenario)):
        problems.append(Problem.STARTING_WEAR_INVALID)
    return problems


def armed_holders(scenario: Scenario) -> list[NpcSheet | MonsterSheet]:
    """장비와 공격을 가진 시트들. NPC 시트와 몬스터 시트다."""
    return [*read_npc_sheets(scenario), *read_monster_sheets(scenario)]


def weapon_fault(holder: NpcSheet | MonsterSheet, attack: MonsterAttack, attacks_of: dict[uuid.UUID, int]) -> bool:
    """
    공격의 무기가 틀렸는가. 무기는 그 시트가 착용한 장비 줄의 물건이고, 공격 보정이 있어야 한다.

    attacks_of 는 공격 보정이 있는 물건의 {항목 ID: 보정} 이다. 무기가 장비에 적힌 것인지는 시트가 봤다.
    """
    if attack.weapon is None:
        return False
    worn = {line.entry_id for line in holder.equipment if line.wear}
    return attack.weapon not in worn or attack.weapon not in attacks_of


def find_combat_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    NPC 와 몬스터의 장비가 공격과 방어에 드는 것에서 문제를 찾는다(#276). 룰북이 없으면 볼 수 없다.

    장비의 착용은 그 물건의 칸에 맞아야 하고(wear_fault), 타고난 방어의 부위는 룰북의 칸이어야 하고,
    공격의 무기는 착용한 장비 중 공격 보정이 있는 물건이어야 한다.
    """
    if ruleset is None:
        return []
    slot_keys = {slot.key for slot in ruleset.equipment_slots}
    rules = read_item_rules(scenario)
    item_slots = {rule.entry_id: (rule.slots, rule.slot_count) for rule in rules}
    attacks_of = {rule.entry_id: rule.attack for rule in rules if rule.attack is not None}
    holders = armed_holders(scenario)
    problems = []
    if any(wear_fault(slot_keys, item_slots, holder.equipment) for holder in holders):
        problems.append(Problem.CARRIED_WEAR_INVALID)
    natural = [one.slot for sheet in read_monster_sheets(scenario) for one in sheet.natural_armor]
    if any(slot not in slot_keys for slot in natural):
        problems.append(Problem.NATURAL_ARMOR_INVALID)
    if any(weapon_fault(holder, attack, attacks_of) for holder in holders for attack in holder.attacks):
        problems.append(Problem.ATTACK_WEAPON_INVALID)
    return problems


def uses_money(scenario: Scenario) -> bool:
    """돈을 쓰는 칸이 있는가. 물건의 값, 상인, 프리젠이 더 받는 돈, 퀘스트의 돈의 보상이다."""
    return (
        any(rule.price is not None for rule in read_item_rules(scenario))
        or any(npc_sheet.merchant for npc_sheet in read_npc_sheets(scenario))
        or any(Pregen.model_validate(document).money for document in scenario.pregens)
        or any(quest.reward_money for quest in read_quest_rules(scenario))
    )


def find_currency_problems(scenario: Scenario) -> list[Problem]:
    """
    돈의 문제를 찾는다. 돈을 쓰는 칸이 있으면 화폐가 있어야 한다(#278).

    초안에서는 화폐와 값을 따로 고칠 수 있어서 입력을 받을 때는 막지 않는다. 판에는 화폐 없이 돈이 들어가지 않는다.
    """
    if scenario.currency is None and uses_money(scenario):
        return [Problem.CURRENCY_MISSING]
    return []


def find_quest_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """
    퀘스트 규칙에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만 적는다.

    가리키는 것은 붙인 로어북의 사건 항목이어야 한다. 아이템 규칙과 같은 까닭으로 굳히기 전에 여기서 막는다.
    보상의 물건은 아이템과 함께 본다(find_item_problems). 이루는 조건과 드러나는 조건은 find_condition_problems,
    드러나는 조건이 돌고 도는지는 has_reveal_cycle 이 본다.
    """
    entries = lore_entries(parts)
    rules = read_quest_rules(scenario)
    pointed = [rule.entry_id for rule in rules]
    problems = []
    if any(entry_id not in entries for entry_id in pointed):
        problems.append(Problem.QUEST_ENTRY_MISSING)
    if any(entry_id in entries and entries[entry_id].kind != LoreKind.EVENT for entry_id in pointed):
        problems.append(Problem.QUEST_NOT_EVENT)
    problems.extend(find_condition_problems(scenario, parts))
    if has_reveal_cycle(rules):
        problems.append(Problem.QUEST_REVEAL_CYCLE)
    return problems


# 조건의 종류마다 target 이 가리켜야 하는 로어북 항목의 종류. 몬스터를 쓰러뜨리기는 로어북이 아니라 몬스터 시트다.
# 퀘스트 잇기는 사건 항목이다. 판의 사건 항목 하나가 퀘스트 하나다
CONDITION_ENTRY_KINDS = {
    QuestConditionKind.REACH_PLACE: LoreKind.PLACE,
    QuestConditionKind.HOLD_ITEM: LoreKind.ITEM,
    QuestConditionKind.DEFEAT_NPC: LoreKind.PERSON,
    QuestConditionKind.NPC_DEAD: LoreKind.PERSON,
    QuestConditionKind.LOSE_ITEM: LoreKind.ITEM,
    QuestConditionKind.QUEST_SUCCEEDED: LoreKind.EVENT,
    QuestConditionKind.QUEST_FAILED: LoreKind.EVENT,
}


def placed_count(scenario: Scenario, monster_id: uuid.UUID) -> int:
    """판의 조우에 놓인 그 몬스터의 마리 수 전부."""
    return sum(encounter.count for encounter in read_encounters(scenario) if encounter.monster_id == monster_id)


def can_succeed(scenario: Scenario, entry_id: uuid.UUID) -> bool:
    """그 퀘스트가 성공할 수 있는가. 이루는 조건이 있어야 한다. 규칙이 없는 사건은 성공하지 않는다."""
    return any(rule.entry_id == entry_id and rule.conditions for rule in read_quest_rules(scenario))


def can_fail(scenario: Scenario, entry_id: uuid.UUID) -> bool:
    """
    그 퀘스트가 실패할 수 있는가. 실패하는 조건이나 기한이 있어야 한다. 규칙이 없는 사건은 실패하지 않는다.

    사람(방장)이 실패시키는 길은 없다(#367). 그래서 실패를 기다리는 잇기는 이것이 참이어야 이룰 수 있다.
    """
    return any(
        rule.entry_id == entry_id and (rule.fail or rule.time_limit_minutes is not None)
        for rule in read_quest_rules(scenario)
    )


def condition_problem(condition: QuestCondition, scenario: Scenario, parts: Parts) -> Problem | None:
    """
    조건 하나의 문제. 없으면 None.

    몬스터를 쓰러뜨리기는 시트를 적은 몬스터여야 하고(판에 들어가는 몬스터), 놓인 마리보다 많이 요구하지 않는다.
    장소에 닿기는 맵의 장소여야 한다(시작 장소, 길의 끝, 명소). 맵에 없는 장소에는 설 수 없다.
    다른 퀘스트의 성공을 기다리면 그 퀘스트에 이루는 조건이 있어야 한다. 없으면 성공하지 않는다.
    다른 퀘스트의 실패를 기다리면 그 퀘스트에 실패하는 조건이나 기한이 있어야 한다. 없으면 실패하지 않는다.
    """
    if condition.kind == QuestConditionKind.DEFEAT_MONSTER:
        sheeted = {sheet.monster_id for sheet in read_monster_sheets(scenario)}
        if condition.target not in sheeted:
            return Problem.QUEST_CONDITION_MISSING
        if placed_count(scenario, condition.target) < condition.count:
            return Problem.QUEST_CONDITION_IMPOSSIBLE
        return None
    entry = lore_entries(parts).get(condition.target)
    if entry is None:
        return Problem.QUEST_CONDITION_MISSING
    if entry.kind != CONDITION_ENTRY_KINDS[condition.kind]:
        return Problem.QUEST_CONDITION_INVALID
    if condition.kind == QuestConditionKind.REACH_PLACE and condition.target not in map_places(
        scenario, read_routes(scenario)
    ):
        return Problem.QUEST_CONDITION_IMPOSSIBLE
    if condition.kind == QuestConditionKind.QUEST_SUCCEEDED and not can_succeed(scenario, condition.target):
        return Problem.QUEST_CONDITION_IMPOSSIBLE
    if condition.kind == QuestConditionKind.QUEST_FAILED and not can_fail(scenario, condition.target):
        return Problem.QUEST_CONDITION_IMPOSSIBLE
    return None


def find_condition_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """
    퀘스트의 조건들(이루는 조건, 드러나는 조건, 실패하는 조건)에서 문제를 찾는다.
    여럿 틀려도 같은 문제는 한 번만, 정한 순서로 적는다.
    """
    found = {
        condition_problem(condition, scenario, parts)
        for rule in read_quest_rules(scenario)
        for condition in [*rule.conditions, *rule.reveal, *rule.fail]
    }
    order = [Problem.QUEST_CONDITION_MISSING, Problem.QUEST_CONDITION_INVALID, Problem.QUEST_CONDITION_IMPOSSIBLE]
    return [problem for problem in order if problem in found]


def reveal_links(rules: list[QuestRule]) -> dict[uuid.UUID, set[uuid.UUID]]:
    """퀘스트마다 드러나려면 끝나야 하는 다른 퀘스트들(퀘스트 잇기)."""
    return {
        rule.entry_id: {condition.target for condition in rule.reveal if condition.kind in QUEST_LINK_CONDITIONS}
        for rule in rules
    }


def leads_back(
    links: dict[uuid.UUID, set[uuid.UUID]], entry_id: uuid.UUID, path: set[uuid.UUID], done: set[uuid.UUID]
) -> bool:
    """
    그 퀘스트에서 잇기를 따라가다 지금 따라온 길(path)로 돌아오는가. 깊이로 따라간다.

    다 본 퀘스트(done)는 다시 보지 않는다. 거기서는 돌아오는 길이 없었다.
    """
    if entry_id in path:
        return True
    if entry_id in done:
        return False
    path.add(entry_id)
    found = any(leads_back(links, target, path, done) for target in links.get(entry_id, ()))
    path.discard(entry_id)
    done.add(entry_id)
    return found


def has_reveal_cycle(rules: list[QuestRule]) -> bool:
    """
    드러나는 조건이 돌고 도는가. 퀘스트 잇기를 따라가다 처음 퀘스트로 돌아오면 돈다.

    숨긴 퀘스트는 숨긴 채로도 이룰 수 있어 막히지는 않는다. 다만 서로를 기다리는 것은 만든 사람의 실수다.
    """
    links = reveal_links(rules)
    done: set[uuid.UUID] = set()
    return any(leads_back(links, entry_id, set(), done) for entry_id in links)


def read_happenings(scenario: Scenario) -> list[HappeningRule]:
    """사건 규칙들을 읽는다."""
    return [HappeningRule.model_validate(document) for document in scenario.happenings]


# 길의 문을 다루는 사건의 효과의 모양(#281)
ROUTE_EFFECT_TYPES = (RouteDoorEffect, RepairRouteEffect)

# 퀘스트의 조건 문제와 같은 까닭의 사건의 조건 문제. 조건 하나의 문제는 condition_problem 이 함께 본다
HAPPENING_CONDITION_PROBLEMS = {
    Problem.QUEST_CONDITION_MISSING: Problem.HAPPENING_CONDITION_MISSING,
    Problem.QUEST_CONDITION_INVALID: Problem.HAPPENING_CONDITION_INVALID,
    Problem.QUEST_CONDITION_IMPOSSIBLE: Problem.HAPPENING_CONDITION_IMPOSSIBLE,
}


def effect_places(effect: HappeningEffect) -> list[uuid.UUID]:
    """
    사건의 효과 하나가 옮기는 데 가리키는 장소들. 옮기는 곳과, 캐릭터를 옮기면 옮겨질 사람이 선 곳(있으면)이다.

    문을 다루는 효과(#281)는 옮기지 않는다. 그 두 끝은 길로 본다(door_effect_invalid).
    """
    if isinstance(effect, MoveNpcEffect) or (isinstance(effect, MoveEffect) and effect.from_place is None):
        return [effect.to_place]
    if isinstance(effect, MoveEffect):
        return [effect.to_place, effect.from_place]
    return []


def happening_places(rules: list[HappeningRule]) -> list[uuid.UUID]:
    """사건의 효과가 가리키는 장소 전부."""
    return [place for rule in rules for effect in rule.effects for place in effect_places(effect)]


def moved_npcs(rules: list[HappeningRule]) -> list[uuid.UUID]:
    """사건의 효과가 옮기는 인물 전부(move_npc, #282)."""
    return [effect.npc for rule in rules for effect in rule.effects if isinstance(effect, MoveNpcEffect)]


def route_effects(rules: list[HappeningRule]) -> list[HappeningEffect]:
    """사건의 효과 중 길의 문을 다루는 것 전부(#281). 잠그기, 열기, 고치기다."""
    return [effect for rule in rules for effect in rule.effects if isinstance(effect, ROUTE_EFFECT_TYPES)]


def door_effect_invalid(effect: HappeningEffect, routes: list[RouteRule]) -> bool:
    """
    문을 다루는 효과 하나가 다룰 문이 없는가(#281). 두 끝 사이의 길이 없거나, 그 길에 자물쇠도 빗장도 없거나,
    적은 장치(device)가 그 길에 없으면 참이다. 길의 방향은 보지 않는다.
    """
    ends = {effect.from_place, effect.to_place}
    route = next((route for route in routes if {route.from_place, route.to_place} == ends), None)
    if route is None:
        return True
    devices = {DoorDevice.LOCK: route.lock, DoorDevice.BAR: route.bar}
    if not any(devices.values()):
        return True
    device = getattr(effect, 'device', None)
    return device is not None and devices[device] is None


def find_happening_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """
    사건 규칙에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만, 정한 순서로 적는다(#367).

    가리키는 것은 붙인 로어북의 사건 항목이어야 한다. 조건은 퀘스트의 조건과 같이 본다(condition_problem).
    효과의 장소는 맵의 장소여야 한다(시작 장소, 길의 끝, 명소). 맵이 없는 판이면 어느 장소도 맵에 없다.
    옮기는 인물(move_npc)은 붙인 로어북의 인물 항목이어야 한다.
    문을 다루는 효과(#281)는 판의 길 중 문이 있는 것을 가리켜야 하고, 장치를 적었으면 그 길에 있어야 한다.
    """
    entries = lore_entries(parts)
    rules = read_happenings(scenario)
    routes = read_routes(scenario)
    on_map = set(map_places(scenario, routes))
    found = set()
    if any(rule.entry_id not in entries for rule in rules):
        found.add(Problem.HAPPENING_ENTRY_MISSING)
    if any(rule.entry_id in entries and entries[rule.entry_id].kind != LoreKind.EVENT for rule in rules):
        found.add(Problem.HAPPENING_NOT_EVENT)
    for rule in rules:
        for condition in rule.when:
            problem = condition_problem(condition, scenario, parts)
            if problem is not None:
                found.add(HAPPENING_CONDITION_PROBLEMS[problem])
    if any(place not in on_map for place in happening_places(rules)):
        found.add(Problem.HAPPENING_PLACE_OFF_MAP)
    if any(npc not in person_ids(parts) for npc in moved_npcs(rules)):
        found.add(Problem.HAPPENING_NPC_NOT_PERSON)
    if any(door_effect_invalid(effect, routes) for effect in route_effects(rules)):
        found.add(Problem.HAPPENING_ROUTE_INVALID)
    order = [
        Problem.HAPPENING_ENTRY_MISSING,
        Problem.HAPPENING_NOT_EVENT,
        Problem.HAPPENING_CONDITION_MISSING,
        Problem.HAPPENING_CONDITION_INVALID,
        Problem.HAPPENING_CONDITION_IMPOSSIBLE,
        Problem.HAPPENING_PLACE_OFF_MAP,
        Problem.HAPPENING_NPC_NOT_PERSON,
        Problem.HAPPENING_ROUTE_INVALID,
    ]
    return [problem for problem in order if problem in found]


def read_routes(scenario: Scenario) -> list[RouteRule]:
    """길들을 읽는다."""
    return [RouteRule.model_validate(document) for document in scenario.routes]


def lock_keys(routes: list[RouteRule]) -> list[uuid.UUID]:
    """길의 자물쇠마다의 열쇠(#281). 길의 순서다."""
    return [route.lock.key for route in routes if route.lock is not None]


def item_lock_keys(rules: list[ItemRule]) -> list[uuid.UUID]:
    """자물쇠 물건마다의 열쇠(#281). 아이템 규칙의 순서다."""
    return [rule.lock.key for rule in rules if rule.lock is not None]


def item_lock_picks(rules: list[ItemRule]) -> list[PickCheck]:
    """자물쇠 물건마다의 따는 판정(#281). 적지 않은 것은 빠진다. 아이템 규칙의 순서다."""
    return [rule.lock.pick for rule in rules if rule.lock is not None and rule.lock.pick is not None]


def tool_acts(routes: list[RouteRule], rules: list[ItemRule]) -> set[AidAct]:
    """도구가 있어야 하는 문의 행동들(#802). 길의 따기와 고치기, 자물쇠 물건의 따기 중 needs_tool 인 것이다."""
    picks = [route.lock.pick for route in routes if route.lock is not None and route.lock.pick is not None]
    repairs = [route.repair for route in routes if route.repair is not None]
    needed = [(AidAct.PICK, check) for check in [*picks, *item_lock_picks(rules)]]
    needed += [(AidAct.REPAIR, check) for check in repairs]
    return {act for act, check in needed if check.needs_tool}


def aided_acts(rules: list[ItemRule]) -> set[AidAct]:
    """판의 물건들이 거드는 행동들(#802)."""
    return {aid.act for rule in rules for aid in rule.aids}


def opening_checks(route: RouteRule) -> list[PickCheck | ForceCheck]:
    """길의 문을 다루는 판정들(#281). 따기, 부수기, 고치기다. 적지 않은 것은 빠진다."""
    pick = route.lock.pick if route.lock is not None else None
    return [check for check in (pick, route.force, route.repair) if check is not None]


def cross_invalid(cross: CrossCheck | ItemThrow | None, ruleset: Ruleset) -> bool:
    """
    길을 넘는 판정이 룰북의 규칙에 맞지 않는가(#281). 능력치와 난이도는 찾는 판정과 같이 보고,
    실패의 피해를 적었으면 룰북의 양의 등급이어야 한다.

    물건을 던지는 판정(#277)도 같이 본다. 그쪽에는 피해가 없다(맞으면 물건의 효과가 든다, #801).
    """
    if cross is None:
        return False
    if find_ability(ruleset, cross.ability) is None or find_difficulty(ruleset, cross.difficulty) is None:
        return True
    harm = getattr(cross, 'harm', None)
    return harm is not None and find_magnitude(ruleset, harm) is None


def map_places(scenario: Scenario, routes: list[RouteRule]) -> list[uuid.UUID]:
    """맵이 가리키는 장소 전부. 시작 장소, 길마다의 두 끝, 명소."""
    places = [place for route in routes for place in (route.from_place, route.to_place)]
    places.extend(scenario.landmarks)
    if scenario.start_place is not None:
        places.append(scenario.start_place)
    return places


def find_invalid(find: FindCheck | PickCheck | ForceCheck | None, ruleset: Ruleset) -> bool:
    """
    찾는 판정(숨긴 길, 숨긴 물건)이 룰북의 규칙에 맞지 않는가. 능력치와 난이도가 규칙에 있어야 한다.

    자물쇠를 따는 판정, 문을 부수는 판정, 고치는 판정(#281)도 같은 모양이라 같이 본다.
    """
    if find is None:
        return False
    return find_ability(ruleset, find.ability) is None or find_difficulty(ruleset, find.difficulty) is None


def read_place_items(scenario: Scenario) -> list[PlaceItem]:
    """장소에 놓인 물건들을 읽는다."""
    return [PlaceItem.model_validate(document) for document in scenario.place_items]


def find_place_item_problems(scenario: Scenario, ruleset: Ruleset | None) -> list[Problem]:
    """
    장소에 놓인 물건에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만 적는다.

    장소는 맵의 장소여야 한다(시작 장소, 길의 끝, 명소). 맵에 없는 장소에는 아무도 설 수 없다.
    가리키는 물건이 붙인 로어북의 물건 항목인지는 아이템과 함께 본다(find_item_problems).
    숨긴 물건을 찾는 판정은 룰북의 능력치와 난이도여야 한다(룰북이 없으면 못 본다).
    """
    rules = read_place_items(scenario)
    on_map = set(map_places(scenario, read_routes(scenario)))
    problems = []
    if any(rule.place_id not in on_map for rule in rules):
        problems.append(Problem.PLACE_ITEM_OFF_MAP)
    if ruleset and any(find_invalid(rule.find, ruleset) for rule in rules):
        problems.append(Problem.PLACE_ITEM_FIND_INVALID)
    return problems


def read_npc_places(scenario: Scenario) -> list[NpcPlace]:
    """인물의 자리들을 읽는다."""
    return [NpcPlace.model_validate(document) for document in scenario.npc_places]


def find_npc_place_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """
    인물의 자리에서 문제를 찾는다(#282). 여럿 틀려도 같은 문제는 한 번만 적는다.

    인물은 붙인 로어북의 인물 항목이어야 한다. 시트가 없어도 된다(기본 NPC 시트를 쓴다).
    장소는 맵의 장소여야 한다(시작 장소, 길의 끝, 명소). 맵이 없는 판이면 어느 장소도 맵에 없다.
    """
    places = read_npc_places(scenario)
    people = person_ids(parts)
    on_map = set(map_places(scenario, read_routes(scenario)))
    problems = []
    if any(place.entry_id not in people for place in places):
        problems.append(Problem.NPC_PLACE_NOT_PERSON)
    if any(place.place_id not in on_map for place in places):
        problems.append(Problem.NPC_PLACE_OFF_MAP)
    return problems


def read_covers(scenario: Scenario) -> list[CoverRule]:
    """장소마다의 커버를 읽는다."""
    return [CoverRule.model_validate(document) for document in scenario.covers]


def find_cover_problems(scenario: Scenario) -> list[Problem]:
    """
    커버에서 문제를 찾는다(#276). 장소는 맵의 장소여야 한다(시작 장소, 길의 끝, 명소).

    맵의 장소가 장소 항목인지는 맵과 함께 본다(find_map_problems). 룰북이 세이브 방식이 아니어도 막지 않는다.
    룰북을 고쳐 세이브 방식으로 바꿀 수 있다. 그때까지 엄폐를 받지 않을 뿐이다.
    """
    on_map = set(map_places(scenario, read_routes(scenario)))
    if any(rule.place_id not in on_map for rule in read_covers(scenario)):
        return [Problem.COVER_OFF_MAP]
    return []


def read_wanders(scenario: Scenario) -> list[WanderTable]:
    """무작위 조우 표들을 읽는다."""
    return [WanderTable.model_validate(document) for document in scenario.wanders]


def wanders_off_map(scenario: Scenario, tables: list[WanderTable]) -> bool:
    """조우 표가 맵 밖을 가리키는가. 맵이 없는데 표가 있거나, 맵의 장소가 아닌 장소의 표가 있다."""
    if tables and scenario.start_place is None:
        return True
    on_map = set(map_places(scenario, read_routes(scenario)))
    return any(table.place_id is not None and table.place_id not in on_map for table in tables)


def find_wander_problems(scenario: Scenario) -> list[Problem]:
    """
    무작위 조우 표에서 문제를 찾는다(#283). 여럿 틀려도 같은 문제는 한 번만 적는다.

    장소는 맵의 장소여야 한다(시작 장소, 길의 끝, 명소). 기본 표도 맵이 있어야 몬스터를 둘 곳이 있다.
    맵의 장소가 장소 항목인지는 맵과 함께 본다(find_map_problems). 몬스터는 시트를 적은 몬스터여야 한다(조우와 같다).
    """
    tables = read_wanders(scenario)
    sheeted = {monster_sheet.monster_id for monster_sheet in read_monster_sheets(scenario)}
    problems = []
    if wanders_off_map(scenario, tables):
        problems.append(Problem.WANDER_OFF_MAP)
    if any(line.monster_id not in sheeted for table in tables for line in table.monsters):
        problems.append(Problem.WANDER_MONSTER_MISSING)
    return problems


def find_map_problems(scenario: Scenario, parts: Parts, ruleset: Ruleset | None) -> list[Problem]:
    """
    맵(시작 장소, 길, 명소)에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만 적는다.

    가리키는 것은 붙인 로어북의 장소 항목이어야 한다. 아이템 규칙과 같은 까닭으로 굳히기 전에 여기서 막는다.
    길이나 명소가 있으면 시작 장소가 있어야 한다.
    숨긴 길을 찾는 판정은 룰북의 능력치와 난이도여야 한다(룰북이 없으면 못 본다). 길을 넘는 판정도 같고,
    실패의 피해는 룰북의 양의 등급이어야 한다(#281). 열쇠 하나는 자물쇠 하나만 연다(자물쇠 물건의 열쇠까지).
    도구가 있어야 하는 문이 있으면 그 행동을 거드는 물건이 판에 있어야 한다(#802).
    열쇠가 물건 항목인지는 아이템과 함께 본다(item_references).
    """
    entries = lore_entries(parts)
    routes = read_routes(scenario)
    pointed = map_places(scenario, routes)
    problems = []
    if any(place not in entries for place in pointed):
        problems.append(Problem.MAP_PLACE_MISSING)
    if any(place in entries and entries[place].kind != LoreKind.PLACE for place in pointed):
        problems.append(Problem.MAP_NOT_PLACE)
    if (routes or scenario.landmarks) and scenario.start_place is None:
        problems.append(Problem.MAP_START_MISSING)
    if ruleset and any(find_invalid(route.find, ruleset) for route in routes):
        problems.append(Problem.ROUTE_FIND_INVALID)
    if ruleset and any(cross_invalid(route.cross, ruleset) for route in routes):
        problems.append(Problem.ROUTE_CROSS_INVALID)
    keys = lock_keys(routes) + item_lock_keys(read_item_rules(scenario))
    if len(set(keys)) != len(keys):
        problems.append(Problem.ROUTE_KEY_REPEATED)
    opening = [check for route in routes for check in opening_checks(route)]
    if ruleset and any(find_invalid(check, ruleset) for check in opening):
        problems.append(Problem.ROUTE_OPEN_INVALID)
    item_rules = read_item_rules(scenario)
    if not tool_acts(routes, item_rules) <= aided_acts(item_rules):
        problems.append(Problem.ROUTE_TOOL_MISSING)
    return problems


def find_seating_problems(scenario: Scenario) -> list[Problem]:
    """
    허용한 방식으로 사람이 앉을 수 있는지 본다.

    프리젠 하나는 한 사람만 고른다. 프리젠만 허용했으면 프리젠의 수가 곧 앉을 수 있는 사람의 수다.
    추천 인원의 최소만큼은 앉을 수 있어야 한다.
    """
    pregen_only = list(scenario.character_modes) == [CharacterMode.PREGEN]
    if pregen_only and len(scenario.pregens) < scenario.min_players:
        return [Problem.PREGENS_TOO_FEW]
    return []


def find_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """게시할 수 없는 이유를 전부 찾는다. 없으면 빈 목록이다."""
    ruleset = read_ruleset(parts.rulebook)
    problems = []
    if parts.rulebook is None:
        problems.append(Problem.RULEBOOK_MISSING)
    if not scenario.openings:
        problems.append(Problem.OPENING_MISSING)
    problems.extend(find_pregen_problems(scenario, ruleset))
    problems.extend(find_default_sheet_problems(scenario, ruleset))
    problems.extend(find_sheet_skill_problems(scenario, ruleset))
    problems.extend(find_player_made_problems(scenario))
    problems.extend(find_point_buy_problems(scenario, ruleset))
    problems.extend(find_score_roll_problems(scenario, ruleset))
    problems.extend(find_npc_sheet_problems(scenario, parts, ruleset))
    problems.extend(find_default_npc_sheet_problems(scenario, parts, ruleset))
    problems.extend(find_monster_sheet_problems(scenario, parts, ruleset))
    problems.extend(find_resistance_problems(scenario, ruleset))
    problems.extend(find_encounter_problems(scenario, parts))
    problems.extend(find_unique_problems(scenario, parts))
    problems.extend(find_item_problems(scenario, parts, ruleset))
    problems.extend(find_quest_problems(scenario, parts))
    problems.extend(find_currency_problems(scenario))
    problems.extend(find_wear_problems(scenario, ruleset))
    problems.extend(find_combat_problems(scenario, ruleset))
    problems.extend(find_map_problems(scenario, parts, ruleset))
    problems.extend(find_place_item_problems(scenario, ruleset))
    problems.extend(find_cover_problems(scenario))
    problems.extend(find_wander_problems(scenario))
    problems.extend(find_happening_problems(scenario, parts))
    problems.extend(find_npc_place_problems(scenario, parts))
    problems.extend(find_seating_problems(scenario))
    return problems


def build_version(scenario: Scenario, rulebook: Rulebook, parts: Parts, number: int, note: str) -> ScenarioVersion:
    """시나리오와 자산들에서 판 객체를 만든다. 아직 저장하지 않는다."""
    snapshot = build_snapshot(scenario, rulebook, parts.world, parts.lorebooks, snapshot_monsters(scenario, parts))
    return ScenarioVersion(
        scenario_id=scenario.asset_id,
        number=number,
        note=note,
        # mode='json': UUID 같은 값을 JSON 에 넣을 수 있는 글자로 바꾼다
        snapshot=snapshot.model_dump(mode='json'),
    )


def has_lore(parts: Parts) -> bool:
    """판에 로어북 항목이 하나라도 있는가. 없으면 색인을 맡기지 않는다. 할 일이 없는 작업을 띄우지 않는다."""
    return any(entries for _, entries in parts.lorebooks)


class VersionIndexer(Protocol):
    """판의 로어북 항목을 벡터로 바꾸는 일을 뒤에서 돌게 맡기는 것. 구현은 app/lore/indexing.py 의 LoreIndexer 다."""

    def schedule(self, version_id: uuid.UUID) -> None:
        """이 판의 색인을 맡긴다. 기다리지 않고 바로 돌아온다."""
        ...


async def readiness(
    session: AsyncSession, owner_id: uuid.UUID, scenario: Scenario, allowed: Sequence[Rating]
) -> tuple[Parts, list[Problem]]:
    """
    게시해도 되는지 본다. 붙인 자산들과 게시할 수 없는 이유(없으면 빈 목록)를 돌려준다.

    성인용 초안인데 allowed 에 성인용이 없으면 AdultContentRequiredError 다(이유의 목록이 아니라 거절이다).
    게시(publish)와 미리 보기(check_publishable)가 함께 쓴다. 둘이 같은 답을 내야 한다.
    """
    require_rating(scenario.asset.rating, allowed)
    parts = await load_parts(session, owner_id, scenario)
    return parts, find_problems(scenario, parts)


async def check_publishable(
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, allowed: Sequence[Rating] = ALL_AGES_ONLY
) -> list[Problem]:
    """
    자기 시나리오를 지금 게시하면 막히는 이유를 전부 돌려준다(#428). 없으면 빈 목록이다. 판을 만들지 않는다.

    게시(publish)와 같은 검사(readiness)다. 잠그지 않는다. 읽기만 하고, 답한 뒤에 초안이 바뀔 수 있다.
    시나리오가 없으면 AssetNotFoundError, 볼 수 없는 등급이면 AdultContentRequiredError 다. 게시와 같다.
    """
    scenario = await assets.get_owned(session, Scenario, owner_id, scenario_id)
    _, problems = await readiness(session, owner_id, scenario, allowed)
    return problems


async def publish(
    session: AsyncSession,
    owner_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: VersionCreate,
    indexer: VersionIndexer,
    allowed: Sequence[Rating] = ALL_AGES_ONLY,
) -> ScenarioVersion:
    """
    자기 시나리오를 게시한다. 시나리오가 없으면 AssetNotFoundError, 조건을 갖추지 못했으면 ScenarioNotReadyError.
    성인용 초안인데 allowed 에 성인용이 없으면 AdultContentRequiredError(#390, app/assets/ratings.py).

    시나리오를 잠그고 한다. 번호는 "지금까지의 가장 큰 번호 + 1"이라, 두 요청이 동시에 세면 같은 번호를 얻는다.
    잠그면 나중 요청은 앞의 판이 저장된 뒤에 센다. DB 의 UNIQUE 는 잠금을 빠뜨렸을 때의 마지막 방어선이다.
    저장한 뒤에 로어북 항목의 색인을 맡긴다(항목이 있을 때만). 색인은 뒤에서 돌고, 실패해도 게시는 그대로다.
    커밋 전에 맡기면, 커밋이 실패했을 때 없는 판을 색인하려 한다.
    """
    scenario = await assets.lock_owned(session, Scenario, owner_id, scenario_id)
    parts, problems = await readiness(session, owner_id, scenario, allowed)
    if problems or parts.rulebook is None:
        raise ScenarioNotReadyError(problems)

    # 다음 번호는 지금까지의 가장 큰 번호에 1 을 더한 것이다
    number = await repository.last_number(session, scenario_id) + 1
    version = build_version(scenario, parts.rulebook, parts, number, data.note)
    repository.add_version(session, version)
    await session.commit()
    if has_lore(parts):
        indexer.schedule(version.id)
    return version


async def list_versions(session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID) -> list[ScenarioVersion]:
    """자기 시나리오의 판을 최근 것부터 전부 돌려준다. 시나리오가 없으면 AssetNotFoundError."""
    await assets.get_owned(session, Scenario, owner_id, scenario_id)
    return await repository.list_versions(session, scenario_id)


async def get_version(
    session: AsyncSession, owner_id: uuid.UUID, scenario_id: uuid.UUID, number: int
) -> ScenarioVersion:
    """자기 시나리오의 판 하나를 돌려준다. 시나리오나 판이 없으면 AssetNotFoundError."""
    await assets.get_owned(session, Scenario, owner_id, scenario_id)
    version = await repository.find_version(session, scenario_id, number)
    if version is None:
        raise AssetNotFoundError
    return version
