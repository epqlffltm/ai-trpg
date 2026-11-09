# trpg-server/app/rounds/turn_order.py

"""
차례대로 진행하는 방식(#287). 라운드 하나가 한 사람의 차례이고, 모두의 차례 한 바퀴가 게임 안의 한 라운드다.

  - 바퀴: 테이블을 시작할 때와 바퀴의 마지막 차례를 닫을 때 다음 바퀴의 순서를 굴린다(begin_cycle).
    룰북의 차례 능력치의 점수가 높은 쪽이 먼저고, 같으면 서버의 주사위다(app/rounds/initiative.py 와 같은 규칙).
    차례를 받는 사람은 그때 앉아 있고, 캐릭터가 살아 있고 쓰러지지 않은 사람이다(can_take_turn).
    바퀴 중간에 새로 앉은 사람은 다음 바퀴부터 든다(2026-11-09 결정)
  - 차례: 라운드를 열 때 남은 차례에서 다음 사람을 꺼낸다(next_actor). 그사이에 떠났거나 쓰러졌거나 죽은 사람은
    건너뛴다. 꺼낼 사람이 없으면 차례의 주인이 없는 라운드다(마감이나 방장이 닫는다)
  - 바퀴의 끝: 지금 차례를 닫을 때 남은 차례에 받을 사람이 없으면 그 차례가 바퀴의 마지막이다(ends_cycle).
    시간에 걸린 일(시계, 죽음의 굴림, 상태의 피해, 부상의 끝, 몬스터의 움직임 같은 것)은 그때만 돈다
    (app/rounds/service.py 의 begin_closing)
  - 라운드의 cycle: 한꺼번에 진행하면 라운드의 번호와 같다. 차례대로면 테이블의 지금 바퀴다(turn_of)

한꺼번에 진행하는 테이블에서는 여기의 어느 것도 테이블을 바꾸지 않는다. DB 를 모른다. 테이블을 고친다.
"""

import uuid
from dataclasses import dataclass

from app.engine.dice import Dice
from app.engine.ruleset import Ruleset
from app.rounds import initiative
from app.rounds.models import Round
from app.rounds.state import is_down
from app.tables import sheets
from app.tables.models import GameTable, TableMember, TurnMode


@dataclass(frozen=True)
class TurnSlot:
    """새로 여는 라운드의 자리. 게임 안의 라운드(cycle)와 차례의 주인, 시계를 흘릴지다."""

    cycle: int
    actor_id: uuid.UUID | None
    passes_clock: bool


def is_turns(table: GameTable) -> bool:
    """차례대로 진행하는 테이블인가."""
    return table.turn_mode == TurnMode.TURNS


def can_take_turn(member: TableMember) -> bool:
    """차례를 받을 수 있는 사람인가. 시트가 있고, 캐릭터가 죽지 않았고, 쓰러지지 않았다."""
    return member.sheet is not None and not sheets.is_dead(member) and not is_down(member)


def roll_order(table: GameTable, ruleset: Ruleset, dice: Dice) -> list[uuid.UUID]:
    """한 바퀴의 차례. 차례를 받을 수 있는 사람들을 차례 능력치와 주사위로 늘어놓는다. 앉은 순서로 받는다."""
    members = [member for member in table.members if can_take_turn(member)]
    turns = [initiative.member_turn(ruleset, member, set()) for member in members]
    return [turn.member.user_id for turn in initiative.order_turns(turns, ruleset, dice)]


def begin_cycle(table: GameTable, ruleset: Ruleset, dice: Dice) -> None:
    """다음 바퀴를 시작한다. 순서를 굴려 남은 차례에 채우고, 바퀴를 하나 올리고, 지난 기다리기를 비운다."""
    table.turn_queue = [str(user_id) for user_id in roll_order(table, ruleset, dice)]
    table.turn_cycle += 1
    table.turn_waits = []


def find_member(table: GameTable, user_id: uuid.UUID) -> TableMember | None:
    """앉은 사람 중에서 이 사람을 찾는다. 떠났으면 None."""
    return next((member for member in table.members if member.user_id == user_id), None)


def takes_turn(table: GameTable, user_id: uuid.UUID) -> bool:
    """남은 차례의 이 사람이 지금 차례를 받을 수 있는가. 떠났거나 쓰러졌거나 죽었으면 아니다."""
    member = find_member(table, user_id)
    return member is not None and can_take_turn(member)


def next_actor(table: GameTable) -> uuid.UUID | None:
    """남은 차례에서 다음 주인을 꺼낸다. 받을 수 없는 사람은 버린다. 없으면 None 이고 남은 차례는 빈다."""
    queue = [uuid.UUID(one) for one in table.turn_queue]
    while queue:
        user_id = queue.pop(0)
        if takes_turn(table, user_id):
            table.turn_queue = [str(one) for one in queue]
            return user_id
    table.turn_queue = []
    return None


def ends_cycle(table: GameTable) -> bool:
    """지금 차례가 바퀴의 마지막인가. 남은 차례에 받을 수 있는 사람이 없다."""
    return not any(takes_turn(table, uuid.UUID(one)) for one in table.turn_queue)


def is_cycle_end(table: GameTable) -> bool:
    """닫는 라운드가 바퀴의 끝인가. 한꺼번에 진행하면 라운드마다 끝이다."""
    return not is_turns(table) or ends_cycle(table)


def turn_of(table: GameTable, previous: Round | None) -> TurnSlot:
    """
    새로 여는 라운드의 자리. previous 는 앞 라운드다(첫 라운드면 None).

    한꺼번에 진행하면 cycle 은 라운드의 번호이고 첫 라운드가 아니면 시계를 흘린다.
    차례대로면 cycle 은 테이블의 지금 바퀴이고, 바퀴가 바뀌었을 때만(앞 라운드와 다를 때) 시계를 흘린다.
    """
    if not is_turns(table):
        number = previous.number + 1 if previous is not None else 1
        return TurnSlot(cycle=number, actor_id=None, passes_clock=previous is not None)
    actor = next_actor(table)
    passes = previous is not None and previous.cycle != table.turn_cycle
    return TurnSlot(cycle=table.turn_cycle, actor_id=actor, passes_clock=passes)


def waiting_actor(table: GameTable, round_: Round, declared: bool) -> list[uuid.UUID]:
    """차례대로 진행하는 라운드에서 기다리는 사람. 주인이 아직 내지 않았고 차례를 받을 수 있으면 그 사람이다."""
    if round_.actor_id is None or declared or not takes_turn(table, round_.actor_id):
        return []
    return [round_.actor_id]
