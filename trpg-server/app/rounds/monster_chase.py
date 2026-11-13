# trpg-server/app/rounds/monster_chase.py

"""
쫓아오는 몬스터(#254). 시트에 쫓아온다고 적은 몬스터(chases)만 쫓는다.

몬스터의 차례에 그 장소에 칠 캐릭터가 없을 때 본다(app/rounds/monster_attacks.py 의 take_monster_turn).
  - 쫓을 사람은 이번 라운드를 닫기 시작할 때 그 마리와 같은 장소에 있었고, 그 뒤 차례에서 떠난 캐릭터다(도망친 사람).
    죽은 캐릭터는 쫓지 않는다. 쓰러진 채 업혀 간 캐릭터는 쫓는다
  - 따라가는 것은 길 한 칸이다. 마리의 장소에서 그 캐릭터가 선 곳으로 한 칸에 가는 길이 있어야 한다.
    한 라운드에 두 칸 이상 멀어졌으면 놓친다. 놓치면 그 자리에 멈추고 돌아가지 않는다(2026-11-08 결정)
  - 몬스터는 문을 열지 못한다. 잠긴 길, 빗장이 걸린 길, 넘기 판정이 있는 길은 따라가지 못한다.
    도망친 사람이 열쇠로 연 문과 푼 빗장은 열린 채라 따라간다(app/rounds/map_actions.py 의 pass_route)
  - 쫓을 사람이 여럿이면 마지막으로 싸운 사람(last_foe)이다. 그 사람이 없으면 서버의 주사위로 고른다(2026-11-08 결정)
  - 따라간 차례에는 치지 않는다. 다음 라운드에 같은 장소에서 친다(2026-11-08 결정). 도망친 사람은 한 라운드를 번다
  - 차례가 도망친 사람보다 먼저 왔으면 그 자리에서 친다. 그 사람이 떠난 뒤의 차례가 아니면 쫓지 않는다

차례의 outcome 에 chased 를 적는다. 덫은 밟지 않는다(싸울 때만 밟는다, app/rounds/foe_traps.py).
DB 를 모른다. 마리의 장소를 고친다. 저장하지는 않는다.
"""

import uuid

from app.assets.scenarios.snapshot import RouteSnapshot, place_entries
from app.engine.dice import choose
from app.rounds.effects import Judging
from app.rounds.monster_scene import SceneMonster
from app.tables import places, route_locks, sheets
from app.tables.models import TableMember


def chases(monster: SceneMonster) -> bool:
    """이 마리가 쫓아오는 몬스터인가. 시트에 적었어야 한다."""
    return monster.definition.chases


def passable(judging: Judging, route: RouteSnapshot | None) -> bool:
    """몬스터가 그 길을 지나갈 수 있는가. 길이 있고, 잠기지 않았고, 빗장이 걸리지 않았고, 넘기 판정이 없어야 한다."""
    if route is None or route.cross is not None:
        return False
    return not route_locks.is_locked(judging.table, route) and not route_locks.is_barred(judging.table, route)


def route_to(judging: Judging, monster: SceneMonster, there: uuid.UUID | None) -> RouteSnapshot | None:
    """마리의 장소에서 there 로 한 칸에 가는, 테이블이 아는 길. 없으면 None."""
    if there is None or judging.snapshot is None:
        return None
    known = places.known_map(judging.snapshot, places.knowledge(judging.table))
    return places.route_between(known, monster.state.place_id, there)


def fled(judging: Judging, monster: SceneMonster) -> list[TableMember]:
    """
    이 마리에게서 도망친 캐릭터들 중 따라갈 수 있는 사람. 앉은 순서다.

    라운드를 닫기 시작할 때 그 마리의 장소에 있었고, 지금은 다른 곳에 서 있고, 죽지 않았고,
    한 칸에 따라갈 수 있어야 한다.
    """
    here = monster.state.place_id
    return [
        member
        for member in judging.table.members
        if member.sheet is not None
        and judging.places_at_start.get(member.user_id) == here
        and member.sheet.place_id not in (here, None)
        and not sheets.is_dead(member)
        and passable(judging, route_to(judging, monster, member.sheet.place_id))
    ]


def pick_quarry(judging: Judging, monster: SceneMonster, runaways: list[TableMember]) -> TableMember:
    """쫓을 사람. 마지막으로 싸운 사람이 그중에 있으면 그 사람, 없으면 서버의 주사위다. runaways 는 비어 있지 않다."""
    for member in runaways:
        if member.user_id == monster.state.last_foe:
            return member
    return choose(runaways, judging.dice)


def place_document(judging: Judging, place_id: uuid.UUID) -> dict:
    """결과에 적을 장소. 항목의 ID 와 이름이다(무작위 조우의 장소와 같은 모양)."""
    names = {entry.id: entry.name for entry in place_entries(judging.snapshot)} if judging.snapshot else {}
    return {'entry_id': str(place_id), 'name': names.get(place_id, '')}


def chase(judging: Judging, monster: SceneMonster) -> dict | None:
    """
    도망친 사람을 길 한 칸 따라간다. 차례의 outcome 에 적을 문서를 돌려준다. 쫓지 않으면 None 이다.

    쫓아오는 몬스터가 아니거나 따라갈 사람이 없으면 쫓지 않는다. 따라가면 마리의 장소가 그 사람이 선 곳이 된다.
    """
    if not chases(monster):
        return None
    runaways = fled(judging, monster)
    if not runaways:
        return None
    quarry = pick_quarry(judging, monster, runaways)
    origin = monster.state.place_id
    monster.state.place_id = quarry.current_sheet.place_id
    return {
        'chased': {
            'user_id': str(quarry.user_id),
            'character_name': quarry.character_name,
            'from_place': place_document(judging, origin),
            'to_place': place_document(judging, monster.state.place_id),
        }
    }
