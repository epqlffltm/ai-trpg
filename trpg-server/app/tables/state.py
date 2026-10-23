# trpg-server/app/tables/state.py

"""
테이블과 자리의 지금 상태를 보고 판단하는 작은 함수들.

DB 를 모른다. 이미 읽어 온 테이블과 자리를 받아 보기만 한다. 고치지 않는다.
틀렸으면 예외를 던지는 require_* 와, 찾은 것을 돌려주는 find_member 로 나뉜다.
테이블 밖의 코드(라운드, 채팅, 스트림, 보관함)도 이것으로 자리와 방장을 확인한다.
"""

import uuid

from app.assets.models import NarrationStyle
from app.assets.scenarios.snapshot import Snapshot
from app.catalog.offers import OfferedModel
from app.catalog.steps import steps_of
from app.rounds.budget import story_fits
from app.rounds.narration_request import to_story
from app.tables import sheets
from app.tables.errors import Conflict, NotHostError, TableConflictError, TableNotFoundError, TableOptionError
from app.tables.models import GameTable, TableMember, TableStatus


def find_member(table: GameTable, user_id: uuid.UUID) -> TableMember | None:
    """테이블에 앉은 사람 중에서 이 사람을 찾는다."""
    return next((member for member in table.members if member.user_id == user_id), None)


def require_member(table: GameTable | None, user_id: uuid.UUID) -> TableMember:
    """이 사람이 이 테이블에 앉아 있는지 확인한다. 테이블이 없거나 앉지 않았으면 TableNotFoundError."""
    member = find_member(table, user_id) if table else None
    if member is None:
        raise TableNotFoundError
    return member


def require_host(table: GameTable, user_id: uuid.UUID) -> None:
    """이 사람이 방장인지 확인한다. 아니면 NotHostError."""
    if table.host_id != user_id:
        raise NotHostError


def require_recruiting(table: GameTable) -> None:
    """테이블이 모집 중인지 확인한다. 아니면 TableConflictError."""
    if table.status != TableStatus.RECRUITING:
        raise TableConflictError(Conflict.NOT_RECRUITING)


def require_story_fits(table: GameTable, snapshot: Snapshot) -> None:
    """
    판의 작가 글(진행 지침, 세계관, GM 메모)이 서술의 입력 예산 안에 드는지 확인한다. 아니면 TableConflictError.

    작가의 글은 라운드마다 통째로 들어간다(app/rounds/budget.py). 예산을 혼자 넘으면 어느 라운드든 판 값보다 비싸다.
    시작할 때 막는다. 라운드 중간에 서술이 실패하는 것보다 낫고, 아직 아무도 값을 내지 않았다.
    예산은 테이블의 입력 단계의 것이다(#387). 시작하면 단계도 고정이라 라운드마다 같다.
    """
    if not story_fits(to_story(snapshot), NarrationStyle(table.narration_style), steps_of(table)):
        raise TableConflictError(Conflict.STORY_TOO_LONG)


def require_choosing(table: GameTable, member: TableMember) -> None:
    """
    이 사람이 캐릭터를 정할 수 있는 때인지 확인한다. 아니면 TableConflictError.

    모집 중에는 누구나 정한다. 진행 중에는 자기 캐릭터가 죽은 사람만 새 캐릭터를 정한다.
    끝난 테이블에서는 아무도 정하지 못한다.
    주사위를 굴리는 것과 "한 번 더"를 받는 것이 이 조건을 쓴다. 둘 다 캐릭터를 정하는 일의 앞걸음이다.
    """
    if table.status == TableStatus.RECRUITING:
        return
    if table.status != TableStatus.PLAYING:
        raise TableConflictError(Conflict.NOT_RECRUITING)
    if not sheets.is_dead(member):
        raise TableConflictError(Conflict.CHARACTER_ALIVE)


def require_not_ended(table: GameTable) -> None:
    """테이블이 끝나지 않았는지 확인한다. 끝났으면 TableConflictError."""
    if table.status == TableStatus.ENDED:
        raise TableConflictError(Conflict.ALREADY_ENDED)


def require_model_offered(found: OfferedModel | None) -> None:
    """
    방장이 고른 서술 모델이 지금 고를 수 있는 것인지 확인한다. 아니면 TableOptionError(narration_model).

    found 는 고를 수 있는 목록에서 찾은 것이다(app/catalog/offers.py 의 find_offered). 없으면 None 이다.
    모델 목록에 없거나, 꺼졌거나, 은퇴했거나, 결제 서버가 팔지 않는 모델이다.
    """
    if found is None:
        raise TableOptionError('narration_model')


def require_steps_offered(found: OfferedModel | None) -> None:
    """
    방장이 고른 단계(#387)를 그 모델로 지금 파는지 확인한다. 아니면 TableOptionError(narration_steps).

    모델은 고를 수 있는데(기본 단계를 판다) 그 단계의 가격표가 없거나 팔지 않는 것이다.
    """
    if found is None:
        raise TableOptionError('narration_steps')
