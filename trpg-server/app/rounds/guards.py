# trpg-server/app/rounds/guards.py

"""
방어하기(#254). 방어 태세를 잡는 행동(defend)을 받고, 라운드가 닫힐 때 누가 방어하는지 정한다.

  - 받기(accept_defend): 규칙과 장소를 보지 않는다. 늘 받는다. 맞서는 굴림의 판이든 고정 난이도의 판이든 든다.
  - 방어가 드는 때(defenders_of): 라운드가 닫힐 때, 판정을 시작하기 전에 정한다. 방어를 선언한 사람은 그 라운드 동안
    방어 태세다. 차례를 기다리지 않는다. 막는 것은 공격에 앞선다. 몬스터가 먼저 쳐도 든다(엄폐와 같다).
  - 막는 법: 그 사람을 노린 몬스터와 NPC 의 공격은 불리하다. 두 번 굴려 나쁜 것을 쓴다(app/engine/check.py).
    불리함은 겹쳐도 두 번만 굴린다(부상의 불리함과 함께여도). 받는 쪽의 굴림(맞서는 굴림)은 그대로다.
  - 차례(judge_defend): 방어 태세를 잡았다고 적는다. 굴림이 없다.
방어는 엔진의 상태다. 서술이 "방패를 들었다"고 써도 생기지 않는다.

DB 를 모른다. 이미 읽어 온 테이블과 선언을 받는다.
"""

import uuid

from app.engine import action as actions
from app.engine.action import DefendAction
from app.rounds.effects import Judging
from app.rounds.models import Declaration
from app.tables.models import TableMember


def accept_defend(action: DefendAction) -> dict:
    """방어하는 행동을 받는다. 규칙과 장소를 보지 않는다. 저장할 모양을 돌려준다."""
    return action.model_dump(mode='json')


def defending(declaration: Declaration) -> bool:
    """방어를 선언했는가."""
    return declaration.action is not None and isinstance(actions.read_action(declaration.action), DefendAction)


def defenders_of(rolling: list[tuple[TableMember, Declaration]]) -> frozenset[uuid.UUID]:
    """이번 라운드에 방어 태세를 잡은 사람들(user_id). 판정을 시작하기 전에 한 번 정한다."""
    return frozenset(member.user_id for member, declaration in rolling if defending(declaration))


def is_guarded(judging: Judging, member: TableMember) -> bool:
    """이 사람이 이번 라운드에 방어 태세인가. 그를 노린 공격은 불리하다."""
    return member.user_id in judging.defending


def judge_defend() -> dict:
    """방어한 사람의 차례. 방어 태세를 잡았다고 적는다. 방어는 판정을 시작할 때 이미 들었다(defenders_of)."""
    return {'defend': {'guarded': True}}


def with_guard(turn: dict, guarded: bool) -> dict:
    """차례의 결과에 방어 태세를 노렸다는 것(guarded)을 붙인다. 아니면 그대로다(방어가 생기기 전의 모양)."""
    return {**turn, 'guarded': True} if guarded else turn
