# game-server/app/assets/scenarios/snapshot.py

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

from pydantic import BaseModel, model_validator

from app.assets.models import (
    CharacterMode,
    ItemKind,
    Lorebook,
    LoreEntry,
    LoreKind,
    NarrationStyle,
    QuestStart,
    Rating,
    RouteVisibility,
    Rulebook,
    Scenario,
    World,
)
from app.assets.scenarios.upgrades import UPGRADES
from app.engine.ruleset import Ruleset
from app.engine.sheet import Sheet

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
SNAPSHOT_FORMAT = 20


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


class RulebookSnapshot(BaseModel):
    """룰북. 진행 지침(AI 가 읽는 글)과 규칙(엔진이 실행하는 데이터)이다."""

    id: uuid.UUID
    title: str
    gm_guide: str
    rules: Ruleset


class PlayersSnapshot(BaseModel):
    """추천 인원."""

    min: int
    max: int


class ItemStackSnapshot(BaseModel):
    """물건 몇 개. 판 안의 로어북 물건 항목 하나(entry_id)를 count 개다."""

    entry_id: uuid.UUID
    count: int


class ItemRuleSnapshot(BaseModel):
    """
    아이템 규칙 하나. 판 안의 로어북 물건 항목 하나(entry_id)가 엔진에서 무엇인지다.

    heals 는 판 안의 룰북의 등급(magnitudes)의 이름이다. 소모품에만 있다.
    """

    entry_id: uuid.UUID
    kind: ItemKind
    heals: str | None = None


class QuestRuleSnapshot(BaseModel):
    """
    퀘스트 규칙 하나. 판 안의 로어북 사건 항목 하나(entry_id)가 퀘스트로서 어떤지다.

    start 는 테이블이 시작할 때의 상태, reward 는 성공했을 때 받는 판 안의 물건이다.
    """

    entry_id: uuid.UUID
    start: QuestStart = QuestStart.HIDDEN
    reward: list[ItemStackSnapshot] = []


class FindSnapshot(BaseModel):
    """숨긴 길을 찾는 판정. 판 안의 룰북의 능력치와 난이도의 이름이다. 난이도가 없으면 규칙의 기본 난이도다."""

    ability: str
    difficulty: str | None = None


class RouteSnapshot(BaseModel):
    """
    길 하나. 판 안의 로어북 장소 항목 둘을 잇는다.

    two_way 가 아니면 from_place 에서 to_place 로만 간다. visibility 는 플레이어가 길을 언제 아는가다.
    숨긴 길은 찾는 판정(find)으로 드러난다.
    """

    from_place: uuid.UUID
    to_place: uuid.UUID
    two_way: bool = True
    visibility: RouteVisibility = RouteVisibility.OPEN
    find: FindSnapshot | None = None


class PregenSnapshot(BaseModel):
    """
    프리젠 하나. 제작자가 미리 만들어 둔 캐릭터다. 판 안의 프리젠은 모두 시트가 있다.

    items 는 이 프리젠을 고른 사람이 시작할 때 더 받는 소지품이다.
    """

    name: str
    description: str
    sheet: Sheet
    items: list[ItemStackSnapshot] = []


class NpcSheetSnapshot(BaseModel):
    """NPC 시트 하나. 판 안의 로어북 인물 항목 하나(entry_id)의 숫자다."""

    entry_id: uuid.UUID
    sheet: Sheet


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
    default_sheet: Sheet | None
    # NPC 시트들. 판 안의 로어북 인물 항목마다 많아야 하나다
    npc_sheets: list[NpcSheetSnapshot]
    # 기본 NPC 시트. 시트가 없는 인물이 쓴다. 그런 인물이 있으면 반드시 있다
    default_npc_sheet: Sheet | None
    # 아이템 규칙들. 판 안의 로어북 물건 항목마다 많아야 하나다. 규칙이 없는 물건은 장비다(item_rule_of)
    items: list[ItemRuleSnapshot] = []
    # 시작 소지품. 캐릭터 모두가 테이블이 시작할 때 받는다
    starting_items: list[ItemStackSnapshot] = []
    # 퀘스트 규칙들. 판 안의 로어북 사건 항목마다 많아야 하나다. 규칙이 없는 사건은 숨긴 채로 시작한다(quest_rule_of)
    quests: list[QuestRuleSnapshot] = []
    # 맵의 시작 장소. 판 안의 로어북 장소 항목이다. 없으면 맵이 없는 판이다(위치도 이동도 없다)
    start_place: uuid.UUID | None = None
    # 맵의 길들. 두 끝이 판 안의 로어북 장소 항목이다. 길이 있으면 시작 장소도 있다
    routes: list[RouteSnapshot] = []
    # 명소. 처음부터 아는 장소들이다. 판 안의 로어북 장소 항목이다. 명소가 있으면 시작 장소도 있다
    landmarks: list[uuid.UUID] = []
    # 플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 그런 방식을 허용했으면 반드시 있다
    player_made_hp: PlayerMadeHpSnapshot | None
    # 주사위로 정한 점수를 방장이 다시 굴리게 해 줄 수 있는가. 제작자가 정한 것이다
    reroll_allowed: bool
    # 추천 문체. 테이블의 방장이 문체를 고르지 않으면 이것으로 서술한다
    narration_style: NarrationStyle
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
    def require_quest_entries(self) -> 'Snapshot':
        """
        퀘스트 규칙이 모두 판 안의 사건 항목을 가리키는지 본다. 아니면 거부한다.

        게시할 때 이미 막는다(scenarios/publishing.py). 판을 읽는 쪽(테이블)은 퀘스트마다 사건 항목이 있다고 믿고 쓴다.
        """
        events = {entry.id for entry in quest_entries(self)}
        if any(rule.entry_id not in events for rule in self.quests):
            raise ValueError('사건 항목이 아닌 것을 가리키는 퀘스트 규칙이 있습니다.')
        return self


def person_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 인물 항목만. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.PERSON]


def item_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 물건 항목만. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.ITEM]


def place_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 장소 항목만. 맵의 장소다. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.PLACE]


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
    """물건 항목 하나의 규칙. 적어 둔 규칙이 있으면 그것, 없으면 장비다(쓰지 않는 물건)."""
    own = next((rule for rule in snapshot.items if rule.entry_id == entry_id), None)
    return own or ItemRuleSnapshot(entry_id=entry_id, kind=ItemKind.GEAR)


def npc_sheet_of(snapshot: Snapshot, entry_id: uuid.UUID) -> Sheet:
    """
    인물 항목 하나가 받을 숫자. 그 인물의 NPC 시트가 있으면 그것, 없으면 기본 NPC 시트다.

    기본 NPC 시트가 필요한데 없는 판은 읽을 때 이미 거부됐다(Snapshot.require_npc_sheets).
    """
    own = next((npc_sheet.sheet for npc_sheet in snapshot.npc_sheets if npc_sheet.entry_id == entry_id), None)
    return own or snapshot.default_npc_sheet


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


def snapshot_lorebook(lorebook: Lorebook, entries: list[LoreEntry]) -> LorebookSnapshot:
    """로어북과 그 항목들을 굳힌다."""
    return LorebookSnapshot(
        id=lorebook.asset_id, title=lorebook.asset.title, entries=[snapshot_entry(entry) for entry in entries]
    )


def snapshot_world(world: World) -> WorldSnapshot:
    """세계관을 굳힌다."""
    return WorldSnapshot(id=world.asset_id, title=world.asset.title, setting=world.setting, gm_notes=world.gm_notes)


def snapshot_rulebook(rulebook: Rulebook) -> RulebookSnapshot:
    """룰북을 굳힌다. 규칙은 문서에서 Ruleset 으로 읽어 모양을 확인하고 싣는다."""
    return RulebookSnapshot(
        id=rulebook.asset_id,
        title=rulebook.asset.title,
        gm_guide=rulebook.gm_guide,
        rules=Ruleset.model_validate(rulebook.rules),
    )


def build_snapshot(
    scenario: Scenario, rulebook: Rulebook, world: World | None, lorebooks: list[tuple[Lorebook, list[LoreEntry]]]
) -> Snapshot:
    """시나리오와 그것이 가리키는 자산들에서 판의 내용을 만든다."""
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
        items=[ItemRuleSnapshot(**rule) for rule in scenario.items],
        starting_items=[ItemStackSnapshot(**stack) for stack in scenario.starting_items],
        quests=[QuestRuleSnapshot(**quest) for quest in scenario.quests],
        start_place=scenario.start_place,
        routes=[RouteSnapshot(**route) for route in scenario.routes],
        landmarks=list(scenario.landmarks),
        player_made_hp=scenario.player_made_hp,
        reroll_allowed=scenario.reroll_allowed,
        narration_style=scenario.narration_style,
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
