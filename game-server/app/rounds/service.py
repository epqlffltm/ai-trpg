# game-server/app/rounds/service.py

"""
라운드를 읽고, 선언을 받고, 라운드를 닫는다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

테이블의 규칙을 그대로 따른다(app/tables/service.py).
  - 라운드는 테이블에 앉은 사람만 본다.
  - 바꾸는 일(선언, 닫기)은 테이블의 행을 잠그고 한다. 라운드를 따로 잠그지 않는다.
    한 테이블의 일은 테이블 하나의 잠금으로 줄을 세운다. 잠금이 둘이면 서로를 기다리며 멈출 수 있다.

라운드가 닫히는 길은 둘이다. 앉은 사람이 모두 선언을 냈을 때 저절로, 또는 방장이 닫을 때.
닫히면 서술자가 결과를 쓰고, 그 글을 장면으로 하는 다음 라운드가 열린다. 이 셋은 한 묶음으로 저장된다.

선언은 낼 때가 아니라 라운드가 닫힐 때 이벤트로 적는다. 마지막 글만 적는다.
열려 있는 동안에는 남의 선언이 보이지 않아야 하는데, 이벤트는 앉은 사람 모두가 읽기 때문이다.
"""

import enum
import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import recorder
from app.events.models import EventType
from app.rounds import opener, repository
from app.rounds.models import Declaration, Round
from app.rounds.narrator import Action, NarrationRequest, Narrator
from app.rounds.schemas import DeclarationUpdate
from app.tables import service as tables
from app.tables.models import GameTable, TableMember, TableStatus


class RoundNotFoundError(Exception):
    """그런 번호의 라운드가 없다."""


class Conflict(enum.StrEnum):
    """요청은 맞지만 테이블의 지금 상태와 부딪히는 이유."""

    # 테이블이 아직 시작하지 않았다. 라운드가 하나도 없다
    NOT_STARTED = 'not_started'
    # 테이블이 진행 중이 아니다. 선언과 닫기는 진행 중에만 된다
    NOT_PLAYING = 'not_playing'


class RoundConflictError(Exception):
    """테이블의 지금 상태와 부딪힌다. reason 이 이유다."""

    def __init__(self, reason: Conflict) -> None:
        super().__init__(reason)
        self.reason = reason


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


def find_declaration(round_: Round, user_id: uuid.UUID) -> Declaration | None:
    """라운드의 선언 중에서 이 사람의 것을 찾는다."""
    return next((declaration for declaration in round_.declarations if declaration.user_id == user_id), None)


def waiting_for(table: GameTable, round_: Round) -> list[uuid.UUID]:
    """앉은 사람 중에서 이 라운드에 아직 선언을 내지 않은 사람들. 들어온 순서다."""
    return [member.user_id for member in table.members if find_declaration(round_, member.user_id) is None]


def put_declaration(round_: Round, member: TableMember, content: str) -> None:
    """
    이 사람의 선언을 적는다. 이미 냈으면 글을 바꾼다.

    캐릭터 이름을 함께 적어 둔다. 이 사람이 나중에 떠나도 누구의 선언이었는지 남는다.
    """
    declaration = find_declaration(round_, member.user_id)
    if declaration is None:
        round_.declarations.append(
            Declaration(user_id=member.user_id, character_name=member.character_name, content=content)
        )
    else:
        declaration.content = content


def build_request(table: GameTable, round_: Round) -> NarrationRequest:
    """
    닫히는 라운드를 서술자에게 줄 모양으로 바꾼다.

    지금 앉아 있는 사람 모두가 들어간다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 들어간다.
    """
    actions = []
    for member in table.members:
        declaration = find_declaration(round_, member.user_id)
        content = declaration.content if declaration else None
        actions.append(Action(character_name=member.character_name, content=content))
    return NarrationRequest(round_number=round_.number, scene=round_.scene, actions=actions)


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


def record_actions(session: AsyncSession, table: GameTable, round_: Round, group: uuid.UUID) -> None:
    """
    닫히는 라운드의 선언을 이벤트로 적는다. 지금 앉아 있는 사람이 낸 것만 적는다. 서술자가 받는 것과 같다.

    선언을 내지 않은 사람은 적지 않는다. 누가 안 냈는지는 라운드가 닫힌 이벤트에 적힌다.
    """
    for member in table.members:
        declaration = find_declaration(round_, member.user_id)
        if declaration is None:
            continue
        payload = {'round': round_.number, 'character_name': member.character_name, 'content': declaration.content}
        recorder.record(session, table, EventType.PLAYER_ACTION, actor_id=member.user_id, payload=payload, group=group)


async def close_round(
    session: AsyncSession, table: GameTable, round_: Round, narrator: Narrator, closer_id: uuid.UUID | None = None
) -> None:
    """
    열려 있는 라운드를 닫고 다음 라운드를 연다. 저장하지는 않는다.

    서술자가 닫힌 라운드의 결과를 쓰고, 그 글이 다음 라운드의 장면이 된다.
    closer_id 는 라운드를 닫은 방장이다. 모두가 내서 저절로 닫혔으면 주지 않는다.

    이벤트는 행동들 → 닫힘 → 서술 → 열림 순서로 적는다. 모두 한 묶음이다.

    닫은 것을 먼저 DB 에 보낸다(flush). 한 테이블에 열린 라운드는 하나뿐이라는 유일 색인이 있어서,
    앞의 것을 닫기 전에 새 것을 넣으면 DB 가 거부한다.
    """
    group = uuid.uuid4()
    record_actions(session, table, round_, group)
    payload = {'number': round_.number, 'idle': [str(user_id) for user_id in waiting_for(table, round_)]}
    closed = recorder.record(session, table, EventType.ROUND_CLOSED, actor_id=closer_id, payload=payload, group=group)

    scene = await narrator.narrate(build_request(table, round_))
    round_.closed_at = func.now()
    await session.flush()
    opener.open_round(session, table, number=round_.number + 1, scene=scene, cause=closed)


async def lock_open_round(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID
) -> tuple[GameTable, TableMember, Round]:
    """
    자기가 앉아 있는 테이블을 잠그고, 열려 있는 라운드를 찾는다. 테이블, 자기 자리, 라운드를 돌려준다.

    앉지 않았으면 TableNotFoundError, 진행 중이 아니면 RoundConflictError.
    """
    table, member = await tables.lock_seated(session, user_id, table_id)
    require_playing(table)
    round_ = require_started(await repository.find_latest_round(session, table_id))
    return table, member, round_


async def save(session: AsyncSession, table: GameTable) -> tuple[GameTable, Round]:
    """저장하고, 테이블과 가장 최근 라운드를 다시 읽어 돌려준다. 라운드가 닫혔으면 새로 열린 것이 나온다."""
    await session.commit()
    return table, await repository.find_latest_round(session, table.id)


async def declare(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: DeclarationUpdate, narrator: Narrator
) -> tuple[GameTable, Round]:
    """
    열려 있는 라운드에 선언을 낸다. 이미 냈으면 바꾼다. 앉은 사람이 모두 냈으면 라운드를 닫고 다음 것을 연다.

    돌려주는 것은 테이블과 가장 최근 라운드다. 이 선언으로 라운드가 닫혔으면 새로 열린 라운드다.

    테이블을 잠그고 한다. 마지막 두 사람이 동시에 내도 라운드는 한 번만 닫힌다.
    """
    table, member, round_ = await lock_open_round(session, user_id, table_id)
    put_declaration(round_, member, data.content)
    if not waiting_for(table, round_):
        await close_round(session, table, round_, narrator)
    return await save(session, table)


async def force_close(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, narrator: Narrator
) -> tuple[GameTable, Round]:
    """
    방장이 열려 있는 라운드를 닫는다. 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 넘어간다.

    방장이 아니면 NotHostError. 자리를 비운 사람 때문에 테이블이 멈추지 않게 한다.
    """
    table, _, round_ = await lock_open_round(session, host_id, table_id)
    tables.require_host(table, host_id)
    await close_round(session, table, round_, narrator, closer_id=host_id)
    return await save(session, table)
