# game-server/app/tables/service.py

"""
테이블을 만들고, 로비에서 찾고, 들어가고, 캐릭터를 정하고, 나가고, 시작하고, 끝낸다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

규칙 셋이 이 파일 전체에 걸쳐 있다.
  - 테이블은 앉은 사람만 본다. 앉지 않은 사람에게는 "없는 테이블"이다.
    로비에 보이기로 한 테이블만은 누구나 목록에서 본다. 그래도 안은 앉아야 보인다.
  - 테이블을 바꾸는 일은 모두 테이블의 행을 잠그고 한다. 잠근 뒤에 확인하고, 그다음에 바꾼다.
  - 내보내기, 방장 넘기기, 시작, 끝내기는 방장만 한다.
  - 테이블을 바꾸면 무슨 일이 있었는지를 이벤트로 적는다(app/events/recorder.py). 바꾼 것과 함께 저장된다.
    캐릭터를 정하는 것은 적지 않는다. 시작할 때 누가 어떤 캐릭터였는지를 한 번 적는다.
"""

import asyncio
import enum
import secrets
import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import service as assets
from app.assets.models import TABLE_MAX_PLAYERS, Scenario, ScenarioVersion
from app.assets.scenarios import repository as versions
from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.assets.service import AssetNotFoundError
from app.auth.tokens import AccessClaims
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.listings import service as listings
from app.rounds import opener
from app.tables import passwords, repository
from app.tables.models import GameTable, TableMember, TableStatus
from app.tables.schemas import CharacterUpdate, HostTransfer, JoinRequest, LobbyJoinRequest, TableCreate


class TableNotFoundError(Exception):
    """그런 테이블이 없다. 앉지 않은 사람이 찾은 경우, 초대 코드가 틀린 경우도 이 예외다."""


class MemberNotFoundError(Exception):
    """그 사람은 이 테이블에 앉아 있지 않다."""


class NotHostError(Exception):
    """방장만 할 수 있는 일을 방장이 아닌 참가자가 하려 했다."""


class WrongPasswordError(Exception):
    """테이블의 비밀번호가 틀렸다. 비밀번호가 걸린 테이블에 비밀번호 없이 들어오려 한 경우도 이 예외다."""


class Conflict(enum.StrEnum):
    """요청은 맞지만 테이블의 지금 상태와 부딪히는 이유."""

    # 자리가 다 찼다
    TABLE_FULL = 'table_full'
    # 모집 중이 아니다. 들어오기, 캐릭터 정하기, 시작은 모집 중에만 된다
    NOT_RECRUITING = 'not_recruiting'
    # 테이블이 이미 끝났다
    ALREADY_ENDED = 'already_ended'
    # 이미 앉아 있다
    ALREADY_SEATED = 'already_seated'
    # 다른 사람이 그 프리젠을 가져갔다
    PREGEN_TAKEN = 'pregen_taken'
    # 캐릭터를 만들지 않은 사람이 있다
    CHARACTERS_MISSING = 'characters_missing'
    # 방장은 자신을 내보낼 수 없다. 나가기를 쓴다
    CANNOT_KICK_SELF = 'cannot_kick_self'
    # 이 등급의 테이블은 혼자서만 할 수 있다(성인 인증이 생길 때까지)
    SOLO_ONLY = 'solo_only'


class TableConflictError(Exception):
    """테이블의 지금 상태와 부딪힌다. reason 이 이유다."""

    def __init__(self, reason: Conflict) -> None:
        super().__init__(reason)
        self.reason = reason


class TableOptionError(Exception):
    """
    고른 번호가 판에 없다. 없는 스타팅이나 없는 프리젠을 골랐다.

    field 는 입력의 어느 칸이 틀렸는지다(opening_index, pregen_index).
    """

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


# --- 판단하는 작은 함수들. DB 를 건드리지 않는다 ---


def new_invite_code() -> str:
    """추측할 수 없는 초대 코드를 만든다. 9 바이트를 글자로 바꾸면 12 글자다."""
    return secrets.token_urlsafe(9)


def seat_limit(viewer: AccessClaims, snapshot: Snapshot) -> int:
    """
    이 사람이 이 판으로 테이블을 만들 때 둘 수 있는 가장 큰 정원.

    볼 수 없는 등급의 판이면(지금은 성인용 전부) 혼자서만 한다. 제작자가 자기 것을 시험해 보는 용도다.
    성인 인증이 생기면 allowed_ratings 가 성인용을 돌려주고, 이 제한은 저절로 풀린다.
    """
    if snapshot.rating in listings.allowed_ratings(viewer):
        return TABLE_MAX_PLAYERS
    return 1


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


def require_not_ended(table: GameTable) -> None:
    """테이블이 끝나지 않았는지 확인한다. 끝났으면 TableConflictError."""
    if table.status == TableStatus.ENDED:
        raise TableConflictError(Conflict.ALREADY_ENDED)


def require_pregen_free(table: GameTable, member: TableMember, pregen_index: int) -> None:
    """다른 사람이 이 프리젠을 가져가지 않았는지 확인한다. 가져갔으면 TableConflictError."""
    others = [other for other in table.members if other is not member]
    if any(other.pregen_index == pregen_index for other in others):
        raise TableConflictError(Conflict.PREGEN_TAKEN)


def resolve_character(snapshot: Snapshot, data: CharacterUpdate) -> tuple[str, str]:
    """
    입력에서 캐릭터의 이름과 설명을 정한다. 없는 프리젠을 골랐으면 TableOptionError.

    프리젠을 골랐으면 프리젠의 것이 바탕이고, 함께 보낸 칸은 보낸 것으로 고쳐 쓴다.
    """
    if data.pregen_index is None:
        return data.name, data.description or ''

    if data.pregen_index >= len(snapshot.pregens):
        raise TableOptionError('pregen_index')
    pregen = snapshot.pregens[data.pregen_index]
    name = data.name if data.name is not None else pregen.name
    description = data.description if data.description is not None else pregen.description
    return name, description


def take_seat(table: GameTable, user_id: uuid.UUID) -> None:
    """
    테이블에 앉는다. 모집 중이 아니거나, 이미 앉아 있거나, 자리가 없으면 TableConflictError.

    테이블을 잠근 뒤에 부른다. 초대 코드로 들어오든 로비에서 들어오든 앉는 규칙은 같다.
    """
    require_recruiting(table)
    if find_member(table, user_id) is not None:
        raise TableConflictError(Conflict.ALREADY_SEATED)
    if len(table.members) >= table.capacity:
        raise TableConflictError(Conflict.TABLE_FULL)
    table.members.append(TableMember(user_id=user_id))


def end(table: GameTable) -> None:
    """테이블을 끝낸다."""
    table.status = TableStatus.ENDED
    table.ended_at = func.now()


def hand_over(table: GameTable) -> EventType | None:
    """
    방장이 떠난 테이블의 다음 방장을 정한다. 남은 사람 중 가장 먼저 들어온 사람이다.

    남은 사람이 없으면 테이블을 끝낸다.
    무슨 일이 일어났는지를 이벤트의 종류로 돌려준다. 이미 끝난 테이블에서 마지막 사람이 나갔으면 아무 일도 없다(None).
    """
    if table.members:
        table.host_id = table.members[0].user_id
        return EventType.HOST_CHANGED
    if table.status != TableStatus.ENDED:
        end(table)
        return EventType.TABLE_ENDED
    return None


def roster(table: GameTable) -> list[dict]:
    """앉은 사람과 캐릭터 이름의 목록. 이벤트에 적을 모양이다."""
    return [{'user_id': str(member.user_id), 'character_name': member.character_name} for member in table.members]


def build_table(
    host_id: uuid.UUID, version: ScenarioVersion, snapshot: Snapshot, data: TableCreate, password_hash: str | None
) -> GameTable:
    """
    판에서 테이블 객체를 만든다. 아직 저장하지 않는다.

    판의 내용을 통째로 복사해 온다. 옛 형식의 판이면 지금의 모양으로 올린 것을 복사한다.
    만든 사람이 방장이자 첫 참가자다. password_hash 는 비밀번호를 계산해 둔 값이다. 비밀번호가 없으면 None 이다.
    """
    return GameTable(
        host_id=host_id,
        version_id=version.id,
        title=snapshot.title,
        # mode='json': UUID 같은 값을 JSON 에 넣을 수 있는 글자로 바꾼다
        content=snapshot.model_dump(mode='json'),
        opening_index=data.opening_index,
        capacity=data.capacity,
        rating=snapshot.rating,
        invite_code=new_invite_code(),
        is_public=data.is_public,
        password_hash=password_hash,
        members=[TableMember(user_id=host_id)],
    )


# --- 비밀번호. 계산이 느려서 다른 요청을 막지 않게 따로 돌린다 ---


async def hash_table_password(password: str | None) -> str | None:
    """
    비밀번호를 저장할 모양으로 바꾼다. 비밀번호가 없으면 None.

    to_thread: 계산을 다른 스레드에서 돌린다. 0.2 초 동안 서버가 다른 요청을 받지 못하는 일을 막는다.
    """
    if password is None:
        return None
    return await asyncio.to_thread(passwords.hash_password, password)


async def check_table_password(table: GameTable, password: str | None) -> None:
    """
    테이블의 비밀번호가 맞는지 확인한다. 틀렸으면 WrongPasswordError.

    비밀번호가 없는 테이블이면 무엇을 보내든 통과한다.
    """
    if table.password_hash is None:
        return
    if password is None or not await asyncio.to_thread(passwords.verify_password, password, table.password_hash):
        raise WrongPasswordError


# --- 만들기 ---


async def resolve_version(session: AsyncSession, viewer: AccessClaims, data: TableCreate) -> ScenarioVersion:
    """
    테이블을 만들 판을 찾는다. 없으면 AssetNotFoundError.

    번호를 적지 않았으면 그 시나리오의 공개 중인 판이다. 남의 시나리오는 이 길로만 쓴다.
    번호를 적었으면 자기 시나리오의 그 판이다. 공개하지 않은 판도 된다.
    """
    if data.version is None:
        _, _, version = await listings.get_public(session, viewer, data.scenario_id)
        return version

    await assets.get_owned(session, Scenario, viewer.user_id, data.scenario_id)
    version = await versions.find_version(session, data.scenario_id, data.version)
    if version is None:
        raise AssetNotFoundError
    return version


async def create_table(session: AsyncSession, viewer: AccessClaims, data: TableCreate) -> GameTable:
    """
    테이블을 만든다. 만든 사람이 방장이 되어 앉는다.

    판이 없으면 AssetNotFoundError, 없는 스타팅을 골랐으면 TableOptionError,
    그 판으로는 둘 수 없는 정원이면 TableConflictError.
    """
    version = await resolve_version(session, viewer, data)
    snapshot = read_snapshot(version.snapshot)

    if data.opening_index >= len(snapshot.openings):
        raise TableOptionError('opening_index')
    if data.capacity > seat_limit(viewer, snapshot):
        raise TableConflictError(Conflict.SOLO_ONLY)

    password_hash = await hash_table_password(data.password)
    table = build_table(viewer.user_id, version, snapshot, data, password_hash)
    repository.add_table(session, table)
    # 테이블을 먼저 DB 에 보낸다. 테이블의 ID 는 그때 정해지고, 이벤트는 그 ID 를 가리킨다
    await session.flush()
    recorder.record(session, table, EventType.TABLE_CREATED, actor_id=viewer.user_id)
    await session.commit()
    return await repository.reload_table(session, table.id)


# --- 읽기 ---


async def get_table(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> GameTable:
    """자기가 앉아 있는 테이블 하나를 돌려준다. 없거나 앉지 않았으면 TableNotFoundError."""
    table = await repository.find_table(session, table_id)
    require_member(table, user_id)
    return table


async def list_tables(
    session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[GameTable], int]:
    """자기가 앉아 있는 테이블의 한 쪽과 전체 개수를 돌려준다."""
    tables = await repository.list_seated(session, user_id, limit, offset)
    total = await repository.count_seated(session, user_id)
    return tables, total


async def list_lobby(
    session: AsyncSession, viewer: AccessClaims, scenario_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[GameTable], int]:
    """
    로비에 보이는 테이블의 한 쪽과 전체 개수를 돌려준다. 보는 사람이 볼 수 있는 등급만 나온다.

    scenario_id 를 주면 그 시나리오로 열린 테이블만 돌려준다.
    """
    ratings = listings.allowed_ratings(viewer)
    tables = await repository.list_lobby(session, ratings, scenario_id, limit, offset)
    total = await repository.count_lobby(session, ratings, scenario_id)
    return tables, total


# --- 바꾸기. 모두 테이블을 잠그고 한다 ---


async def lock_seated(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> tuple[GameTable, TableMember]:
    """
    자기가 앉아 있는 테이블을 잠그고, 테이블과 자기 자리를 돌려준다. 없거나 앉지 않았으면 TableNotFoundError.

    잠근 뒤에 읽은 값으로 확인한다. 잠그기 전에 확인하면, 그사이에 내보내졌을 수 있다.
    """
    table = await repository.lock_table(session, table_id)
    member = require_member(table, user_id)
    return table, member


async def save(session: AsyncSession, table: GameTable) -> GameTable:
    """바꾼 테이블을 저장하고 다시 읽어 돌려준다."""
    await session.commit()
    return await repository.reload_table(session, table.id)


async def join_table(session: AsyncSession, viewer: AccessClaims, data: JoinRequest) -> GameTable:
    """
    초대 코드로 테이블에 들어가 앉는다.

    코드가 틀렸거나 볼 수 없는 등급의 테이블이면 TableNotFoundError.
    모집 중이 아니거나, 이미 앉아 있거나, 자리가 없으면 TableConflictError.

    비밀번호를 묻지 않는다. 초대 코드를 가진 사람은 방장이 직접 부른 사람이다.
    테이블을 잠그고 한다. 한 자리가 남았을 때 두 사람이 동시에 "자리가 있네"를 보고 둘 다 앉는 일을 막는다.
    """
    table = await repository.lock_table_by_invite_code(session, data.invite_code)
    if table is None or table.rating not in listings.allowed_ratings(viewer):
        raise TableNotFoundError

    take_seat(table, viewer.user_id)
    recorder.record(session, table, EventType.MEMBER_JOINED, actor_id=viewer.user_id, payload={'via': 'invite'})
    return await save(session, table)


async def join_public_table(
    session: AsyncSession, viewer: AccessClaims, table_id: uuid.UUID, data: LobbyJoinRequest
) -> GameTable:
    """
    로비에 보이는 테이블에 들어가 앉는다. 초대 코드가 필요 없다.

    로비에 보이지 않는 테이블이거나 볼 수 없는 등급이면 TableNotFoundError, 비밀번호가 틀렸으면 WrongPasswordError,
    모집 중이 아니거나, 이미 앉아 있거나, 자리가 없으면 TableConflictError.

    비밀번호를 먼저 확인하고, 그다음에 잠근다. 확인하는 데 0.2 초가 걸려서, 잠근 채로 하면 그동안 테이블이 멈춘다.
    비밀번호와 로비에 보이는지는 테이블을 만든 뒤로 바뀌지 않으므로, 잠그기 전에 봐도 낡은 값이 아니다.
    """
    table = await repository.find_table(session, table_id)
    if table is None or not table.is_public or table.rating not in listings.allowed_ratings(viewer):
        raise TableNotFoundError
    await check_table_password(table, data.password)

    table = await repository.lock_table(session, table_id)
    take_seat(table, viewer.user_id)
    recorder.record(session, table, EventType.MEMBER_JOINED, actor_id=viewer.user_id, payload={'via': 'lobby'})
    return await save(session, table)


async def set_character(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: CharacterUpdate
) -> GameTable:
    """
    자기 캐릭터를 정한다. 직접 만들거나 프리젠을 가져온다. 다시 부르면 통째로 바뀐다.

    모집 중이 아니거나 다른 사람이 그 프리젠을 가져갔으면 TableConflictError, 없는 프리젠이면 TableOptionError.

    프리젠을 가져갔다가 직접 만든 캐릭터로 바꾸면, 그 프리젠은 다시 고를 수 있게 된다.
    """
    table, member = await lock_seated(session, user_id, table_id)
    require_recruiting(table)

    name, description = resolve_character(read_snapshot(table.content), data)
    if data.pregen_index is not None:
        require_pregen_free(table, member, data.pregen_index)

    member.character_name = name
    member.character_description = description
    member.pregen_index = data.pregen_index
    return await save(session, table)


def record_hand_over(session: AsyncSession, table: GameTable, outcome: EventType | None, left: TableEvent) -> None:
    """
    방장이 나간 뒤에 일어난 일(hand_over 가 돌려준 것)을 이벤트로 적는다. 원인은 방장이 나간 이벤트다.

    사람이 한 일이 아니므로 actor_id 가 없다.
    """
    if outcome == EventType.HOST_CHANGED:
        recorder.record(session, table, outcome, payload={'user_id': str(table.host_id)}, cause=left)
    elif outcome == EventType.TABLE_ENDED:
        recorder.record(session, table, outcome, cause=left)


async def leave_table(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> None:
    """
    테이블에서 나간다. 앉지 않았으면 TableNotFoundError.

    방장이 나가면 남은 사람 중 가장 먼저 들어온 사람이 방장이 된다. 마지막 사람이 나가면 테이블이 끝난다.
    """
    table, member = await lock_seated(session, user_id, table_id)
    table.members.remove(member)
    payload = {'character_name': member.character_name}
    left = recorder.record(session, table, EventType.MEMBER_LEFT, actor_id=user_id, payload=payload)
    if table.host_id == user_id:
        record_hand_over(session, table, hand_over(table), left)
    await session.commit()


async def kick_member(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, user_id: uuid.UUID) -> GameTable:
    """
    방장이 참가자를 내보낸다. 초대 코드를 새로 만든다. 내보낸 사람이 옛 코드로 다시 들어오지 못한다.

    방장이 아니면 NotHostError, 그 사람이 앉아 있지 않으면 MemberNotFoundError,
    끝난 테이블이거나 자신을 내보내려 하면 TableConflictError.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)
    if user_id == host_id:
        raise TableConflictError(Conflict.CANNOT_KICK_SELF)

    member = find_member(table, user_id)
    if member is None:
        raise MemberNotFoundError

    table.members.remove(member)
    table.invite_code = new_invite_code()
    # 새 초대 코드는 적지 않는다. 이벤트는 앉은 사람 모두가 읽는다
    payload = {'user_id': str(user_id), 'character_name': member.character_name}
    recorder.record(session, table, EventType.MEMBER_KICKED, actor_id=host_id, payload=payload)
    return await save(session, table)


async def transfer_host(
    session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, data: HostTransfer
) -> GameTable:
    """
    방장을 다른 참가자에게 넘긴다.

    방장이 아니면 NotHostError, 받을 사람이 앉아 있지 않으면 MemberNotFoundError, 끝난 테이블이면 TableConflictError.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)
    if find_member(table, data.user_id) is None:
        raise MemberNotFoundError

    table.host_id = data.user_id
    payload = {'user_id': str(data.user_id)}
    recorder.record(session, table, EventType.HOST_CHANGED, actor_id=host_id, payload=payload)
    return await save(session, table)


async def start_table(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID) -> GameTable:
    """
    방장이 테이블을 시작한다. 그 뒤로는 새로 들어올 수 없고 캐릭터를 바꿀 수 없다.
    첫 라운드를 연다. 장면은 테이블을 만들 때 고른 스타팅이다.

    방장이 아니면 NotHostError, 모집 중이 아니거나 캐릭터를 만들지 않은 사람이 있으면 TableConflictError.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_recruiting(table)
    if any(member.character_name is None for member in table.members):
        raise TableConflictError(Conflict.CHARACTERS_MISSING)

    table.status = TableStatus.PLAYING
    table.started_at = func.now()
    payload = {'members': roster(table)}
    started = recorder.record(session, table, EventType.TABLE_STARTED, actor_id=host_id, payload=payload)
    opening = read_snapshot(table.content).openings[table.opening_index]
    opener.open_round(session, table, number=1, scene=opening, cause=started)
    return await save(session, table)


async def end_table(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID) -> GameTable:
    """
    방장이 테이블을 끝낸다.

    방장이 아니면 NotHostError, 이미 끝났으면 TableConflictError.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_not_ended(table)

    end(table)
    recorder.record(session, table, EventType.TABLE_ENDED, actor_id=host_id)
    return await save(session, table)
