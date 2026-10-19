# game-server/app/rounds/drops.py

"""
몬스터를 쓰러뜨리면 엔진이 드롭을 준다(#372). 방장은 PC 라서 얻는 것을 정하지 않는다(#367).

  - 살아 있던 마리가 처음 쓰러졌을 때(제압이든 죽임이든) 한 번만 굴린다. 이미 쓰러진 마리를 죽여도 다시 굴리지 않는다.
    몬스터에게는 회복이 없어서 살아 있음에서 쓰러짐이나 죽음으로 바뀌는 일은 마리마다 한 번뿐이다.
  - 나올 것은 그 마리가 지금 지닌 것(장비와 소지품, app/tables/monster_items.py)뿐이다(#456).
    줄마다 판에 적은 확률로 따로 굴려 정한다(app/engine/drops.py). 나온 줄은 그 마리에게서 빠진다.
    나오지 않은 줄은 그 마리가 그대로 지닌다. 이미 빼앗긴 것은 나오지 않는다.
  - 받는 사람은 그 마리가 있던 장소의 죽지 않은 캐릭터 중 한 명이다. 서버의 주사위로 고른다.
    한 번 쓰러뜨리면 한 명을 고르고 나온 것을 모두 그 사람이 받는다. 쓰러져 있어도 죽지 않았으면 받는다.
    막타를 친 사람에게 주지 않는다. 막타를 노리게 된다.
  - 받을 사람이 없으면 나온 것은 사라진다. 한 가지의 상한을 넘으면 넘친 몫을 잃는다.
    라운드를 닫는 중이라 예외를 던져 라운드를 깨지 않는다. 잃은 것도 결과에 적는다.

판정 안에서 한 번 부른다(app/rounds/checks.py). 결과는 선언의 outcome 에 적히고 그 뒤로는 읽기만 한다.
서술을 다시 맡겨도 다시 굴리지 않는다. 이벤트(items_gained)는 라운드를 적을 때 남긴다(app/rounds/records.py).
DB 를 모른다. 소지품을 고친다. 저장하지는 않는다.
"""

import uuid

from app.engine.dice import choose
from app.engine.drops import Dropped, comes_out
from app.rounds.effects import Judging
from app.rounds.monster_scene import SceneMonster, find_scene_monster
from app.tables import items, monster_items, sheets
from app.tables.models import GameTable, NpcStatus, TableMember

# 드롭의 출처. 이벤트의 source 에 적는다. 지금은 몬스터뿐이다
MONSTER_SOURCE = 'monster'


def downed_now(effect: dict) -> bool:
    """이 변화로 살아 있던 마리가 처음 쓰러졌거나 죽었는가."""
    return effect['status_before'] == NpcStatus.ALIVE and effect['status'] != NpcStatus.ALIVE


def heirs(table: GameTable, place_id: uuid.UUID) -> list[TableMember]:
    """그 장소에서 드롭을 받을 수 있는 사람들. 지금 캐릭터가 그 장소에 있고 죽지 않았다. 앉은 순서다."""
    return [
        member
        for member in table.members
        if member.sheet is not None and member.sheet.place_id == place_id and not sheets.is_dead(member)
    ]


def stow(judging: Judging, member: TableMember, dropped: list[Dropped]) -> list[dict]:
    """
    나온 것을 그 사람에게 담는다. 한 가지의 상한까지만 담고 넘친 몫은 잃는다. 물건마다 담은 것을 문서로 돌려준다.

    count 는 받은 개수, lost 는 잃은 개수, total 은 받은 뒤의 개수다.
    """
    stowed = []
    for one in dropped:
        given = items.add_up_to(judging.table.id, member.sheet, one.entry_id, one.count)
        stowed.append(
            {
                'entry_id': str(one.entry_id),
                'name': judging.items[one.entry_id].name,
                'count': given,
                'lost': one.count - given,
                'total': items.count_of(member.sheet, one.entry_id),
            }
        )
    return stowed


def vanish(judging: Judging, dropped: list[Dropped]) -> list[dict]:
    """받을 사람이 없어 나온 것이 모두 사라졌다. stow 와 같은 모양으로 돌려준다. 아무도 갖지 않아 total 이 없다."""
    return [
        {
            'entry_id': str(one.entry_id),
            'name': judging.items[one.entry_id].name,
            'count': 0,
            'lost': one.count,
            'total': None,
        }
        for one in dropped
    ]


def describe(monster: SceneMonster, member: TableMember | None, things: list[dict]) -> dict:
    """드롭을 선언의 outcome 에 적을 모양. 어느 마리에게서, 누가, 무엇을 받았는가. 받은 사람이 없으면 None 이다."""
    return {
        'source': MONSTER_SOURCE,
        'monster_id': str(monster.state.id),
        'monster_name': monster.name,
        'user_id': str(member.user_id) if member else None,
        'character_name': member.character_name if member else None,
        'items': things,
    }


def hand_out(judging: Judging, monster: SceneMonster, dropped: list[Dropped]) -> dict:
    """나온 것을 받을 사람 한 명을 골라 준다. 받을 사람이 없으면 사라진다."""
    candidates = heirs(judging.table, monster.state.place_id)
    if not candidates:
        return describe(monster, None, vanish(judging, dropped))
    member = choose(candidates, judging.dice)
    return describe(monster, member, stow(judging, member, dropped))


def fall_from(monster: SceneMonster, judging: Judging) -> list[Dropped]:
    """
    처음 쓰러진 마리가 지닌 것에서 떨어질 것을 줄마다 굴린다. 떨어진 줄은 그 마리에게서 뺀다. 줄의 차례다.

    지닌 것이 없으면 굴리지 않는다. 나온 줄은 지금 지닌 개수 그대로 나온다.
    """
    fallen = []
    for one in monster_items.carried(monster.state, monster.definition):
        if comes_out(one.chance, judging.dice):
            monster_items.set_count(monster.state, one.slot, 0)
            fallen.append(Dropped(entry_id=one.entry_id, count=one.count))
    return fallen


def drop_after(judging: Judging, effect: dict | None) -> dict | None:
    """
    몬스터의 변화 뒤에 드롭을 굴리고 준다. 준(또는 사라진) 것을 문서로 돌려준다.

    처음 쓰러진 것이 아니거나, 지닌 것이 없는 마리거나, 굴려서 아무것도 안 나왔으면 None 이다. 그때는 굴린 것만 있다.
    """
    if effect is None or not downed_now(effect):
        return None
    monster = find_scene_monster(judging.monsters, uuid.UUID(effect['monster_id']))
    if monster is None:
        return None
    dropped = fall_from(monster, judging)
    if not dropped:
        return None
    return hand_out(judging, monster, dropped)
