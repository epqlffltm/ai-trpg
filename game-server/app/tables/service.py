# game-server/app/tables/service.py

"""
테이블을 만들고, 로비에서 찾고, 들어가고, 캐릭터를 정하고, 나가고, 시작하고, 끝낸다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.
판단과 계산은 작은 모듈에 있고, 여기는 그것들을 차례로 부르고 저장한다.
  - app/tables/errors.py: 거절되는 까닭들
  - app/tables/state.py: 자리와 방장, 테이블의 상태를 보는 판단
  - app/tables/building.py: 테이블 만들기(초대 코드, 정원의 상한, 문체, 비밀번호)
  - app/tables/seating.py: 앉기, 끝내기, 다음 방장 정하기
  - app/tables/characters.py: 캐릭터 정하기와 시작할 때의 명단

규칙 몇 가지가 테이블의 일 전체에 걸쳐 있다.
  - 테이블은 앉은 사람만 본다. 앉지 않은 사람에게는 "없는 테이블"이다.
    로비에 보이기로 한 테이블만은 누구나 목록에서 본다. 그래도 안은 앉아야 보인다.
  - 테이블을 바꾸는 일은 모두 테이블의 행을 잠그고 한다. 잠근 뒤에 확인하고, 그다음에 바꾼다.
  - 내보내기, 방장 넘기기, 시작, 끝내기는 방장만 한다.
  - 테이블을 바꾸면 무슨 일이 있었는지를 이벤트로 적는다(app/events/recorder.py). 바꾼 것과 함께 저장된다.
  - 저장은 commit 하나로 한다. 저장하면서 "새 이벤트가 생겼다"는 신호를 보낸다(app/realtime/signals.py).
    캐릭터를 정하는 것은 적지 않는다. 시작할 때 누가 어떤 캐릭터였는지를 한 번 적는다.
  - 캐릭터의 숫자(시트)는 게임을 시작할 때 준다(app/tables/sheets.py). 모집 중에는 바뀔 숫자가 없다.
  - 진행 중에는 캐릭터를 바꾸지 못한다. 캐릭터가 죽은 사람만 새 캐릭터를 들인다(app/tables/replacements.py).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets import ratings
from app.assets import service as assets
from app.assets.models import Scenario, ScenarioVersion
from app.assets.scenarios import repository as versions
from app.assets.scenarios.snapshot import read_snapshot
from app.assets.service import AssetNotFoundError
from app.auth.tokens import AccessClaims
from app.billing import charges
from app.calendar import state as calendar
from app.events import recorder
from app.events.models import EventType
from app.limits.setup import Limiting
from app.listings import service as listings
from app.realtime import signals
from app.realtime.signals import Kind, Signal
from app.rounds import opener
from app.tables import monsters, npcs, places, quests, repository, sheets
from app.tables.building import build_table, hash_table_password, new_invite_code, require_rating
from app.tables.characters import accept_character, roster, write_character
from app.tables.errors import Conflict, MemberNotFoundError, TableConflictError, TableNotFoundError, TableOptionError
from app.tables.model_choice import ModelChoice, choose_model
from app.tables.model_picker import ModelPicker
from app.tables.models import GameTable, TableMember, TableStatus
from app.tables.password_attempts import guarded_password_check
from app.tables.schemas import CharacterUpdate, HostTransfer, JoinRequest, LobbyJoinRequest, TableCreate
from app.tables.seating import end, hand_over, record_hand_over, take_seat
from app.tables.state import (
    find_member,
    require_host,
    require_member,
    require_not_ended,
    require_recruiting,
    require_story_fits,
)

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


def created_payload(choice: ModelChoice) -> dict:
    """테이블을 만든 이벤트에 싣는 것. 정한 서술 모델과 시나리오의 추천 모델. 둘이 다르면 화면이 알린다."""
    return {'narration_model': choice.slug, 'recommended_model': choice.recommended}


async def create_table(
    session: AsyncSession, viewer: AccessClaims, data: TableCreate, picker: ModelPicker
) -> GameTable:
    """
    테이블을 만든다. 만든 사람이 방장이 되어 앉는다.
    서술 모델은 방장이 고른 것, 아니면 시나리오의 추천 모델, 쓸 수 없으면 같은 회사의 대신 쓸 모델이다
    (app/tables/model_choice.py). picker 로 지금 고를 수 있는지 본다.
    판의 시작 시각을 가리키는 게임 안의 시계를 함께 단다(app/calendar/).

    판이 없으면 AssetNotFoundError, 없는 스타팅이나 판이 허용하지 않는 캐릭터 방식을 골랐으면 TableOptionError,
    성인용 판인데 성인용 내용을 볼 수 없는 사람이면 AdultContentRequiredError,
    그 판으로는 둘 수 없는 정원이면 TableConflictError.
    서술 모델을 정하지 못하면 TableOptionError(narration_model).
    """
    version = await resolve_version(session, viewer, data)
    snapshot = read_snapshot(version.snapshot)
    require_rating(viewer, snapshot.rating)

    if data.opening_index >= len(snapshot.openings):
        raise TableOptionError('opening_index')
    modes = sheets.narrow_modes(snapshot.character_modes, data.character_modes)
    if modes is None:
        raise TableOptionError('character_modes')
    by_pregens = sheets.seats_by_pregens(snapshot, modes)
    if by_pregens is not None and data.capacity > by_pregens:
        raise TableConflictError(Conflict.PREGENS_TOO_FEW)

    recommended = await versions.recommended_model(session, version.scenario_id)
    choice = await choose_model(session, picker, data.narration_model, recommended)
    password_hash = await hash_table_password(data.password)
    table = build_table(viewer.user_id, version, snapshot, data, modes, password_hash)
    table.narration_model = choice.slug
    calendar.start_clock(table, snapshot)
    repository.add_table(session, table)
    # 테이블을 먼저 DB 에 보낸다. 테이블의 ID 는 그때 정해지고, 이벤트는 그 ID 를 가리킨다
    await session.flush()
    payload = created_payload(choice)
    recorder.record(session, table, EventType.TABLE_CREATED, actor_id=viewer.user_id, payload=payload)
    await commit(session, table)
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
    allowed = ratings.allowed_ratings(viewer)
    tables = await repository.list_lobby(session, allowed, scenario_id, limit, offset)
    total = await repository.count_lobby(session, allowed, scenario_id)
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


async def commit(session: AsyncSession, table: GameTable) -> None:
    """
    테이블을 바꾼 것을 저장한다. 테이블을 바꾸는 일은 모두 이것으로 끝낸다(라운드도 이것을 쓴다).

    저장하면서 "이 테이블에 새 이벤트가 생겼다"는 신호를 보낸다. 스트림을 열어 둔 사람들이 깨어나 새 것을 읽는다.
    신호는 커밋될 때 함께 나간다. 저장에 실패하면 나가지 않는다.
    이벤트가 없는 저장(캐릭터 정하기)에도 보낸다. 깨어난 쪽이 읽을 것이 없을 뿐이다.
    """
    await signals.publish(session, Signal(table_id=table.id, kind=Kind.EVENTS))
    await session.commit()


async def save(session: AsyncSession, table: GameTable) -> GameTable:
    """바꾼 테이블을 저장하고 다시 읽어 돌려준다."""
    await commit(session, table)
    return await repository.reload_table(session, table.id)


async def join_table(session: AsyncSession, viewer: AccessClaims, data: JoinRequest) -> GameTable:
    """
    초대 코드로 테이블에 들어가 앉는다.

    코드가 틀렸으면 TableNotFoundError, 성인용 테이블인데 성인용 내용을 볼 수 없는 사람이면 AdultContentRequiredError.
    코드를 받은 사람은 테이블이 있다는 것을 이미 알아서 숨기지 않는다. 화면이 본인인증으로 안내할 수 있게 까닭을 알린다.
    모집 중이 아니거나, 이미 앉아 있거나, 자리가 없으면 TableConflictError.

    비밀번호를 묻지 않는다. 초대 코드를 가진 사람은 방장이 직접 부른 사람이다.
    테이블을 잠그고 한다. 한 자리가 남았을 때 두 사람이 동시에 "자리가 있네"를 보고 둘 다 앉는 일을 막는다.
    """
    table = await repository.lock_table_by_invite_code(session, data.invite_code)
    if table is None:
        raise TableNotFoundError
    require_rating(viewer, table.rating)

    take_seat(table, viewer.user_id)
    recorder.record(session, table, EventType.MEMBER_JOINED, actor_id=viewer.user_id, payload={'via': 'invite'})
    return await save(session, table)


async def join_public_table(
    session: AsyncSession, viewer: AccessClaims, table_id: uuid.UUID, data: LobbyJoinRequest, limiting: Limiting
) -> GameTable:
    """
    로비에 보이는 테이블에 들어가 앉는다. 초대 코드가 필요 없다.

    로비에 보이지 않는 테이블이거나 볼 수 없는 등급이면 TableNotFoundError, 비밀번호가 틀렸으면 WrongPasswordError,
    너무 많이 틀렸으면 TooManyAttempts(passwords.guard_password), 모집 중이 아니거나, 이미 앉아 있거나,
    자리가 없으면 TableConflictError.

    비밀번호를 먼저 확인하고, 그다음에 잠근다. 확인하는 데 0.2 초가 걸려서, 잠근 채로 하면 그동안 테이블이 멈춘다.
    비밀번호와 로비에 보이는지는 테이블을 만든 뒤로 바뀌지 않으므로, 잠그기 전에 봐도 낡은 값이 아니다.
    """
    table = await repository.find_table(session, table_id)
    if table is None or not table.is_public or table.rating not in ratings.allowed_ratings(viewer):
        raise TableNotFoundError
    await guarded_password_check(table, viewer.user_id, data.password, limiting)

    table = await repository.lock_table(session, table_id)
    take_seat(table, viewer.user_id)
    recorder.record(session, table, EventType.MEMBER_JOINED, actor_id=viewer.user_id, payload={'via': 'lobby'})
    return await save(session, table)


async def set_character(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: CharacterUpdate
) -> GameTable:
    """
    자기 캐릭터를 정한다. 직접 만들거나 프리젠을 가져온다. 다시 부르면 통째로 바뀐다.

    모집 중이 아니거나, 이 테이블에서 허용하지 않는 방식이거나, 다른 사람이 그 프리젠을 가져갔거나,
    주사위 방식인데 아직 굴리지 않았으면 TableConflictError.
    없는 프리젠이거나, 직접 정한 능력치가 이 테이블의 규칙에 맞지 않으면 TableOptionError.

    프리젠을 가져갔다가 직접 만든 캐릭터로 바꾸면, 그 프리젠은 다시 고를 수 있게 된다.
    능력치를 직접 정했다가 다른 방식으로 바꾸면, 적어 둔 능력치는 지워진다.
    숫자(시트)는 여기서 주지 않는다. 게임을 시작할 때 준다. 직접 정한 능력치는 그때까지 자리에 적어 둔다.

    진행 중에는 이 길로 캐릭터를 바꾸지 못한다. 캐릭터가 죽은 사람이 새 캐릭터를 들이는 길은 따로 있다
    (app/tables/replacements.py).
    """
    table, member = await lock_seated(session, user_id, table_id)
    require_recruiting(table)
    chosen = accept_character(table, read_snapshot(table.content), member, data)
    write_character(member, chosen)
    return await save(session, table)


async def leave_table(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> None:
    """
    테이블에서 나간다. 앉지 않았으면 TableNotFoundError.

    방장이 나가면 남은 사람 중 가장 먼저 들어온 사람이 방장이 된다. 마지막 사람이 나가면 테이블이 끝난다.
    나간 사람의 닫히지 않은 라운드의 서술 값은 돌려준다(charges.release_departed).
    """
    table, member = await lock_seated(session, user_id, table_id)
    table.members.remove(member)
    await charges.release_departed(session, table.id, user_id, datetime.now(UTC))
    payload = {'character_name': member.character_name}
    left = recorder.record(session, table, EventType.MEMBER_LEFT, actor_id=user_id, payload=payload)
    if table.host_id == user_id:
        record_hand_over(session, table, hand_over(table), left)
    await commit(session, table)


async def kick_member(session: AsyncSession, host_id: uuid.UUID, table_id: uuid.UUID, user_id: uuid.UUID) -> GameTable:
    """
    방장이 참가자를 내보낸다. 초대 코드를 새로 만든다. 내보낸 사람이 옛 코드로 다시 들어오지 못한다.
    내보낸 사람의 닫히지 않은 라운드의 서술 값은 돌려준다(charges.release_departed).
    크레딧이 모자란 사람을 내보내면 그 라운드를 바로 다시 맡겨 서술할 수 있다.

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
    await charges.release_departed(session, table.id, user_id, datetime.now(UTC))
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
    앉은 사람 모두에게 캐릭터 시트를 주고, 판의 인물마다 NPC 의 상태를, 사건마다 퀘스트를,
    조우마다 몬스터의 상태를 만들고, 첫 라운드를 연다.
    맵이 있는 판이면 캐릭터 모두를 시작 장소에 세운다.
    장면은 테이블을 만들 때 고른 스타팅이다.

    방장이 아니면 NotHostError, 모집 중이 아니거나 캐릭터를 만들지 않은 사람이 있거나
    판의 작가 글이 서술의 입력 예산을 넘으면 TableConflictError.

    상태를 바꾸고, 시트를 주고, 이벤트를 적고, 라운드를 여는 것이 한 묶음으로 저장된다. 일부만 되는 일이 없다.
    NPC 의 상태는 이벤트에 적지 않는다. 누가 NPC 인지는 로어북의 내용이고, 로어북은 AI 만 읽는다.
    몬스터의 상태도 적지 않는다. 아직 가 보지 않은 장소에 무엇이 있는지 드러난다.
    """
    table, _ = await lock_seated(session, host_id, table_id)
    require_host(table, host_id)
    require_recruiting(table)
    snapshot = read_snapshot(table.content)
    require_story_fits(table, snapshot)
    # 캐릭터를 정하지 않은 사람이 있으면 그 사람이 받을 시트도 없다. 아무에게도 주지 않고 거절한다
    if not sheets.hand_out(table, snapshot):
        raise TableConflictError(Conflict.CHARACTERS_MISSING)
    places.place_at_start(table, snapshot)
    repository.add_npcs(session, npcs.make_npcs(table.id, snapshot))
    repository.add_monsters(session, monsters.make_monsters(table.id, snapshot))
    table.quests.extend(quests.make_quests(table.id, snapshot, table.clock.minutes))

    table.status = TableStatus.PLAYING
    table.started_at = func.now()
    payload = {'members': roster(table)}
    started = recorder.record(session, table, EventType.TABLE_STARTED, actor_id=host_id, payload=payload)
    opening = snapshot.openings[table.opening_index]
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
