# game-server/app/rounds/state.py

"""
라운드와 테이블의 지금 상태를 보고 판단하는 작은 함수들.

DB 를 모른다. 이미 읽어 온 테이블, 자리, 라운드를 받아 보기만 한다. 고치지 않는다.
틀렸으면 RoundConflictError 를 던지는 require_* 와, 참거짓이나 찾은 것을 돌려주는 나머지로 나뉜다.

쓰러진 사람(HP 0)은 글만 낼 수 있고, 라운드는 그 사람의 선언을 기다리지 않는다.
새 캐릭터는 열려 있는 라운드에 들어온다(app/tables/replacements.py). 들어온 것은 라운드에 적힌다(arrivals).
들어온 라운드에는 선언을 내지 않고, 라운드도 그 사람을 기다리지 않는다. 그 라운드의 장면에 아직 없는 인물이다.
"""

import uuid
from datetime import datetime

from app.assets.scenarios.snapshot import read_snapshot
from app.engine import health
from app.engine.ruleset import Ruleset
from app.rounds.errors import Conflict, RoundConflictError
from app.rounds.models import Declaration, Round, RoundStatus
from app.tables.models import GameTable, TableMember, TableStatus


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


def is_ready(table: GameTable, round_: Round) -> bool:
    """
    기다리던 사람이 모두 냈는가. 그리고 앉은 사람 중 누군가는 냈는가.

    기다릴 사람이 아무도 없어도 낸 사람이 없으면 닫지 않는다. 모두 쓰러진 테이블이 저절로 넘어가지 않게 한다.
    그때는 방장이 닫거나 마감이 닫는다.
    """
    if waiting_for(table, round_):
        return False
    return any(find_declaration(round_, member.user_id) is not None for member in table.members)


def is_overdue(round_: Round, now: datetime) -> bool:
    """선언을 받는 중인 라운드의 마감이 지났는가. 마감이 없으면 지나지 않는다."""
    return round_.status == RoundStatus.OPEN and round_.deadline_at is not None and round_.deadline_at <= now


def rules_of(table: GameTable) -> Ruleset:
    """
    이 테이블의 규칙. 테이블이 들고 있는 판의 복사본에서 읽는다.

    복사본을 통째로 읽는다. 규칙이 없던 때의 복사본이면 그때의 규칙으로 올려 읽어야 하기 때문이다.
    """
    return read_snapshot(table.content).rulebook.rules


def has_outcome(declaration: Declaration | None) -> bool:
    """이 선언에 판정의 결과가 적혀 있는가. 주사위를 굴린 판정(치료도)만이다. 지목은 naming_of 로 읽는다."""
    return declaration is not None and declaration.outcome is not None and 'roll' in declaration.outcome


def item_use_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 물건 쓰기의 결과(app/rounds/item_actions.py 의 judge_use). 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('item_use')


def item_give_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 물건 건네기의 결과(app/rounds/item_actions.py 의 judge_give). 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('item_give')


def move_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 가기의 결과(app/rounds/map_actions.py 의 judge_move). 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('move')


def search_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 찾기의 결과(app/rounds/map_actions.py 의 judge_search). 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('search')


def take_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 줍기의 결과(app/rounds/place_item_actions.py 의 judge_take). 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('take')


def put_down_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 내려놓기의 결과(app/rounds/place_item_actions.py). 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('put_down')


def steal_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 훔치기의 결과(app/rounds/steals.py). 아니었거나, 결과가 없거나, 겨눈 마리가 사라졌으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('steal')


def loot_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 빼앗기의 결과(app/rounds/loots.py). 아니었거나, 결과가 없거나, 대상이 사라졌으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('loot')


def rest_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 쉬기의 결과(app/rounds/rests.py). 쉬는 행동이 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('rest')


def naming_of(declaration: Declaration | None) -> dict | None:
    """이 선언에 적힌 지목의 결과(app/rounds/naming.py 의 judge_naming). 지목이 아니었거나 결과가 없으면 None."""
    if declaration is None or declaration.outcome is None:
        return None
    return declaration.outcome.get('naming')
