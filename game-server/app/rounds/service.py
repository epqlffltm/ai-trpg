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

선언은 낼 때가 아니라 라운드가 닫힐 때 이벤트로 적는다. 마지막 글만 적는다.
열려 있는 동안에는 남의 선언이 보이지 않아야 하는데, 이벤트는 앉은 사람 모두가 읽기 때문이다.

판정은 닫기 시작할 때 한 번만 한다. 결과를 선언에 적어 두고, 그 뒤로는 읽기만 한다.
서술이 실패해 다시 맡겨도 주사위를 다시 굴리지 않는다. 다시 굴리면 서술을 실패시켜 결과를 바꿀 수 있다.

HP 도 그때 한 번만 바뀐다. 판정의 결과에 따라 피해를 입거나 회복한다(app/engine/health.py).
HP 가 0 이면 쓰러진 것이다. 쓰러진 사람은 글만 낼 수 있고, 라운드는 그 사람의 선언을 기다리지 않는다.

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
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.engine import action as actions
from app.engine import death, health
from app.engine.action import CheckAction
from app.engine.check import Check, find_ability, find_difficulty
from app.engine.dice import Dice
from app.engine.health import ChangeKind
from app.engine.ruleset import Ruleset
from app.events import recorder
from app.events import repository as event_repository
from app.events.models import EventType, TableEvent
from app.rounds import opener, repository
from app.rounds.models import Declaration, Round, RoundStatus
from app.rounds.narrator import DeathSaveNote, Impact, Move, NarrationRequest, PastRound, StoryContext, Verdict
from app.rounds.prompt import HISTORY_ROUNDS
from app.rounds.schemas import DeclarationUpdate
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables import sheets
from app.tables.models import DeathCause, GameTable, TableMember, TableStatus


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
    """선언에 붙은 행동의 대상이 이 테이블에 앉은 사람이 아니다."""


# 닫는 중인 채로 이 시간(초)이 지나면 서술을 맡은 작업이 사라진 것으로 본다. 그때부터 다시 맡길 수 있다.
# 서술자가 답하는 데 걸릴 수 있는 가장 긴 시간보다 길어야 한다. 짧으면 아직 도는 서술 위에 또 서술을 맡긴다
CLOSING_RETRY_SECONDS = 60.0


class NarrationScheduler(Protocol):
    """
    서술을 뒤에서 돌게 맡기는 것의 모양. 구현은 app/rounds/closing.py 에 있다.

    이 파일이 그 파일을 불러오지 않으려고 모양만 여기 둔다. 그 파일이 이 파일을 불러온다.
    """

    def schedule(self, table_id: uuid.UUID, number: int) -> None:
        """이 테이블의 이 라운드의 서술을 맡긴다. 기다리지 않고 바로 돌아온다."""
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


def is_stalled(round_: Round, now: datetime) -> bool:
    """
    닫는 중인 채로 너무 오래 머물렀는가. 서술을 맡은 작업이 사라졌다고 볼 만큼 지났는가.

    now 는 지금 시각이다. 테스트가 시간을 마음대로 흘리려고 받는다.
    """
    if round_.status != RoundStatus.CLOSING:
        return False
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
    """
    if action.recover is None or action.target is not None:
        return action
    return action.model_copy(update={'target': actor_id})


def accept_action(table: GameTable, member: TableMember, action: CheckAction | None) -> dict | None:
    """
    선언에 붙은 행동을 이 테이블과 견주어 보고, 저장할 모양으로 바꾼다. 행동이 없으면 None.

    member 는 선언하는 사람이다.
      - 쓰러져 있으면 RoundConflictError. 쓰러진 사람은 글만 낼 수 있다.
      - 규칙에 없는 능력, 난이도, 양의 등급이면 ActionNotInRulesError.
      - 대상이 이 테이블에 앉은 사람이 아니면 ActionTargetError.
    비워 둔 난이도는 규칙의 기본 난이도로, 비워 둔 회복의 대상은 자기 자신으로 채운다.
    """
    if action is None:
        return None
    if is_down(member):
        raise RoundConflictError(Conflict.CHARACTER_DOWNED)
    ruleset = rules_of(table)
    fault = actions.find_fault(ruleset, action)
    if fault is not None:
        raise ActionNotInRulesError(fault)
    if action.target is not None and tables.find_member(table, action.target) is None:
        raise ActionTargetError
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


def find_affected(table: GameTable, actor: TableMember, action: CheckAction, kind: ChangeKind) -> TableMember | None:
    """
    HP 가 바뀔 사람을 찾는다. 피해는 행동한 사람이 입고, 회복은 행동의 대상이 받는다.

    대상이 그사이에 테이블을 떠났으면 None.
    """
    return actor if kind == ChangeKind.DAMAGE else tables.find_member(table, action.target)


def apply_consequence(
    table: GameTable, actor: TableMember, action: CheckAction, check: Check, ruleset: Ruleset, dice: Dice
) -> dict | None:
    """
    판정의 결과에 따라 HP 를 바꾸고, 바뀐 내용을 문서로 돌려준다. 아무 일도 없으면 None.

    시트의 hp 를 고친다. 저장하지는 않는다. 양을 정하는 주사위를 여기서 굴린다.
    돌려준 문서는 선언의 outcome 안에 적힌다. 누구의 HP 가 얼마에서 얼마로 바뀌었는지가 다 담긴다.
    """
    found = actions.consequence(action, check)
    if found is None:
        return None
    kind, magnitude_key = found
    affected = find_affected(table, actor, action, kind)
    # 대상이 떠났거나 시트가 없으면 바뀔 HP 가 없다. 양을 정하는 주사위도 굴리지 않는다.
    # 죽은 캐릭터도 그렇다. 회복으로 되살리지 못한다
    if affected is None or affected.sheet is None or sheets.is_dead(affected):
        return None

    sheet = affected.sheet
    magnitude = health.find_magnitude(ruleset, magnitude_key)
    change = health.change_hp(kind, magnitude, sheet.hp, sheet.max_hp, dice)
    sheet.hp = change.after
    # 일어났으면 죽음의 굴림에서 센 것은 처음으로 돌아간다. 다시 쓰러지면 처음부터 센다
    if not change.downed:
        sheets.clear_death_saves(sheet)
    return {
        'kind': change.kind.value,
        'magnitude': magnitude_key,
        'user_id': str(affected.user_id),
        'character_name': affected.character_name,
        'rolls': list(change.rolls),
        'amount': change.amount,
        'before': change.before,
        'after': change.after,
        'max_hp': sheet.max_hp,
        'downed': change.downed,
    }


def roll_checks(table: GameTable, round_: Round, dice: Dice) -> None:
    """
    닫히는 라운드의 행동을 판정하고, 결과에 따라 HP 를 바꾸고, 결과를 선언에 적는다. 들어온 순서로 굴린다.

    한 사람의 판정과 그 결과(피해, 회복)를 끝낸 뒤에 다음 사람으로 넘어간다.
    앞사람이 쓰러뜨린 것을 뒷사람이 일으킬 수 있다.

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

    ruleset = rules_of(table)
    for member, declaration in rolling:
        action = CheckAction.model_validate(declaration.action)
        check = actions.attempt(ruleset, action, member.sheet.abilities, dice)
        effect = apply_consequence(table, member, action, check, ruleset, dice)
        declaration.outcome = {**asdict(check), 'effect': effect}


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


def find_death_save(round_: Round, user_id: uuid.UUID) -> DeathSaveNote | None:
    """라운드에 적힌 죽음의 굴림 중에서 이 사람의 것을 서술자에게 줄 모양으로 찾는다. 없으면 None."""
    found = next((save for save in round_.death_saves if save['user_id'] == str(user_id)), None)
    if found is None:
        return None
    return DeathSaveNote(
        roll=found['roll'],
        target=found['target'],
        success=found['success'],
        successes=found['successes'],
        failures=found['failures'],
        fate=found['fate'],
    )


def to_impact(effect: dict | None) -> Impact | None:
    """선언에 적힌 HP 의 변화를 서술자에게 줄 모양으로 바꾼다. 변화가 없었으면 None."""
    if effect is None:
        return None
    return Impact(
        kind=effect['kind'],
        character_name=effect['character_name'],
        amount=effect['amount'],
        hp=effect['after'],
        max_hp=effect['max_hp'],
        downed=effect['downed'],
    )


def to_verdict(ruleset: Ruleset, declaration: Declaration) -> Verdict:
    """
    선언에 적힌 행동과 결과를 서술자에게 줄 모양으로 바꾼다. key 를 규칙에 적힌 이름으로 바꾼다.

    결과가 적힌 선언에만 쓴다(has_outcome).
    """
    ability = find_ability(ruleset, declaration.action['ability'])
    difficulty = find_difficulty(ruleset, declaration.action['difficulty'])
    outcome = declaration.outcome
    return Verdict(
        ability=ability.name,
        difficulty=difficulty.name,
        roll=outcome['roll'],
        modifier=outcome['modifier'],
        total=outcome['total'],
        target=outcome['target'],
        success=outcome['success'],
        impact=to_impact(outcome.get('effect')),
    )


def build_request(table: GameTable, round_: Round) -> NarrationRequest:
    """
    닫히는 라운드를 서술자에게 줄 모양으로 바꾼다.

    지금 앉아 있는 사람 모두가 들어간다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 들어간다.
    판정의 결과와 HP 의 변화는 선언에 적힌 것을, 죽음의 굴림은 라운드에 적힌 것을 읽는다. 여기서 굴리지 않는다.
    쓰러져 있는지, 죽었는지는 이번 라운드의 결과를 반영한 뒤의 것이다.
    이 라운드에 새로 들어온 캐릭터는 라운드에 적힌 것(arrivals)으로 안다. 누구의 뒤를 잇는지를 함께 준다.
    """
    declarations = [find_declaration(round_, member.user_id) for member in table.members]
    ruleset = rules_of(table) if any(has_outcome(declaration) for declaration in declarations) else None

    moves = []
    for member, declaration in zip(table.members, declarations, strict=True):
        content = declaration.content if declaration else None
        verdict = to_verdict(ruleset, declaration) if has_outcome(declaration) else None
        arrival = find_arrival(round_, member.user_id)
        moves.append(
            Move(
                character_name=member.character_name,
                content=content,
                verdict=verdict,
                downed=is_down(member),
                death_save=find_death_save(round_, member.user_id),
                dead=sheets.is_dead(member),
                replaces=arrival['replaces'] if arrival else None,
            )
        )
    return NarrationRequest(round_number=round_.number, scene=round_.scene, moves=moves)


def to_story(snapshot: Snapshot) -> StoryContext:
    """
    판의 복사본에서 이야기의 바탕을 꺼낸다. 서술자에게만 준다.

    룰북의 진행 지침과 세계관의 GM 메모가 들어간다. 이것들은 AI 가 읽으라고 쓴 글이다. 플레이어에게 내보내지 않는다.
    세계관이 없는 시나리오면 설정과 GM 메모는 빈 글이다. 로어북은 넣지 않는다(검색 단계의 일).
    """
    world = snapshot.world
    return StoryContext(
        title=snapshot.title,
        rating=snapshot.rating,
        guide=snapshot.rulebook.gm_guide,
        setting=world.setting if world else '',
        gm_notes=world.gm_notes if world else '',
    )


def to_past(round_: Round) -> PastRound:
    """
    지난 라운드를 서술자에게 줄 모양으로 바꾼다. 그때의 장면과, 선언마다 "캐릭터 이름: 글" 한 줄.

    선언에 적어 둔 캐릭터 이름을 쓴다. 그 사람이 떠났거나 새 캐릭터로 바뀌었어도 그때의 이름이 남는다.
    """
    lines = [f'{declaration.character_name}: {declaration.content}' for declaration in round_.declarations]
    return PastRound(number=round_.number, scene=round_.scene, lines=lines)


# --- 읽기 ---


async def get_current_round(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> tuple[GameTable, Round]:
    """
    자기가 앉아 있는 테이블의 가장 최근 라운드를 돌려준다. 테이블도 함께 돌려준다.

    앉지 않았으면 TableNotFoundError, 아직 시작하지 않았으면 RoundConflictError.
    """
    table = await tables.get_table(session, user_id, table_id)
    round_ = require_started(await repository.find_latest_round(session, table_id))
    return table, round_


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
    판정으로 HP 가 바뀌었으면 바로 뒤에 그것도 적는다.

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
    }
    rolled = recorder.record(session, table, EventType.CHECK_ROLLED, payload=payload, cause=cause)
    effect = outcome.get('effect')
    if effect is not None:
        record_hp_change(session, table, effect, cause=rolled)


def record_hp_change(session: AsyncSession, table: GameTable, effect: dict, cause: TableEvent) -> None:
    """
    HP 가 바뀐 것을 이벤트로 적는다. 그 변화를 부른 판정의 이벤트(cause)에 잇는다.

    행한 사람(actor_id)을 적지 않는다. HP 를 바꾼 것은 엔진이다. 누구의 HP 인지는 payload 의 user_id 다.
    """
    payload = {'round': cause.payload['round'], **effect}
    recorder.record(session, table, EventType.HP_CHANGED, payload=payload, cause=cause)


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


def begin_closing(
    session: AsyncSession, table: GameTable, round_: Round, dice: Dice, closer_id: uuid.UUID | None = None
) -> None:
    """
    열려 있는 라운드를 닫기 시작한다. 선언을 마감하고 행동을 판정한다. 저장하지는 않는다.

    closer_id 는 라운드를 닫은 방장이다. 모두가 내서 저절로 닫혔으면 주지 않는다.
    이벤트는 행동(과 그 판정)들 → 죽음의 굴림들 → 닫힘 순서로 적는다. 한 묶음이다.
    나중에 적히는 서술과 열림도 이 묶음에 들어간다.

    주사위는 여기서만 굴린다. 열려 있는 라운드에 한 번만 부르므로 한 선언을 두 번 굴리지 않는다.
    죽음의 굴림은 행동의 판정을 끝낸 뒤에 굴린다. 이번 라운드에 회복을 받아 일어난 캐릭터는 굴리지 않는다.
    누가 굴릴지는 판정 전에 본다. 이번 라운드에 쓰러진 캐릭터는 다음 라운드부터 굴린다.
    서술자를 부르지 않는다. 저장한 뒤에 따로 맡긴다(NarrationScheduler).
    """
    group = uuid.uuid4()
    dying = find_dying(table)
    roll_checks(table, round_, dice)
    round_.death_saves = roll_death_saves(table, dying, dice)
    record_actions(session, table, round_, group)
    record_death_saves(session, table, round_, group)
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
    행동의 대상이 이 테이블에 앉은 사람이 아니면 ActionTargetError.
    테이블을 잠그고 한다. 마지막 두 사람이 동시에 내도 라운드는 한 번만 닫힌다.
    """
    table, member, round_ = await lock_current_round(session, user_id, table_id)
    require_open(round_)
    if sheets.is_dead(member):
        raise RoundConflictError(Conflict.CHARACTER_DEAD)
    if find_arrival(round_, user_id) is not None:
        raise RoundConflictError(Conflict.CHARACTER_ARRIVING)
    put_declaration(round_, member, data.content, accept_action(table, member, data.action))

    everyone_declared = not waiting_for(table, round_)
    if everyone_declared:
        begin_closing(session, table, round_, dice)
    saved = await save(session, table)
    # 저장한 뒤에 맡긴다. 먼저 맡기면 서술을 맡은 작업이 아직 저장되지 않은 것을 읽는다
    if everyone_declared:
        scheduler.schedule(table.id, round_.number)
    return saved


async def force_close(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, scheduler: NarrationScheduler, dice: Dice
) -> tuple[GameTable, Round]:
    """
    방장이 라운드를 닫는다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 넘어간다.

    방장이 아니면 NotHostError. 자리를 비운 사람 때문에 테이블이 멈추지 않게 한다.

    이미 닫는 중이면 두 가지다.
      - 맡긴 지 얼마 안 됐으면 RoundConflictError. 서술이 돌고 있다. 또 맡기면 같은 서술을 두 번 시킨다.
      - 한참 지났으면(is_stalled) 서술을 다시 맡긴다. 맡았던 작업이 사라진 것이다. 이벤트를 다시 적지는 않는다.
        주사위도 다시 굴리지 않는다. 처음 닫을 때 선언에 적어 둔 결과를 그대로 쓴다.
        닫기 시작한 시각을 지금으로 고친다. 다시 맡긴 것 위에 또 맡기지 않게 한다.
    """
    table, _, round_ = await lock_current_round(session, host_id, table_id)
    tables.require_host(table, host_id)

    if round_.status == RoundStatus.OPEN:
        begin_closing(session, table, round_, dice, closer_id=host_id)
    elif is_stalled(round_, datetime.now(UTC)):
        round_.closing_at = datetime.now(UTC)
    else:
        raise RoundConflictError(Conflict.ROUND_CLOSING)

    saved = await save(session, table)
    scheduler.schedule(table.id, round_.number)
    return saved


# --- 서술을 맡은 작업이 부르는 것. 요청 밖에서 돈다(app/rounds/closing.py) ---


async def load_closing_request(session: AsyncSession, table_id: uuid.UUID, number: int) -> NarrationRequest | None:
    """
    닫는 중인 라운드를 서술자에게 줄 모양으로 읽는다. 닫는 중이 아니면 None.

    None 이면 할 일이 없다. 다른 작업이 이미 마무리했거나 테이블이 지워졌다.
    잠그지 않는다. 닫는 중인 라운드의 선언은 더 바뀌지 않는다. 지난 라운드는 닫혀서 바뀌지 않는다.
    이야기의 바탕과 지난 라운드 몇 개를 함께 싣는다. 가짜 서술자는 읽지 않고, 언어 모델의 서술자가 읽는다.
    """
    table = await table_repository.find_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or round_ is None or round_.status != RoundStatus.CLOSING:
        return None
    history = await repository.list_rounds_before(session, table_id, number, HISTORY_ROUNDS)
    story = to_story(read_snapshot(table.content))
    return replace(build_request(table, round_), story=story, history=[to_past(past) for past in history])


async def finish_closing(session: AsyncSession, table_id: uuid.UUID, number: int, scene: str) -> None:
    """
    닫는 중인 라운드를 닫고, 서술(scene)을 장면으로 하는 다음 라운드를 연다. 저장한다.

    테이블을 잠그고, 잠근 뒤에 라운드가 아직 닫는 중인지 본다. 아니면 아무것도 하지 않는다.
    같은 라운드의 서술이 둘 돌았어도(다시 맡긴 경우) 먼저 온 것만 받아들여진다. 다음 라운드가 둘 열리지 않는다.

    서술하는 사이에 테이블이 끝났으면 라운드만 닫고 다음 라운드를 열지 않는다.

    닫은 것을 먼저 DB 에 보낸다(flush). 한 테이블에 닫히지 않은 라운드는 하나뿐이라는 유일 색인이 있어서,
    앞의 것을 닫기 전에 새 것을 넣으면 DB 가 거부한다.
    """
    table = await table_repository.lock_table(session, table_id)
    round_ = await repository.find_round(session, table_id, number)
    if table is None or round_ is None or round_.status != RoundStatus.CLOSING:
        return

    round_.closed_at = datetime.now(UTC)
    if table.status == TableStatus.PLAYING:
        await session.flush()
        closed = await event_repository.find_latest(session, table_id, EventType.ROUND_CLOSED)
        opener.open_round(session, table, number=number + 1, scene=scene, cause=closed)
    await tables.commit(session, table)
