# game-server/app/rounds/service.py

"""
라운드를 읽고, 선언을 받고, 라운드를 닫는다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

테이블의 규칙을 그대로 따른다(app/tables/service.py).
  - 라운드는 테이블에 앉은 사람만 본다.
  - 바꾸는 일(선언, 닫기)은 테이블의 행을 잠그고 한다. 라운드를 따로 잠그지 않는다.
    한 테이블의 일은 테이블 하나의 잠금으로 줄을 세운다. 잠금이 둘이면 서로를 기다리며 멈출 수 있다.

라운드가 닫히는 길은 둘이다. 앉은 사람이 모두 선언을 냈을 때 저절로, 또는 방장이 닫을 때.

닫는 일은 둘로 나뉜다. 사이에 GM 의 서술이 있고, 서술은 오래 걸린다(AI 를 부르면 몇 초에서 십몇 초).
  1. 닫기 시작(begin_closing): 테이블을 잠그고, 선언을 마감하고, 행동을 판정하고, 저장한다.
     라운드는 "닫는 중"이 된다.
  2. 서술: 잠금도 DB 연결도 없이, 요청과 따로 도는 작업이 서술자를 부른다(app/rounds/closing.py).
  3. 닫기 마무리(finish_closing): 다시 잠그고, 서술을 장면으로 하는 다음 라운드를 열고, 저장한다.
잠금을 쥔 채로 서술을 기다리지 않는다. 기다리면 그동안 이 테이블의 채팅과 나가기가 전부 멈춘다.

서술을 맡은 작업은 사라질 수 있다(서버가 꺼짐, 서술자가 실패함). 그러면 라운드가 닫는 중에 머문다.
맡긴 지 한참 지난 라운드는 방장이 닫기를 다시 눌러 서술을 다시 맡긴다(is_stalled).

서술을 맡길 때마다 닫기 시작한 시각(closing_at)을 새로 적는다. 이 시각이 "몇 번째로 맡긴 서술인가"의 표다.
서술을 맡은 작업은 맡을 때의 시각을 들고 다니고, 라운드를 바꾸기 전에 잠금 안에서 그 시각이 아직 같은지 본다.
다시 맡긴 뒤에 늦게 끝난 옛 작업은 시각이 달라 아무것도 바꾸지 못한다. 실패를 적지도, 라운드를 닫지도 못한다.
칸을 따로 두지 않는다. 시각은 테이블을 잠근 채로만 고치고, 다시 맡기려면 실패가 적혔거나 한참 지나야 해서
같은 시각이 두 번 적히지 않는다.

선언은 낼 때가 아니라 라운드가 닫힐 때 이벤트로 적는다. 마지막 글만 적는다.
열려 있는 동안에는 남의 선언이 보이지 않아야 하는데, 이벤트는 앉은 사람 모두가 읽기 때문이다.

판정은 닫기 시작할 때 한 번만 한다. 결과를 선언에 적어 두고, 그 뒤로는 읽기만 한다.
서술이 실패해 다시 맡겨도 주사위를 다시 굴리지 않는다. 다시 굴리면 서술을 실패시켜 결과를 바꿀 수 있다.
서술자에게 줄 각자 한 일도 그때 만들어 라운드에 굳힌다(app/rounds/narration_request.py).
서술은 지금 앉은 사람이 아니라 굳혀 둔 것을 읽는다. 그사이에 누가 나가도 장면에서 빠지지 않는다.

HP 도 그때 한 번만 바뀐다. 판정의 결과에 따라 피해를 입거나 회복한다(app/engine/health.py).
HP 가 0 이면 쓰러진 것이다. 쓰러진 사람은 글만 낼 수 있고, 라운드는 그 사람의 선언을 기다리지 않는다.

행동은 이번 장면에 나온 NPC 를 겨눌 수 있다(app/rounds/cast.py). 성공하면 그 NPC 가 피해를 입거나 회복한다.
NPC 의 상태도 그때 한 번만 바뀐다(app/tables/npcs.py 의 change_npc). 바뀐 것은 판정 뒤에 이벤트로 적는다.
누구를 겨눌 수 있는지는 선언을 받을 때와 닫기 시작할 때 같다. 장면은 라운드가 열린 뒤로 바뀌지 않는다.

쓰러진 캐릭터는 라운드가 닫힐 때마다 죽음의 굴림을 굴린다(app/engine/death.py). 이것도 닫기 시작할 때 한 번만이다.
이번 라운드에 쓰러진 캐릭터는 굴리지 않는다. 동료가 일으킬 틈이 한 라운드는 있다.
이번 라운드에 회복을 받아 일어난 캐릭터도 굴리지 않는다. 행동의 결과를 먼저 끝내고 나서 굴린다.
죽은 캐릭터의 플레이어는 선언을 낼 수 없다. 새 캐릭터가 있어야 한다.

새 캐릭터는 열려 있는 라운드에 들어온다(app/tables/replacements.py). 들어온 것은 라운드에 적힌다(arrivals).
들어온 라운드에는 선언을 내지 않고, 라운드도 그 사람을 기다리지 않는다. 그 라운드의 장면에 아직 없는 인물이다.
라운드가 닫힐 때 서술자가 새 캐릭터를 이야기에 들이고, 다음 라운드부터 행동한다.
"""

import enum
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import NarrationStyle
from app.assets.scenarios.snapshot import read_snapshot
from app.core.config import NARRATION_BUDGET_SECONDS
from app.engine import action as actions
from app.engine import death, health
from app.engine.action import CheckAction, Consequence, Recipient
from app.engine.check import Check
from app.engine.dice import Dice
from app.engine.health import Change, ChangeKind
from app.engine.injury import Trigger
from app.engine.ruleset import Ruleset
from app.events import recorder
from app.events import repository as event_repository
from app.events.models import EventType, TableEvent
from app.rounds import injuries as round_injuries
from app.rounds import narration_request, opener, repository
from app.rounds.cast import CastMember, Scene, cast_of, condition_of, find_cast_member
from app.rounds.models import Declaration, Round, RoundStatus
from app.rounds.narrator import InjuryNote, Move, NarrationRequest, PersonState
from app.rounds.prompt import HISTORY_ROUNDS
from app.rounds.schemas import DeclarationUpdate
from app.tables import injuries, npcs, sheets
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables.models import DeathCause, GameTable, InjurySource, TableMember, TableNpc, TableStatus


class RoundNotFoundError(Exception):
    """그런 번호의 라운드가 없다."""


class Conflict(enum.StrEnum):
    """요청은 맞지만 테이블의 지금 상태와 부딪히는 이유."""

    # 테이블이 아직 시작하지 않았다. 라운드가 하나도 없다
    NOT_STARTED = 'not_started'
    # 테이블이 진행 중이 아니다. 선언과 닫기는 진행 중에만 된다
    NOT_PLAYING = 'not_playing'
    # 라운드가 닫는 중이다. 선언을 마감했고 GM 이 서술하고 있다. 끝나면 다음 라운드가 열린다
    ROUND_CLOSING = 'round_closing'
    # 캐릭터가 쓰러져 있다. 행동을 붙일 수 없다. 글만 낼 수 있다
    CHARACTER_DOWNED = 'character_downed'
    # 캐릭터가 죽었다. 선언을 낼 수 없다. 새 캐릭터가 있어야 한다
    CHARACTER_DEAD = 'character_dead'
    # 이 라운드에 새로 들어온 캐릭터다. 다음 라운드부터 선언을 낸다
    CHARACTER_ARRIVING = 'character_arriving'
    # 행동이 겨눈 NPC 가 이미 죽었다
    NPC_DEAD = 'npc_dead'
    # 캐릭터가 입은 부상 때문에 행동하지 못한다(기절 같은 것). 글만 낼 수 있다
    CHARACTER_INCAPACITATED = 'character_incapacitated'
    # 노려 친 부상을 대상이 이미 입고 있다(이미 잃은 눈)
    ALREADY_INJURED = 'already_injured'


class RoundConflictError(Exception):
    """테이블의 지금 상태와 부딪힌다. reason 이 이유다."""

    def __init__(self, reason: Conflict) -> None:
        super().__init__(reason)
        self.reason = reason


class ActionNotInRulesError(Exception):
    """
    선언에 붙은 행동이 이 테이블의 규칙에 없는 것을 가리킨다.

    field 는 행동의 어느 칸이 틀렸는지다(ability, difficulty, risk, recover).
    """

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class ActionTargetError(Exception):
    """
    선언에 붙은 행동의 대상이 겨눌 수 없는 것이다.

    field 는 행동의 어느 칸인지다. target 이면 이 테이블에 앉은 사람이 아니고, npc 면 이번 장면에 나온 인물이 아니다.
    """

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


# 서술을 맡은 작업 하나가 쓰는 시간(초). 모두 닫기 시작한 시각(closing_at)부터 센다(app/rounds/closing.py).
# 로어북, 지난 일, 인물의 이력을 고르는 시간. 넘으면 고르지 못한 것 없이 서술한다
RETRIEVAL_BUDGET_SECONDS = 30.0
# 미리 보기를 닫고 닫기를 마무리(저장)하는 시간
SAVING_BUDGET_SECONDS = 15.0
# 작업 전체의 상한. 고르기 + 서술(다시 시도하기와 넘어가기를 합친 NARRATION_BUDGET_SECONDS) + 마무리.
# 이 시간이 지나면 작업을 끊고 실패를 적는다. 멈춘 DB 연결이나 잠금을 하염없이 기다리지 않는다
CLOSING_JOB_SECONDS = RETRIEVAL_BUDGET_SECONDS + NARRATION_BUDGET_SECONDS + SAVING_BUDGET_SECONDS
# 끊긴 뒤에 실패를 적는 시간. 이것도 넘으면 적지 못한 채로 끝나고, 아래의 시간이 지난 뒤에 다시 맡길 수 있다
FAILURE_RECORD_SECONDS = 10.0
# 끊긴 작업이 정리(미리 보기 닫기)를 마칠 여유
CLOSING_RETRY_MARGIN_SECONDS = 5.0
# 닫는 중인 채로 이 시간(초)이 지나면 서술을 맡은 작업이 사라진 것으로 본다. 그때부터 다시 맡길 수 있다.
# 작업이 살아 있을 수 있는 가장 긴 시간보다 길어야 한다. 짧으면 아직 도는 서술 위에 또 서술을 맡긴다.
# 그래서 따로 적지 않고 위의 시간들을 더해서 만든다. 하나를 늘리면 이것도 늘어난다
CLOSING_RETRY_SECONDS = CLOSING_JOB_SECONDS + FAILURE_RECORD_SECONDS + CLOSING_RETRY_MARGIN_SECONDS


class NarrationScheduler(Protocol):
    """
    서술을 뒤에서 돌게 맡기는 것의 모양. 구현은 app/rounds/closing.py 에 있다.

    이 파일이 그 파일을 불러오지 않으려고 모양만 여기 둔다. 그 파일이 이 파일을 불러온다.
    """

    def schedule(self, table_id: uuid.UUID, number: int, started: datetime) -> None:
        """
        이 테이블의 이 라운드의 서술을 맡긴다. 기다리지 않고 바로 돌아온다.

        started 는 이번에 맡기며 적은 닫기 시작한 시각(closing_at)이다. 작업이 이것으로 자기 차례인지 안다.
        """
        ...


# --- 판단하는 작은 함수들. DB 를 건드리지 않는다 ---


def require_playing(table: GameTable) -> None:
    """테이블이 진행 중인지 확인한다. 아니면 RoundConflictError."""
    if table.status == TableStatus.RECRUITING:
        raise RoundConflictError(Conflict.NOT_STARTED)
    if table.status != TableStatus.PLAYING:
        raise RoundConflictError(Conflict.NOT_PLAYING)


def require_started(round_: Round | None) -> Round:
    """라운드가 있는지 확인한다. 테이블이 아직 시작하지 않아 하나도 없으면 RoundConflictError."""
    if round_ is None:
        raise RoundConflictError(Conflict.NOT_STARTED)
    return round_


def require_open(round_: Round) -> None:
    """라운드가 선언을 받는 중인지 확인한다. 닫는 중이면 RoundConflictError."""
    if round_.status != RoundStatus.OPEN:
        raise RoundConflictError(Conflict.ROUND_CLOSING)


def is_run(round_: Round | None, started: datetime) -> bool:
    """
    이 라운드가 started 에 맡긴 서술을 아직 기다리고 있는가. 서술을 맡은 작업이 라운드를 읽거나 바꾸기 전에 본다.

    닫는 중이 아니면(이미 닫혔거나 없다) 아니다. 닫기 시작한 시각이 다르면 그 뒤에 다시 맡긴 것이다. 그것도 아니다.
    """
    return round_ is not None and round_.status == RoundStatus.CLOSING and round_.closing_at == started


def is_stalled(round_: Round, now: datetime) -> bool:
    """
    닫는 중인 라운드의 서술이 멈췄는가. 다시 맡겨도 되는가.

    서술이 끝내 실패한 것을 알면 바로 그렇다. 모르면 서술을 맡은 작업이 사라졌다고 볼 만큼 지났는지로 판단한다.
    now 는 지금 시각이다. 테스트가 시간을 마음대로 흘리려고 받는다.
    """
    if round_.status != RoundStatus.CLOSING:
        return False
    if round_.narration_failed_at is not None:
        return True
    return now - round_.closing_at >= timedelta(seconds=CLOSING_RETRY_SECONDS)


def find_declaration(round_: Round, user_id: uuid.UUID) -> Declaration | None:
    """라운드의 선언 중에서 이 사람의 것을 찾는다."""
    return next((declaration for declaration in round_.declarations if declaration.user_id == user_id), None)


def is_down(member: TableMember) -> bool:
    """이 사람의 캐릭터가 쓰러져 있는가. 시트가 없으면(시작 전) 쓰러진 것이 아니다."""
    return member.sheet is not None and health.is_downed(member.sheet.hp)


def find_arrival(round_: Round, user_id: uuid.UUID) -> dict | None:
    """이 라운드에 새로 들어온 캐릭터 중에서 이 사람의 것을 찾는다. 이 사람이 새 캐릭터를 들이지 않았으면 None."""
    return next((arrival for arrival in round_.arrivals if arrival['user_id'] == str(user_id)), None)


def waiting_for(table: GameTable, round_: Round) -> list[uuid.UUID]:
    """
    앉은 사람 중에서 이 라운드에 선언을 내야 하는데 아직 내지 않은 사람들. 들어온 순서다.

    쓰러진 사람은 기다리지 않는다. 한 사람이 쓰러졌다고 테이블이 멈추지 않게 한다.
    이 라운드에 새 캐릭터를 들인 사람도 기다리지 않는다. 그 캐릭터는 다음 라운드부터 선언을 낸다.
    """
    return [
        member.user_id
        for member in table.members
        if find_declaration(round_, member.user_id) is None
        and not is_down(member)
        and find_arrival(round_, member.user_id) is None
    ]


def rules_of(table: GameTable) -> Ruleset:
    """
    이 테이블의 규칙. 테이블이 들고 있는 판의 복사본에서 읽는다.

    복사본을 통째로 읽는다. 규칙이 없던 때의 복사본이면 그때의 규칙으로 올려 읽어야 하기 때문이다.
    """
    return read_snapshot(table.content).rulebook.rules


def aim(action: CheckAction, actor_id: uuid.UUID) -> CheckAction:
    """
    회복의 대상을 비워 뒀으면 행동한 사람 자신으로 채운 행동을 돌려준다. 받은 행동은 고치지 않는다.

    저장하는 행동에는 회복이 있으면 늘 대상이 적혀 있게 한다. 읽는 쪽이 "비어 있으면 자기"를 다시 따지지 않는다.
    NPC 를 회복시키는 행동은 대상이 NPC 다. 채우지 않는다.
    """
    if action.recover is None or action.target is not None or action.npc is not None:
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


def accept_action(
    table: GameTable, member: TableMember, action: CheckAction | None, cast: list[CastMember]
) -> dict | None:
    """
    선언에 붙은 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다. 행동이 없으면 None.

    member 는 선언하는 사람이고, cast 는 이번 장면의 인물들이다.
      - 쓰러져 있으면 RoundConflictError. 쓰러진 사람은 글만 낼 수 있다.
      - 행동을 막는 부상(기절 같은 것)을 입었으면 RoundConflictError. 그 사람도 글만 낼 수 있다.
      - 규칙에 없는 능력, 난이도, 양의 등급이면 ActionNotInRulesError.
      - 대상이 이 테이블에 앉은 사람이 아니면 ActionTargetError.
      - 겨눈 NPC 가 이번 장면의 인물이 아니면 ActionTargetError, 이미 죽었으면 RoundConflictError.
      - 노린 부상이 규칙에서 노릴 수 없는 것이면 ActionNotInRulesError, 대상이 이미 입었으면 RoundConflictError.
    비워 둔 난이도는 규칙의 기본 난이도로, 비워 둔 회복의 대상은 자기 자신으로 채운다.
    """
    if action is None:
        return None
    if is_down(member):
        raise RoundConflictError(Conflict.CHARACTER_DOWNED)
    ruleset = rules_of(table)
    if member.sheet is not None and round_injuries.is_incapacitated(ruleset, member.sheet.injuries):
        raise RoundConflictError(Conflict.CHARACTER_INCAPACITATED)
    fault = actions.find_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    if action.target is not None and tables.find_member(table, action.target) is None:
        raise ActionTargetError('target')
    if action.npc is not None:
        require_npc_target(cast, action.npc, action.aim)
    return aim(actions.settle(ruleset, action), member.user_id).model_dump(mode='json')


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


def has_outcome(declaration: Declaration | None) -> bool:
    """이 선언에 판정의 결과가 적혀 있는가."""
    return declaration is not None and declaration.outcome is not None


def find_affected(
    table: GameTable, actor: TableMember, action: CheckAction, recipient: Recipient
) -> TableMember | None:
    """
    HP 가 바뀔 사람을 찾는다. 실패의 대가는 행동한 사람이 입고, 회복은 행동의 대상이 받는다.

    대상이 그사이에 테이블을 떠났으면 None.
    """
    return actor if recipient == Recipient.ACTOR else tables.find_member(table, action.target)


@dataclass(frozen=True)
class Judging:
    """
    닫히는 라운드의 판정에 함께 쓰는 것들. 테이블, 규칙, 주사위, 이번 장면의 인물, 라운드의 번호.

    판정 하나와 그 결과(HP, NPC 의 상태, 부상)를 정하는 함수들이 이것을 함께 받는다.
    """

    table: GameTable
    ruleset: Ruleset
    dice: Dice
    cast: list[CastMember]
    round_number: int


def injury_after(judging: Judging, change: Change, max_hp: int, dead: bool, rows: list) -> dict | None:
    """
    피해 뒤에 부상 표를 굴릴 일이면 굴리고, 나온 부상을 입힌다. 굴린 것을 문서로 돌려준다. 굴리지 않았으면 None.

    rows 는 입는 쪽(시트나 NPC 상태)의 부상 목록이다.
    """
    rolled = round_injuries.roll_after(judging.ruleset, judging.dice, change, max_hp, dead)
    if rolled is None:
        return None
    return round_injuries.take(judging.ruleset, rolled, rows, judging.table.id, judging.round_number)


def change_member(judging: Judging, actor: TableMember, action: CheckAction, found: Consequence) -> dict | None:
    """
    앉은 사람의 HP 를 바꾸고, 바뀐 내용을 문서로 돌려준다. 바뀔 HP 가 없으면 None.

    시트의 hp 를 고친다. 저장하지는 않는다. 양을 정하는 주사위를 여기서 굴린다.
    큰 타격이나 쓰러짐이면 부상 표도 굴린다(injury_roll). 양의 주사위 다음에 굴린다.
    돌려준 문서는 선언의 outcome 안에 적힌다. 누구의 HP 가 얼마에서 얼마로 바뀌었는지가 다 담긴다.
    """
    affected = find_affected(judging.table, actor, action, found.recipient)
    # 대상이 떠났거나 시트가 없으면 바뀔 HP 가 없다. 양을 정하는 주사위도 굴리지 않는다.
    # 죽은 캐릭터도 그렇다. 회복으로 되살리지 못한다
    if affected is None or affected.sheet is None or sheets.is_dead(affected):
        return None

    sheet = affected.sheet
    magnitude = health.find_magnitude(judging.ruleset, found.magnitude)
    change = health.change_hp(found.kind, magnitude, sheet.hp, sheet.max_hp, judging.dice)
    sheet.hp = change.after
    # 일어났으면 죽음의 굴림에서 센 것은 처음으로 돌아간다. 다시 쓰러지면 처음부터 센다
    if not change.downed:
        sheets.clear_death_saves(sheet)
    # 캐릭터는 피해로 바로 죽지 않는다(죽음의 굴림으로 죽는다)
    injury_roll = injury_after(judging, change, sheet.max_hp, False, sheet.injuries)
    return {
        'kind': change.kind.value,
        'magnitude': found.magnitude,
        'user_id': str(affected.user_id),
        'character_name': affected.character_name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': sheet.max_hp,
        'downed': change.downed,
        'injury_roll': injury_roll,
    }


def npc_injury(judging: Judging, action: CheckAction, change: Change, npc: TableNpc) -> dict | None:
    """
    HP 가 바뀐 NPC 가 입는 부상. 노려 친 타격이면 그 부상이 확정으로 생기고 표를 굴리지 않는다.
    아니면 큰 타격이나 쓰러짐에 표를 굴린다. 죽었으면 어느 쪽도 없다. 회복이면 아무것도 없다.
    """
    if npcs.is_dead(npc):
        return None
    if action.aim is not None and change.kind == ChangeKind.DAMAGE:
        return round_injuries.take_aimed(
            judging.ruleset, action.aim, npc.injuries, judging.table.id, judging.round_number
        )
    return injury_after(judging, change, npc.max_hp, False, npc.injuries)


def change_cast_member(judging: Judging, action: CheckAction, found: Consequence) -> dict | None:
    """
    겨눈 NPC 의 HP 와 생사를 바꾸고, 바뀐 내용을 문서로 돌려준다. 바뀔 것이 없으면 None.

    상태를 고치는 것은 change_npc 다. 저장하지는 않는다.
    큰 타격이나 쓰러짐이면 부상 표도 굴린다. 죽었으면 굴리지 않는다.
    같은 라운드에 앞사람이 그 NPC 를 죽였으면 아무 일도 없다. 양을 정하는 주사위도 굴리지 않는다.
    문서에는 HP 의 숫자까지 다 적는다. 앉은 사람에게 내보낼 때 숫자를 뺀다(app/rounds/schemas.py, 이벤트의 VISIBLE).
    몸 상태(condition)는 부상까지 정한 뒤의 것이다.
    """
    member = find_cast_member(judging.cast, action.npc)
    # 선언을 받을 때 장면의 인물인지 봤다. 장면은 바뀌지 않으므로 없을 수 없지만, 없으면 아무 일도 없는 것으로 둔다
    if member is None or npcs.is_dead(member.npc):
        return None

    npc = member.npc
    status_before = npc.status
    magnitude = health.find_magnitude(judging.ruleset, found.magnitude)
    change = npcs.change_npc(npc, found.kind, magnitude, action.lethal, judging.dice)
    injury_roll = npc_injury(judging, action, change, npc)
    return {
        'kind': change.kind.value,
        'magnitude': found.magnitude,
        'entry_id': str(member.entry_id),
        'name': member.name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': npc.max_hp,
        'lethal': action.lethal,
        'status_before': status_before,
        'status': npc.status,
        'condition': condition_of(npc),
        'injury_roll': injury_roll,
    }


def apply_consequence(judging: Judging, actor: TableMember, action: CheckAction, check: Check) -> dict:
    """
    판정의 결과에 따라 HP 를 바꾸고, 바뀐 내용을 선언의 outcome 에 넣을 칸들로 돌려준다.

    effect 는 앉은 사람의 변화, npc_effect 는 NPC 의 변화다. 한 판정에서 둘 중 하나만 일어난다. 없으면 둘 다 None.
    대가는 늘 행동한 사람이 입는다. 대상의 일(타격, 회복)은 행동이 NPC 를 겨눴으면 NPC 가, 아니면 앉은 사람이 받는다.
    """
    found = actions.consequence(action, check)
    if found is None:
        return {'effect': None, 'npc_effect': None}
    if found.recipient == Recipient.TARGET and action.npc is not None:
        return {'effect': None, 'npc_effect': change_cast_member(judging, action, found)}
    return {'effect': change_member(judging, actor, action, found), 'npc_effect': None}


def judge(judging: Judging, member: TableMember, action: CheckAction) -> dict:
    """
    한 사람의 행동을 판정하고 그 결과를 정한다. 선언의 outcome 에 적을 문서를 돌려준다.

    그 캐릭터가 입은 부상이 이 행동의 능력에 주는 것(보정 깎기, 불리함)을 판정에 적용한다(hindrance).
    """
    sheet = member.sheet
    hindrance = round_injuries.hindrance_for(judging.ruleset, sheet.injuries, action.ability)
    hindered = actions.attempt_hindered(judging.ruleset, action, sheet.abilities, judging.dice, hindrance)
    return {
        **asdict(hindered.check),
        'hindrance': round_injuries.hindrance_document(hindered),
        'called_shot': round_injuries.called_shot_document(judging.ruleset, action.aim),
        **apply_consequence(judging, member, action, hindered.check),
    }


def roll_checks(table: GameTable, round_: Round, dice: Dice, cast: list[CastMember]) -> None:
    """
    닫히는 라운드의 행동을 판정하고, 결과에 따라 HP 를 바꾸고, 결과를 선언에 적는다. 들어온 순서로 굴린다.

    한 사람의 판정과 그 결과(피해, 회복, 부상)를 끝낸 뒤에 다음 사람으로 넘어간다.
    앞사람이 쓰러뜨린 것을 뒷사람이 일으킬 수 있다. NPC 도 그렇다. 앞사람이 죽인 NPC 는 뒷사람이 바꾸지 못한다.
    cast 는 이번 장면의 인물들이다. NPC 의 상태는 그 안에 들어 있고, 여기서 고친다.

    지금 앉아 있고, 선언에 행동을 붙였고, 시트가 있는 사람만 굴린다.
    진행 중인 테이블에서는 모두에게 시트가 있다(app/tables/sheets.py). 없는 사람이 있어도 라운드는 닫혀야 해서 건너뛴다.

    규칙은 굴릴 사람이 있을 때만 읽는다. 판에 굳은 복사본을 통째로 읽는 일이라 싸지 않다.
    """
    rolling = [
        (member, declaration)
        for member in table.members
        if (declaration := find_declaration(round_, member.user_id)) is not None
        and declaration.action is not None
        and member.sheet is not None
    ]
    if not rolling:
        return

    judging = Judging(table=table, ruleset=rules_of(table), dice=dice, cast=cast, round_number=round_.number)
    for member, declaration in rolling:
        declaration.outcome = judge(judging, member, CheckAction.model_validate(declaration.action))


def find_dying(table: GameTable) -> list[TableMember]:
    """앉은 사람 중에서 캐릭터가 쓰러져 있고 아직 죽지 않은 사람들. 들어온 순서다."""
    return [member for member in table.members if sheets.is_downed_alive(member)]


def roll_death_saves(table: GameTable, dying: list[TableMember], dice: Dice) -> list[dict]:
    """
    죽음의 굴림을 굴리고, 센 것을 시트에 적고, 굴린 것들을 문서의 목록으로 돌려준다. 들어온 순서로 굴린다.

    dying 은 이 라운드의 행동을 판정하기 전에 쓰러져 있던 사람들이다. 그중 지금도 쓰러져 있는 사람만 굴린다.
    그사이에 회복을 받아 일어난 사람은 굴리지 않는다.
    고비를 넘긴 사람과, 죽음의 굴림이 없는 규칙의 테이블은 굴릴 것이 없다(app/engine/death.py).
    실패가 다 모이면 그 자리에서 죽은 것으로 적는다.

    돌려준 목록은 라운드에 적힌다. 서술자와 이벤트는 그것을 읽는다. 다시 굴리지 않는다.
    규칙은 굴릴 사람이 있을 때만 읽는다.
    """
    still_down = [member for member in dying if sheets.is_downed_alive(member)]
    if not still_down:
        return []

    ruleset = rules_of(table)
    rolled = []
    for member in still_down:
        sheet = member.sheet
        save = death.roll_death_save(ruleset, sheet.death_successes, sheet.death_failures, dice)
        if save is None:
            continue
        sheet.death_successes = save.successes
        sheet.death_failures = save.failures
        if save.fate == death.Fate.DEAD:
            sheets.mark_dead(sheet)
        rolled.append({'user_id': str(member.user_id), 'character_name': member.character_name, **asdict(save)})
    return rolled


def build_moves(table: GameTable, round_: Round) -> list[Move]:
    """
    닫히는 라운드에서 각자 한 일을 서술자에게 줄 모양으로 만든다. 닫기 시작할 때 한 번 만들어 라운드에 굳힌다.

    지금 앉아 있는 사람 모두가 들어간다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 들어간다.
    판정의 결과와 HP 의 변화는 선언에 적힌 것을, 죽음의 굴림은 라운드에 적힌 것을 읽는다. 여기서 굴리지 않는다.
    쓰러져 있는지, 죽었는지는 이번 라운드의 결과를 반영한 뒤의 것이다. 그래서 판정과 죽음의 굴림 뒤에 부른다.
    이 라운드에 새로 들어온 캐릭터는 라운드에 적힌 것(arrivals)으로 안다. 누구의 뒤를 잇는지를 함께 준다.
    """
    declarations = [find_declaration(round_, member.user_id) for member in table.members]
    wounded = any(member.sheet is not None and injuries.active(member.sheet.injuries) for member in table.members)
    needs_rules = wounded or any(has_outcome(declaration) for declaration in declarations)
    ruleset = rules_of(table) if needs_rules else None

    moves = []
    for member, declaration in zip(table.members, declarations, strict=True):
        content = declaration.content if declaration else None
        verdict = narration_request.to_verdict(ruleset, declaration) if has_outcome(declaration) else None
        arrival = find_arrival(round_, member.user_id)
        moves.append(
            Move(
                character_name=member.character_name,
                content=content,
                verdict=verdict,
                downed=is_down(member),
                death_save=narration_request.find_death_save(round_, member.user_id),
                dead=sheets.is_dead(member),
                replaces=arrival['replaces'] if arrival else None,
                injuries=worn_notes(ruleset, member),
            )
        )
    return moves


def worn_notes(ruleset: Ruleset | None, member: TableMember) -> list[InjuryNote]:
    """이 사람의 지금 캐릭터가 입고 있는 부상들을 서술자에게 줄 모양으로. 규칙을 읽지 않았으면 입은 것이 없다."""
    if ruleset is None or member.sheet is None:
        return []
    return round_injuries.notes(ruleset, member.sheet.injuries)


def frozen_style(table: GameTable, round_: Round) -> NarrationStyle:
    """
    닫는 중인 라운드에 굳혀 둔 문체를 읽는다.

    굳혀 둔 것이 없으면 지금 테이블의 문체다. 굳히기 전에 닫기 시작한 라운드만 그렇다.
    """
    return NarrationStyle(round_.narration_style or table.narration_style)


def frozen_moves(table: GameTable, round_: Round) -> list[Move]:
    """
    닫는 중인 라운드에 굳혀 둔 각자 한 일을 읽는다.

    굳혀 둔 것이 없으면 지금 앉은 사람들로 만든다. 굳히기 전에 닫기 시작한 라운드만 그렇다(마이그레이션 c9e1f3a5b7d8).
    """
    if round_.moves is None:
        return build_moves(table, round_)
    return narration_request.read_moves(round_.moves)


def to_people(cast: list[CastMember], ruleset: Ruleset) -> list[PersonState]:
    """이번 장면의 인물들을 서술자에게 줄 모양으로. 몸 상태를 말로 적는다. 숫자는 주지 않는다. 입은 부상을 함께 준다."""
    return [
        PersonState(
            name=member.name,
            condition=condition_of(member.npc),
            injuries=round_injuries.notes(ruleset, member.npc.injuries),
        )
        for member in cast
    ]


# --- 읽기 ---


async def get_current_round(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> tuple[GameTable, Round]:
    """
    자기가 앉아 있는 테이블의 가장 최근 라운드를 돌려준다. 테이블도 함께 돌려준다.

    앉지 않았으면 TableNotFoundError, 아직 시작하지 않았으면 RoundConflictError.
    """
    table = await tables.get_table(session, user_id, table_id)
    round_ = require_started(await repository.find_latest_round(session, table_id))
    return table, round_


async def get_scene_cast(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[Round, list[CastMember]]:
    """
    자기가 앉아 있는 테이블의 가장 최근 라운드와, 그 장면의 인물들을 돌려준다. 행동으로 겨눌 수 있는 NPC 들이다.

    앉지 않았으면 TableNotFoundError, 아직 시작하지 않았으면 RoundConflictError.
    """
    table, round_ = await get_current_round(session, user_id, table_id)
    return round_, (await load_scene(session, table, round_)).cast


async def get_round(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, number: int
) -> tuple[GameTable, Round]:
    """자기가 앉아 있는 테이블의 라운드 하나를 번호로 돌려준다. 없으면 RoundNotFoundError."""
    table = await tables.get_table(session, user_id, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if round_ is None:
        raise RoundNotFoundError
    return table, round_


async def list_rounds(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, limit: int, offset: int
) -> tuple[GameTable, list[Round], int]:
    """자기가 앉아 있는 테이블의 라운드 한 쪽과 전체 개수를 돌려준다. 처음 것부터다."""
    table = await tables.get_table(session, user_id, table_id)
    rounds = await repository.list_rounds(session, table_id, limit, offset)
    total = await repository.count_rounds(session, table_id)
    return table, rounds, total


# --- 바꾸기. 모두 테이블을 잠그고 한다 ---


def record_check(session: AsyncSession, table: GameTable, declaration: Declaration, cause: TableEvent) -> None:
    """
    판정의 결과를 이벤트로 적는다. 그 판정을 부른 행동의 이벤트(cause)에 잇는다.
    판정으로 HP 가 바뀌었으면(앉은 사람이든 NPC 든) 바로 뒤에 그것도 적는다.

    행한 사람(actor_id)을 적지 않는다. 주사위를 굴린 것은 플레이어가 아니라 엔진이다.
    누구의 판정인지는 원인으로 이은 행동의 이벤트와 캐릭터 이름으로 안다.
    """
    outcome = declaration.outcome
    payload = {
        'round': cause.payload['round'],
        'character_name': declaration.character_name,
        'ability': declaration.action['ability'],
        'difficulty': declaration.action['difficulty'],
        'roll': outcome['roll'],
        'modifier': outcome['modifier'],
        'total': outcome['total'],
        'target': outcome['target'],
        'success': outcome['success'],
        'hindrance': outcome.get('hindrance'),
        'called_shot': outcome.get('called_shot'),
    }
    rolled = recorder.record(session, table, EventType.CHECK_ROLLED, payload=payload, cause=cause)
    effect = outcome.get('effect')
    if effect is not None:
        changed = record_hp_change(session, table, effect, cause=rolled)
        holder = {'user_id': effect['user_id'], 'character_name': effect['character_name']}
        record_injury(session, table, effect.get('injury_roll'), holder, cause=changed)
    npc_effect = outcome.get('npc_effect')
    if npc_effect is not None:
        changed = record_npc_change(session, table, npc_effect, cause=rolled)
        holder = {'entry_id': npc_effect['entry_id'], 'name': npc_effect['name']}
        record_injury(session, table, npc_effect.get('injury_roll'), holder, cause=changed)


def record_injury(
    session: AsyncSession, table: GameTable, injury_roll: dict | None, holder: dict, cause: TableEvent
) -> None:
    """
    새 부상이 생겼으면 이벤트로 적는다. 그 부상을 부른 HP 의 변화의 이벤트(cause)에 잇는다.

    부상 표로 생겼거나(큰 타격, 쓰러짐), 노려 쳐서 생겼다. 어느 쪽인지는 source 로 적는다.
    표를 굴리지 않았거나 부상이 없는 줄이 나왔으면 적지 않는다. 굴린 것은 HP 의 변화의 이벤트에 이미 있다.
    holder 는 누가 입었는지다. 캐릭터면 user_id 와 캐릭터 이름, NPC 면 항목의 id 와 장면의 호칭이다.
    """
    if injury_roll is None or injury_roll['injury'] is None:
        return
    payload = {
        'round': cause.payload['round'],
        **holder,
        'injury': injury_roll['injury'],
        'source': source_of(injury_roll),
        'ends_after_round': injury_roll['ends_after_round'],
    }
    recorder.record(session, table, EventType.INJURY_GAINED, payload=payload, cause=cause)


def source_of(injury_roll: dict) -> InjurySource:
    """부상이 생긴 일의 문서에서 그 부상이 어떻게 생겼는지."""
    if injury_roll['trigger'] == Trigger.CALLED_SHOT:
        return InjurySource.CALLED_SHOT
    return InjurySource.INJURY_TABLE


def record_npc_change(session: AsyncSession, table: GameTable, effect: dict, cause: TableEvent) -> TableEvent:
    """
    NPC 의 상태가 바뀐 것을 이벤트로 적는다. 그 변화를 부른 판정의 이벤트(cause)에 잇는다.

    HP 의 숫자까지 다 적는다. 앉은 사람에게 내보낼 칸은 이벤트 API 가 고른다(app/events/router.py 의 VISIBLE).
    행한 사람(actor_id)을 적지 않는다. 상태를 바꾼 것은 엔진이다.
    """
    payload = {'round': cause.payload['round'], **effect}
    return recorder.record(session, table, EventType.NPC_CHANGED, payload=payload, cause=cause)


def record_hp_change(session: AsyncSession, table: GameTable, effect: dict, cause: TableEvent) -> TableEvent:
    """
    HP 가 바뀐 것을 이벤트로 적는다. 그 변화를 부른 판정의 이벤트(cause)에 잇는다.

    행한 사람(actor_id)을 적지 않는다. HP 를 바꾼 것은 엔진이다. 누구의 HP 인지는 payload 의 user_id 다.
    """
    payload = {'round': cause.payload['round'], **effect}
    return recorder.record(session, table, EventType.HP_CHANGED, payload=payload, cause=cause)


def record_actions(session: AsyncSession, table: GameTable, round_: Round, group: uuid.UUID) -> None:
    """
    닫히는 라운드의 선언을 이벤트로 적는다. 지금 앉아 있는 사람이 낸 것만 적는다. 서술자가 받는 것과 같다.

    판정이 있었던 선언은 행동 바로 뒤에 그 결과를 적는다. 판정은 이미 끝나 있다(roll_checks). 여기서는 적기만 한다.
    선언을 내지 않은 사람은 적지 않는다. 누가 안 냈는지는 라운드가 닫힌 이벤트에 적힌다.
    """
    for member in table.members:
        declaration = find_declaration(round_, member.user_id)
        if declaration is None:
            continue
        payload = {
            'round': round_.number,
            'character_name': member.character_name,
            'content': declaration.content,
            'action': declaration.action,
        }
        acted = recorder.record(
            session, table, EventType.PLAYER_ACTION, actor_id=member.user_id, payload=payload, group=group
        )
        if has_outcome(declaration):
            record_check(session, table, declaration, cause=acted)


def record_death(
    session: AsyncSession,
    table: GameTable,
    save: dict,
    round_number: int,
    cause: TableEvent,
) -> None:
    """
    죽음의 굴림으로 캐릭터가 죽은 것을 이벤트로 적는다. 그 굴림의 이벤트(cause)에 잇는다.

    행한 사람(actor_id)을 적지 않는다. 규칙이 정한 죽음이다.
    """
    payload = {
        'round': round_number,
        'user_id': save['user_id'],
        'character_name': save['character_name'],
        'cause': DeathCause.DEATH_SAVE,
    }
    recorder.record(session, table, EventType.CHARACTER_DIED, payload=payload, cause=cause)


def record_death_saves(session: AsyncSession, table: GameTable, round_: Round, group: uuid.UUID) -> None:
    """
    닫히는 라운드에 굴린 죽음의 굴림을 이벤트로 적는다. 굴림은 이미 끝나 있다(roll_death_saves). 여기서는 적기만 한다.
    그 굴림으로 죽었으면 바로 뒤에 그것도 적는다.

    행한 사람(actor_id)을 적지 않는다. 주사위를 굴린 것은 엔진이다. 누구의 굴림인지는 payload 의 user_id 다.
    """
    for save in round_.death_saves:
        payload = {'round': round_.number, **save}
        rolled = recorder.record(session, table, EventType.DEATH_SAVE_ROLLED, payload=payload, group=group)
        if save['fate'] == death.Fate.DEAD:
            record_death(session, table, save, round_.number, cause=rolled)


def record_injury_endings(
    session: AsyncSession, table: GameTable, ended: list[round_injuries.Ended], round_number: int, group: uuid.UUID
) -> None:
    """
    이 라운드가 닫힐 때 풀린 짧은 부상들을 이벤트로 적는다. 푸는 일은 이미 끝나 있다(expire_all). 여기서는 적기만 한다.

    행한 사람(actor_id)을 적지 않는다. 정한 라운드가 지나 엔진이 푼 것이다.
    """
    for one in ended:
        payload = {'round': round_number, **one.holder, 'injury': one.injury.injury, 'reason': 'expired'}
        recorder.record(session, table, EventType.INJURY_ENDED, payload=payload, group=group)


def begin_closing(
    session: AsyncSession,
    table: GameTable,
    round_: Round,
    dice: Dice,
    scene: Scene,
    closer_id: uuid.UUID | None = None,
) -> None:
    """
    열려 있는 라운드를 닫기 시작한다. 선언을 마감하고 행동을 판정한다. 저장하지는 않는다.

    closer_id 는 라운드를 닫은 방장이다. 모두가 내서 저절로 닫혔으면 주지 않는다.
    scene 은 이번 장면의 NPC 들이다(load_scene). 행동이 겨눈 NPC 의 상태를 여기서 바꾼다.
    판정과 죽음의 굴림을 끝낸 뒤에 짧은 부상을 푼다. 이번 라운드의 판정에는 아직 효과가 있었다.
    이벤트는 행동(과 그 판정, 변화, 부상)들 → 죽음의 굴림들 → 풀린 부상들 → 닫힘 순서로 적는다. 한 묶음이다.
    나중에 적히는 서술과 열림도 이 묶음에 들어간다.

    주사위는 여기서만 굴린다. 열려 있는 라운드에 한 번만 부르므로 한 선언을 두 번 굴리지 않는다.
    죽음의 굴림은 행동의 판정을 끝낸 뒤에 굴린다. 이번 라운드에 회복을 받아 일어난 캐릭터는 굴리지 않는다.
    누가 굴릴지는 판정 전에 본다. 이번 라운드에 쓰러진 캐릭터는 다음 라운드부터 굴린다.
    서술자에게 줄 각자 한 일과 그때의 문체를 여기서 라운드에 굳힌다. 서술은 지금의 테이블이 아니라 이것을 읽는다.
    서술자를 부르지 않는다. 저장한 뒤에 따로 맡긴다(NarrationScheduler).
    """
    group = uuid.uuid4()
    dying = find_dying(table)
    roll_checks(table, round_, dice, scene.cast)
    round_.death_saves = roll_death_saves(table, dying, dice)
    ended = round_injuries.expire_all(table.members, scene, round_.number)
    round_.moves = narration_request.dump_moves(build_moves(table, round_))
    round_.narration_style = table.narration_style
    record_actions(session, table, round_, group)
    record_death_saves(session, table, round_, group)
    record_injury_endings(session, table, ended, round_.number, group)
    payload = {'number': round_.number, 'idle': [str(user_id) for user_id in waiting_for(table, round_)]}
    recorder.record(session, table, EventType.ROUND_CLOSED, actor_id=closer_id, payload=payload, group=group)
    round_.closing_at = datetime.now(UTC)


async def lock_current_round(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[GameTable, TableMember, Round]:
    """
    자기가 앉아 있는 테이블을 잠그고, 가장 최근 라운드를 찾는다. 테이블, 자기 자리, 라운드를 돌려준다.

    앉지 않았으면 TableNotFoundError, 진행 중이 아니면 RoundConflictError.
    진행 중인 테이블의 가장 최근 라운드는 선언을 받는 중이거나 닫는 중이다.
    """
    table, member = await tables.lock_seated(session, user_id, table_id)
    require_playing(table)
    round_ = require_started(await repository.find_latest_round(session, table_id))
    return table, member, round_


async def load_scene(session: AsyncSession, table: GameTable, round_: Round) -> Scene:
    """
    이번 장면의 NPC 들을 읽는다. 테이블의 NPC 상태 전부와, 그중 라운드의 장면에 나온 인물들이다.

    테이블을 잠근 요청 안에서 부르면 돌려준 인물의 상태를 그대로 고칠 수 있다.
    """
    states = await table_repository.list_npcs(session, table.id)
    return Scene(npcs=states, cast=cast_of(read_snapshot(table.content), round_.scene, states))


def hand_over(scheduler: NarrationScheduler, saved: tuple[GameTable, Round]) -> None:
    """
    방금 저장한 닫는 중인 라운드의 서술을 맡긴다. 저장한 닫기 시작한 시각을 함께 넘긴다.

    저장한 뒤에 다시 읽은 라운드(save 가 돌려준 것)를 받는다. 작업이 견주는 값이 DB 에 적힌 값과 같아야 한다.
    """
    table, round_ = saved
    scheduler.schedule(table.id, round_.number, round_.closing_at)


async def save(session: AsyncSession, table: GameTable) -> tuple[GameTable, Round]:
    """저장하고, 테이블과 가장 최근 라운드를 다시 읽어 돌려준다."""
    await tables.commit(session, table)
    return table, await repository.find_latest_round(session, table.id)


async def declare(
    session: AsyncSession,
    user_id: uuid.UUID,
    table_id: uuid.UUID,
    data: DeclarationUpdate,
    scheduler: NarrationScheduler,
    dice: Dice,
) -> tuple[GameTable, Round]:
    """
    열려 있는 라운드에 선언을 낸다. 이미 냈으면 바꾼다. 앉은 사람이 모두 냈으면 라운드를 닫기 시작한다.

    돌려주는 것은 테이블과 그 라운드다. 이 선언으로 닫기 시작했으면 "닫는 중"인 채로 돌아온다.
    서술이 끝나 다음 라운드가 열린 것은 스트림으로 알게 된다.

    닫는 중인 라운드에는 낼 수 없다(RoundConflictError). 쓰러진 사람은 행동을 붙일 수 없다(RoundConflictError).
    캐릭터가 죽은 사람은 글도 낼 수 없다(RoundConflictError).
    이 라운드에 새 캐릭터를 들인 사람도 낼 수 없다(RoundConflictError). 다음 라운드부터 낸다.
    행동이 이 테이블의 규칙에 없는 것을 가리키면 ActionNotInRulesError.
    행동의 대상이 이 테이블에 앉은 사람이나 이번 장면의 인물이 아니면 ActionTargetError.
    겨눈 NPC 가 이미 죽었으면 RoundConflictError.
    테이블을 잠그고 한다. 마지막 두 사람이 동시에 내도 라운드는 한 번만 닫힌다.
    """
    table, member, round_ = await lock_current_round(session, user_id, table_id)
    require_open(round_)
    if sheets.is_dead(member):
        raise RoundConflictError(Conflict.CHARACTER_DEAD)
    if find_arrival(round_, user_id) is not None:
        raise RoundConflictError(Conflict.CHARACTER_ARRIVING)
    scene = await load_scene(session, table, round_)
    put_declaration(round_, member, data.content, accept_action(table, member, data.action, scene.cast))

    everyone_declared = not waiting_for(table, round_)
    if everyone_declared:
        begin_closing(session, table, round_, dice, scene)
    saved = await save(session, table)
    # 저장한 뒤에 맡긴다. 먼저 맡기면 서술을 맡은 작업이 아직 저장되지 않은 것을 읽는다
    if everyone_declared:
        hand_over(scheduler, saved)
    return saved


async def force_close(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, scheduler: NarrationScheduler, dice: Dice
) -> tuple[GameTable, Round]:
    """
    방장이 라운드를 닫는다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 넘어간다.

    방장이 아니면 NotHostError. 자리를 비운 사람 때문에 테이블이 멈추지 않게 한다.

    이미 닫는 중이면 두 가지다.
      - 맡긴 지 얼마 안 됐으면 RoundConflictError. 서술이 돌고 있다. 또 맡기면 같은 서술을 두 번 시킨다.
      - 서술이 끝내 실패했거나 한참 지났으면(is_stalled) 서술을 다시 맡긴다. 이벤트를 다시 적지는 않는다.
        주사위도 다시 굴리지 않는다. 처음 닫을 때 선언에 적어 둔 결과를 그대로 쓴다.
        닫기 시작한 시각을 지금으로 고치고 실패의 표시를 지운다. 다시 맡긴 것 위에 또 맡기지 않게 한다.
        시각이 바뀌므로 앞서 맡은 작업이 아직 살아 있어도 이 라운드를 더는 바꾸지 못한다(is_run).
    """
    table, _, round_ = await lock_current_round(session, host_id, table_id)
    tables.require_host(table, host_id)

    if round_.status == RoundStatus.OPEN:
        begin_closing(session, table, round_, dice, await load_scene(session, table, round_), closer_id=host_id)
    elif is_stalled(round_, datetime.now(UTC)):
        round_.closing_at = datetime.now(UTC)
        round_.narration_failed_at = None
    else:
        raise RoundConflictError(Conflict.ROUND_CLOSING)

    saved = await save(session, table)
    hand_over(scheduler, saved)
    return saved


# --- 서술을 맡은 작업이 부르는 것. 요청 밖에서 돈다(app/rounds/closing.py) ---


async def load_closing_request(
    session: AsyncSession, table_id: uuid.UUID, number: int, started: datetime
) -> NarrationRequest | None:
    """
    닫는 중인 라운드를 서술자에게 줄 모양으로 읽는다. started 에 맡긴 서술을 기다리는 라운드가 아니면 None.

    None 이면 할 일이 없다. 다른 작업이 이미 마무리했거나, 그 뒤에 다시 맡겼거나, 테이블이 지워졌다.
    잠그지 않는다. 읽는 것은 모두 더 바뀌지 않는다.
      - 각자 한 일과 문체는 닫기 시작할 때 굳혀 둔 것이다. 그 뒤에 누가 나가도, 방장이 문체를 바꿔도 그대로다.
      - 이야기의 바탕은 판의 복사본에서 꺼낸다. 판은 고치지 않는다.
      - 지난 라운드는 닫혀서 바뀌지 않는다.
      - NPC 의 상태는 닫기 시작할 때 바뀐 뒤로 다음 라운드가 열릴 때까지 바뀌지 않는다.
    그래서 서술을 몇 번 다시 맡겨도 서술자는 같은 것을 받는다.
    이야기의 바탕과 지난 라운드 몇 개는 가짜 서술자는 읽지 않고, 언어 모델의 서술자가 읽는다.
    """
    table = await table_repository.find_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or not is_run(round_, started):
        return None
    history = await repository.list_rounds_before(session, table_id, number, HISTORY_ROUNDS)
    snapshot = read_snapshot(table.content)
    scene = await load_scene(session, table, round_)
    return NarrationRequest(
        round_number=round_.number,
        scene=round_.scene,
        moves=frozen_moves(table, round_),
        story=narration_request.to_story(snapshot),
        history=[narration_request.to_past(past) for past in history],
        style=frozen_style(table, round_),
        table_id=table.id,
        host_id=table.host_id,
        people=to_people(scene.cast, snapshot.rulebook.rules),
    )


async def fail_closing(session: AsyncSession, table_id: uuid.UUID, number: int, started: datetime, reason: str) -> None:
    """
    닫는 중인 라운드의 서술이 끝내 실패한 것을 적는다. 저장한다.

    라운드는 닫는 중에 머문다. 실패한 시각을 적어 방장이 기다리지 않고 다시 맡길 수 있게 하고,
    앉은 사람 모두에게 이벤트로 알린다. reason 은 마지막 실패의 이유다(timeout, cut_off …).

    테이블을 잠그고, 잠근 뒤에 이 라운드가 started 에 맡긴 서술을 아직 기다리는지, 실패가 적히지 않았는지 본다.
    아니면 아무것도 하지 않는다.
      - 이미 닫혔다. 마무리의 저장이 끝난 뒤에 예외가 났거나(저장 도중에 끊긴 경우를 포함한다) 다른 작업이 닫았다.
        잠금을 기다리는 동안 그 저장이 끝나므로, 잠근 뒤에 읽은 것이 실제의 상태다.
      - 그 뒤에 다시 맡겼다(닫기 시작한 시각이 다르다). 옛 작업의 실패가 지금 도는 서술에 실패를 적지 못한다.
      - 이미 실패를 적었다.

    서술이 실패로 끝나는 곳은 여기 하나다. 포인트를 붙이면 맡을 때 잡아 둔 것을 여기서 돌려준다.
    """
    table = await table_repository.lock_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or not is_run(round_, started):
        return
    if round_.narration_failed_at is not None:
        return

    round_.narration_failed_at = datetime.now(UTC)
    closed = await event_repository.find_latest(session, table_id, EventType.ROUND_CLOSED)
    payload = {'round': number, 'reason': reason}
    recorder.record(session, table, EventType.NARRATION_FAILED, payload=payload, cause=closed)
    await tables.commit(session, table)


async def finish_closing(
    session: AsyncSession, table_id: uuid.UUID, number: int, started: datetime, scene: str
) -> None:
    """
    닫는 중인 라운드를 닫고, 서술(scene)을 장면으로 하는 다음 라운드를 연다. 저장한다.

    테이블을 잠그고, 잠근 뒤에 이 라운드가 started 에 맡긴 서술을 아직 기다리는지 본다. 아니면 아무것도 하지 않는다.
    같은 라운드의 서술이 둘 돌았어도(다시 맡긴 경우) 지금 맡긴 것만 받아들여진다. 다음 라운드가 둘 열리지 않는다.
    다시 맡긴 뒤에 늦게 온 옛 서술은 버린다. 라운드를 바꾸는 것은 지금 맡긴 작업 하나뿐이다.

    서술하는 사이에 테이블이 끝났으면 라운드만 닫고 다음 라운드를 열지 않는다.

    닫은 것을 먼저 DB 에 보낸다(flush). 한 테이블에 닫히지 않은 라운드는 하나뿐이라는 유일 색인이 있어서,
    앞의 것을 닫기 전에 새 것을 넣으면 DB 가 거부한다.
    """
    table = await table_repository.lock_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or not is_run(round_, started):
        return

    round_.closed_at = datetime.now(UTC)
    if table.status == TableStatus.PLAYING:
        await session.flush()
        closed = await event_repository.find_latest(session, table_id, EventType.ROUND_CLOSED)
        opener.open_round(session, table, number=number + 1, scene=scene, cause=closed)
    await tables.commit(session, table)
