# trpg-server/app/assets/scenarios/snapshot.py

"""
판에 굳히는 내용의 모양과, 초안에서 그것을 만드는 방법.

판은 DB 에 문서 하나(JSON)로 들어간다. DB 는 문서의 안을 검증하지 못한다.
그래서 쓰는 쪽과 읽는 쪽이 모두 이 파일의 모양을 거친다. 이 파일이 문서의 계약이다.

판은 고치지 않는다. 모양이 바뀌어도 이미 굳힌 문서는 옛 모양 그대로 DB 에 남는다.
그래서 읽을 때 지금의 모양으로 올려 읽는다(read_snapshot). 저장된 문서는 건드리지 않는다.
옛 형식을 한 단계씩 올리는 함수들은 app/assets/scenarios/upgrades.py 에 있다. 형식을 올릴 때는 그 파일의 설명을 따른다.

여기의 함수는 DB 를 모른다. 이미 읽어 온 객체를 받아 모양만 바꾼다.
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, model_validator

from app.assets.bestiaries.models import Monster, MonsterKind
from app.assets.models import (
    DEFAULT_ROUND_MINUTES,
    DEFAULT_START_DAY,
    DEFAULT_START_HOUR,
    CharacterMode,
    HappeningEffectKind,
    ItemKind,
    ItemRarity,
    Lorebook,
    LoreEntry,
    LoreKind,
    NarrationStyle,
    NpcAttitude,
    NpcCaught,
    PlaceItemVisibility,
    QuestConditionKind,
    QuestMatch,
    QuestStart,
    Rating,
    RouteVisibility,
    Rulebook,
    Scenario,
    Surprise,
    World,
)
from app.assets.scenarios.upgrades import UPGRADES
from app.calendar.clock import TimeOfDay
from app.engine.action import DoorDevice
from app.engine.item_aids import ItemAid
from app.engine.item_effects import Effect
from app.engine.ruleset import InjuryNature, Ruleset
from app.engine.sheet import CharacterSheet, Sheet

# 문서의 모양이 바뀔 때 올리는 번호. 옛 판을 읽는 코드가 어느 모양인지 알 수 있다.
#   1: 도입부가 하나다(opening)
#   2: 스타팅이 여러 개다(openings)
#   3: 추천 인원(recommended_players)과 프리젠(pregens)이 있다
#   4: 룰북에 규칙(rules)이 있다
#   5: 프리젠에 시트(sheet)가 있고, 허용하는 캐릭터 방식(character_modes)과 기본 시트(default_sheet)가 있다
#   6: 규칙에 피해와 회복의 양을 나타내는 등급(magnitudes)이 있다
#   7: 규칙에 최대 HP 에 닿는 능력치(hp_ability)가 있고, 플레이어가 능력치를 정한 캐릭터의
#      최대 HP 를 구하는 값(player_made_hp)이 있다
#   8: 규칙에 점수제(point_buy)가 있다
#   9: 규칙에 점수를 주사위로 정하는 법(score_roll)이 있고, 다시 굴리게 해 줄 수 있는지(reroll_allowed)가 있다
#  10: 규칙에 죽음의 굴림(death_save)이 있다
#  11: 추천 문체(narration_style)가 있다
#  12: 로어북 항목에 종류(kind)가 있다
#  13: 인물 항목의 숫자(npc_sheets)와 기본 NPC 시트(default_npc_sheet)가 있다
#  14: 규칙에 부상(injuries), 부상 표(injury_table), 부상 표를 굴리는 때(injury_triggers), 노려 치기(called_shot)가 있다
#  15: 규칙에 치료(treatment)가 있고, 부상에 치료의 난이도(treat_difficulty)와 줄이는 라운드(treat_rounds)가 있다
#  16: 로어북 항목에 지목할 때 맞다고 받는 이름들(true_names)이 있다
#  17: 물건 항목의 규칙(items), 시작 소지품(starting_items), 프리젠의 소지품(pregens[].items)이 있다
#  18: 사건 항목의 퀘스트 규칙(quests)이 있다
#  19: 맵의 시작 장소(start_place)와 길(routes)이 있다
#  20: 길을 아는 때(routes[].visibility: open, fog, hidden)와 명소(landmarks)가 있다. 길의 hidden 은 없어졌다
#  21: 몬스터(monsters)가 있다. 시트를 적은 몬스터만 들어간다
#  22: 조우(encounters)가 있다. 맵의 장소에 판의 몬스터가 몇 마리 있는지다
#  23: 몬스터에 공격(attacks)과 네임드 표시(unique)가, 조우에 기습(surprise)이,
#      규칙에 차례를 정하는 능력치(initiative_ability)가 있다
#  24: 게임 안의 시계(clock: 시작하는 날과 시, 라운드 하나에 흐르는 기본 시간)가 있다
#  25: 오래 가는 부상이 낫기까지(heal_minutes), 치료가 앞당기는(treat_minutes), 덧나서 늦춰지는(delay_minutes)
#      기간이 라운드 수가 아니라 게임 안의 시간(분)이다. 짧은 부상은 그대로 라운드 수(rounds)다
#  26: 길에 한 칸 가는 데 걸리는 게임 안의 시간(routes[].travel_minutes)이 있다
#  27: 퀘스트 규칙에 드러난 때부터 세는 기한(quests[].time_limit_minutes)이 있다
#  28: 규칙에 쉬기(rest: 짧은 휴식, 긴 휴식, 되살아나기, 저절로 회복하기)가 있다
#  29: 몬스터에 쓰러뜨렸을 때 나오는 물건(drops: 물건 항목, 개수, 확률)이 있다
#  30: 퀘스트 규칙에 이루는 조건(quests[].conditions)과 그 조건을 맞추는 법(quests[].match: all, any)이 있다
#  31: 퀘스트 규칙에 드러나는 조건(quests[].reveal)과 그 조건을 맞추는 법(quests[].reveal_match)이 있다.
#      조건에 다른 퀘스트의 성공과 실패(quest_succeeded, quest_failed)가 있다
#  32: 장소에 놓인 물건(place_items: 장소, 물건, 개수, 보이기 open·hidden, 숨긴 것의 찾는 판정)이 있다
#  33: 퀘스트의 조건에 이룰 때 물건을 가져가는지(conditions[].consume)가 있다
#  34: 몬스터가 지닌 물건(monsters[].equipment, inventory: 물건 항목, 개수, 떨어질 확률)이 있다.
#      드롭(drops)은 없어졌다. 드롭은 지닌 것에서만 나온다
#  35: 아이템 규칙에 물건의 등급(items[].rarity: normal, rare, unique, epic, legendary)이 있다
#  36: 규칙에 훔치기(steal)가, 몬스터에 둔한지(dull)가 있다
#  37: 인물의 NPC 시트에 처음 태도(npc_sheets[].attitude: friendly, neutral, hostile)가 있다
#  38: 인물의 NPC 시트에 지닌 물건(npc_sheets[].equipment, inventory)과 둔한지(dull)가 있다. 몬스터와 같은 모양이다
#  39: 인물의 NPC 시트에 훔치다 들켰을 때(npc_sheets[].on_caught: hostile, fight)가 있다
#  40: 규칙에 빼앗긴 NPC 가 깨어날 때의 반응(robbed_wake: hostile, wary)이 있다. 태도에 경계(wary)가 더해졌다
#  41: 인물의 NPC 시트에 공격(npc_sheets[].attacks)이 있다. 몬스터의 공격과 같은 모양이다
#  42: 세계관에 참고 자료를 켤 수 있는지(world.references_allowed)가 있다(#482)
#  43: 퀘스트 규칙에 실패하는 조건(quests[].fail)과 그 조건을 맞추는 법(quests[].fail_match)이 있다(#367).
#      조건의 종류에 인물이 죽음(npc_dead)과 물건을 잃음(lose_item)이 더해졌다
#  44: 사건 규칙(happenings: 조건이 채워지면 한 번 일어나 캐릭터를 옮기는 것)이 있다(#367)
#  45: 규칙에 서술 지침(rulebook.rules.narration: 분위기, 판정 결과 단계마다의 묘사, 하지 말 것)이 있다(#616)
#  46: 돈이 있다(#278). 화폐(currency: 이름, 단위, 시작 돈, 사 주는 백분율), 물건의 값(items[].price),
#      프리젠이 더 받는 돈(pregens[].money), 퀘스트의 돈의 보상(quests[].reward_money), 상인(npc_sheets[].merchant)
#  47: 장비의 칸이 있다(#276). 규칙의 칸(rulebook.rules.equipment_slots), 물건이 들어가는 칸(items[].slots,
#      items[].slot_count), 시작할 때 착용하는 칸(starting_items[].wear, pregens[].items[].wear)
#  48: 장비가 공격과 방어에 든다(#276). 규칙의 방어 방식(rulebook.rules.armor)과 칸이 맞을 가중치
#      (equipment_slots[].hit_weight), 물건의 공격 보정과 방어(items[].attack, defense, guard),
#      NPC 와 몬스터가 착용한 칸(equipment[].wear), 공격의 무기(attacks[].weapon), 몬스터의 타고난 방어(natural_armor)
#  49: 세이브와 관통이 있다(#276). 규칙의 세이브 방식과 그 목표값, 관통의 기준값(armor.save_target, pierce_base),
#      물건의 관통력과 불굴 세이브(items[].ap, ward), 몬스터의 타고난 불굴 세이브(monsters[].ward)
#  50: 인물의 자리(npc_places: 인물이 처음 있는 맵의 장소)와 인물을 옮기는 사건의 효과(happenings[].effects[] 의
#      kind move_npc 와 그 인물 npc)가 있다(#282)
#  51: 장소마다의 커버(covers: 장소, 커버의 값)가 있다(#276 의 커버 세이브)
#  52: 길의 조건이 있다(#281). 지날 때마다 굴리는 넘기 판정(routes[].cross: 능력, 난이도, 실패의 피해)과
#      열쇠의 자물쇠(routes[].lock: 열쇠, 처음에 잠겼는가)
#  53: 문을 여는 다른 길이 있다(#281). 자물쇠를 따는 판정(routes[].lock.pick: 능력, 난이도, 도구),
#      한쪽의 빗장(routes[].bar: 있는 쪽, 처음에 걸렸는가), 문을 부수는 판정(routes[].force)
#  54: 길의 문을 다루는 사건의 효과가 있다(#281). happenings[].effects[] 의 kind lock_route, unlock_route,
#      repair_route 와 그 길의 두 끝(from_place, to_place), 잠그고 여는 장치(device)
#  55: 부서진 문을 고치는 판정이 있다(#281). routes[].repair: 능력, 난이도, 도구
#  56: 물건이 문에 다는 새 자물쇠일 수 있다(#281). items[].lock: 열쇠와 따는 판정
#  57: 무작위 조우 표(wanders: 장소(비우면 기본 표), 하루의 때, 확률, 몬스터의 줄)가 있다(#283)
#  58: 소모품이 부상을 풀 수 있다(#277). items[].cures: 룰북의 부상의 이름표들
#  59: 소모품을 던질 수 있다(#277). items[].throw: 던지는 판정 {ability, difficulty, harm}
#  60: 소모품을 치료에 붙여 쓸 수 있다(#277). items[].treat_bonus: 치료 판정의 보정에 더하는 값
#  61: 몬스터가 부상을 입는다(#799). rulebook.rules.injuries[].natures: 부상의 성질,
#      monsters[].immune, vulnerable: 타입의 면역에 더하고 빼는 성질
#  62: 소모품의 효과 목록(#800). items[].effects: 회복, 풀기, 피해, 부상. heals, cures 는 효과가 됐다.
#      rulebook.rules.item_check: 물건을 인물이나 몬스터에게 쓸 때 맞히는 판정(능력치, 난이도)
#  63: 모든 물건을 던진다(#801). items[].throw 는 판정(능력치, 난이도)만이고, 맞았을 때의 피해(harm)는
#      효과의 damage 가 됐다. 던지는 판정이 없는 물건은 룰북의 맞히는 판정(item_check)으로 던진다
#  64: 물건이 다른 행동을 거든다(#802). items[].aids: 행동(치료, 따기, 고치기, 부수기, 넘기), 보정, 없어지는 방식.
#      treat_bonus 는 치료의 거들기가 됐다. 따기와 고치기의 도구(tool)는 도구가 있어야 하는가(needs_tool)가 됐다
#  65: HP 말고 다른 수치가 있다(#804). rulebook.rules.resources: 이름표, 이름, 최소, 최대(기준, 능력치, 상한), 시작,
#      쉬기의 변화. 물건의 효과에 맞추기(adjust: 수치, 양)가 있다
#  66: 기술과 주문이 있다(#805). rulebook.rules.skills: 이름표, 이름, 비용(수치, 양), 대상(self, ally), 효과들.
#      시트(default_sheet, pregens[].sheet)에 아는 기술(skills)이 있다
SNAPSHOT_FORMAT = 66


# 길의 문을 다루는 사건의 효과(#281). 두 끝(from_place, to_place)이 판의 길 하나를 가리킨다
ROUTE_EFFECTS = frozenset(
    {HappeningEffectKind.LOCK_ROUTE, HappeningEffectKind.UNLOCK_ROUTE, HappeningEffectKind.REPAIR_ROUTE}
)


class EntrySnapshot(BaseModel):
    """
    로어북의 항목 하나. 종류를 적지 않은 것(평가 데이터, 테스트)은 기타다.

    true_names 는 인물을 지목할 때 맞다고 받는 이름들이다(app/rounds/naming.py). 비어 있으면 항목의 이름 하나다.
    적지 않은 것(평가 데이터, 테스트)은 비어 있다.
    """

    id: uuid.UUID
    name: str
    keywords: list[str]
    content: str
    kind: LoreKind = LoreKind.OTHER
    true_names: list[str] = []


class LorebookSnapshot(BaseModel):
    """로어북 하나와 그 항목 전부."""

    id: uuid.UUID
    title: str
    entries: list[EntrySnapshot]


class WorldSnapshot(BaseModel):
    """세계관."""

    id: uuid.UUID
    title: str
    setting: str
    gm_notes: str
    # 방장이 참고 자료를 켤 수 있는가(app/references/policy.py)
    references_allowed: bool = False


class RulebookSnapshot(BaseModel):
    """룰북. 진행 지침(AI 가 읽는 글)과 규칙(엔진이 실행하는 데이터)이다."""

    id: uuid.UUID
    title: str
    gm_guide: str
    rules: Ruleset


class ClockSnapshot(BaseModel):
    """
    게임 안의 시계. 테이블이 시작할 때의 시각(며칠째, 몇 시)과 라운드 하나에 흐르는 기본 시간(분).

    비우면 새 시나리오의 기본값(1일째 8시, 10분)이다. 형식 24 보다 옛 판은 올릴 때 이 값을 적는다(upgrades.py).
    """

    start_day: int = DEFAULT_START_DAY
    start_hour: int = DEFAULT_START_HOUR
    round_minutes: int = DEFAULT_ROUND_MINUTES


class PlayersSnapshot(BaseModel):
    """추천 인원."""

    min: int
    max: int


class CurrencySnapshot(BaseModel):
    """화폐(#278). 이름과 단위, 캐릭터 모두가 시작할 때 받는 돈, 상인이 사 주는 값의 백분율이다."""

    name: str
    unit: str = ''
    starting: int = 0
    sell_percent: int


class ItemStackSnapshot(BaseModel):
    """
    물건 몇 개. 판 안의 로어북 물건 항목 하나(entry_id)를 count 개다.

    wear 는 그중 하나를 시작할 때 착용하는 규칙의 칸들이다(#276). 비어 있으면 착용하지 않는다.
    """

    entry_id: uuid.UUID
    count: int
    wear: list[str] = []


class PickSnapshot(BaseModel):
    """
    자물쇠를 따는 판정(#281). 능력치, 난이도의 이름과 도구가 있어야 하는가(#802).

    도구는 그 행동을 거드는 물건이면 어느 것이든 된다. 형식 64 보다 옛 판의 특정 도구는 이것과 그 물건의 거들기가 된다.
    """

    ability: str
    difficulty: str | None = None
    needs_tool: bool = False


class ItemThrowSnapshot(BaseModel):
    """물건을 던지는 판정(#277). 능력치와 난이도(없으면 룰북의 기본)다. 맞으면 물건의 효과가 든다(#801)."""

    ability: str
    difficulty: str | None = None


class ItemLockSnapshot(BaseModel):
    """물건이 문에 다는 새 자물쇠(#281). 여는 열쇠(판 안의 물건 항목)와 따는 판정(없으면 못 딴다)."""

    key: uuid.UUID
    pick: PickSnapshot | None = None


class ItemRuleSnapshot(BaseModel):
    """
    아이템 규칙 하나. 판 안의 로어북 물건 항목 하나(entry_id)가 엔진에서 무엇인지다.

    effects 는 쓰면 대상에게 일어나는 일들이다(#800, app/engine/item_effects.py). 소모품에만 있다.
    rarity 는 물건의 등급이다.
    price 는 상인이 파는 값이다(#278). 비어 있으면 사고팔 수 없다.
    slots 는 착용할 때 들어갈 수 있는 규칙의 칸들, slot_count 는 그중 몇 칸을 함께 차지하는가다(#276).
    slots 가 비어 있으면 착용하지 않는 물건이다.
    lock 은 이 물건이 문에 다는 새 자물쇠일 때의 그 자물쇠다(#281).
    throw 는 던지는 판정이다(#277). aids 는 이 물건이 거드는 행동들이다(#802, app/engine/item_aids.py).
    """

    entry_id: uuid.UUID
    kind: ItemKind
    # 쓰면 일어나는 일들. 형식 62 보다 옛 판의 heals 는 회복, cures 는 풀기가 된다
    effects: list[Effect] = []
    rarity: ItemRarity = ItemRarity.NORMAL
    price: int | None = None
    slots: list[str] = []
    slot_count: int = 1
    # 무기의 공격 보정, 차지한 칸의 방어, 모든 부위의 방어(#276). 형식 48 보다 옛 판의 물건에는 없다
    attack: int | None = None
    defense: int | None = None
    guard: int | None = None
    # 무기의 관통력과 불굴 세이브의 값. 형식 49 보다 옛 판의 물건에는 없다
    ap: int | None = None
    ward: int | None = None
    # 문에 다는 새 자물쇠. 형식 56 보다 옛 판의 물건에는 없다
    lock: ItemLockSnapshot | None = None
    # 던지는 판정. 형식 59 보다 옛 판의 물건에는 없다
    throw: ItemThrowSnapshot | None = None
    # 거드는 행동들. 형식 64 보다 옛 판의 treat_bonus 는 치료의 거들기, 따기·고치기의 도구는 그 행동의 거들기가 된다
    aids: list[ItemAid] = []


class QuestConditionSnapshot(BaseModel):
    """
    퀘스트의 조건 하나. target 은 종류마다 판 안의 장소 항목, 몬스터, 물건 항목, 인물 항목, 사건 항목(퀘스트)이다.

    consume 은 물건 갖기(hold_item)를 이룰 때 그 물건을 가져가는지다(배달). 이루는 조건에만 있다.
    """

    kind: QuestConditionKind
    target: uuid.UUID
    count: int = 1
    consume: bool = False


class QuestRuleSnapshot(BaseModel):
    """
    퀘스트 규칙 하나. 판 안의 로어북 사건 항목 하나(entry_id)가 퀘스트로서 어떤지다.

    start 는 테이블이 시작할 때의 상태, reward 는 성공했을 때 받는 판 안의 물건, reward_money 는 받는 돈이다.
    time_limit_minutes 는 드러난 때부터 세는 기한(분)이다. 비어 있으면 기한이 없다.
    conditions 는 이루는 조건, match 는 그것을 모두 채워야 하는지 하나라도 되는지다. 조건이 없으면 성공하지 않는다.
    reveal 은 숨긴 퀘스트가 드러나는 조건, reveal_match 는 그것을 맞추는 법이다. 없으면 이루어야만 드러난다.
    fail 은 실패하는 조건, fail_match 는 그것을 맞추는 법이다. 없으면 기한으로만 실패한다.
    """

    entry_id: uuid.UUID
    start: QuestStart = QuestStart.HIDDEN
    reward: list[ItemStackSnapshot] = []
    reward_money: int = 0
    time_limit_minutes: int | None = None
    conditions: list[QuestConditionSnapshot] = []
    match: QuestMatch = QuestMatch.ALL
    reveal: list[QuestConditionSnapshot] = []
    reveal_match: QuestMatch = QuestMatch.ALL
    fail: list[QuestConditionSnapshot] = []
    fail_match: QuestMatch = QuestMatch.ALL


class HappeningEffectSnapshot(BaseModel):
    """
    사건의 효과 하나. 캐릭터 옮기기(move), 인물 옮기기(move_npc, #282), 길의 문 다루기(#281)다.
    장소는 판의 맵의 장소 항목이다.

    move: from_place 가 없으면 죽지 않은 캐릭터 모두를, 있으면 그 장소에 서 있던 죽지 않은 캐릭터만 to_place 로 옮긴다.
    move_npc: 판 안의 인물 항목 하나(npc)를 to_place 로 옮긴다. 죽은 인물은 옮기지 않는다. from_place 는 없다.
    lock_route, unlock_route, repair_route: 두 끝이 from_place 와 to_place 인 길(방향은 보지 않는다)의 문을
    잠그고, 열고, 고친다. 잠그고 열기는 device 의 장치만, 비었으면 그 문의 장치 모두다. 형식 54 보다 옛 판에는 없다.
    """

    kind: HappeningEffectKind
    to_place: uuid.UUID
    from_place: uuid.UUID | None = None
    npc: uuid.UUID | None = None
    device: DoorDevice | None = None


class HappeningSnapshot(BaseModel):
    """
    사건 규칙 하나(#367). 판 안의 로어북 사건 항목 하나(entry_id)다. 조건(when)이 채워지면 한 번 일어나 효과를 낸다.

    조건의 모양은 퀘스트의 것과 같다. match 는 그것을 모두 채워야 하는지 하나라도 되는지다.
    """

    entry_id: uuid.UUID
    when: list[QuestConditionSnapshot]
    match: QuestMatch = QuestMatch.ALL
    effects: list[HappeningEffectSnapshot]


class FindSnapshot(BaseModel):
    """숨긴 길을 찾는 판정. 판 안의 룰북의 능력치와 난이도의 이름이다. 난이도가 없으면 규칙의 기본 난이도다."""

    ability: str
    difficulty: str | None = None


class CrossSnapshot(BaseModel):
    """길을 넘는 판정(#281). 판 안의 룰북의 능력치, 난이도, 실패했을 때 다치는 양의 등급의 이름이다."""

    ability: str
    difficulty: str | None = None
    harm: str | None = None


class LockSnapshot(BaseModel):
    """길의 자물쇠(#281). 여는 열쇠(판 안의 물건 항목), 시작할 때 잠겨 있는가, 따는 판정(없으면 못 딴다)."""

    key: uuid.UUID
    locked: bool = True
    pick: PickSnapshot | None = None


class BarSnapshot(BaseModel):
    """길의 빗장(#281). 있는 쪽(길의 한 끝)과 시작할 때 걸려 있는가."""

    side: uuid.UUID
    barred: bool = False


class ForceSnapshot(BaseModel):
    """문을 부수는 판정(#281). 능력치와 난이도의 이름이다."""

    ability: str
    difficulty: str | None = None


class RepairSnapshot(PickSnapshot):
    """부서진 문을 고치는 판정(#281). 능력치, 난이도의 이름과 있어야 하는 도구(판 안의 물건 항목, 없으면 None)."""


class RouteSnapshot(BaseModel):
    """
    길 하나. 판 안의 로어북 장소 항목 둘을 잇는다.

    two_way 가 아니면 from_place 에서 to_place 로만 간다. visibility 는 플레이어가 길을 언제 아는가다.
    숨긴 길은 찾는 판정(find)으로 드러난다. travel_minutes 는 한 칸 가는 데 걸리는 게임 안의 시간(분)이다.
    비어 있으면 라운드의 걸음 안에서 간다. 형식 26 보다 옛 판은 모두 비어 있다.
    cross 는 지날 때마다 굴리는 넘기 판정, lock 은 열쇠의 자물쇠다(#281). 형식 52 보다 옛 판은 둘 다 없다.
    bar 는 한쪽의 빗장, force 는 문을 부수는 판정이다. 형식 53 보다 옛 판은 둘 다 없고 자물쇠를 따지 못한다.
    repair 는 부서진 문을 고치는 판정이다. 형식 55 보다 옛 판은 없다(고치지 못한다).
    """

    from_place: uuid.UUID
    to_place: uuid.UUID
    two_way: bool = True
    visibility: RouteVisibility = RouteVisibility.OPEN
    find: FindSnapshot | None = None
    travel_minutes: int | None = None
    cross: CrossSnapshot | None = None
    lock: LockSnapshot | None = None
    bar: BarSnapshot | None = None
    force: ForceSnapshot | None = None
    repair: RepairSnapshot | None = None


class PregenSnapshot(BaseModel):
    """
    프리젠 하나. 제작자가 미리 만들어 둔 캐릭터다. 판 안의 프리젠은 모두 시트가 있다.

    items 와 money 는 이 프리젠을 고른 사람이 시작할 때 더 받는 소지품과 돈이다.
    """

    name: str
    description: str
    sheet: CharacterSheet
    items: list[ItemStackSnapshot] = []
    money: int = 0


class CarriedItemSnapshot(BaseModel):
    """
    몬스터나 NPC 가 지닌 물건 한 줄. 판 안의 로어북 물건 항목 하나(entry_id)를 count 개 지녔다. 몬스터는 마리마다다.

    chance(%)는 처음 쓰러졌을 때 이 줄이 떨어질 확률이다.
    """

    entry_id: uuid.UUID
    count: int
    chance: int
    # 착용한 칸들(#276). 장비의 줄에만 있다. 형식 48 보다 옛 판에는 없다
    wear: list[str] = []


class AttackSnapshot(BaseModel):
    """몬스터의 공격 하나. 이름표(능력치, 난이도, 양의 등급)는 판 안의 규칙의 것이다."""

    name: str
    ability: str
    difficulty: str
    harm: str
    # 이 공격에 쓰는 무기(#276). 시트의 장비 줄의 물건이다. 형식 48 보다 옛 판의 공격은 맨몸이다
    weapon: uuid.UUID | None = None


class NpcSheetSnapshot(BaseModel):
    """NPC 시트 하나. 판 안의 로어북 인물 항목 하나(entry_id)의 숫자와 처음 태도와 지닌 물건이다."""

    entry_id: uuid.UUID
    sheet: Sheet
    # 처음 태도. 형식 37 보다 옛 판의 인물은 중립이다
    attitude: NpcAttitude = NpcAttitude.NEUTRAL
    # 지닌 물건. 줄의 번호는 장비 다음 소지품의 차례다(app/tables/npc_items.py).
    # 형식 38 보다 옛 판의 인물은 아무것도 지니지 않고 둔하지 않다
    equipment: list[CarriedItemSnapshot] = []
    inventory: list[CarriedItemSnapshot] = []
    dull: bool = False
    # 훔치다 들켰을 때. 형식 39 보다 옛 판의 인물은 적대만 한다
    on_caught: NpcCaught = NpcCaught.HOSTILE
    # 공격들. 몬스터의 것과 같은 모양이다. 형식 41 보다 옛 판의 인물은 공격이 없다
    attacks: list[AttackSnapshot] = []
    # 상인인가(#278). 소지품 중 값이 있는 물건을 팔고, 값이 있는 물건을 사 준다. 형식 46 보다 옛 판의 인물은 아니다
    merchant: bool = False


class NaturalArmorSnapshot(BaseModel):
    """몬스터의 한 부위의 타고난 방어(#276). 칸은 판 안의 규칙의 장비의 칸이다."""

    slot: str
    defense: int


class MonsterSnapshot(BaseModel):
    """
    몬스터 하나. 도감의 몬스터(글과 타입)와 시나리오의 몬스터 시트(숫자)를 합친 것이다.

    한 종류다. 테이블에 몇 마리가 나오든 판에는 하나다. 어느 도감에서 왔는지는 플레이에 쓰지 않아서 싣지 않는다.
    """

    id: uuid.UUID
    name: str
    content: str
    kind: MonsterKind
    sheet: Sheet
    # 공격들. 비어 있으면 공격하지 않는다
    attacks: list[AttackSnapshot] = []
    # 네임드 몹인가. 판 전체에서 한 마리다(Snapshot.require_unique_once)
    unique: bool = False
    # 지닌 물건. 장비와 소지품이다. 쓰러뜨렸을 때의 드롭은 여기서만 나온다.
    # 줄의 번호는 장비 다음 소지품의 차례다(app/tables/monster_items.py). 형식 34 보다 옛 판의 드롭은 소지품이다
    equipment: list[CarriedItemSnapshot] = []
    inventory: list[CarriedItemSnapshot] = []
    # 둔한가. 둔하면 훔치기가 쉽다(규칙의 steal.dull). 형식 36 보다 옛 판의 몬스터는 둔하지 않다
    dull: bool = False
    # 부위마다 타고난 방어(#276). 형식 48 보다 옛 판의 몬스터는 없다
    natural_armor: list[NaturalArmorSnapshot] = []
    # 타고난 불굴 세이브. 형식 49 보다 옛 판의 몬스터는 없다
    ward: int | None = None
    # 타입의 면역에 더하고 빼는 부상의 성질(#799). 형식 61 보다 옛 판의 몬스터는 타입의 면역 그대로다
    immune: list[InjuryNature] = []
    vulnerable: list[InjuryNature] = []


class EncounterSnapshot(BaseModel):
    """조우 하나. 판 안의 로어북 장소 항목 하나(place_id)에 판의 몬스터 하나(monster_id)가 count 마리 있다."""

    place_id: uuid.UUID
    monster_id: uuid.UUID
    count: int
    surprise: Surprise = Surprise.NONE


class PlaceItemSnapshot(BaseModel):
    """
    장소에 놓인 물건 한 줄. 판 안의 장소 항목 하나(place_id)에 판 안의 물건 항목 하나(entry_id)가 count 개 있다.

    숨긴 물건(hidden)은 찾는 판정(find)으로 드러난다. 판의 줄 순서가 테이블의 남은 개수(table_place_items)의 번호다.
    """

    place_id: uuid.UUID
    entry_id: uuid.UUID
    count: int
    visibility: PlaceItemVisibility = PlaceItemVisibility.OPEN
    find: FindSnapshot | None = None


class NpcPlaceSnapshot(BaseModel):
    """인물의 자리 하나(#282). 판 안의 인물 항목 하나(entry_id)가 처음에 판 안의 장소 항목 하나(place_id)에 있다."""

    entry_id: uuid.UUID
    place_id: uuid.UUID


class CoverSnapshot(BaseModel):
    """장소 하나의 커버. 판 안의 장소 항목 하나(place_id)에 숨을 곳이 얼마나 좋은지(cover)다."""

    place_id: uuid.UUID
    cover: int


class WanderMonsterSnapshot(BaseModel):
    """무작위 조우 표의 한 줄(#283). 판의 몬스터 하나(monster_id)가 count 마리, 뽑힐 몫(weight), 누가 기습하는가."""

    monster_id: uuid.UUID
    count: int
    weight: int
    surprise: Surprise = Surprise.NONE


class WanderTableSnapshot(BaseModel):
    """
    무작위 조우 표 하나(#283). 판 안의 장소 항목 하나(place_id, 비우면 기본 표)에서 하루의 때(times, 비우면 언제나)에
    쓴다. 한 번 굴리면 chance% 로 조우가 나고, 나면 몬스터의 줄 하나를 몫대로 뽑는다.
    """

    place_id: uuid.UUID | None = None
    times: list[TimeOfDay] = []
    chance: int
    monsters: list[WanderMonsterSnapshot] = []


class PlayerMadeHpSnapshot(BaseModel):
    """플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 기준값과 상한이다."""

    base: int
    cap: int


class Snapshot(BaseModel):
    """
    판 하나의 내용 전부. 플레이에 필요한 것이 이 안에 다 있다.

    각 자산의 id 는 굳힐 때의 초안을 가리킨다. 어디서 왔는지 알려 줄 뿐이고, 판을 읽을 때 초안을 다시 보지 않는다.
    gm_guide 와 gm_notes 가 들어 있다. 만든 사람이 아닌 사람에게 이 문서를 그대로 내주면 안 된다.
    """

    format: int = SNAPSHOT_FORMAT
    title: str
    description: str
    # 이용 등급. 시나리오의 것만 굳힌다. 재료(룰북, 세계관, 로어북)의 등급은 보지 않는다.
    # 테이블에 누가 들어올 수 있는지와, AI 에게 주는 지침이 이 값에 따라 달라진다
    rating: Rating
    # 스타팅들. 하나 이상이다. 테이블을 만들 때 이 중 하나를 순번으로 고른다.
    # 판은 바뀌지 않으므로 순번이 밀리지 않는다
    openings: list[str]
    # 추천 인원. 강제하지 않는다
    recommended_players: PlayersSnapshot
    # 프리젠들. 플레이어가 테이블에 앉을 때 골라서 가져갈 수 있다
    pregens: list[PregenSnapshot]
    # 허용하는 캐릭터 방식들. 하나 이상이다. 테이블은 이 안에서만 고를 수 있다
    character_modes: list[CharacterMode]
    # 기본 시트. 캐릭터를 직접 만든 사람이 받는 숫자다. 직접 만들기를 허용했으면 반드시 있다
    default_sheet: CharacterSheet | None
    # NPC 시트들. 판 안의 로어북 인물 항목마다 많아야 하나다
    npc_sheets: list[NpcSheetSnapshot]
    # 기본 NPC 시트. 시트가 없는 인물이 쓴다. 그런 인물이 있으면 반드시 있다
    default_npc_sheet: Sheet | None
    # 몬스터들. 시나리오가 시트를 적은 몬스터만이다. 하나하나가 숫자를 갖는다
    monsters: list[MonsterSnapshot] = []
    # 조우들. 장소는 판 안의 로어북 장소 항목, 몬스터는 위의 몬스터다. 조우가 있으면 시작 장소도 있다
    encounters: list[EncounterSnapshot] = []
    # 아이템 규칙들. 판 안의 로어북 물건 항목마다 많아야 하나다. 규칙이 없는 물건은 장비다(item_rule_of)
    items: list[ItemRuleSnapshot] = []
    # 시작 소지품. 캐릭터 모두가 테이블이 시작할 때 받는다
    starting_items: list[ItemStackSnapshot] = []
    # 화폐(#278). 없으면 돈이 없는 판이다. 값, 상인, 돈의 보상이 있으면 반드시 있다
    currency: CurrencySnapshot | None = None
    # 퀘스트 규칙들. 판 안의 로어북 사건 항목마다 많아야 하나다. 규칙이 없는 사건은 숨긴 채로 시작한다(quest_rule_of)
    quests: list[QuestRuleSnapshot] = []
    # 맵의 시작 장소. 판 안의 로어북 장소 항목이다. 없으면 맵이 없는 판이다(위치도 이동도 없다)
    start_place: uuid.UUID | None = None
    # 맵의 길들. 두 끝이 판 안의 로어북 장소 항목이다. 길이 있으면 시작 장소도 있다
    routes: list[RouteSnapshot] = []
    # 명소. 처음부터 아는 장소들이다. 판 안의 로어북 장소 항목이다. 명소가 있으면 시작 장소도 있다
    landmarks: list[uuid.UUID] = []
    # 장소에 놓인 물건들. 장소는 판 안의 장소 항목, 물건은 판 안의 물건 항목이다. 있으면 시작 장소도 있다
    place_items: list[PlaceItemSnapshot] = []
    # 장소마다의 커버(#276). 장소는 판 안의 장소 항목이다. 있으면 시작 장소도 있다. 형식 50 보다 옛 판에는 없다
    covers: list[CoverSnapshot] = []
    # 무작위 조우 표들(#283). 장소는 판 안의 장소 항목이고 몬스터는 판의 몬스터다. 있으면 시작 장소도 있다.
    # 형식 57 보다 옛 판에는 없다
    wanders: list[WanderTableSnapshot] = []
    # 사건 규칙들. 판 안의 로어북 사건 항목마다 많아야 하나다. 효과의 장소는 판의 맵의 장소다(#367)
    happenings: list[HappeningSnapshot] = []
    # 인물의 자리들(#282). 인물 하나에 많아야 하나다. 인물은 판 안의 인물 항목, 장소는 판 안의 장소 항목이다.
    # 있으면 시작 장소도 있다. 자리가 없는 인물은 장면의 글로 나온다
    npc_places: list[NpcPlaceSnapshot] = []
    # 플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 그런 방식을 허용했으면 반드시 있다
    player_made_hp: PlayerMadeHpSnapshot | None
    # 주사위로 정한 점수를 방장이 다시 굴리게 해 줄 수 있는가. 제작자가 정한 것이다
    reroll_allowed: bool
    # 추천 문체. 테이블의 방장이 문체를 고르지 않으면 이것으로 서술한다
    narration_style: NarrationStyle
    # 게임 안의 시계. 테이블의 시계가 여기서 시작한다(app/calendar)
    clock: ClockSnapshot = ClockSnapshot()
    rulebook: RulebookSnapshot
    world: WorldSnapshot | None
    lorebooks: list[LorebookSnapshot]

    @model_validator(mode='after')
    def require_npc_sheets(self) -> 'Snapshot':
        """
        모든 인물 항목이 받을 숫자가 있는지 본다. 시트가 없는 인물이 있는데 기본 NPC 시트가 없으면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 여기는 그것을 판의 계약으로 굳혀 두는 것이다.
        판을 읽는 쪽(테이블의 시작)은 인물마다 숫자가 있다고 믿고 쓴다.
        """
        covered = {npc_sheet.entry_id for npc_sheet in self.npc_sheets}
        uncovered = [entry for entry in person_entries(self) if entry.id not in covered]
        if uncovered and self.default_npc_sheet is None:
            raise ValueError('시트가 없는 인물이 있는데 기본 NPC 시트가 없습니다.')
        return self

    @model_validator(mode='after')
    def reject_duplicate_monsters(self) -> 'Snapshot':
        """
        같은 몬스터가 두 번 있으면 거부한다. 어느 숫자를 쓸지 정할 수 없다.

        시나리오의 입력에서 이미 막는다(scenarios/schemas.py). 판을 읽는 쪽은 몬스터의 id 로 하나를 찾는다.
        """
        monster_ids = [monster.id for monster in self.monsters]
        if len(set(monster_ids)) != len(monster_ids):
            raise ValueError('같은 몬스터가 두 번 있습니다.')
        return self

    @model_validator(mode='after')
    def require_encounter_targets(self) -> 'Snapshot':
        """
        조우가 모두 판 안의 장소 항목과 판의 몬스터를 가리키는지, 조우가 있으면 시작 장소가 있는지 본다.
        아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py).
        판을 읽는 쪽(테이블의 시작)은 마리마다 숫자와 자리가 있다고 믿고 쓴다.
        """
        places = {entry.id for entry in place_entries(self)}
        monsters = {monster.id for monster in self.monsters}
        if any(encounter.place_id not in places for encounter in self.encounters):
            raise ValueError('장소 항목이 아닌 것을 가리키는 조우가 있습니다.')
        if any(encounter.monster_id not in monsters for encounter in self.encounters):
            raise ValueError('판에 없는 몬스터를 가리키는 조우가 있습니다.')
        if self.encounters and self.start_place is None:
            raise ValueError('조우가 있는데 시작 장소가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_unique_once(self) -> 'Snapshot':
        """
        네임드 몹은 판 전체에서 한 마리다. 조우 한 줄에 한 마리, 그런 줄이 하나뿐이어야 한다. 아니면 거부한다.

        게시할 때 이미 막는다(unique_monster_repeated). 읽는 쪽은 네임드 몹을 번호 없이 부른다.
        """
        unique = {monster.id for monster in self.monsters if monster.unique}
        counts = [encounter.count for encounter in self.encounters if encounter.monster_id in unique]
        lines = [encounter.monster_id for encounter in self.encounters if encounter.monster_id in unique]
        if any(count > 1 for count in counts) or len(lines) != len(set(lines)):
            raise ValueError('네임드 몹이 두 마리 이상 있습니다.')
        return self

    @model_validator(mode='after')
    def require_item_entries(self) -> 'Snapshot':
        """
        아이템 규칙과 소지품(퀘스트의 보상 포함)이 모두 판 안의 물건 항목을 가리키는지 본다. 아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 판을 읽는 쪽(테이블)은 소지품마다 물건 항목이 있다고 믿고 쓴다.
        """
        items = {entry.id for entry in item_entries(self)}
        stacks = [
            *self.starting_items,
            *(stack for pregen in self.pregens for stack in pregen.items),
            *(stack for quest in self.quests for stack in quest.reward),
        ]
        pointed = [rule.entry_id for rule in self.items] + [stack.entry_id for stack in stacks]
        if any(entry_id not in items for entry_id in pointed):
            raise ValueError('물건 항목이 아닌 것을 가리키는 아이템 규칙이나 소지품이 있습니다.')
        return self

    @model_validator(mode='after')
    def require_route_keys(self) -> 'Snapshot':
        """
        길의 자물쇠와 자물쇠 물건마다 열쇠가 판 안의 물건 항목이고, 열쇠 하나가 자물쇠 하나만 여는지 본다(#281).
        아니면 거부한다.

        게시할 때 이미 막는다(item_not_item, route_key_repeated). 테이블은 열쇠로 그 길 하나를 찾는다.
        """
        items = {entry.id for entry in item_entries(self)}
        keys = route_keys(self) + item_lock_keys(self)
        if any(key not in items for key in keys):
            raise ValueError('물건 항목이 아닌 것을 열쇠로 적은 자물쇠가 있습니다.')
        if len(set(keys)) != len(keys):
            raise ValueError('열쇠 하나가 두 자물쇠를 엽니다.')
        return self

    @model_validator(mode='after')
    def require_fitting_wear(self) -> 'Snapshot':
        """
        시작할 때의 착용이 맞는지 본다(#276). 시작 소지품만으로도, 프리젠마다 그 소지품을 더해서도 본다.
        아니면 거부한다.

        게시할 때 이미 막는다(starting_wear_invalid). 판을 읽는 쪽(테이블의 시작)은 그대로 끼운다.
        """
        slot_keys = {slot.key for slot in self.rulebook.rules.equipment_slots}
        fits = {rule.entry_id: (rule.slots, rule.slot_count) for rule in self.items}
        groups = [self.starting_items, *([*self.starting_items, *pregen.items] for pregen in self.pregens)]
        if any(wear_fault(slot_keys, fits, group) for group in groups):
            raise ValueError('시작할 때의 착용이 규칙의 칸이나 물건의 칸과 맞지 않습니다.')
        return self

    @model_validator(mode='after')
    def require_currency(self) -> 'Snapshot':
        """
        돈을 쓰는 칸(물건의 값, 상인, 프리젠의 돈, 퀘스트의 돈의 보상)이 있으면 화폐가 있는지 본다. 아니면 거부한다.

        게시할 때 이미 막는다(currency_missing). 판을 읽는 쪽(거래, 보상)은 돈이 있으면 화폐도 있다고 믿고 쓴다.
        """
        uses_money = (
            any(rule.price is not None for rule in self.items)
            or any(npc_sheet.merchant for npc_sheet in self.npc_sheets)
            or any(pregen.money for pregen in self.pregens)
            or any(quest.reward_money for quest in self.quests)
        )
        if uses_money and self.currency is None:
            raise ValueError('돈을 쓰는 칸이 있는데 화폐가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_place_entries(self) -> 'Snapshot':
        """
        시작 장소, 길의 두 끝, 명소가 모두 판 안의 장소 항목인지, 길이나 명소가 있으면 시작 장소가 있는지 본다.
        아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 판을 읽는 쪽(테이블)은 위치마다 장소 항목이 있다고 믿고 쓴다.
        """
        places = {entry.id for entry in place_entries(self)}
        pointed = [route_end for route in self.routes for route_end in (route.from_place, route.to_place)]
        pointed.extend(self.landmarks)
        if self.start_place is not None:
            pointed.append(self.start_place)
        if any(place not in places for place in pointed):
            raise ValueError('장소 항목이 아닌 것을 가리키는 시작 장소, 길, 명소가 있습니다.')
        if (self.routes or self.landmarks) and self.start_place is None:
            raise ValueError('길이나 명소가 있는데 시작 장소가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_place_item_targets(self) -> 'Snapshot':
        """
        놓인 물건이 모두 판 안의 장소 항목과 물건 항목을 가리키는지, 놓인 물건이 있으면 시작 장소가 있는지 본다.
        아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 판을 읽는 쪽(테이블)은 줄마다 장소와 물건이 있다고 믿고 쓴다.
        """
        places = {entry.id for entry in place_entries(self)}
        things = {entry.id for entry in item_entries(self)}
        if any(rule.place_id not in places or rule.entry_id not in things for rule in self.place_items):
            raise ValueError('장소나 물건이 아닌 것을 가리키는 놓인 물건이 있습니다.')
        if self.place_items and self.start_place is None:
            raise ValueError('놓인 물건이 있는데 시작 장소가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_cover_places(self) -> 'Snapshot':
        """
        커버가 모두 판 안의 장소 항목을 가리키는지, 커버가 있으면 시작 장소가 있는지 본다. 아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 판을 읽는 쪽(app/rounds/covers.py)은 장소가 있다고 믿고 쓴다.
        """
        places = {entry.id for entry in place_entries(self)}
        if any(rule.place_id not in places for rule in self.covers):
            raise ValueError('장소 항목이 아닌 것을 가리키는 커버가 있습니다.')
        if self.covers and self.start_place is None:
            raise ValueError('커버가 있는데 시작 장소가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_wander_targets(self) -> 'Snapshot':
        """
        무작위 조우 표가 모두 판 안의 장소 항목과 판의 몬스터를 가리키는지, 표가 있으면 시작 장소가 있는지 본다(#283).
        아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 판을 읽는 쪽은 나온 몬스터에 숫자와 자리가 있다고 믿고 쓴다.
        """
        places = {entry.id for entry in place_entries(self)}
        monsters = {monster.id for monster in self.monsters}
        if any(table.place_id is not None and table.place_id not in places for table in self.wanders):
            raise ValueError('장소 항목이 아닌 것을 가리키는 조우 표가 있습니다.')
        if any(line.monster_id not in monsters for table in self.wanders for line in table.monsters):
            raise ValueError('판에 없는 몬스터를 가리키는 조우 표가 있습니다.')
        if self.wanders and self.start_place is None:
            raise ValueError('조우 표가 있는데 시작 장소가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_quest_entries(self) -> 'Snapshot':
        """
        퀘스트 규칙이 모두 판 안의 사건 항목을 가리키는지 본다. 아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 판을 읽는 쪽(테이블)은 퀘스트마다 사건 항목이 있다고 믿고 쓴다.
        """
        events = {entry.id for entry in quest_entries(self)}
        if any(rule.entry_id not in events for rule in self.quests):
            raise ValueError('사건 항목이 아닌 것을 가리키는 퀘스트 규칙이 있습니다.')
        return self

    @model_validator(mode='after')
    def require_happening_targets(self) -> 'Snapshot':
        """
        사건 규칙이 모두 판 안의 사건 항목을 가리키고, 효과의 장소가 모두 판 안의 장소 항목인지,
        옮기는 인물(move_npc)이 판 안의 인물 항목인지,
        문을 다루는 효과(#281)가 문이 있는 길과 그 길의 장치를 가리키는지 본다.
        사건이 있으면 시작 장소가 있는지도 본다(옮길 맵이 있어야 한다). 아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py).
        판을 읽는 쪽(app/rounds/happenings.py)은 장소가 있다고 믿고 쓴다.
        """
        events = {entry.id for entry in quest_entries(self)}
        places = {entry.id for entry in place_entries(self)}
        people = {entry.id for entry in person_entries(self)}
        effects = [effect for rule in self.happenings for effect in rule.effects]
        pointed = [place for effect in effects for place in (effect.to_place, effect.from_place) if place is not None]
        moved = [effect.npc for effect in effects if effect.kind == HappeningEffectKind.MOVE_NPC]
        doors = [effect for effect in effects if effect.kind in ROUTE_EFFECTS]
        if any(rule.entry_id not in events for rule in self.happenings):
            raise ValueError('사건 항목이 아닌 것을 가리키는 사건 규칙이 있습니다.')
        if any(place not in places for place in pointed):
            raise ValueError('장소 항목이 아닌 것을 가리키는 사건의 효과가 있습니다.')
        if any(npc not in people for npc in moved):
            raise ValueError('인물 항목이 아닌 것을 옮기는 사건의 효과가 있습니다.')
        if any(not door_effect_fits(self, effect) for effect in doors):
            raise ValueError('문이 없는 길이나 그 길에 없는 장치를 다루는 사건의 효과가 있습니다.')
        if self.happenings and self.start_place is None:
            raise ValueError('사건 규칙이 있는데 시작 장소가 없습니다.')
        return self

    @model_validator(mode='after')
    def require_npc_place_targets(self) -> 'Snapshot':
        """
        인물의 자리가 모두 판 안의 인물 항목과 장소 항목을 가리키는지, 자리가 있으면 시작 장소가 있는지 본다.
        아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 테이블을 시작할 때 인물을 그 장소에 둔다(app/tables/npcs.py).
        """
        people = {entry.id for entry in person_entries(self)}
        places = {entry.id for entry in place_entries(self)}
        if any(place.entry_id not in people for place in self.npc_places):
            raise ValueError('인물 항목이 아닌 것을 가리키는 인물의 자리가 있습니다.')
        if any(place.place_id not in places for place in self.npc_places):
            raise ValueError('장소 항목이 아닌 것을 가리키는 인물의 자리가 있습니다.')
        if self.npc_places and self.start_place is None:
            raise ValueError('인물의 자리가 있는데 시작 장소가 없습니다.')
        return self


class WornStack(Protocol):
    """시작할 때 착용을 적은 줄. 시나리오의 입력(ItemStack)과 판(ItemStackSnapshot)이 이 모양이다."""

    entry_id: uuid.UUID
    wear: list[str]


def wear_fault(
    slot_keys: set[str], fits: Mapping[uuid.UUID, tuple[list[str], int]], stacks: Sequence[WornStack]
) -> bool:
    """
    한 캐릭터가 시작할 때 받을 줄들의 착용이 틀렸는가(#276).

    slot_keys 는 규칙의 칸들, fits 는 물건마다 (들어갈 수 있는 칸, 차지하는 칸의 수)다.
    규칙이 없는 물건은 착용하지 않는다. 착용한 칸은 규칙에 있고, 그 물건이 들어갈 수 있는 칸이고,
    차지하는 칸의 수와 같아야 한다. 두 줄이 한 칸을 함께 쓰지 않는다.
    """
    used: list[str] = []
    for stack in stacks:
        if not stack.wear:
            continue
        slots, count = fits.get(stack.entry_id, ([], 1))
        if len(stack.wear) != count or any(slot not in slots or slot not in slot_keys for slot in stack.wear):
            return True
        used.extend(stack.wear)
    return len(set(used)) != len(used)


def person_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 인물 항목만. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.PERSON]


def item_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 물건 항목만. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.ITEM]


def place_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 장소 항목만. 맵의 장소다. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.PLACE]


def npc_place_of(snapshot: Snapshot, entry_id: uuid.UUID) -> uuid.UUID | None:
    """인물 하나가 처음 있는 장소(#282). 자리를 적지 않은 인물이면 None 이다."""
    return next((place.place_id for place in snapshot.npc_places if place.entry_id == entry_id), None)


def cover_at(snapshot: Snapshot, place_id: uuid.UUID | None) -> int:
    """그 장소의 커버. 커버가 없거나 장소가 없으면(맵에 서 있지 않다) 0 이다."""
    return next((rule.cover for rule in snapshot.covers if rule.place_id == place_id), 0)


def route_keys(snapshot: Snapshot) -> list[uuid.UUID]:
    """길의 자물쇠마다의 열쇠. 판의 길 순서다(#281)."""
    return [route.lock.key for route in snapshot.routes if route.lock is not None]


def item_locks(snapshot: Snapshot) -> list[ItemLockSnapshot]:
    """자물쇠 물건마다의 자물쇠(#281). 판의 아이템 규칙 순서다."""
    return [rule.lock for rule in snapshot.items if rule.lock is not None]


def item_lock_keys(snapshot: Snapshot) -> list[uuid.UUID]:
    """자물쇠 물건마다의 열쇠(#281). 판의 아이템 규칙 순서다."""
    return [lock.key for lock in item_locks(snapshot)]


def door_devices(route: RouteSnapshot) -> list[DoorDevice]:
    """그 길의 문에 있는 장치들(#281). 자물쇠, 빗장의 차례다. 문이 없는 길이면 빈 목록이다."""
    present = [(DoorDevice.LOCK, route.lock), (DoorDevice.BAR, route.bar)]
    return [device for device, part in present if part is not None]


def route_between(snapshot: Snapshot, one: uuid.UUID, other: uuid.UUID) -> RouteSnapshot | None:
    """두 끝이 그 둘인 판의 길(#281). 방향도, 플레이어가 아는지도 보지 않는다. 없으면 None."""
    return next((route for route in snapshot.routes if {route.from_place, route.to_place} == {one, other}), None)


def door_effect_fits(snapshot: Snapshot, effect: HappeningEffectSnapshot) -> bool:
    """
    문을 다루는 사건의 효과(#281)가 문이 있는 길을 가리키고, 장치를 적었으면 그 장치가 그 길에 있는가.

    두 끝 사이에 길이 없거나, 길에 문이 없거나, 적은 장치가 없으면 거짓이다.
    """
    route = route_between(snapshot, effect.from_place, effect.to_place)
    if route is None or not door_devices(route):
        return False
    return effect.device is None or effect.device in door_devices(route)


def has_map(snapshot: Snapshot) -> bool:
    """맵이 있는 판인가. 시작 장소가 있어야 캐릭터가 설 곳이 있다."""
    return snapshot.start_place is not None


def quest_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 사건 항목만. 사건 하나가 퀘스트 하나다. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.EVENT]


def quest_rule_of(snapshot: Snapshot, entry_id: uuid.UUID) -> QuestRuleSnapshot:
    """사건 항목 하나의 퀘스트 규칙. 적어 둔 규칙이 있으면 그것, 없으면 숨긴 채로 시작하고 보상이 없다."""
    own = next((rule for rule in snapshot.quests if rule.entry_id == entry_id), None)
    return own or QuestRuleSnapshot(entry_id=entry_id)


def item_rule_of(snapshot: Snapshot, entry_id: uuid.UUID) -> ItemRuleSnapshot:
    """물건 항목 하나의 규칙. 적어 둔 규칙이 있으면 그것, 없으면 노말 장비다(쓰지 않는 물건)."""
    own = next((rule for rule in snapshot.items if rule.entry_id == entry_id), None)
    return own or ItemRuleSnapshot(entry_id=entry_id, kind=ItemKind.GEAR)


def monster_of(snapshot: Snapshot, monster_id: uuid.UUID) -> MonsterSnapshot:
    """
    판의 몬스터 하나. 조우가 가리키는 몬스터를 찾을 때 쓴다.

    조우가 판에 없는 몬스터를 가리키는 판은 읽을 때 이미 거부됐다(Snapshot.require_encounter_targets).
    """
    return next(monster for monster in snapshot.monsters if monster.id == monster_id)


def npc_sheet_of(snapshot: Snapshot, entry_id: uuid.UUID) -> Sheet:
    """
    인물 항목 하나가 받을 숫자. 그 인물의 NPC 시트가 있으면 그것, 없으면 기본 NPC 시트다.

    기본 NPC 시트가 필요한데 없는 판은 읽을 때 이미 거부됐다(Snapshot.require_npc_sheets).
    """
    own = next((npc_sheet.sheet for npc_sheet in snapshot.npc_sheets if npc_sheet.entry_id == entry_id), None)
    return own or snapshot.default_npc_sheet


def own_npc_sheet(snapshot: Snapshot, entry_id: uuid.UUID) -> NpcSheetSnapshot | None:
    """인물 항목 하나에 적은 NPC 시트. 적지 않았으면(기본 NPC 시트를 받는 인물) None 이다."""
    return next((npc_sheet for npc_sheet in snapshot.npc_sheets if npc_sheet.entry_id == entry_id), None)


def npc_attitude_of(snapshot: Snapshot, entry_id: uuid.UUID) -> NpcAttitude:
    """인물 항목 하나의 처음 태도. 그 인물의 NPC 시트가 있으면 그 태도, 없으면 중립이다."""
    own = own_npc_sheet(snapshot, entry_id)
    return own.attitude if own else NpcAttitude.NEUTRAL


def snapshot_entry(entry: LoreEntry) -> EntrySnapshot:
    """항목을 굳힌다."""
    return EntrySnapshot(
        id=entry.id,
        name=entry.name,
        keywords=entry.keywords,
        content=entry.content,
        kind=LoreKind(entry.kind),
        true_names=list(entry.true_names),
    )


def snapshot_monster(
    monster: Monster,
    sheet: Sheet,
    attacks: list[AttackSnapshot],
    equipment: list[CarriedItemSnapshot],
    inventory: list[CarriedItemSnapshot],
    dull: bool = False,
    natural_armor: list[NaturalArmorSnapshot] | None = None,
    ward: int | None = None,
    immune: list[InjuryNature] | None = None,
    vulnerable: list[InjuryNature] | None = None,
) -> MonsterSnapshot:
    """몬스터와 그 시트, 공격, 지닌 물건, 둔한지, 타고난 방어와 불굴 세이브, 면역에 더하고 빼는 성질을 굳힌다."""
    return MonsterSnapshot(
        id=monster.id,
        name=monster.name,
        content=monster.content,
        kind=MonsterKind(monster.kind),
        sheet=sheet,
        attacks=attacks,
        unique=monster.unique,
        equipment=equipment,
        inventory=inventory,
        dull=dull,
        natural_armor=natural_armor or [],
        ward=ward,
        immune=immune or [],
        vulnerable=vulnerable or [],
    )


def snapshot_lorebook(lorebook: Lorebook, entries: list[LoreEntry]) -> LorebookSnapshot:
    """로어북과 그 항목들을 굳힌다."""
    return LorebookSnapshot(
        id=lorebook.asset_id, title=lorebook.asset.title, entries=[snapshot_entry(entry) for entry in entries]
    )


def snapshot_world(world: World) -> WorldSnapshot:
    """세계관을 굳힌다."""
    return WorldSnapshot(
        id=world.asset_id,
        title=world.asset.title,
        setting=world.setting,
        gm_notes=world.gm_notes,
        references_allowed=world.references_allowed,
    )


def snapshot_rulebook(rulebook: Rulebook) -> RulebookSnapshot:
    """룰북을 굳힌다. 규칙은 문서에서 Ruleset 으로 읽어 모양을 확인하고 싣는다."""
    return RulebookSnapshot(
        id=rulebook.asset_id,
        title=rulebook.asset.title,
        gm_guide=rulebook.gm_guide,
        rules=Ruleset.model_validate(rulebook.rules),
    )


def build_snapshot(
    scenario: Scenario,
    rulebook: Rulebook,
    world: World | None,
    lorebooks: list[tuple[Lorebook, list[LoreEntry]]],
    monsters: list[MonsterSnapshot],
) -> Snapshot:
    """
    시나리오와 그것이 가리키는 자산들에서 판의 내용을 만든다.

    몬스터는 이미 시트와 합친 것을 받는다. 어느 몬스터에 시트가 있는지는 게시하는 쪽이 도감과 견주어 고른다.
    """
    return Snapshot(
        title=scenario.asset.title,
        description=scenario.asset.description,
        rating=scenario.asset.rating,
        openings=list(scenario.openings),
        recommended_players=PlayersSnapshot(**scenario.recommended_players),
        pregens=[PregenSnapshot(**pregen) for pregen in scenario.pregens],
        character_modes=list(scenario.character_modes),
        default_sheet=scenario.default_sheet,
        npc_sheets=[NpcSheetSnapshot(**npc_sheet) for npc_sheet in scenario.npc_sheets],
        default_npc_sheet=scenario.default_npc_sheet,
        monsters=monsters,
        encounters=[EncounterSnapshot(**encounter) for encounter in scenario.encounters],
        items=[ItemRuleSnapshot(**rule) for rule in scenario.items],
        starting_items=[ItemStackSnapshot(**stack) for stack in scenario.starting_items],
        currency=CurrencySnapshot(**scenario.currency) if scenario.currency else None,
        quests=[QuestRuleSnapshot(**quest) for quest in scenario.quests],
        start_place=scenario.start_place,
        routes=[RouteSnapshot(**route) for route in scenario.routes],
        landmarks=list(scenario.landmarks),
        place_items=[PlaceItemSnapshot(**rule) for rule in scenario.place_items],
        covers=[CoverSnapshot(**rule) for rule in scenario.covers],
        wanders=[WanderTableSnapshot(**table) for table in scenario.wanders],
        happenings=[HappeningSnapshot(**rule) for rule in scenario.happenings],
        npc_places=[NpcPlaceSnapshot(**place) for place in scenario.npc_places],
        player_made_hp=scenario.player_made_hp,
        reroll_allowed=scenario.reroll_allowed,
        narration_style=scenario.narration_style,
        clock=ClockSnapshot(**scenario.clock),
        rulebook=snapshot_rulebook(rulebook),
        world=snapshot_world(world) if world else None,
        lorebooks=[snapshot_lorebook(lorebook, entries) for lorebook, entries in lorebooks],
    )


def read_snapshot(document: dict) -> Snapshot:
    """
    DB 에서 꺼낸 문서를 지금의 모양으로 읽는다. 옛 형식이면 올려서 읽는다.

    받은 문서는 고치지 않는다. 올린 결과를 DB 에 다시 쓰지도 않는다.
    """
    while document['format'] in UPGRADES:
        document = UPGRADES[document['format']](document)
    return Snapshot.model_validate(document)
