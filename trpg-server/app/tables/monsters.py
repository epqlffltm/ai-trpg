# trpg-server/app/tables/monsters.py

"""
테이블의 몬스터 상태(table_monsters)를 만드는 작은 함수들.

DB 를 모른다. 이미 읽어 온 판을 받아 객체를 만든다. 저장은 부른 쪽이 한다.

만들기. 게임을 시작할 때 판의 조우마다 마리 수만큼 상태를 만들어 그 장소에 둔다(app/tables/service.py).
일행이 그 장소에 서면 "거기 있던" 몬스터를 만난다. 들어서는 순간에 꺼내지 않는다.
캐릭터가 서는 길(이동, 업혀 가기, 판의 사건, 시작)이 여럿인데, 어느 것을 거쳐도 같은 몬스터를 만나게 하려는 것이다.
숫자는 판의 몬스터의 시트다. HP 는 가득 찬 채로, 살아 있는 채로 시작한다. NPC 와 같다(app/tables/npcs.py).

번호. 같은 몬스터는 테이블 전체에서 1 부터 차례로 번호를 받는다. 조우의 순서, 그 안의 마리 순서다.
수로 쥐가 두 장소에 셋, 둘 있으면 첫 장소의 것이 1~3, 둘째 장소의 것이 4~5 다. 부를 때 쓴다.

바꾸기. 몬스터의 HP 와 생사를 바꾸는 함수는 change_monster 하나다. 판정의 결과로 라운드가 부른다(app/rounds/checks.py).
피해의 양은 규칙의 등급으로 주사위를 굴려 정한다(app/engine/health.py). NPC 와 같다.
HP 가 0 이 됐을 때 쓰러지는지 죽는지는 타입의 성질(Traits)이 정한다. 죽은 몬스터는 바꾸지 않는다.
"""

import uuid
from collections import Counter
from dataclasses import dataclass

from app.assets.bestiaries.models import MonsterKind
from app.assets.scenarios.snapshot import MonsterSnapshot, Snapshot, monster_of
from app.engine import health
from app.engine.dice import Dice
from app.engine.health import Change, ChangeKind
from app.engine.ruleset import Magnitude, Ruleset
from app.tables.models import NpcStatus, TableMonster


@dataclass(frozen=True)
class Traits:
    """
    몬스터의 타입이 엔진에서 갖는 성질. 엔진은 타입의 이름이 아니라 이 성질을 보고 다르게 다룬다.

    성질이 늘면 칸을 더하고 아래의 표(TRAITS)를 채운다. 판정의 코드는 고치지 않는다.
    """

    # HP 가 0 이 되면 제압이어도 부서진다(죽음). 의식이 없어 쓰러짐이 뜻이 없는 것들이다
    destroyed_at_zero: bool = False
    # 걸리지 않는 성질은 여기 없다. 룰북이 타입마다 정한다(rules.monster_immunities, #886)


# 타입마다의 성질. 모든 타입이 있어야 한다(tests/test_monster_combat.py 가 본다)
TRAITS: dict[MonsterKind, Traits] = {
    MonsterKind.HUMANOID: Traits(),
    MonsterKind.BEAST: Traits(),
    MonsterKind.UNDEAD: Traits(destroyed_at_zero=True),
    MonsterKind.CONSTRUCT: Traits(destroyed_at_zero=True),
    MonsterKind.OTHER: Traits(),
}


def kind_immunities(ruleset: Ruleset, kind: MonsterKind) -> frozenset[str]:
    """그 타입이 걸리지 않는 성질들. 룰북이 정한다(rules.monster_immunities, #886). 적지 않은 타입은 없다."""
    found = next((one for one in ruleset.monster_immunities if one.kind == kind), None)
    return frozenset(found.natures) if found is not None else frozenset()


def immunities(ruleset: Ruleset, monster: MonsterSnapshot) -> frozenset[str]:
    """
    이 몬스터가 걸리지 않는 부상의 성질들(#799). 타입의 면역(룰북, #886)에 시트에서 더한 것을 넣고, 뺀 것을 뺀다.
    """
    return (kind_immunities(ruleset, monster.kind) | frozenset(monster.immune)) - frozenset(monster.vulnerable)


def new_monster(table_id: uuid.UUID, monster: MonsterSnapshot, place_id: uuid.UUID, number: int) -> TableMonster:
    """한 마리의 상태를 만든다. 시트의 숫자를 복사하고, HP 를 가득 채우고, 살아 있는 것으로 둔다."""
    return TableMonster(
        id=uuid.uuid4(),
        table_id=table_id,
        monster_id=monster.id,
        number=number,
        place_id=place_id,
        abilities=dict(monster.sheet.abilities),
        max_hp=monster.sheet.max_hp,
        hp=monster.sheet.max_hp,
        status=NpcStatus.ALIVE,
    )


def make_monsters(table_id: uuid.UUID, snapshot: Snapshot) -> list[TableMonster]:
    """이 테이블의 몬스터를 마리마다 만든다. 조우의 순서, 그 안의 마리 순서다. 조우가 없으면 빈 목록이다."""
    made: list[TableMonster] = []
    numbers: Counter[uuid.UUID] = Counter()
    for encounter in snapshot.encounters:
        monster = monster_of(snapshot, encounter.monster_id)
        for _ in range(encounter.count):
            numbers[monster.id] += 1
            made.append(new_monster(table_id, monster, encounter.place_id, numbers[monster.id]))
    return made


def traits_of(kind: MonsterKind) -> Traits:
    """이 타입의 성질."""
    return TRAITS[kind]


def is_dead(monster: TableMonster) -> bool:
    """이 몬스터가 죽었는가(부서졌는가). 죽은 몬스터는 겨누지 못하고, 바뀌지 않는다."""
    return monster.status == NpcStatus.DEAD


def status_after(hp: int, lethal: bool, traits: Traits) -> NpcStatus:
    """
    HP 가 바뀐 뒤의 생사. HP 가 있으면 살아 있다. 0 이면 죽이려는 타격이나 부서지는 타입은 죽음, 아니면 쓰러짐이다.

    쓰러진 몬스터가 제압을 또 받으면 쓰러진 채다(부서지는 타입은 쓰러져 있을 일이 없다).
    """
    if not health.is_downed(hp):
        return NpcStatus.ALIVE
    return NpcStatus.DEAD if lethal or traits.destroyed_at_zero else NpcStatus.DOWNED


def change_monster(
    monster: TableMonster, traits: Traits, magnitude: Magnitude, lethal: bool, dice: Dice, cut: int = 0
) -> Change:
    """
    몬스터 한 마리가 피해를 한 번 입는다. 양을 정하는 주사위를 여기서 굴린다. 바뀐 것을 돌려준다.

    몬스터의 상태를 고치는 길은 이 함수 하나다. 상태를 고친다. 저장하지는 않는다. 죽은 몬스터에는 부르지 않는다.
    몬스터에게는 회복이 없다(app/engine/action.py 의 CheckAction). cut 은 방어구와 가죽이 피해에서 깎는 양이다(#276).
    """
    change = health.change_hp(ChangeKind.DAMAGE, magnitude, monster.hp, monster.max_hp, dice, cut)
    monster.hp = change.after
    monster.status = status_after(change.after, lethal, traits)
    return change
