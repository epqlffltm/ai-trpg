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

from pydantic import BaseModel

from app.assets.models import Lorebook, LoreEntry, Rating, Rulebook, Scenario, World

# 문서의 모양이 바뀔 때 올리는 번호. 옛 판을 읽는 코드가 어느 모양인지 알 수 있다.
#   1: 도입부가 하나다(opening)
#   2: 스타팅이 여러 개다(openings)
SNAPSHOT_FORMAT = 2


class EntrySnapshot(BaseModel):
    """로어북의 항목 하나."""

    id: uuid.UUID
    name: str
    keywords: list[str]
    content: str


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
    """룰북."""

    id: uuid.UUID
    title: str
    gm_guide: str


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
    rulebook: RulebookSnapshot
    world: WorldSnapshot | None
    lorebooks: list[LorebookSnapshot]


def snapshot_entry(entry: LoreEntry) -> EntrySnapshot:
    """항목을 굳힌다."""
    return EntrySnapshot(id=entry.id, name=entry.name, keywords=entry.keywords, content=entry.content)


def snapshot_lorebook(lorebook: Lorebook, entries: list[LoreEntry]) -> LorebookSnapshot:
    """로어북과 그 항목들을 굳힌다."""
    return LorebookSnapshot(
        id=lorebook.asset_id, title=lorebook.asset.title, entries=[snapshot_entry(entry) for entry in entries]
    )


def snapshot_world(world: World) -> WorldSnapshot:
    """세계관을 굳힌다."""
    return WorldSnapshot(id=world.asset_id, title=world.asset.title, setting=world.setting, gm_notes=world.gm_notes)


def snapshot_rulebook(rulebook: Rulebook) -> RulebookSnapshot:
    """룰북을 굳힌다."""
    return RulebookSnapshot(id=rulebook.asset_id, title=rulebook.asset.title, gm_guide=rulebook.gm_guide)


def build_snapshot(
    scenario: Scenario, rulebook: Rulebook, world: World | None, lorebooks: list[tuple[Lorebook, list[LoreEntry]]]
) -> Snapshot:
    """시나리오와 그것이 가리키는 자산들에서 판의 내용을 만든다."""
    return Snapshot(
        title=scenario.asset.title,
        description=scenario.asset.description,
        rating=scenario.asset.rating,
        openings=list(scenario.openings),
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


# 형식 번호와, 그 형식을 바로 다음 형식으로 올리는 함수.
# 형식을 올릴 때마다 한 줄씩 더한다. 옛 문서는 이 함수들을 차례로 거쳐 지금의 모양이 된다
UPGRADES: dict[int, Callable[[dict], dict]] = {1: upgrade_from_1}


def read_snapshot(document: dict) -> Snapshot:
    """
    DB 에서 꺼낸 문서를 지금의 모양으로 읽는다. 옛 형식이면 올려서 읽는다.

    받은 문서는 고치지 않는다. 올린 결과를 DB 에 다시 쓰지도 않는다.
    """
    while document['format'] in UPGRADES:
        document = UPGRADES[document['format']](document)
    return Snapshot.model_validate(document)
