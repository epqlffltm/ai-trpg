# trpg-server/app/rounds/waits.py

"""
기다리기. 시간을 건너뛰는 행동(wait)을 받고, 라운드가 닫힐 때 시간이 흐를지 정한다(#367).

"사흘 뒤"처럼 장면을 건너뛰는 시간은 방장이 정하던 것이다(다음 걸음 정하기). 방장은 PC 라서
기한이 있는 퀘스트를 혼자 넘기게 하면 안 된다. 그래서 앉은 사람 모두가 기다리기를 선언해야 흐른다.
  - 받기: 1분~일주일(app/engine/action.py 의 WaitAction). 규칙과 상관없다. 몬스터가 있어도 받는다.
  - 차례(judge_wait): 부른 시간만 적는다. 흐를지는 아직 모른다. 뒤의 차례에 맞을 수 있다.
  - 라운드가 닫힐 때(settle): 판정과 죽음의 굴림을 다 끝낸 뒤에 본다.
    선언을 낸 사람이 모두 기다리기였고, 내지 않은 사람이 없고(쓰러진 사람은 세지 않는다),
    그 라운드에 아무도 맞지 않았으면 다음 라운드가 적어도 가장 짧게 부른 시간만큼 뒤에 열린다.
    아니면 기다림이 깨진다. 까닭은 hurt(누가 맞았다)나 not_all(모두가 기다리지 않았다)이다.
    가장 짧은 것을 따른다. 길게 부른 사람도 그만큼은 기다리겠다고 한 것이다.
  - 부상이 낫는 것과 저절로 회복하기는 늘어난 걸음(장면이 끝나는 때)으로 본다. 그래서 그것들보다 먼저 정한다
    (app/rounds/service.py 의 begin_closing). 기다리는 것은 쉬는 것이 아니다. 쉬기의 회복은 없다.
  - 퀘스트의 기한은 라운드가 열린 시각으로 본다(app/rounds/deadlines.py). 기다려 기한을 넘기면 다음 라운드가
    닫힐 때 실패한다. 기한이 지나 열린 그 라운드에 이루면 성공이다(기한의 규칙 그대로).

DB 를 모른다. 선언의 결과와 테이블의 시계(다음 걸음)를 고친다. 저장은 부른 쪽이 한다.
"""

import enum
import uuid

from app.calendar import state as calendar
from app.engine.action import WaitAction
from app.rounds.models import Declaration, Round
from app.rounds.state import find_declaration, is_down, wait_of, waiting_for
from app.tables.models import GameTable


class Broken(enum.StrEnum):
    """기다림이 깨진 까닭."""

    # 그 라운드에 누가 피해를 입었다. 싸우는 중에 시간을 건너뛰지 않는다
    HURT = 'hurt'
    # 기다리기가 아닌 행동을 냈거나 선언을 내지 않은 사람이 있다
    NOT_ALL = 'not_all'


def accept_wait(action: WaitAction) -> dict:
    """기다리는 행동을 받는다. 규칙과 장소를 보지 않는다. 저장할 모양을 돌려준다."""
    return action.model_dump(mode='json')


def judge_wait(action: WaitAction) -> dict:
    """기다리는 사람의 차례. 부른 시간을 적는다. 흐를지는 라운드가 닫힐 때 정한다(settle)."""
    return {'wait': {'minutes': action.minutes}}


def waiting(table: GameTable, round_: Round) -> list[Declaration]:
    """이번 라운드에 기다린 사람들의 선언. 앉은 순서다. 차례가 와서 기다리기를 적은 사람만이다."""
    declarations = [find_declaration(round_, member.user_id) for member in table.members]
    return [declaration for declaration in declarations if wait_of(declaration) is not None]


def someone_else_acted(table: GameTable, round_: Round) -> bool:
    """
    기다리지 않은 사람이 있는가. 기다리기가 아닌 선언을 냈거나, 내야 했는데 내지 않았다.

    쓰러진 사람은 선언을 내지 않으므로 세지 않는다. 차례가 오기 전에 쓰러진 사람의 기다리기는 적히지 않았다.
    """
    if waiting_for(table, round_):
        return True
    for member in table.members:
        declaration = find_declaration(round_, member.user_id)
        if declaration is not None and not is_down(member) and wait_of(declaration) is None:
            return True
    return False


def broken_by(table: GameTable, round_: Round, hurt: set[uuid.UUID]) -> Broken | None:
    """기다림이 깨진 까닭. 깨지지 않았으면 None. 맞은 것을 먼저 본다."""
    if hurt:
        return Broken.HURT
    if someone_else_acted(table, round_):
        return Broken.NOT_ALL
    return None


def shortest(declarations: list[Declaration]) -> int:
    """기다린 사람들이 부른 시간 중 가장 짧은 것(분)."""
    return min(wait_of(declaration)['minutes'] for declaration in declarations)


def finish_wait(declaration: Declaration, broken: Broken | None) -> None:
    """기다린 사람 하나의 결과를 그 선언의 outcome 의 wait 에 적는다. 흘렀는지(waited)와 깨진 까닭이다."""
    result = {**wait_of(declaration), 'waited': broken is None, 'reason': broken}
    # 새 문서로 바꿔 끼운다. 안을 고치면 DB 의 JSON 칸이 바뀐 줄 모른다
    declaration.outcome = {**declaration.outcome, 'wait': result}


def settle(table: GameTable, round_: Round, hurt: set[uuid.UUID]) -> None:
    """
    라운드가 닫힐 때 기다림을 끝낸다. 모두 기다렸고 아무도 맞지 않았으면 다음 걸음을 가장 짧은 시간까지 늘린다.

    hurt 는 이번 라운드에 피해를 입은 사람들이다(app/rounds/judging.py 의 roll_checks).
    기다린 사람이 없으면 아무것도 하지 않는다.
    """
    declarations = waiting(table, round_)
    if not declarations:
        return
    broken = broken_by(table, round_, hurt)
    for declaration in declarations:
        finish_wait(declaration, broken)
    if broken is None:
        calendar.stretch_next_step(table, shortest(declarations))
