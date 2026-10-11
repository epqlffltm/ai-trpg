# game-server/app/rounds/acceptance.py

"""
선언을 받는다. 선언에 붙은 행동을 테이블과 견주어 보고, 저장할 모양으로 바꿔 라운드에 적는다.

DB 를 모른다. 이미 읽어 온 테이블, 자리, 라운드, 이번 장면의 인물을 받는다.
저장은 부른 쪽(app/rounds/service.py)이 한다.

행동은 둘이다(app/engine/action.py).
  - 판정(CheckAction). 이번 장면에 나온 NPC 를 겨눌 수 있다(app/rounds/cast.py). 노려 칠 수도 있다.
  - 치료(TreatAction). 능력과 난이도는 규칙이 정한다. 대상이 그 부상을 입고 있어야 한다.
누구를 겨눌 수 있는지는 선언을 받을 때와 닫기 시작할 때 같다. 장면은 라운드가 열린 뒤로 바뀌지 않는다.
비워 둔 칸(난이도, 회복과 치료의 대상)은 여기서 채워 저장한다. 읽는 쪽이 "비어 있으면"을 다시 따지지 않는다.
"""

import uuid

from app.engine import action as actions
from app.engine.action import CheckAction, TreatAction
from app.engine.ruleset import Ruleset
from app.rounds import injuries as round_injuries
from app.rounds.cast import CastMember, find_cast_member
from app.rounds.errors import ActionNotInRulesError, ActionTargetError, Conflict, RoundConflictError
from app.rounds.models import Declaration, Round
from app.rounds.state import find_declaration, is_down, rules_of
from app.tables import npcs, sheets
from app.tables import service as tables
from app.tables.models import GameTable, TableMember


def aim(action: CheckAction, actor_id: uuid.UUID) -> CheckAction:
    """
    회복의 대상을 비워 뒀으면 행동한 사람 자신으로 채운 행동을 돌려준다. 받은 행동은 고치지 않는다.

    저장하는 행동에는 회복이 있으면 늘 대상이 적혀 있게 한다. 읽는 쪽이 "비어 있으면 자기"를 다시 따지지 않는다.
    NPC 를 회복시키는 행동은 대상이 NPC 다. 채우지 않는다.
    """
    if action.recover is None or action.target is not None or action.npc is not None:
        return action
    return action.model_copy(update={'target': actor_id})


def aim_treatment(action: TreatAction, actor_id: uuid.UUID) -> TreatAction:
    """치료받는 쪽을 비워 뒀으면 치료하는 사람 자신으로 채운 행동을 돌려준다. 받은 행동은 고치지 않는다."""
    if action.target is not None or action.npc is not None:
        return action
    return action.model_copy(update={'target': actor_id})


def require_npc_target(cast: list[CastMember], npc_id: uuid.UUID, aim: str | None) -> None:
    """
    겨눈 NPC 가 이번 장면의 살아 있는(쓰러졌어도 된다) 인물인지 본다. 노려 쳤으면 그 부상을 아직 입지 않았는지도 본다.

    장면에 나오지 않았으면 ActionTargetError, 이미 죽었거나 노린 부상을 이미 입었으면 RoundConflictError.
    """
    member = find_cast_member(cast, npc_id)
    if member is None:
        raise ActionTargetError('npc')
    if npcs.is_dead(member.npc):
        raise RoundConflictError(Conflict.NPC_DEAD)
    if aim is not None and round_injuries.wears(member.npc.injuries, aim):
        raise RoundConflictError(Conflict.ALREADY_INJURED)


def require_able(table: GameTable, member: TableMember) -> Ruleset:
    """
    선언하는 사람이 행동을 붙일 수 있는지 본다. 이 테이블의 규칙을 돌려준다.

    쓰러져 있거나, 행동을 막는 부상(기절 같은 것)을 입었으면 RoundConflictError. 그 사람은 글만 낼 수 있다.
    """
    if is_down(member):
        raise RoundConflictError(Conflict.CHARACTER_DOWNED)
    ruleset = rules_of(table)
    if member.sheet is not None and round_injuries.is_incapacitated(ruleset, member.sheet.injuries):
        raise RoundConflictError(Conflict.CHARACTER_INCAPACITATED)
    return ruleset


def accept_check(
    table: GameTable, member: TableMember, action: CheckAction, cast: list[CastMember], ruleset: Ruleset
) -> dict:
    """
    판정하는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 규칙에 없는 능력, 난이도, 양의 등급이면 ActionNotInRulesError.
      - 대상이 이 테이블에 앉은 사람이 아니면 ActionTargetError.
      - 겨눈 NPC 가 이번 장면의 인물이 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 노린 부상이 규칙에서 노릴 수 없는 것이면 ActionNotInRulesError, 대상이 이미 입었으면 RoundConflictError.
    비워 둔 난이도는 규칙의 기본 난이도로, 비워 둔 회복의 대상은 자기 자신으로 채운다.
    """
    fault = actions.find_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    if action.target is not None and tables.find_member(table, action.target) is None:
        raise ActionTargetError('target')
    if action.npc is not None:
        require_npc_target(cast, action.npc, action.aim)
    return aim(actions.settle(ruleset, action), member.user_id).model_dump(mode='json')


def patient_rows(table: GameTable, action: TreatAction, cast: list[CastMember]) -> list:
    """
    치료받는 쪽의 부상 목록. 대상을 채운 행동(aim_treatment)에 쓴다.

      - NPC 가 이번 장면의 인물이 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 앉은 사람이 아니면 ActionTargetError, 그 캐릭터가 이미 죽었으면 RoundConflictError.
    """
    if action.npc is not None:
        member = find_cast_member(cast, action.npc)
        if member is None:
            raise ActionTargetError('npc')
        if npcs.is_dead(member.npc):
            raise RoundConflictError(Conflict.NPC_DEAD)
        return member.npc.injuries
    patient = tables.find_member(table, action.target)
    if patient is None:
        raise ActionTargetError('target')
    if sheets.is_dead(patient):
        raise RoundConflictError(Conflict.PATIENT_DEAD)
    return patient.sheet.injuries if patient.sheet is not None else []


def accept_treatment(
    table: GameTable, member: TableMember, action: TreatAction, cast: list[CastMember], ruleset: Ruleset
) -> dict:
    """
    치료하는 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다.

      - 규칙에서 치료할 수 없는 부상이면 ActionNotInRulesError(injury).
      - 대상이 앉은 사람이나 이번 장면의 인물이 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 대상이 그 부상을 입고 있지 않으면 RoundConflictError.
    비워 둔 대상은 자기 자신으로 채운다.
    """
    fault = actions.find_treat_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    aimed = aim_treatment(action, member.user_id)
    if not round_injuries.wears(patient_rows(table, aimed, cast), aimed.injury):
        raise RoundConflictError(Conflict.NOT_INJURED)
    return aimed.model_dump(mode='json')


def accept_action(
    table: GameTable, member: TableMember, action: CheckAction | TreatAction | None, cast: list[CastMember]
) -> dict | None:
    """
    선언에 붙은 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다. 행동이 없으면 None.

    member 는 선언하는 사람이고, cast 는 이번 장면의 인물들이다.
    쓰러져 있거나 행동을 막는 부상을 입었으면 RoundConflictError(require_able).
    나머지는 행동의 종류마다 본다(accept_check, accept_treatment).
    """
    if action is None:
        return None
    ruleset = require_able(table, member)
    if isinstance(action, TreatAction):
        return accept_treatment(table, member, action, cast, ruleset)
    return accept_check(table, member, action, cast, ruleset)


def put_declaration(round_: Round, member: TableMember, content: str, action: dict | None) -> None:
    """
    이 사람의 선언을 적는다. 이미 냈으면 글과 행동을 통째로 바꾼다.

    캐릭터 이름을 함께 적어 둔다. 이 사람이 나중에 떠나도 누구의 선언이었는지 남는다.
    """
    declaration = find_declaration(round_, member.user_id)
    if declaration is None:
        round_.declarations.append(
            Declaration(user_id=member.user_id, character_name=member.character_name, content=content, action=action)
        )
    else:
        declaration.content = content
        declaration.action = action
