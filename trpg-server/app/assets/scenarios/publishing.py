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
    Encounter,
    FindCheck,
    ItemRule,
    ItemStack,
    MonsterAttack,
    MonsterSheet,
    NpcSheet,
    PlaceItem,
    Pregen,
    QuestCondition,
    QuestRule,
    RouteRule,
    VersionCreate,
)
from app.assets.scenarios.snapshot import (
    AttackSnapshot,
    CarriedItemSnapshot,
    MonsterSnapshot,
    build_snapshot,
    snapshot_monster,
)
from app.assets.service import AssetNotFoundError
from app.engine.check import find_ability, find_difficulty
from app.engine.health import find_magnitude
from app.engine.ruleset import Ruleset
from app.engine.sheet import Sheet, fits


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
    # 룰북의 규칙에 없는 등급을 회복의 양(heals)으로 적은 소모품이 있다
    ITEM_MAGNITUDE_MISSING = 'item_magnitude_missing'
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
    # 놓인 물건이 맵에 없는 장소(시작 장소, 길의 끝, 명소가 아닌 곳)에 있다. 아무도 그곳에 설 수 없다
    PLACE_ITEM_OFF_MAP = 'place_item_off_map'
    # 숨긴 물건을 찾는 판정의 능력치나 난이도가 룰북의 규칙에 없다
    PLACE_ITEM_FIND_INVALID = 'place_item_find_invalid'
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
    # 네임드 몹이 두 마리 이상 놓인다. 조우 한 줄에 둘 이상이거나, 두 줄 이상에 나온다
    UNIQUE_MONSTER_REPEATED = 'unique_monster_repeated'


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


def read_pregen_sheets(scenario: Scenario) -> list[Sheet | None]:
    """프리젠들의 시트를 읽는다. 시트가 없는 프리젠의 자리는 None 이다."""
    documents = [pregen.get('sheet') for pregen in scenario.pregens]
    return [Sheet.model_validate(document) if document else None for document in documents]


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
    if ruleset and not fits(ruleset, Sheet.model_validate(scenario.default_sheet)):
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
    if ruleset and any(attack_fault(ruleset, attack) for npc_sheet in npc_sheets for attack in npc_sheet.attacks):
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
    if ruleset and any(attack_fault(ruleset, attack) for sheet in monster_sheets for attack in sheet.attacks):
        problems.append(Problem.MONSTER_ATTACK_INVALID)
    return problems


def attack_fault(ruleset: Ruleset, attack: MonsterAttack) -> bool:
    """이 공격의 능력치, 난이도, 양의 등급 중 룰북의 규칙에 없는 것이 있는가."""
    return (
        find_ability(ruleset, attack.ability) is None
        or find_difficulty(ruleset, attack.difficulty) is None
        or find_magnitude(ruleset, attack.harm) is None
    )


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
    몬스터와 NPC 마다 지닌 물건(장비와 소지품), 장소에 놓인 물건.
    """
    stacks = [ItemStack.model_validate(document) for document in scenario.starting_items]
    for document in scenario.pregens:
        stacks.extend(Pregen.model_validate(document).items)
    for quest in read_quest_rules(scenario):
        stacks.extend(quest.reward)
    sheets = [*read_monster_sheets(scenario), *read_npc_sheets(scenario)]
    carried = [line.entry_id for sheet in sheets for line in [*sheet.equipment, *sheet.inventory]]
    placed = [rule.entry_id for rule in read_place_items(scenario)]
    rules = [rule.entry_id for rule in read_item_rules(scenario)]
    return rules + [stack.entry_id for stack in stacks] + carried + placed


def find_item_problems(scenario: Scenario, parts: Parts, ruleset: Ruleset | None) -> list[Problem]:
    """
    아이템 규칙과 소지품에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만 적는다.

    가리키는 것은 붙인 로어북의 물건 항목이어야 한다. NPC 시트와 같은 까닭으로 굳히기 전에 여기서 막는다.
    소모품의 회복의 양은 룰북의 등급이어야 한다. 룰북이 없으면 볼 수 없다(그때는 RULEBOOK_MISSING 이다).
    """
    entries = lore_entries(parts)
    pointed = item_references(scenario)
    problems = []
    if any(entry_id not in entries for entry_id in pointed):
        problems.append(Problem.ITEM_ENTRY_MISSING)
    if any(entry_id in entries and entries[entry_id].kind != LoreKind.ITEM for entry_id in pointed):
        problems.append(Problem.ITEM_NOT_ITEM)
    heals = [rule.heals for rule in read_item_rules(scenario) if rule.heals is not None]
    if ruleset and any(find_magnitude(ruleset, key) is None for key in heals):
        problems.append(Problem.ITEM_MAGNITUDE_MISSING)
    return problems


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
    QuestConditionKind.QUEST_SUCCEEDED: LoreKind.EVENT,
    QuestConditionKind.QUEST_FAILED: LoreKind.EVENT,
}


def placed_count(scenario: Scenario, monster_id: uuid.UUID) -> int:
    """판의 조우에 놓인 그 몬스터의 마리 수 전부."""
    return sum(encounter.count for encounter in read_encounters(scenario) if encounter.monster_id == monster_id)


def can_succeed(scenario: Scenario, entry_id: uuid.UUID) -> bool:
    """그 퀘스트가 성공할 수 있는가. 이루는 조건이 있어야 한다. 규칙이 없는 사건은 성공하지 않는다."""
    return any(rule.entry_id == entry_id and rule.conditions for rule in read_quest_rules(scenario))


def condition_problem(condition: QuestCondition, scenario: Scenario, parts: Parts) -> Problem | None:
    """
    조건 하나의 문제. 없으면 None.

    몬스터를 쓰러뜨리기는 시트를 적은 몬스터여야 하고(판에 들어가는 몬스터), 놓인 마리보다 많이 요구하지 않는다.
    장소에 닿기는 맵의 장소여야 한다(시작 장소, 길의 끝, 명소). 맵에 없는 장소에는 설 수 없다.
    다른 퀘스트의 성공을 기다리면 그 퀘스트에 이루는 조건이 있어야 한다. 없으면 성공하지 않는다.
    실패는 기한이나 방장이 정하므로 따로 보지 않는다.
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
    return None


def find_condition_problems(scenario: Scenario, parts: Parts) -> list[Problem]:
    """
    퀘스트의 조건들(이루는 조건, 드러나는 조건)에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만, 정한 순서로 적는다.
    """
    found = {
        condition_problem(condition, scenario, parts)
        for rule in read_quest_rules(scenario)
        for condition in [*rule.conditions, *rule.reveal]
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


def read_routes(scenario: Scenario) -> list[RouteRule]:
    """길들을 읽는다."""
    return [RouteRule.model_validate(document) for document in scenario.routes]


def map_places(scenario: Scenario, routes: list[RouteRule]) -> list[uuid.UUID]:
    """맵이 가리키는 장소 전부. 시작 장소, 길마다의 두 끝, 명소."""
    places = [place for route in routes for place in (route.from_place, route.to_place)]
    places.extend(scenario.landmarks)
    if scenario.start_place is not None:
        places.append(scenario.start_place)
    return places


def find_invalid(find: FindCheck | None, ruleset: Ruleset) -> bool:
    """찾는 판정(숨긴 길, 숨긴 물건)이 룰북의 규칙에 맞지 않는가. 능력치와 난이도가 규칙에 있어야 한다."""
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


def find_map_problems(scenario: Scenario, parts: Parts, ruleset: Ruleset | None) -> list[Problem]:
    """
    맵(시작 장소, 길, 명소)에서 문제를 찾는다. 여럿 틀려도 같은 문제는 한 번만 적는다.

    가리키는 것은 붙인 로어북의 장소 항목이어야 한다. 아이템 규칙과 같은 까닭으로 굳히기 전에 여기서 막는다.
    길이나 명소가 있으면 시작 장소가 있어야 한다.
    숨긴 길을 찾는 판정은 룰북의 능력치와 난이도여야 한다(룰북이 없으면 못 본다).
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
    problems.extend(find_player_made_problems(scenario))
    problems.extend(find_point_buy_problems(scenario, ruleset))
    problems.extend(find_score_roll_problems(scenario, ruleset))
    problems.extend(find_npc_sheet_problems(scenario, parts, ruleset))
    problems.extend(find_default_npc_sheet_problems(scenario, parts, ruleset))
    problems.extend(find_monster_sheet_problems(scenario, parts, ruleset))
    problems.extend(find_encounter_problems(scenario, parts))
    problems.extend(find_unique_problems(scenario, parts))
    problems.extend(find_item_problems(scenario, parts, ruleset))
    problems.extend(find_quest_problems(scenario, parts))
    problems.extend(find_map_problems(scenario, parts, ruleset))
    problems.extend(find_place_item_problems(scenario, ruleset))
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
    require_rating(scenario.asset.rating, allowed)
    parts = await load_parts(session, owner_id, scenario)

    problems = find_problems(scenario, parts)
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
