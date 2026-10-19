# trpg-server/app/rounds/initiative.py

"""
라운드의 차례. 앉은 사람의 행동과 몬스터와 NPC 의 공격을 어떤 순서로 판정할지 정한다.

장면에 맞붙은 몬스터(공격이 있고 쓰러지지 않은 마리)나 싸우는 NPC(app/rounds/npc_attacks.py 의 can_act)가
있을 때만 차례를 정한다(app/rounds/judging.py). 없으면 지금처럼 앉은 순서로 판정한다.
몬스터도 싸우는 NPC 도 없는 판과 옛 라운드는 그대로 간다.

차례를 정하는 법은 셋이다. 앞의 것이 같을 때만 뒤의 것을 본다.
  1. 기습한 쪽이 먼저다. 만난 첫 라운드(engaged_round)에만 조우의 기습(surprise)을 쓴다.
     monsters 면 그 조우의 마리가, party 면 그 장소에 서 있는 캐릭터가 먼저다. NPC 는 기습하지 않는다.
  2. 규칙의 차례 능력치(initiative_ability)의 점수가 높은 쪽이 먼저다. 규칙에 없으면(None) 모두 같다.
  3. 그래도 같으면 서버의 주사위다. 같은 무리만 굴린다.
     같은 눈이 또 나오면 앉은 사람, 그다음 장면의 몬스터, 그다음 장면의 인물 순서다.

DB 를 모른다. 이미 읽어 온 판, 테이블, 몬스터 상태를 받는다. 여기서 바꾸는 것은 마리의 engaged_round 뿐이다.
"""

import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import groupby

from app.assets.models import Surprise
from app.assets.scenarios.snapshot import EncounterSnapshot, Snapshot
from app.engine.dice import Dice
from app.engine.ruleset import Ruleset
from app.rounds.cast import CastMember
from app.rounds.monster_scene import SceneMonster
from app.tables.models import TableMember


class TurnKind(StrEnum):
    """차례의 주인. 앉은 사람의 캐릭터이거나 몬스터 한 마리이거나 장면의 인물(NPC) 하나다."""

    PC = 'pc'
    MONSTER = 'monster'
    NPC = 'npc'


@dataclass(frozen=True)
class Turn:
    """
    차례 하나. 누구의 차례인지와, 그 자리를 정한 값들(기습, 점수, 주사위)이다.

    member, monster, npc 중 하나만 있다. tiebreak 는 같은 무리가 있어 주사위를 굴렸을 때만 있다.
    """

    kind: TurnKind
    member: TableMember | None
    monster: SceneMonster | None
    first: bool
    score: int | None
    tiebreak: int | None = None
    npc: CastMember | None = None


def mark_engaged(monsters: list[SceneMonster], round_number: int) -> None:
    """
    장면의 마리 중 아직 만나지 않은 것에 이번 라운드를 만난 첫 라운드로 적는다.

    장면의 마리는 살아 있는 캐릭터가 서 있는 장소에 있다(app/rounds/monster_scene.py). 그래서 지금 만난 것이다.
    한 번 적으면 고치지 않는다. 기습은 이 라운드에만 쓴다.
    """
    for monster in monsters:
        if monster.state.engaged_round is None:
            monster.state.engaged_round = round_number


def encounter_of(snapshot: Snapshot, monster: SceneMonster) -> EncounterSnapshot | None:
    """이 마리가 나온 조우. 마리는 조우의 장소에 놓였고 지금은 움직이지 않는다. 찾지 못하면 None."""
    return next(
        (
            encounter
            for encounter in snapshot.encounters
            if encounter.place_id == monster.state.place_id and encounter.monster_id == monster.state.monster_id
        ),
        None,
    )


def surprise_of(snapshot: Snapshot, monster: SceneMonster, round_number: int) -> Surprise:
    """이 마리의 조우가 이번 라운드에 쓰는 기습. 만난 첫 라운드가 아니면 기습이 없다."""
    if monster.state.engaged_round != round_number:
        return Surprise.NONE
    encounter = encounter_of(snapshot, monster)
    return encounter.surprise if encounter is not None else Surprise.NONE


def ambushed_places(snapshot: Snapshot, monsters: list[SceneMonster], round_number: int) -> set[uuid.UUID]:
    """이번 라운드에 일행이 기습한 장소들. 그 장소에 서 있는 캐릭터가 먼저다."""
    return {
        monster.state.place_id for monster in monsters if surprise_of(snapshot, monster, round_number) == Surprise.PARTY
    }


def score_of(ruleset: Ruleset, abilities: dict[str, int]) -> int | None:
    """차례 능력치의 점수. 규칙에 차례 능력치가 없으면 None 이다(모두 같은 것으로 본다)."""
    if ruleset.initiative_ability is None:
        return None
    return abilities.get(ruleset.initiative_ability)


def member_turn(ruleset: Ruleset, member: TableMember, ambushed: set[uuid.UUID]) -> Turn:
    """앉은 사람 하나의 차례. 서 있는 장소에서 일행이 기습했으면 먼저다."""
    return Turn(
        kind=TurnKind.PC,
        member=member,
        monster=None,
        first=member.sheet.place_id in ambushed,
        score=score_of(ruleset, member.sheet.abilities),
    )


def monster_turn(ruleset: Ruleset, snapshot: Snapshot, monster: SceneMonster, round_number: int) -> Turn:
    """몬스터 한 마리의 차례. 그 조우가 이번 라운드에 기습했으면 먼저다."""
    return Turn(
        kind=TurnKind.MONSTER,
        member=None,
        monster=monster,
        first=surprise_of(snapshot, monster, round_number) == Surprise.MONSTERS,
        score=score_of(ruleset, monster.state.abilities),
    )


def npc_turn(ruleset: Ruleset, person: CastMember) -> Turn:
    """싸우는 인물 하나의 차례. 인물은 기습하지 않는다. 점수는 테이블의 그 인물의 것이다."""
    return Turn(
        kind=TurnKind.NPC,
        member=None,
        monster=None,
        first=False,
        score=score_of(ruleset, person.npc.abilities),
        npc=person,
    )


def rank_of(turn: Turn) -> tuple[bool, int]:
    """주사위 전의 자리. 기습한 쪽이 먼저, 그다음 점수가 높은 쪽이 먼저다. 점수가 없으면 모두 0 으로 본다."""
    return (not turn.first, -(turn.score or 0))


def break_ties(turns: list[Turn], die: int, dice: Dice) -> list[Turn]:
    """
    자리가 같은 무리마다 주사위를 굴려 높은 눈이 먼저 오게 한다. 혼자인 무리는 굴리지 않는다.

    turns 는 자리(rank_of) 순서로 정렬되어 있어야 한다. 같은 눈은 받은 순서를 그대로 둔다.
    """
    ordered = []
    for _, group in groupby(turns, key=rank_of):
        members = list(group)
        if len(members) == 1:
            ordered.extend(members)
            continue
        rolled = [replace(turn, tiebreak=dice.roll(die)) for turn in members]
        ordered.extend(sorted(rolled, key=lambda turn: -turn.tiebreak))
    return ordered


def order_turns(turns: list[Turn], die: int, dice: Dice) -> list[Turn]:
    """
    차례들을 판정할 순서로 늘어놓는다. 기습 → 점수 → 주사위다.

    turns 는 앉은 사람(앉은 순서), 그다음 몬스터(장면의 순서), 그다음 인물(장면의 순서)로 받는다.
    모든 것이 같으면 그 순서를 지킨다.
    """
    return break_ties(sorted(turns, key=rank_of), die, dice)


def turn_document(turn: Turn) -> dict:
    """
    차례 하나를 라운드의 turns 에 적을 문서로. 누구인지와 자리를 정한 값들이다.

    몬스터와 인물의 차례에서 한 일(공격, 대상, 굴림)은 부른 쪽이 outcome 으로 덧붙인다
    (app/rounds/monster_attacks.py, app/rounds/npc_attacks.py). 앉은 사람의 차례에서 한 일은 그 사람의 선언에 적힌다.
    인물의 이름은 장면에서 부르는 이름이다(진짜 이름이 드러나기 전이면 진짜 이름이 아니다).
    """
    common = {'kind': turn.kind.value, 'first': turn.first, 'score': turn.score, 'tiebreak': turn.tiebreak}
    if turn.kind == TurnKind.PC:
        return {**common, 'user_id': str(turn.member.user_id), 'character_name': turn.member.character_name}
    if turn.kind == TurnKind.NPC:
        return {**common, 'entry_id': str(turn.npc.entry_id), 'name': turn.npc.name}
    return {**common, 'monster_id': str(turn.monster.state.id), 'name': turn.monster.name}
