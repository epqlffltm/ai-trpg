# trpg-server/app/rounds/cast.py

"""
이번 장면의 인물들. 플레이어가 행동으로 겨눌 수 있는 NPC 와, 서술자에게 알려 줄 NPC 의 지금 상태.

NPC 는 로어북의 인물 항목이다. 로어북은 AI 만 읽는 글이라 인물의 목록을 플레이어에게 통째로 보여 주지 않는다.
대신 이번 라운드의 장면(앞 라운드의 서술, 첫 라운드는 스타팅)에 나온 인물만 고른다.
장면은 앉은 사람 모두가 이미 읽은 글이다. 거기서 고르면 새로 드러나는 것이 없다.

나왔는지는 로어북 검색과 같은 법으로 본다(app/lore/retrieval.py 의 mentions).
이름이나 키워드가 글에 그대로 있으면 나온 것이다.
부르는 이름도 검색과 같다(scene_label). 장면에 나온 낱말이다. 진짜 이름이 아직 나오지 않았으면 진짜 이름을 쓰지 않는다.
플레이어가 진짜 이름을 맞힌(지목한) 인물은 그 뒤로 진짜 이름으로 부른다(app/rounds/naming.py).
그래서 인물 항목의 키워드는 장면에서 그 인물을 부르는 호칭이어야 한다. 이 목록으로 플레이어에게 보일 수 있다.

자리가 있는 인물(#282). 판에 처음 있는 장소를 적은 인물은 글이 아니라 자리로 고른다. 몬스터와 같다
(app/rounds/monster_scene.py). 살아 있는 캐릭터가 서 있는 장소들에 있는 인물이 장면에 든다. 글에 나와도
아무도 그 장소에 서 있지 않으면 들지 않는다. 서술이 다른 곳의 인물을 불러내지 못한다.
글에 나오지 않은 채 장면에 든 인물은 가장 긴 키워드로 부른다(standing_label). 진짜 이름이 새지 않는다.
자리가 있는 인물은 같은 장소에 선 캐릭터만 겨눈다(reaches). 자리가 없는 인물은 누구나 겨눈다(지금처럼).
맵이 없는 판은 자리를 적을 수 없다(게시할 때 막는다).

상태(table_npcs)가 없는 인물은 들어가지 않는다. 이 기능이 생기기 전에 시작한 테이블이 그렇다.

여기의 함수는 DB 를 모른다. 이미 읽어 온 판, 장면, 상태를 받는다.
"""

import uuid
from collections.abc import Iterable, Set
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.assets.scenarios.snapshot import EntrySnapshot, NpcSheetSnapshot, Snapshot, own_npc_sheet, person_entries
from app.lore.retrieval import mentions, scene_label
from app.tables.models import NpcStatus, TableMember, TableMonster, TableNpc

if TYPE_CHECKING:
    # 이번 장면의 몬스터(app/rounds/monster_scene.py).
    # 그 파일이 이 파일의 condition_of 를 쓰므로 실행할 때는 가져오지 않는다
    from app.rounds.monster_scene import SceneMonster


@dataclass(frozen=True)
class CastMember:
    """
    이번 장면의 인물 하나. 장면에서 부르는 이름과 이 테이블에서의 상태와 판에 적은 NPC 시트다.

    definition 은 지닌 물건을 셀 때 쓴다(app/tables/npc_items.py). 시트를 적지 않은 인물은 None 이다.
    """

    entry_id: uuid.UUID
    name: str
    npc: TableNpc
    definition: NpcSheetSnapshot | None = None


# 서술자에게 주는 NPC 의 몸 상태. HP 의 숫자를 주지 않는다. 숫자를 주면 모델이 그것을 장면에 쓴다
UNHURT = '멀쩡함'
HURT = '다침'
BADLY_HURT = '크게 다침'
CONDITIONS = {NpcStatus.DOWNED: '쓰러짐(의식 없음)', NpcStatus.DEAD: '죽음'}


@dataclass(frozen=True)
class Scene:
    """
    이번 장면을 다루는 데 필요한 NPC 들. 테이블의 NPC 상태 전부와, 그중 장면에 나온 인물들.

    장면에 나오지 않은 인물도 상태가 바뀔 수 있다(짧은 부상이 풀린다). 그래서 둘을 함께 든다.
    몬스터도 장면의 마리와 테이블의 마리 전부를 함께 든다. 장면의 마리는 그 전부 중 일부다(같은 객체다).
    """

    npcs: list[TableNpc]
    cast: list[CastMember]
    # 이번 장면의 몬스터들. 살아 있는 캐릭터가 서 있는 장소들의 마리다(app/rounds/monster_scene.py)
    monsters: list['SceneMonster'] = field(default_factory=list)
    # 테이블의 몬스터 상태 전부. 장면 밖의 마리도 든다. 퀘스트의 조건(몇 마리를 쓰러뜨렸나)을 셀 때 쓴다
    all_monsters: list[TableMonster] = field(default_factory=list)


def is_named(npc: TableNpc) -> bool:
    """플레이어가 이 인물의 진짜 이름을 맞혔는가."""
    return npc.named_round is not None


def standing_label(entry: EntrySnapshot) -> str:
    """
    글에 나오지 않고 자리로 장면에 든 인물을 부를 이름. 키워드 중 가장 긴 것, 키워드가 없으면 이름이다.

    키워드는 장면의 호칭이라 드러나도 된다. 장면의 호칭(scene_label)과 같은 까닭으로 가장 긴 것을 고른다.
    """
    keywords = [word for word in entry.keywords if word.strip()]
    return max(keywords, key=len) if keywords else entry.name


def label_of(entry: EntrySnapshot, scene: str, npc: TableNpc) -> str:
    """
    이 인물을 부를 이름. 진짜 이름을 맞혔으면 진짜 이름, 장면에 나왔으면 장면의 호칭이다.

    글에 나오지 않았으면(자리로 장면에 든 인물) 가장 긴 키워드다(standing_label).
    """
    if is_named(npc):
        return entry.name
    if mentions(entry, scene):
        return scene_label(entry, scene)
    return standing_label(entry)


def is_placed(npc: TableNpc) -> bool:
    """이 인물에게 자리(맵의 장소)가 있는가. 판에 자리를 적었거나 사건이 옮긴 인물이다."""
    return npc.place_id is not None


def in_scene(entry: EntrySnapshot, scene: str, npc: TableNpc, here: Set[uuid.UUID]) -> bool:
    """
    이 인물이 장면에 있는가. 자리가 있으면 캐릭터가 서 있는 장소(here)에 있어야 하고, 없으면 글에 나와야 한다.
    """
    if is_placed(npc):
        return npc.place_id in here
    return mentions(entry, scene)


def cast_of(
    snapshot: Snapshot, scene: str, npcs: Iterable[TableNpc], here: Set[uuid.UUID] = frozenset()
) -> list[CastMember]:
    """
    이 장면의 인물들. 판의 인물 항목 순서다. 상태가 없는 인물은 뺀다.

    here 는 살아 있는 캐릭터가 서 있는 장소들이다(app/rounds/monster_scene.py 의 occupied_places).
    """
    states = {npc.entry_id: npc for npc in npcs}
    return [
        CastMember(
            entry.id, label_of(entry, scene, states[entry.id]), states[entry.id], own_npc_sheet(snapshot, entry.id)
        )
        for entry in person_entries(snapshot)
        if entry.id in states and in_scene(entry, scene, states[entry.id], here)
    ]


def labels_of(snapshot: Snapshot, scene: str, npcs: Iterable[TableNpc]) -> dict[uuid.UUID, str]:
    """
    이 테이블의 인물마다 부를 이름(label_of). 장면 밖의 인물도 든다. 상태가 없는 인물은 뺀다.

    사건이 옮긴 인물처럼 장면에 없을 수도 있는 인물을 서술자에게 이를 때 쓴다(app/rounds/narration_request.py).
    """
    states = {npc.entry_id: npc for npc in npcs}
    return {
        entry.id: label_of(entry, scene, states[entry.id]) for entry in person_entries(snapshot) if entry.id in states
    }


def find_cast_member(cast: list[CastMember], entry_id: uuid.UUID) -> CastMember | None:
    """이번 장면의 인물 중에서 이 항목의 것을 찾는다. 장면에 나오지 않았으면 None."""
    return next((member for member in cast if member.entry_id == entry_id), None)


def reaches(member: TableMember, person: CastMember) -> bool:
    """
    이 캐릭터가 이 인물에게 닿는가(겨눌 수 있는가). 자리가 없는 인물은 누구나, 있는 인물은 같은 장소에 선 캐릭터만이다.
    """
    if not is_placed(person.npc):
        return True
    return member.sheet is not None and member.sheet.place_id == person.npc.place_id


def find_reachable(cast: list[CastMember], member: TableMember, entry_id: uuid.UUID) -> CastMember | None:
    """
    이번 장면의 인물 중에서 이 캐릭터가 닿는 이 항목의 것을 찾는다. 장면에 없거나 다른 장소에 있으면 None.

    장면에 없는 것과 다른 장소에 있는 것을 가르지 않는다. 몬스터와 같다(app/rounds/acceptance.py).
    """
    person = find_cast_member(cast, entry_id)
    return person if person is not None and reaches(member, person) else None


def condition_of(npc: TableNpc | TableMonster) -> str:
    """
    NPC 나 몬스터의 몸 상태를 말로. 쓰러짐과 죽음은 생사로, 살아 있으면 HP 가 얼마나 남았는지로 나눈다.

    HP 가 가득하면 멀쩡함, 절반을 넘게 남았으면 다침, 그 아래면 크게 다침이다.
    """
    if npc.status in CONDITIONS:
        return CONDITIONS[NpcStatus(npc.status)]
    if npc.hp >= npc.max_hp:
        return UNHURT
    return HURT if npc.hp * 2 > npc.max_hp else BADLY_HURT
