# trpg-server/app/rounds/effects.py

"""
닫히는 라운드의 판정이 함께 쓰는 것과, 바뀐 HP 를 선언의 outcome 에 적을 문서로 만드는 함수들.

판정(app/rounds/checks.py), 치료(app/rounds/treatments.py), 물건 쓰기(app/rounds/item_actions.py)가 함께 쓴다.
서로를 가져오지 않게 여기 둔다.
DB 를 모른다. 저장하지 않는다.
"""

import uuid
from dataclasses import dataclass, field

from app.assets.scenarios.snapshot import EntrySnapshot, Snapshot
from app.engine.dice import Dice
from app.engine.health import Change
from app.engine.ruleset import InjuryNature, Ruleset
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember, condition_of
from app.rounds.monster_scene import SceneMonster
from app.tables.injuries import Moment
from app.tables.items import CatalogItem
from app.tables.models import GameTable, TableMember, TableMonster, TableNpc


@dataclass(frozen=True)
class Judging:
    """
    닫히는 라운드의 판정에 함께 쓰는 것들. 테이블, 규칙, 주사위, 이번 장면의 인물, 라운드의 번호,
    테이블의 NPC 상태 전부와 판의 인물 항목.

    판정 하나와 그 결과(HP, NPC 의 상태, 부상)를 정하는 함수들이 이것을 함께 받는다.
    """

    table: GameTable
    ruleset: Ruleset
    dice: Dice
    cast: list[CastMember]
    round_number: int
    # 이 라운드가 닫히는 게임 안의 때. 부상이 생기고 낫는 때를 정한다(app/rounds/injuries.py 의 moment_of)
    moment: Moment
    # 테이블의 NPC 상태 전부와 판의 인물 항목. 지목은 장면에 없는 인물도 짚을 수 있다(app/rounds/naming.py)
    npcs: list[TableNpc]
    people: list[EntrySnapshot]
    # 판의 물건들(app/tables/items.py 의 catalog). 물건을 쓰거나 건넬 때 이름과 규칙을 찾는다
    items: dict[uuid.UUID, CatalogItem] = field(default_factory=dict)
    # 판의 복사본. 맵에서 가고 찾을 때 길과 장소를 찾는다(app/rounds/map_actions.py)
    snapshot: Snapshot | None = None
    # 이번 장면의 몬스터들(app/rounds/monster_scene.py). 몬스터의 상태는 그 안에 들어 있고, 판정에서 고친다
    monsters: list[SceneMonster] = field(default_factory=list)
    # 이번 라운드에 피해를 입은 앉은 사람들(user_id). 판정이 피해를 줄 때마다 더한다(mark_hurt).
    # 쉬는 사람이 다쳤으면 휴식이 깨진다(app/rounds/rests.py)
    hurt: set[uuid.UUID] = field(default_factory=set)
    # 이번 라운드에 몬스터나 NPC 마다 싸운 앉은 사람들(몬스터의 id 나 NPC 의 항목 id → user_id).
    # 몬스터가 쳤거나, 쳤거나, 훔치다 들켰다. NPC 는 타격으로 겨눴거나, 훔치다 들켜 싸움이 붙었다.
    # 차례대로 더한다. 도둑의 차례 전에 다른 사람과 싸웠으면 정신이 팔렸다(app/rounds/steals.py)
    fights: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=dict)
    # 훔치다 들킨 도둑(몬스터의 id 나 NPC 의 항목 id → user_id). 그 마리나 인물은 이번 라운드의 차례에 도둑을 노린다
    # (app/rounds/monster_attacks.py, app/rounds/npc_attacks.py)
    provoked: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    # 라운드를 닫기 시작할 때 이미 쓰러져 있던(죽지 않은) 앉은 사람들(user_id).
    # 몬스터와 NPC 는 이들도 칠 수 있다. 이번 라운드에 쓰러진 사람은 들지 않는다(app/rounds/downed_strikes.py)
    downed_at_start: frozenset[uuid.UUID] = frozenset()
    # 이번 라운드에 엄폐한 앉은 사람들과 그 장소의 커버(user_id → 커버, #276). 판정을 시작하기 전에 정한다.
    # 그 라운드 동안 그 사람의 세이브에 든다(app/rounds/covers.py, app/rounds/blows.py)
    covers: dict[uuid.UUID, int] = field(default_factory=dict)


def mark_fight(judging: Judging, monster: TableMonster, member: TableMember) -> None:
    """몬스터 한 마리와 앉은 사람 하나가 이번 라운드에 싸웠다고 적는다. 처음 싸운 라운드도 적는다."""
    judging.fights.setdefault(monster.id, set()).add(member.user_id)
    if monster.fought_round is None:
        monster.fought_round = judging.round_number


def mark_npc_fight(judging: Judging, npc: TableNpc, member: TableMember) -> None:
    """NPC 하나와 앉은 사람 하나가 이번 라운드에 싸웠다고 적는다. 처음 싸운 라운드도 적는다. 키는 항목의 id 다."""
    judging.fights.setdefault(npc.entry_id, set()).add(member.user_id)
    if npc.fought_round is None:
        npc.fought_round = judging.round_number


def mark_hurt(judging: Judging, member: TableMember) -> None:
    """앉은 사람 하나가 이번 라운드에 피해를 입었다고 적는다."""
    judging.hurt.add(member.user_id)


def injury_after(
    judging: Judging,
    change: Change,
    max_hp: int,
    dead: bool,
    rows: list,
    immune: frozenset[InjuryNature] = round_injuries.NO_IMMUNITY,
    prank: bool = False,
) -> dict | None:
    """
    피해 뒤에 부상 표를 굴릴 일이면 굴리고, 나온 부상을 입힌다. 굴린 것을 문서로 돌려준다. 굴리지 않았으면 None.

    rows 는 입는 쪽(시트나 NPC 상태나 몬스터)의 부상 목록이다. immune 은 그쪽이 면역인 성질이다(#799, 몬스터).
    prank 면 동료의 장난(#803)이다. 짧은 부상만 입힌다.
    """
    rolled = round_injuries.roll_after(judging.ruleset, judging.dice, change, max_hp, dead)
    if rolled is None:
        return None
    return round_injuries.take(judging.ruleset, rolled, rows, judging.table.id, judging.moment, immune, prank)


def member_effect(affected: TableMember, magnitude: str, change: Change, injury_roll: dict | None) -> dict:
    """
    앉은 사람의 HP 가 바뀐 것을 선언의 outcome 에 넣을 문서로. 누구의 HP 가 얼마에서 얼마로 바뀌었는지가 다 담긴다.

    injury_roll 은 그 피해로 부상 표를 굴린 것이다. 굴리지 않았으면 None.
    """
    return {
        'kind': change.kind.value,
        'magnitude': magnitude,
        'user_id': str(affected.user_id),
        'character_name': affected.character_name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': affected.sheet.max_hp,
        'downed': change.downed,
        'injury_roll': injury_roll,
    }


def npc_effect(
    member: CastMember, magnitude: str, change: Change, lethal: bool, status_before: str, injury_roll: dict | None
) -> dict:
    """
    NPC 의 상태가 바뀐 것을 선언의 outcome 에 넣을 문서로.

    HP 의 숫자까지 다 적는다. 앉은 사람에게 내보낼 때 숫자를 뺀다(app/rounds/schemas.py, 이벤트의 VISIBLE).
    몸 상태(condition)는 부상까지 정한 뒤의 것이다.
    """
    npc = member.npc
    return {
        'kind': change.kind.value,
        'magnitude': magnitude,
        'entry_id': str(member.entry_id),
        'name': member.name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': npc.max_hp,
        'lethal': lethal,
        'status_before': status_before,
        'status': npc.status,
        'condition': condition_of(npc),
        'injury_roll': injury_roll,
    }


def monster_effect(
    monster: SceneMonster,
    magnitude: str,
    change: Change,
    lethal: bool,
    status_before: str,
    injury_roll: dict | None = None,
) -> dict:
    """
    몬스터 한 마리의 상태가 바뀐 것을 선언의 outcome 에 넣을 문서로. NPC 와 같은 모양이다(npc_effect).

    HP 의 숫자까지 다 적는다. 앉은 사람에게 내보낼 때 숫자를 뺀다(app/rounds/schemas.py, 이벤트의 VISIBLE).
    injury_roll 은 그 피해로 입은(또는 면역으로 입지 않은) 부상이다(#799). 없었으면 None.
    """
    state = monster.state
    return {
        'kind': change.kind.value,
        'magnitude': magnitude,
        'monster_id': str(state.id),
        'name': monster.name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': state.max_hp,
        'lethal': lethal,
        'status_before': status_before,
        'status': state.status,
        'condition': condition_of(state),
        'injury_roll': injury_roll,
    }
