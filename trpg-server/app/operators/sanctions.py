# trpg-server/app/operators/sanctions.py

"""
운영자의 제재(#392). 규칙의 원본은 docs/architecture/operators.md 의 "제재"다.

  - 시나리오 제재: 공개를 내리고 그 판을 다시 공개하지 못하게 한다.
    제작자가 혼자 쓰는 것(자기 판으로 테이블 열기)은 막지 않는다.
    고쳐서 새 판을 내면 그 판은 바로 공개할 수 있다. 이미 그 판으로 열린 테이블은 그대로다(필요하면 테이블을 끝낸다)
  - 공개 금지(블랙리스트): 한 사람의 시나리오가 정해진 수(PUBLISHING_BAN_THRESHOLD)만큼 제재되면 저절로 공개를 막는다.
    운영자가 직접 금지하거나 풀 수도 있다. 금지되어도 자기 시나리오와 남의 시나리오로 플레이하는 것은 된다
  - 테이블 끝내기: 방장이 끝낸 것과 같은 흐름이다.
    앉은 사람에게는 "운영자가 끝냈다"(payload 의 by)가 보이고 사유는 보이지 않는다.
    걸린 서술 값은 정리 작업이 돌려준다(끝난 테이블의 청구, app/billing/repository.py 의 release_abandoned)
  - 사용자 정지는 여기에 없다. 인증 서버의 명령(suspend_account)으로 한다. 관리 서버가 생기면 그쪽으로 옮긴다

제재는 감사 기록(operator_actions)과 한 트랜잭션에서 커밋한다. 제재가 되지 않았으면 기록도 남지 않는다.
당사자의 알림(시나리오 제재, 공개 금지와 풀기)도 같은 트랜잭션에서 발송함에 적는다(app/operators/notices.py).
테이블 끝내기는 알리지 않는다. 앉은 사람이 테이블의 이벤트로 본다.
HTTP 를 모른다. 운영자인지는 부르는 쪽(app/operators/router.py)이 확인했다.
"""

import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.service import AssetNotFoundError
from app.events import recorder
from app.events.models import EventType
from app.listings import repository as listings
from app.listings.service import unpublish
from app.observability.context import current_ids
from app.operators import notices, repository
from app.operators.models import ActionKind, OperatorAction, PublishingBan, ScenarioSanction
from app.operators.publishing import is_active
from app.tables import repository as tables
from app.tables import service as table_service
from app.tables.errors import Conflict, TableConflictError, TableNotFoundError
from app.tables.models import GameTable, TableStatus
from app.tables.seating import end

logger = logging.getLogger(__name__)

# 운영자의 제재 로그의 operation(docs/observability.md)
ACTION_OPERATION = 'operator.act'
# 테이블을 끝낸 이벤트의 payload 에 싣는, 끝낸 쪽
ENDED_BY_OPERATOR = 'operator'
# 저절로 금지될 때 적는 사유. 사람이 쓴 글이 아니다
AUTO_BAN_REASON = '제재된 시나리오가 정해진 수에 닿았다'


class SanctionConflict(enum.StrEnum):
    """제재를 할 수 없는 지금의 상태."""

    # 공개 중인 판이 없다. 제재는 공개를 내리는 일이다
    NOT_PUBLISHED = 'not_published'
    # 이미 공개 금지 중이다
    ALREADY_BANNED = 'already_banned'
    # 공개 금지 중이 아니다
    NOT_BANNED = 'not_banned'


class SanctionConflictError(Exception):
    """제재가 지금의 상태와 부딪힌다(409). reason 이 까닭이다."""

    def __init__(self, reason: SanctionConflict) -> None:
        super().__init__(reason)
        self.reason = reason


class BanState(enum.StrEnum):
    """제재 하나를 본 뒤의 공개 금지."""

    # 금지 중이 아니다
    NOT_BANNED = 'not_banned'
    # 이미 금지 중이었다
    ALREADY_BANNED = 'already_banned'
    # 이번 제재로 저절로 금지되었다
    NEWLY_BANNED = 'newly_banned'


@dataclass(frozen=True)
class SanctionResult:
    """시나리오를 제재한 결과."""

    scenario_id: uuid.UUID
    version_number: int
    owner_id: uuid.UUID
    # 이 제재로(또는 이미) 제작자가 공개 금지 중인가
    publishing_banned: bool


# --- 기록 ---


def build_action(
    operator_id: uuid.UUID, kind: ActionKind, target_id: uuid.UUID, reason: str, now: datetime
) -> OperatorAction:
    """제재의 감사 기록 한 줄을 만든다. 아직 저장하지 않는다."""
    return OperatorAction(
        operator_id=operator_id,
        acted_at=now,
        action=kind,
        target_id=target_id,
        reason=reason,
        request_id=current_ids().get('request_id'),
    )


def log_action(action: OperatorAction) -> None:
    """제재를 로그에 남긴다. 커밋한 뒤에 부른다. 사유는 싣지 않는다."""
    logger.info(
        '운영자가 제재했다',
        extra={
            'operation': ACTION_OPERATION,
            'operator_id': str(action.operator_id),
            'action': action.action,
            'target_id': str(action.target_id),
        },
    )


# --- 공개 금지 ---


def reached(count: int, threshold: int) -> bool:
    """제재된 수가 공개 금지에 닿았는가."""
    return count >= threshold


def restart(ban: PublishingBan, banned_by: uuid.UUID | None, reason: str, now: datetime) -> None:
    """풀렸던 공개 금지의 줄을 다시 금지로 쓴다."""
    ban.banned_at, ban.banned_by, ban.reason = now, banned_by, reason
    ban.lifted_at, ban.lifted_by = None, None


async def impose_ban(
    session: AsyncSession, user_id: uuid.UUID, banned_by: uuid.UUID | None, reason: str, now: datetime
) -> PublishingBan:
    """공개 금지의 줄을 금지 중으로 만든다. 없으면 새로 만든다. 사람마다 잠근 뒤에 부른다(lock_owner)."""
    ban = await repository.find_ban(session, user_id)
    if ban is None:
        ban = PublishingBan(user_id=user_id, banned_at=now, banned_by=banned_by, reason=reason)
        repository.add_ban(session, ban)
    else:
        restart(ban, banned_by, reason, now)
    return ban


async def ban_if_due(session: AsyncSession, owner_id: uuid.UUID, now: datetime, threshold: int) -> BanState:
    """
    제재된 수가 금지에 닿았으면 저절로 공개를 금지한다. 그 뒤의 공개 금지를 돌려준다. 사람마다 잠근 뒤에 부른다.

    풀린 적이 있으면 푼 뒤의 제재만 센다.
    """
    ban = await repository.find_ban(session, owner_id)
    if is_active(ban):
        return BanState.ALREADY_BANNED
    count = await repository.count_sanctions(session, owner_id, ban.lifted_at if ban else None)
    if not reached(count, threshold):
        return BanState.NOT_BANNED
    await impose_ban(session, owner_id, None, AUTO_BAN_REASON, now)
    return BanState.NEWLY_BANNED


async def tell_owner(
    session: AsyncSession, action: OperatorAction, owner_id: uuid.UUID, title: str, version_number: int, ban: BanState
) -> None:
    """시나리오 제재를 제작자에게 알린다. 이번 제재로 저절로 금지되었으면 그것도 따로 알린다. 기록을 flush 한다."""
    await session.flush()
    banned = ban != BanState.NOT_BANNED
    notices.tell_sanctioned(session, action, owner_id, title, version_number, banned)
    if ban == BanState.NEWLY_BANNED:
        notices.tell_banned(session, action, owner_id, automatic=True)


# --- 운영자의 제재 ---


async def sanction_scenario(
    session: AsyncSession, operator_id: uuid.UUID, scenario_id: uuid.UUID, reason: str, now: datetime, threshold: int
) -> SanctionResult:
    """
    공개 중인 판을 제재한다. 공개를 내리고, 그 판을 다시 공개하지 못하게 하고, 공개 금지에 닿았는지 본다.

    시나리오가 없으면 AssetNotFoundError, 공개 중인 판이 없으면 SanctionConflictError(NOT_PUBLISHED).
    """
    scenario = await repository.lock_scenario(session, scenario_id)
    if scenario is None:
        raise AssetNotFoundError
    listing = await listings.find_listing(session, scenario_id)
    if listing is None or listing.version_id is None:
        raise SanctionConflictError(SanctionConflict.NOT_PUBLISHED)
    version = await listings.find_version_by_id(session, listing.version_id)
    owner_id = scenario.asset.owner_id

    repository.add_sanction(
        session,
        ScenarioSanction(
            version_id=version.id,
            scenario_id=scenario_id,
            owner_id=owner_id,
            operator_id=operator_id,
            sanctioned_at=now,
            reason=reason,
        ),
    )
    unpublish(listing)
    await session.flush()
    await repository.lock_owner(session, owner_id)
    ban = await ban_if_due(session, owner_id, now, threshold)
    action = build_action(operator_id, ActionKind.SCENARIO_SANCTION, scenario_id, reason, now)
    repository.add_action(session, action)
    await tell_owner(session, action, owner_id, scenario.asset.title, version.number, ban)
    await session.commit()
    log_action(action)
    return SanctionResult(scenario_id, version.number, owner_id, ban != BanState.NOT_BANNED)


async def end_table(
    session: AsyncSession, operator_id: uuid.UUID, table_id: uuid.UUID, reason: str, now: datetime
) -> GameTable:
    """
    운영자가 테이블을 끝낸다. 앉아 있지 않아도 된다. 없으면 TableNotFoundError, 이미 끝났으면 TableConflictError.

    이벤트에는 "운영자가 끝냈다"만 남고 운영자가 누구인지, 사유는 남지 않는다(앉은 사람이 읽는다).
    """
    table = await tables.lock_table(session, table_id)
    if table is None:
        raise TableNotFoundError
    if table.status == TableStatus.ENDED:
        raise TableConflictError(Conflict.ALREADY_ENDED)

    end(table)
    recorder.record(session, table, EventType.TABLE_ENDED, payload={'by': ENDED_BY_OPERATOR})
    action = build_action(operator_id, ActionKind.TABLE_END, table_id, reason, now)
    repository.add_action(session, action)
    ended = await table_service.save(session, table)
    log_action(action)
    return ended


async def ban_publisher(
    session: AsyncSession, operator_id: uuid.UUID, user_id: uuid.UUID, reason: str, now: datetime
) -> PublishingBan:
    """운영자가 한 사람의 공개를 금지한다. 이미 금지 중이면 SanctionConflictError(ALREADY_BANNED)."""
    await repository.lock_owner(session, user_id)
    if is_active(await repository.find_ban(session, user_id)):
        raise SanctionConflictError(SanctionConflict.ALREADY_BANNED)
    ban = await impose_ban(session, user_id, operator_id, reason, now)
    action = build_action(operator_id, ActionKind.PUBLISHING_BAN, user_id, reason, now)
    repository.add_action(session, action)
    await session.flush()
    notices.tell_banned(session, action, user_id, automatic=False)
    await session.commit()
    log_action(action)
    return ban


async def lift_ban(
    session: AsyncSession, operator_id: uuid.UUID, user_id: uuid.UUID, reason: str, now: datetime
) -> PublishingBan:
    """운영자가 공개 금지를 푼다. 금지 중이 아니면 SanctionConflictError(NOT_BANNED). 그 뒤의 제재부터 다시 센다."""
    await repository.lock_owner(session, user_id)
    ban = await repository.find_ban(session, user_id)
    if not is_active(ban):
        raise SanctionConflictError(SanctionConflict.NOT_BANNED)
    ban.lifted_at, ban.lifted_by = now, operator_id
    action = build_action(operator_id, ActionKind.PUBLISHING_UNBAN, user_id, reason, now)
    repository.add_action(session, action)
    await session.flush()
    notices.tell_unbanned(session, action, user_id)
    await session.commit()
    log_action(action)
    return ban
