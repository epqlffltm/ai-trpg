# game-server/app/rounds/victims.py

"""
물건을 가져갈 대상 하나(몬스터 한 마리나 NPC 하나)를 같은 모양으로 보는 법. 훔치기(app/rounds/steals.py)와
빼앗기(app/rounds/loots.py)가 함께 쓴다.

대상이 무엇이든 지닌 것(app/tables/carried.py)을 읽고 고치는 길과, 결과에 적을 대상의 칸이 같다.
몬스터면 monster_id·monster_name, NPC 면 npc_id·npc_name 이 채워지고 다른 쪽은 비어 있다.

DB 를 모른다. 이미 읽어 온 장면의 마리와 인물을 받는다.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from app.rounds.cast import CastMember
from app.rounds.monster_scene import SceneMonster
from app.tables import carried, monster_items, npc_items
from app.tables.carried import Carried
from app.tables.models import NpcStatus, TableMonster, TableNpc


@dataclass(frozen=True)
class Victim:
    """
    물건을 가져갈 대상 하나. 몬스터 한 마리나 NPC 하나를 같은 모양으로 본다.

    key 는 이번 라운드에 누구와 싸웠는지 찾는 키(몬스터의 id, NPC 의 항목 id)다(Judging.fights).
    kind 는 몬스터의 타입이다. NPC 는 타입이 없어 None 이다(둔한 타입이 걸리지 않는다).
    dull, unwary, abilities 는 훔치기의 목표값에 쓴다. 빼앗기는 굴리지 않아 보지 않는다.
    origin 은 결과에 적을 대상의 칸들이다(monster_id·monster_name 이나 npc_id·npc_name).
    set_count 는 줄의 번호와 개수를 받아 대상이 지닌 개수를 고친다.
    """

    key: uuid.UUID
    name: str
    abilities: dict
    kind: str | None
    dull: bool
    unwary: bool
    held: list[Carried]
    set_count: Callable[[int, int], None]
    origin: dict


def is_unwary(state: TableMonster | TableNpc) -> bool:
    """싸움 전인가. 아직 아무와도 싸우지 않았거나, 쓰러져 있다. 몬스터와 NPC 가 같다."""
    return state.fought_round is None or state.status == NpcStatus.DOWNED


def monster_origin(monster: SceneMonster) -> dict:
    """결과에 적을 대상의 칸들. 몬스터면 npc 칸이 비어 있다."""
    return {'monster_id': str(monster.state.id), 'monster_name': monster.name, 'npc_id': None, 'npc_name': None}


def npc_origin(person: CastMember) -> dict:
    """결과에 적을 대상의 칸들. NPC 면 monster 칸이 비어 있다."""
    return {'monster_id': None, 'monster_name': None, 'npc_id': str(person.entry_id), 'npc_name': person.name}


def monster_victim(monster: SceneMonster) -> Victim:
    """몬스터 한 마리를 대상으로 본다."""
    state = monster.state
    return Victim(
        key=state.id,
        name=monster.name,
        abilities=state.abilities,
        kind=monster.definition.kind,
        dull=monster.definition.dull,
        unwary=is_unwary(state),
        held=monster_items.carried(state, monster.definition),
        set_count=lambda slot, count: monster_items.set_count(state, slot, count),
        origin=monster_origin(monster),
    )


def npc_victim(person: CastMember) -> Victim:
    """NPC 하나를 대상으로 본다. 시트를 적지 않은 인물은 아무것도 지니지 않고 둔하지 않다."""
    npc = person.npc
    return Victim(
        key=person.entry_id,
        name=person.name,
        abilities=npc.abilities,
        kind=None,
        dull=person.definition.dull if person.definition else False,
        unwary=is_unwary(npc),
        held=npc_items.carried(npc, person.definition),
        set_count=lambda slot, count: npc_items.set_count(npc, slot, count),
        origin=npc_origin(person),
    )


def find_monster_carried(monster: SceneMonster, entry_id: uuid.UUID) -> Carried | None:
    """그 마리가 지금 지닌 그 물건의 줄. 지니지 않았으면 None."""
    return carried.find_carried(monster_items.carried(monster.state, monster.definition), entry_id)


def find_npc_carried(person: CastMember, entry_id: uuid.UUID) -> Carried | None:
    """그 인물이 지금 지닌 그 물건의 줄. 지니지 않았으면 None."""
    return carried.find_carried(npc_items.carried(person.npc, person.definition), entry_id)
