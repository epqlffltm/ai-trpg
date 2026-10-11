# game-server/app/assets/scenarios/snapshot.py

"""
판에 굳히는 내용의 모양과, 초안에서 그것을 만드는 방법.

판은 DB 에 문서 하나(JSON)로 들어간다. DB 는 문서의 안을 검증하지 못한다.
그래서 쓰는 쪽과 읽는 쪽이 모두 이 파일의 모양을 거친다. 이 파일이 문서의 계약이다.

판은 고치지 않는다. 모양이 바뀌어도 이미 굳힌 문서는 옛 모양 그대로 DB 에 남는다.
그래서 읽을 때 지금의 모양으로 올려 읽는다(read_snapshot). 저장된 문서는 건드리지 않는다.

여기의 함수는 DB 를 모른다. 이미 읽어 온 객체를 받아 모양만 바꾼다.
"""

import uuid
from collections.abc import Callable

from pydantic import BaseModel, model_validator

from app.assets.models import (
    DEFAULT_NARRATION_STYLE,
    TABLE_MAX_PLAYERS,
    CharacterMode,
    Lorebook,
    LoreEntry,
    LoreKind,
    NarrationStyle,
    Rating,
    Rulebook,
    Scenario,
    World,
)
from app.engine.ruleset import Ruleset
from app.engine.sheet import Sheet
from app.engine.templates import SRD5

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
SNAPSHOT_FORMAT = 14

# 시트가 없던 때의 판을 읽을 때 채우는 숫자. 모든 능력치가 이 점수이고, 최대 HP 가 이 값이다.
# 그때의 규칙은 SRD5 템플릿뿐이었다. 10 은 그 규칙에서 보정이 0 인 점수다
BASELINE_SCORE = 10
BASELINE_MAX_HP = 10


class EntrySnapshot(BaseModel):
    """로어북의 항목 하나. 종류를 적지 않은 것(평가 데이터, 테스트)은 기타다."""

    id: uuid.UUID
    name: str
    keywords: list[str]
    content: str
    kind: LoreKind = LoreKind.OTHER


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


class PregenSnapshot(BaseModel):
    """프리젠 하나. 제작자가 미리 만들어 둔 캐릭터다. 판 안의 프리젠은 모두 시트가 있다."""

    name: str
    description: str
    sheet: Sheet


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


def person_entries(snapshot: Snapshot) -> list[EntrySnapshot]:
    """판의 로어북에서 인물 항목만. 로어북의 순서, 그 안의 항목 순서다."""
    return [entry for lorebook in snapshot.lorebooks for entry in lorebook.entries if entry.kind == LoreKind.PERSON]


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
        id=entry.id, name=entry.name, keywords=entry.keywords, content=entry.content, kind=LoreKind(entry.kind)
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
        player_made_hp=scenario.player_made_hp,
        reroll_allowed=scenario.reroll_allowed,
        narration_style=scenario.narration_style,
        rulebook=snapshot_rulebook(rulebook),
        world=snapshot_world(world) if world else None,
        lorebooks=[snapshot_lorebook(lorebook, entries) for lorebook, entries in lorebooks],
    )


def upgrade_from_1(document: dict) -> dict:
    """형식 1 의 문서를 형식 2 로 올린다. 하나뿐이던 도입부가 첫 번째 스타팅이 된다."""
    upgraded = {key: value for key, value in document.items() if key != 'opening'}
    upgraded['openings'] = [document['opening']]
    upgraded['format'] = 2
    return upgraded


def upgrade_from_2(document: dict) -> dict:
    """
    형식 2 의 문서를 형식 3 으로 올린다.

    그때는 추천 인원과 프리젠이 없었다. 추천 인원은 "몇 명이든 된다"로, 프리젠은 없는 것으로 읽는다.
    """
    upgraded = dict(document)
    upgraded['recommended_players'] = {'min': 1, 'max': TABLE_MAX_PLAYERS}
    upgraded['pregens'] = []
    upgraded['format'] = 3
    return upgraded


def upgrade_from_3(document: dict) -> dict:
    """
    형식 3 의 문서를 형식 4 로 올린다.

    그때는 룰북에 규칙이 없었다. 그때 만든 룰북이 지금 받았을 규칙(SRD5 템플릿)으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션). 내놓은 템플릿의 값은 고치지 않으므로 읽을 때마다 같다.

    지금의 SRD5 에는 나중에 생긴 칸(magnitudes, hp_ability, point_buy, score_roll, death_save, 부상의 칸들)도 들어 있다.
    뒤의 단계가 같은 값으로 다시 채우므로 결과는 같다.
    """
    upgraded = dict(document)
    upgraded['rulebook'] = {**document['rulebook'], 'rules': SRD5.model_dump(mode='json')}
    upgraded['format'] = 4
    return upgraded


def baseline_sheet(rules: dict) -> dict:
    """규칙의 능력치를 모두 기준 점수로 채운 시트를 문서로 만든다. 시트가 없던 판을 읽을 때 쓴다."""
    abilities = {ability['key']: BASELINE_SCORE for ability in rules['abilities']}
    return {'abilities': abilities, 'max_hp': BASELINE_MAX_HP}


def upgrade_from_4(document: dict) -> dict:
    """
    형식 4 의 문서를 형식 5 로 올린다.

    그때는 캐릭터에 숫자가 없었고, 프리젠을 고를 수도 직접 만들 수도 있었다.
    두 방식을 모두 허용한 것으로 읽고, 프리젠의 시트와 기본 시트는 기준 시트로 읽는다.
    """
    sheet = baseline_sheet(document['rulebook']['rules'])
    upgraded = dict(document)
    upgraded['pregens'] = [{**pregen, 'sheet': sheet} for pregen in document['pregens']]
    # 그때 있던 방식은 이 둘이다. 글자 그대로 적는다. 방식이 나중에 늘어도 옛 판이 허용한 것은 늘지 않는다
    upgraded['character_modes'] = ['pregen', 'custom']
    upgraded['default_sheet'] = sheet
    upgraded['format'] = 5
    return upgraded


def upgrade_from_5(document: dict) -> dict:
    """
    형식 5 의 문서를 형식 6 으로 올린다.

    그때는 규칙에 양의 등급이 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 등급으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    """
    magnitudes = SRD5.model_dump(mode='json')['magnitudes']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'magnitudes': magnitudes}}
    upgraded['format'] = 6
    return upgraded


def upgrade_from_6(document: dict) -> dict:
    """
    형식 6 의 문서를 형식 7 로 올린다.

    그때는 규칙에 최대 HP 에 닿는 능력치가 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).

    플레이어가 능력치를 정하는 방식도 없었다. 그 방식에 쓰는 값(player_made_hp)은 없는 것으로 읽는다.
    """
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['player_made_hp'] = None
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'hp_ability': SRD5.hp_ability}}
    upgraded['format'] = 7
    return upgraded


def upgrade_from_7(document: dict) -> dict:
    """
    형식 7 의 문서를 형식 8 로 올린다.

    그때는 규칙에 점수제가 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    규칙에 점수제가 있다고 그 판에서 점수제를 쓸 수 있는 것은 아니다. 판이 허용한 방식(character_modes)은 그대로다.
    """
    point_buy = SRD5.model_dump(mode='json')['point_buy']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'point_buy': point_buy}}
    upgraded['format'] = 8
    return upgraded


def upgrade_from_8(document: dict) -> dict:
    """
    형식 8 의 문서를 형식 9 로 올린다.

    그때는 규칙에 점수를 주사위로 정하는 법이 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    규칙에 그 법이 있다고 그 판에서 주사위로 정할 수 있는 것은 아니다. 판이 허용한 방식(character_modes)은 그대로다.

    주사위로 정하는 방식이 없었으니 다시 굴리기도 없었다. 다시 굴리게 해 줄 수 없는 것으로 읽는다.
    """
    score_roll = SRD5.model_dump(mode='json')['score_roll']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['reroll_allowed'] = False
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'score_roll': score_roll}}
    upgraded['format'] = 9
    return upgraded


def upgrade_from_9(document: dict) -> dict:
    """
    형식 9 의 문서를 형식 10 으로 올린다.

    그때는 규칙에 죽음의 굴림이 없었다. 쓰러진 캐릭터는 죽지 않고 쓰러진 채로 있었다.
    그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 것으로 읽는다. DB 의 룰북에도 같은 값을 채웠다(마이그레이션).
    이미 진행 중인 테이블도 이 형식으로 올려 읽는다. 그 테이블에서 쓰러져 있던 캐릭터는 다음 라운드부터 굴린다.
    """
    death_save = SRD5.model_dump(mode='json')['death_save']
    rulebook = document['rulebook']
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': {**rulebook['rules'], 'death_save': death_save}}
    upgraded['format'] = 10
    return upgraded


def upgrade_from_10(document: dict) -> dict:
    """
    형식 10 의 문서를 형식 11 로 올린다.

    그때는 추천 문체가 없었다. 문체를 지시하지 않았지만, 지금 제작자가 고르지 않았을 때와 같은 정통으로 읽는다.
    이미 진행 중인 테이블도 이 형식으로 올려 읽는다. 방장이 문체를 고르지 않았으면 다음 서술부터 정통이다.
    """
    upgraded = dict(document)
    upgraded['narration_style'] = DEFAULT_NARRATION_STYLE.value
    upgraded['format'] = 11
    return upgraded


def upgrade_from_11(document: dict) -> dict:
    """
    형식 11 의 문서를 형식 12 로 올린다.

    그때는 로어북 항목에 종류가 없었다. 모두 기타로 읽는다. DB 의 항목에도 같은 값을 채웠다(마이그레이션).
    기타는 지금까지와 똑같이 다룬다. 이미 진행 중인 테이블의 서술도 바뀌지 않는다.
    """
    upgraded = dict(document)
    upgraded['lorebooks'] = [
        {**lorebook, 'entries': [{**entry, 'kind': LoreKind.OTHER.value} for entry in lorebook['entries']]}
        for lorebook in document['lorebooks']
    ]
    upgraded['format'] = 12
    return upgraded


def upgrade_from_12(document: dict) -> dict:
    """
    형식 12 의 문서를 형식 13 으로 올린다.

    그때는 NPC 에 숫자가 없었다. NPC 시트는 없는 것으로, 기본 NPC 시트는 기준 시트로 읽는다.
    인물 항목은 모두 기본 NPC 시트를 쓴다. 이미 진행 중인 테이블은 시작할 때 NPC 의 상태를 만들지 않았으므로
    읽는 모양만 바뀐다.
    """
    upgraded = dict(document)
    upgraded['npc_sheets'] = []
    upgraded['default_npc_sheet'] = baseline_sheet(document['rulebook']['rules'])
    upgraded['format'] = 13
    return upgraded


# 부상이 생길 때 규칙에 더해진 칸들
INJURY_FIELDS = ('injuries', 'injury_table', 'injury_triggers', 'called_shot')


def upgrade_from_13(document: dict) -> dict:
    """
    형식 13 의 문서를 형식 14 로 올린다.

    그때는 규칙에 부상이 없었다. 그때의 규칙은 SRD5 템플릿뿐이었으므로 그 템플릿의 부상으로 읽는다.
    DB 의 룰북에도 같은 값을 채웠다(마이그레이션). 이미 진행 중인 테이블도 다음 라운드부터 부상이 생길 수 있다.
    """
    template = SRD5.model_dump(mode='json')
    rulebook = document['rulebook']
    rules = {**rulebook['rules'], **{field: template[field] for field in INJURY_FIELDS}}
    upgraded = dict(document)
    upgraded['rulebook'] = {**rulebook, 'rules': rules}
    upgraded['format'] = 14
    return upgraded


# 형식 번호와, 그 형식을 바로 다음 형식으로 올리는 함수.
# 형식을 올릴 때마다 한 줄씩 더한다. 옛 문서는 이 함수들을 차례로 거쳐 지금의 모양이 된다
UPGRADES: dict[int, Callable[[dict], dict]] = {
    1: upgrade_from_1,
    2: upgrade_from_2,
    3: upgrade_from_3,
    4: upgrade_from_4,
    5: upgrade_from_5,
    6: upgrade_from_6,
    7: upgrade_from_7,
    8: upgrade_from_8,
    9: upgrade_from_9,
    10: upgrade_from_10,
    11: upgrade_from_11,
    12: upgrade_from_12,
    13: upgrade_from_13,
}


def read_snapshot(document: dict) -> Snapshot:
    """
    DB 에서 꺼낸 문서를 지금의 모양으로 읽는다. 옛 형식이면 올려서 읽는다.

    받은 문서는 고치지 않는다. 올린 결과를 DB 에 다시 쓰지도 않는다.
    """
    while document['format'] in UPGRADES:
        document = UPGRADES[document['format']](document)
    return Snapshot.model_validate(document)
