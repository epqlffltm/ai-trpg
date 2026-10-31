# trpg-server/app/rounds/happening_traps.py

"""
판의 사건이 옮긴 캐릭터와 인물이 닿은 곳의 덫을 밟는 것(#806 ②-c). 라운드가 닫힐 때 사건 바로 뒤에 정한다
(app/rounds/service.py 의 begin_closing).

  - 사건(app/rounds/happenings.py)은 행동의 판정이 끝난 뒤에 일어난다. 덫을 밟을 판정 도구(규칙, 주사위, 판의 물건)를
    여기서 다시 모은다(app/rounds/judging.py 의 build_judging). 이 라운드에 일어난 사건이 누구를 옮겼고
    테이블에 놓인 덫이 있을 때만 모은다.
  - 캐릭터는 가기로 들어온 것과 같다(app/rounds/trap_actions.py 의 spring_on_arrival). 그 장소의 아직 찾지 못한 덫을
    놓은 순서대로 터뜨린다. 찾아낸 덫은 밟지 않는다. 걸려 죽으면 남은 덫은 그대로다.
  - 인물은 싸우는 인물과 같다(app/rounds/foe_traps.py 의 npc_steps). 장면 밖으로 옮겨졌어도 밟는다.
    인물은 테이블이 덫을 찾아냈는지 모르므로 그 장소의 덫을 모두 놓은 순서대로 밟는다. 죽으면 멈춘다.
  - 밟은 것은 일어난 사건의 줄(table_happenings.traps)에 적는다. 사건의 이벤트에는 싣지 않는다
    (맞춘 수치에 보이기가 있다). 이벤트는 사건(happening_occurred)에 trap_sprung 들을 잇는다(record).
  - 이 라운드에 쉰 사람의 휴식은 사건보다 먼저 정했다. 사건 뒤의 덫에 다쳐도 그 휴식은 깨지지 않는다.

DB 를 모른다(이벤트를 적는 record 말고). 덫과 밟은 쪽의 상태와 사건의 줄을 고친다. 저장하지 않는다.
"""

import dataclasses
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import Dice
from app.events.models import TableEvent
from app.rounds import foe_traps, records
from app.rounds.cast import CastMember, Scene, cast_member_of, find_cast_member
from app.rounds.effects import Judging
from app.rounds.judging import build_judging
from app.rounds.models import Round
from app.rounds.trap_actions import spring_on_arrival
from app.tables import npcs, sheets, traps
from app.tables.models import GameTable, TableHappening
from app.tables.state import find_member


def rows_of(table: GameTable, round_number: int) -> list[TableHappening]:
    """이 라운드에 일어난 사건 가운데 누군가를 옮긴 것들."""
    return [row for row in table.happenings if row.round_number == round_number and (row.moves or row.npc_moves)]


def settle(table: GameTable, round_: Round, dice: Dice, scene: Scene) -> None:
    """
    이 라운드의 사건이 옮긴 사람과 인물이 닿은 곳의 덫을 밟는다.

    놓인 덫이 없거나 옮긴 사람이 없으면 아무것도 안 한다(판을 다시 읽지 않는다).
    """
    rows = rows_of(table, round_.number)
    if not rows or not any(traps.is_armed(trap) for trap in table.traps):
        return
    judging = build_judging(table, round_, dice, scene)
    for row in rows:
        row.traps = [*character_traps(judging, row), *npc_traps(judging, row, round_.scene)]


def character_traps(judging: Judging, row: TableHappening) -> list[dict]:
    """사건 하나가 옮긴 캐릭터들이 닿은 곳에서 터뜨린 덫들. 옮긴 차례, 놓은 차례다."""
    stepped = []
    for move in row.moves:
        member = find_member(judging.table, uuid.UUID(move['user_id']))
        if member is None or member.sheet is None or sheets.is_dead(member):
            continue
        who = {'kind': 'pc', 'user_id': move['user_id'], 'character_name': move['character_name']}
        stepped.extend({**who, 'place': move['to'], 'trap': sprung} for sprung in spring_on_arrival(judging, member))
    return stepped


def with_person(judging: Judging, person: CastMember) -> Judging:
    """그 인물이 장면에 없으면 장면의 인물에 더한 판정 도구. HP 를 바꾸는 함수들이 장면에서 인물을 찾는다."""
    if find_cast_member(judging.cast, person.entry_id) is not None:
        return judging
    return dataclasses.replace(judging, cast=[*judging.cast, person])


def npc_traps(judging: Judging, row: TableHappening, scene: str) -> list[dict]:
    """사건 하나가 옮긴 인물들이 닿은 곳에서 밟은 덫들. 옮긴 차례, 놓은 차례다. 죽은 인물은 밟지 않는다."""
    stepped = []
    states = {npc.entry_id: npc for npc in judging.npcs}
    for move in row.npc_moves:
        npc = states.get(uuid.UUID(move['entry_id']))
        if npc is None:
            continue
        person = find_cast_member(judging.cast, npc.entry_id) or cast_member_of(judging.snapshot, scene, npc)
        local = with_person(judging, person)
        who = {'kind': 'npc', 'entry_id': move['entry_id'], 'name': person.name}
        stepped.extend({**who, 'place': trap['place'], 'trap': trap} for trap in steps_until_done(local, person))
    return stepped


def steps_until_done(judging: Judging, person: CastMember) -> list[dict]:
    """인물이 그 장소의 덫을 놓은 순서대로 모두 밟는다. 죽으면 멈춘다."""
    stepped = []
    while not npcs.is_dead(person.npc):
        one = foe_traps.npc_steps(judging, person)
        if one is None:
            break
        stepped.append(one)
    return stepped


def find_row(table: GameTable, round_number: int, entry_id: str) -> TableHappening | None:
    """이 라운드에 일어난 그 사건의 줄."""
    return next(
        (row for row in table.happenings if row.round_number == round_number and str(row.entry_id) == entry_id), None
    )


def record(session: AsyncSession, table: GameTable, round_number: int, occurred: list[tuple[dict, TableEvent]]) -> None:
    """
    사건이 옮긴 쪽이 밟은 덫마다 이벤트를 적는다. 그 사건의 이벤트(happening_occurred)에 잇는다.

    캐릭터는 가기에서 터진 덫과 같은 모양이고(records.record_trap_sprung), 인물은 싸우는 인물이 밟은 덫과 같다
    (records.record_stepped).
    """
    for payload, event in occurred:
        row = find_row(table, round_number, payload['entry_id'])
        for one in (row.traps or []) if row is not None else []:
            if one['kind'] == 'pc':
                mover = {'user_id': one['user_id'], 'character_name': one['character_name'], 'to': one['place']}
                records.record_trap_sprung(session, table, mover, one['trap'], event)
            else:
                records.record_stepped(
                    session, table, round_number, 'npc', one['entry_id'], one['name'], one['trap'], event
                )
