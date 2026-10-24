# trpg-server/app/rounds/wanders.py

"""
무작위 조우(#283). 라운드가 닫힐 때 길을 오거나 길게 쉰 장소에서 판의 조우 표로 한 번 굴려 몬스터를 놓는다.

굴리는 것도 놓는 것도 엔진이다. 서술은 몬스터를 불러내지 못한다(#254 의 즉흥 조우와 따로다).
  - 무엇이 굴림을 부르나: 걸리는 시간이 있는 길을 한 칸 와서 닿은 장소(arrive), 길게 쉰 사람이 있는 장소(rest).
    한 장소는 한 라운드에 한 번만 굴린다. 같은 장소에 쉰 사람이 있으면 쉬기로 굴린다.
    업혀 온 사람은 따로 부르지 않는다. 업은 사람이 온 것이다.
  - 어느 표로 굴리나: 그 장소의 표가 있으면 그 장소의 것, 없으면 판의 기본 표다. 그중 하루의 때가 맞는 표다.
    길로 왔으면 닿은 때(지금 시각 + 그 길에 걸린 시간), 쉬었으면 눕는 때(지금 시각)다. 맞는 표가 없으면 굴리지 않는다.
  - 그 장소에 살아 있는 몬스터가 이미 있으면 굴리지 않는다. 한 장소에 무리는 하나다.
    그래서 테이블의 몬스터가 끝없이 늘지 않는다.
  - 굴림: 1~100 이 표의 확률 이하면 조우다. 그다음 몬스터의 줄을 몫(weight)대로 하나 뽑는다.
  - 놓기: 그 줄의 마리 수만큼 그 장소에 몬스터를 더한다. 번호는 테이블의 같은 몬스터 뒤로 잇는다.
    쉬기로 굴렸으면 몬스터가 기습한다(줄에 적은 것과 상관없이). 쉬던 사람의 쉬기는 깨진다(app/rounds/rests.py).
    일행이 만나는 것은 다음 라운드다. 그 라운드가 만난 첫 라운드라 기습이 든다(app/rounds/initiative.py).

DB 를 모른다. 테이블과 그 몬스터들을 받아 새 마리를 만든다. 저장(session.add)과 이벤트는 부른 쪽이 한다.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Surprise
from app.assets.scenarios.snapshot import (
    Snapshot,
    WanderMonsterSnapshot,
    WanderTableSnapshot,
    monster_of,
    place_entries,
    read_snapshot,
)
from app.calendar.clock import TimeOfDay, read_time
from app.engine.dice import Dice
from app.events import recorder
from app.events.models import EventType
from app.rounds.models import Round
from app.rounds.state import find_declaration, move_of, rest_of
from app.tables import monsters as table_monsters
from app.tables.models import GameTable, NpcStatus, TableMonster


class Cause:
    """무엇이 굴림을 불렀나. 이벤트의 cause 에 적는다."""

    # 걸리는 시간이 있는 길을 와서 닿았다
    ARRIVE = 'arrive'
    # 길게 쉬었다
    REST = 'rest'


# 조우의 굴림은 1~100 이다. 표의 확률(%) 이하면 조우다
CHANCE_SIDES = 100
# 길게 쉬는 것만 굴림을 부른다. 짧게 쉬는 것은 길을 멈춘 것에 가깝다
LONG_REST = 'long'


@dataclass(frozen=True)
class Trigger:
    """한 장소의 굴림 하나. 어디서(place_id), 무엇이 불렀나(cause), 그때의 시각(minutes, 1일째 0시부터)."""

    place_id: uuid.UUID
    cause: str
    minutes: int


def arrivals(table: GameTable, round_: Round) -> dict[uuid.UUID, int]:
    """
    걸리는 시간이 있는 길로 와서 닿은 장소마다 닿은 시각. 같은 장소에 여럿이 왔으면 가장 늦게 닿은 때다.

    가지 못한 가기에는 걸린 시간(travel_minutes)이 적히지 않는다(app/rounds/map_actions.py 의 judge_move).
    """
    found: dict[uuid.UUID, int] = {}
    for member in table.members:
        move = move_of(find_declaration(round_, member.user_id))
        if move is None or move['travel_minutes'] is None:
            continue
        place = uuid.UUID(move['to']['entry_id'])
        found[place] = max(found.get(place, 0), table.clock.minutes + move['travel_minutes'])
    return found


def rest_places(table: GameTable, round_: Round) -> set[uuid.UUID]:
    """길게 쉰 사람이 서 있는 장소들."""
    places = set()
    for member in table.members:
        rest = rest_of(find_declaration(round_, member.user_id))
        if rest is not None and rest['length'] == LONG_REST and member.sheet.place_id is not None:
            places.add(member.sheet.place_id)
    return places


def find_triggers(table: GameTable, round_: Round) -> list[Trigger]:
    """
    이번 라운드에 굴릴 장소들. 장소마다 하나다. 쉰 사람이 있는 장소는 쉬기로, 아니면 닿은 것으로 굴린다.

    장소의 ID 순서다. 같은 판정이면 늘 같은 순서로 주사위를 굴린다.
    """
    resting = rest_places(table, round_)
    arrived = arrivals(table, round_)
    triggers = [Trigger(place, Cause.REST, table.clock.minutes) for place in resting]
    triggers += [Trigger(place, Cause.ARRIVE, minutes) for place, minutes in arrived.items() if place not in resting]
    return sorted(triggers, key=lambda trigger: str(trigger.place_id))


def fits_time(rule: WanderTableSnapshot, time: TimeOfDay) -> bool:
    """이 표를 이 때에 쓰는가. 때를 비운 표는 언제나 쓴다."""
    return not rule.times or time in rule.times


def table_for(snapshot: Snapshot, place_id: uuid.UUID, time: TimeOfDay) -> WanderTableSnapshot | None:
    """
    그 장소에서 그 때에 쓰는 표. 그 장소의 표가 하나라도 있으면 그중에서, 없으면 판의 기본 표 중에서 찾는다.

    한 장소의 표들은 때가 겹치지 않는다(게시할 때 막았다). 맞는 표가 없으면 None 이다.
    """
    own = [rule for rule in snapshot.wanders if rule.place_id == place_id]
    candidates = own or [rule for rule in snapshot.wanders if rule.place_id is None]
    return next((rule for rule in candidates if fits_time(rule, time)), None)


def has_living_monster(monsters: list[TableMonster], place_id: uuid.UUID) -> bool:
    """그 장소에 살아 있는 몬스터가 있는가. 쓰러지거나 죽은 것은 세지 않는다."""
    return any(monster.place_id == place_id and monster.status == NpcStatus.ALIVE for monster in monsters)


def pick_line(rule: WanderTableSnapshot, dice: Dice) -> WanderMonsterSnapshot:
    """몬스터의 줄 하나를 몫대로 뽑는다. 1 부터 몫의 합까지 굴려 줄의 차례대로 센다."""
    roll = dice.roll(sum(line.weight for line in rule.monsters))
    for line in rule.monsters:
        roll -= line.weight
        if roll <= 0:
            return line
    return rule.monsters[-1]


def roll_line(rule: WanderTableSnapshot, dice: Dice) -> WanderMonsterSnapshot | None:
    """
    표로 한 번 굴린다. 조우가 나면 뽑힌 몬스터의 줄, 아니면 None.

    확률이 0 인 표(안전한 곳)는 굴리지 않는다.
    """
    if rule.chance <= 0 or dice.roll(CHANCE_SIDES) > rule.chance:
        return None
    return pick_line(rule, dice)


def surprise_for(line: WanderMonsterSnapshot, cause: str) -> Surprise:
    """나온 마리의 기습. 쉬는 중에 나왔으면 몬스터가 기습한다. 아니면 줄에 적은 것이다."""
    return Surprise.MONSTERS if cause == Cause.REST else line.surprise


def next_number(monsters: list[TableMonster], monster_id: uuid.UUID) -> int:
    """테이블에서 그 몬스터가 받을 다음 번호. 같은 몬스터의 가장 큰 번호 뒤다. 없으면 1 이다."""
    return max((monster.number for monster in monsters if monster.monster_id == monster_id), default=0) + 1


def spawn(
    table: GameTable, snapshot: Snapshot, monsters: list[TableMonster], trigger: Trigger, line: WanderMonsterSnapshot
) -> list[TableMonster]:
    """뽑힌 줄의 마리 수만큼 그 장소에 몬스터를 만든다. 번호는 테이블의 같은 몬스터 뒤로 잇는다. monsters 에 더한다."""
    monster = monster_of(snapshot, line.monster_id)
    first = next_number(monsters, monster.id)
    made = [
        table_monsters.new_monster(table.id, monster, trigger.place_id, first + offset) for offset in range(line.count)
    ]
    for state in made:
        state.surprise = surprise_for(line, trigger.cause)
    monsters.extend(made)
    return made


def met_document(
    snapshot: Snapshot, trigger: Trigger, line: WanderMonsterSnapshot, made: list[TableMonster], round_number: int
) -> dict:
    """나온 무리 하나를 이벤트와 서술에 적을 모양. 어디에, 무엇이, 몇 마리, 무엇이 불렀나, 누가 기습하나."""
    places = {entry.id: entry.name for entry in place_entries(snapshot)}
    monster = monster_of(snapshot, line.monster_id)
    return {
        'round': round_number,
        'place': {'entry_id': str(trigger.place_id), 'name': places.get(trigger.place_id, '')},
        'monster': {'id': str(monster.id), 'name': monster.name},
        'count': len(made),
        'cause': trigger.cause,
        'surprise': made[0].surprise,
    }


def meet(
    table: GameTable, snapshot: Snapshot, monsters: list[TableMonster], trigger: Trigger, round_number: int, dice: Dice
) -> tuple[dict, list[TableMonster]] | None:
    """한 장소에서 굴린다. 조우가 났으면 (이벤트의 모양, 새 마리들), 아니면 None."""
    rule = table_for(snapshot, trigger.place_id, read_time(trigger.minutes).time_of_day)
    if rule is None or has_living_monster(monsters, trigger.place_id):
        return None
    line = roll_line(rule, dice)
    if line is None:
        return None
    made = spawn(table, snapshot, monsters, trigger, line)
    return met_document(snapshot, trigger, line, made, round_number), made


def settle_wanders(
    table: GameTable, round_: Round, monsters: list[TableMonster], dice: Dice
) -> tuple[list[dict], list[TableMonster]]:
    """
    이번 라운드의 무작위 조우를 모두 정한다. (나온 무리들, 새 마리들)을 돌려준다. 표가 없는 판이면 빈 것이다.

    monsters 는 테이블의 몬스터 전부다. 새 마리를 여기에 더한다. 새 마리를 저장하는 것은 부른 쪽이다.
    """
    triggers = find_triggers(table, round_)
    if not triggers:
        return [], []
    snapshot = read_snapshot(table.content)
    if not snapshot.wanders:
        return [], []
    met, made = [], []
    for trigger in triggers:
        result = meet(table, snapshot, monsters, trigger, round_.number, dice)
        if result is not None:
            met.append(result[0])
            made.extend(result[1])
    return met, made


def ambushed(table: GameTable, round_: Round, met: list[dict]) -> set[uuid.UUID]:
    """쉬는 중에 몬스터가 덮친 사람들. 쉬기로 굴려 무리가 나온 장소에서 쉰 사람이다. 그 쉬기는 깨진다."""
    places = {uuid.UUID(one['place']['entry_id']) for one in met if one['cause'] == Cause.REST}
    return {
        member.user_id
        for member in table.members
        if rest_of(find_declaration(round_, member.user_id)) is not None and member.sheet.place_id in places
    }


def record_wanders(session: AsyncSession, table: GameTable, met: list[dict], group: uuid.UUID) -> None:
    """나온 무리마다 이벤트를 적는다(monsters_appeared). 닫힘의 묶음에 넣는다. 행한 사람은 없다(엔진이 굴렸다)."""
    for payload in met:
        recorder.record(session, table, EventType.MONSTERS_APPEARED, payload=payload, group=group)
