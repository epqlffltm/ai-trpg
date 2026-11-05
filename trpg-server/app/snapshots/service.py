# trpg-server/app/snapshots/service.py

"""
테이블의 장면 그림 한 장의 길(#983). chat·story 서버의 것과 같은 차례다. 아래의 각 줄이 함수 하나다.

  응답하기 전(실패하면 HTTP 의 오류로 답한다)
    1. begin_snapshot: 앉은 테이블의 그 라운드인지 보고, 그 장면으로 지시를 만들고, 기록(pending)을 저장한다.
       한 테이블에 그리는 중인 것은 하나다(부분 유일 색인). 둘째는 SnapshotBusyError
    2. hold_snapshot: 누른 사람에게 홀드를 건다. 걸리지 않으면 기록을 declined 로 두고 SnapshotDeclinedError
  응답한 뒤(작업 관리자가 돌리는 작업. 사람들은 목록을 다시 읽는다)
    3. draw_snapshot: 그림을 만들고 누른 사람의 그림으로 asset 서버에 맡긴다.
       됐으면 확정할 것, 아니면 돌려줄 것으로 적는다
    4. settle_snapshot: 결제 서버에 확정이나 반환을 맡긴다. 못 했으면 정리 작업(app/snapshots/settler.py)이 마저 한다
  지우기
    - delete_snapshot: 그린 사람이 테이블에서 자기 그림 한 장을 지운다. asset 의 그림을 먼저, 기록을 나중에 지운다.
      돈은 돌려주지 않는다
    - delete_mine: 같은 일을 갤러리에서 한다. 테이블을 나갔거나 지웠어도 자기 그림이면 지운다
  갤러리
    - list_kept: 내가 다 그린 그림들. 테이블을 넘어 최근에 만든 것부터다
  보기
    - list_snapshots: 테이블의 그림들. 앉은 사람 모두가 본다(누가 그렸든)
    - snapshot_image: 그림의 바이트. asset 서버에서 서명만으로 받아 대신 내준다(앉은 사람만)

  - 그림의 지시는 서버의 상태로 만든다(app/snapshots/prompt.py). 그림 모델은 상태를 바꾸지 못한다(그림만 돌려준다)
  - 바깥(공급자, asset, 결제 서버)을 부르는 동안 DB 의 연결을 쥐지 않는다
  - 같은 실패를 저절로 되풀이하지 않는다(사람이 다시 누른다). 실패하면 돈은 돌려준다
  - 누른 사람의 토큰은 그 요청이 맡긴 작업 안에서 asset 에 맡길 때만 쓰고 저장하지 않는다
  - 그리기 시작(홀드가 걸림)과 끝(다 그림, 실패)은 테이블의 스트림에 알린다(scene_snapshot).
    같은 트랜잭션에서 신호를 보내므로 기록이 옮겨진 때에만 나간다.
    청구의 확정·반환은 화면이 볼 것이 바뀌지 않아 알리지 않는다
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ai_core.image_provider import ImageProvider, ImageRequest
from ai_core.provider import ProviderError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.asset_server.client import AssetClient, AssetNotFoundError, AssetUnavailableError, ImageContent
from app.billing.client import Billing
from app.realtime import signals
from app.realtime.signals import Kind, Signal
from app.rounds.models import Round
from app.rounds.service import get_round
from app.snapshots import charging, repository
from app.snapshots.charging import HoldDeclined, Settled
from app.snapshots.models import DUE_STATUSES, SnapshotBilling, SnapshotOutcome, TableSnapshot
from app.snapshots.prompt import snapshot_prompt
from app.snapshots.providers import price_code_of
from app.snapshots.schemas import KeptSnapshotOut, KeptSnapshotPage, SnapshotOut, SnapshotStatus
from app.tables.models import GameTable
from app.tables.service import get_table

logger = logging.getLogger(__name__)

# 그리는 중인 채로 이만큼 지나면 서버가 꺼진 것으로 본다(정리 작업이 실패로 적고 돌려준다). 그리는 상한보다 길다
SNAPSHOT_STALE = timedelta(minutes=10)
# 실패의 까닭(공급자의 것 밖의 것)
ASSET_UNAVAILABLE = 'asset_unavailable'
CANCELLED = 'cancelled'
SERVER_ERROR = 'server_error'
# 작업 관리자의 자리가 다 차서 그리지 못했다
JOBS_FULL = 'jobs_full'


class SnapshotUnavailableError(Exception):
    """장면 그림을 만들지 않는 서버다(SNAPSHOT_PROVIDER 가 off 이거나 키가 없다, 작업의 자리가 없다)."""


class NotDrawableError(Exception):
    """그릴 수 없는 라운드다(장면의 글자가 없다)."""


class SnapshotBusyError(Exception):
    """그 테이블에서 다른 그림을 그리는 중이다."""


class SnapshotNotFoundError(Exception):
    """그림이 없다(다른 테이블의 것, 아직 다 그리지 않은 것, asset 에서 지운 것)."""


class SnapshotSettlingError(Exception):
    """청구를 정리하는 중이라 지우지 못한다(정리 작업이 곧 끝낸다)."""


class SnapshotDeclinedError(Exception):
    """홀드가 걸리지 않았다. code 는 까닭이다(credit_short, gold_required, not_for_sale, billing_unavailable)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SnapshotStart:
    """한 장을 그리는 데 드는 것. 저장한 뒤에는 ORM 객체 대신 이것을 들고 다닌다."""

    snapshot_id: uuid.UUID
    table_id: uuid.UUID
    owner_id: uuid.UUID
    reference: str
    price_code: str
    prompt: str


def hold_reference(snapshot_id: uuid.UUID) -> str:
    """홀드의 이름표. 서술 값의 것(game:…)과 섞이지 않게 img 를 붙인다."""
    return f'game:img:{snapshot_id}'


def require_drawable(round_: Round) -> None:
    """장면의 글자가 있어야 한다. 아니면 NotDrawableError."""
    if not round_.scene.strip():
        raise NotDrawableError


def character_names(table: GameTable) -> list[str]:
    """앉은 사람들의 캐릭터 이름. 이름을 아직 짓지 않은 사람은 뺀다."""
    return [member.character_name for member in table.members if member.character_name]


def new_snapshot(table_id: uuid.UUID, round_number: int, owner_id: uuid.UUID, model: str) -> TableSnapshot:
    """그리기 전의 기록(pending). 아직 저장하지 않는다."""
    snapshot_id = uuid.uuid4()
    return TableSnapshot(
        id=snapshot_id,
        table_id=table_id,
        round_number=round_number,
        owner_id=owner_id,
        model=model,
        reference=hold_reference(snapshot_id),
        price_code=price_code_of(model),
        billing_status=SnapshotBilling.PENDING,
    )


async def saved(session: AsyncSession, snapshot: TableSnapshot) -> None:
    """기록을 저장한다. 그 테이블에 그리는 중인 것이 있으면 되돌리고 SnapshotBusyError."""
    repository.add(session, snapshot)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise SnapshotBusyError from error


async def begin_snapshot(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, table_id: uuid.UUID, number: int, model: str
) -> SnapshotStart:
    """
    그 라운드의 장면 그림을 그릴 기록을 저장하고 지시를 만든다.
    앉지 않은 테이블이면 TableNotFoundError, 라운드가 없으면 RoundNotFoundError,
    그릴 수 없으면 NotDrawableError, 그리는 중이면 SnapshotBusyError.
    """
    async with session_factory() as session:
        table, round_ = await get_round(session, user_id, table_id, number)
        require_drawable(round_)
        prompt = snapshot_prompt(table.title, round_.number, character_names(table), round_.scene)
        snapshot = new_snapshot(table.id, round_.number, user_id, model)
        await saved(session, snapshot)
    return SnapshotStart(
        snapshot_id=snapshot.id,
        table_id=table_id,
        owner_id=user_id,
        reference=snapshot.reference,
        price_code=snapshot.price_code,
        prompt=prompt,
    )


async def announce(session: AsyncSession, table_id: uuid.UUID | None) -> None:
    """테이블의 스트림에 "장면 그림이 바뀌었다"를 보낸다. 커밋될 때 나간다. 테이블을 지웠으면 보내지 않는다."""
    if table_id is not None:
        await signals.publish(session, Signal(table_id=table_id, kind=Kind.SNAPSHOTS))


async def mark(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot_id: uuid.UUID,
    expected: frozenset[SnapshotBilling],
    values: dict[str, object],
    table_id: uuid.UUID | None = None,
) -> bool:
    """청구의 상태를 옮기고 커밋한다. 옮겼으면 True. table_id 를 주면 옮겼을 때 그 테이블에 알린다."""
    async with session_factory() as session:
        moved = await repository.move_billing(session, snapshot_id, expected, values)
        if moved:
            await announce(session, table_id)
        await session.commit()
    return moved


async def hold_snapshot(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, start: SnapshotStart, now: datetime
) -> None:
    """홀드를 건다. 걸리지 않으면 기록을 declined(실패)로 두고 SnapshotDeclinedError."""
    try:
        await charging.place_hold(billing, start.reference, start.owner_id, start.price_code)
    except HoldDeclined as declined:
        values = {
            'billing_status': SnapshotBilling.DECLINED,
            'outcome': SnapshotOutcome.FAILED,
            'error_code': declined.code,
            'finished_at': now,
        }
        await mark(session_factory, start.snapshot_id, frozenset({SnapshotBilling.PENDING}), values)
        raise SnapshotDeclinedError(declined.code) from declined
    await mark(
        session_factory,
        start.snapshot_id,
        frozenset({SnapshotBilling.PENDING}),
        {'billing_status': SnapshotBilling.HELD},
        start.table_id,
    )


def ready_values(image_id: uuid.UUID, input_tokens: int | None, output_tokens: int | None, now: datetime) -> dict:
    """다 그리고 맡겼을 때 적을 것. 확정할 차례다."""
    return {
        'billing_status': SnapshotBilling.CAPTURE_DUE,
        'outcome': SnapshotOutcome.READY,
        'image_id': image_id,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'finished_at': now,
    }


def failed_values(code: str, now: datetime) -> dict:
    """실패했을 때 적을 것. 돌려줄 차례다."""
    return {
        'billing_status': SnapshotBilling.RELEASE_DUE,
        'outcome': SnapshotOutcome.FAILED,
        'error_code': code,
        'finished_at': now,
    }


async def draw_and_keep(provider: ImageProvider, asset: AssetClient, token: str, start: SnapshotStart, now: datetime):
    """그림을 만들고 누른 사람의 그림으로 asset 에 맡긴다. 적을 것을 돌려준다(실패해도 올리지 않는다. 멈춤은 올린다)."""
    try:
        image = await provider.generate(ImageRequest(prompt=start.prompt))
        image_id = await asset.keep_image(token, image.data)
    except ProviderError as error:
        return failed_values(str(error), now)
    except AssetUnavailableError:
        return failed_values(ASSET_UNAVAILABLE, now)
    return ready_values(image_id, image.input_tokens, image.output_tokens, now)


async def finish(
    session_factory: async_sessionmaker[AsyncSession],
    billing: Billing,
    start: SnapshotStart,
    values: dict,
    now: datetime,
) -> None:
    """그린 결과를 적고 테이블에 알린다. 확정이나 반환할 차례가 됐으면 바로 맡긴다."""
    snapshot_id = start.snapshot_id
    await mark(session_factory, snapshot_id, frozenset({SnapshotBilling.HELD}), values, start.table_id)
    async with session_factory() as session:
        snapshot = await repository.get(session, snapshot_id)
    if snapshot is not None and snapshot.billing_status in DUE_STATUSES:
        await settle_snapshot(session_factory, billing, snapshot, now)


async def draw_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    billing: Billing,
    provider: ImageProvider,
    asset: AssetClient,
    token: str,
    start: SnapshotStart,
    clock: Callable[[], datetime],
) -> None:
    """
    그림을 만들어 맡기고 결과를 적은 뒤 확정이나 반환을 맡긴다. 작업 관리자가 돌린다.
    서버가 꺼지며 멈추면(취소) 실패로 적고 돌려줄 것으로 둔다(다음에 뜬 서버의 정리 작업이 맡긴다).
    """
    try:
        values = await draw_and_keep(provider, asset, token, start, clock())
    except asyncio.CancelledError:
        values = failed_values(CANCELLED, clock())
        await mark(session_factory, start.snapshot_id, frozenset({SnapshotBilling.HELD}), values, start.table_id)
        raise
    except Exception:
        logger.exception('장면 그림을 만들지 못했습니다', extra={'snapshot_id': str(start.snapshot_id)})
        values = failed_values(SERVER_ERROR, clock())
    await finish(session_factory, billing, start, values, clock())


async def refuse_snapshot(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, start: SnapshotStart, now: datetime
) -> None:
    """작업의 자리가 없어 그리지 못했다. 실패로 적고 돌려준다."""
    await finish(session_factory, billing, start, failed_values(JOBS_FULL, now), now)


def settled_values(snapshot: TableSnapshot, capture: bool, result: charging.Settlement, now: datetime) -> dict:
    """맡겨 본 결과로 적을 것. 못 맡겼으면 다음에 부를 때와 횟수다."""
    if result.result == Settled.DONE:
        return {'billing_status': SnapshotBilling.CAPTURED if capture else SnapshotBilling.RELEASED}
    if result.result == Settled.FAILED:
        return {'billing_status': SnapshotBilling.FAILED, 'error_code': result.error_code}
    attempts = snapshot.settle_attempts + 1
    return {'settle_attempts': attempts, 'next_settle_at': now + charging.retry_delay(attempts)}


async def settle_snapshot(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, snapshot: TableSnapshot, now: datetime
) -> None:
    """확정할 것은 확정하고 돌려줄 것은 돌려준다. 결과를 적는다."""
    capture = snapshot.billing_status == SnapshotBilling.CAPTURE_DUE
    result = await charging.settle(billing, snapshot.reference, capture)
    expected = frozenset({SnapshotBilling(snapshot.billing_status)})
    await mark(session_factory, snapshot.id, expected, settled_values(snapshot, capture, result, now))


def status_of(snapshot: TableSnapshot) -> SnapshotStatus:
    """화면의 상태. 끝나지 않았으면 그리는 중이다."""
    if snapshot.outcome == SnapshotOutcome.READY:
        return SnapshotStatus.READY
    if snapshot.outcome == SnapshotOutcome.FAILED:
        return SnapshotStatus.FAILED
    return SnapshotStatus.DRAWING


def snapshot_out(snapshot: TableSnapshot, viewer_id: uuid.UUID) -> SnapshotOut:
    """응답의 모양. 실패의 까닭은 그린 사람에게만 싣는다(크레딧이 모자란 것은 그 사람의 일이다)."""
    failed = snapshot.outcome == SnapshotOutcome.FAILED
    by_me = snapshot.owner_id == viewer_id
    return SnapshotOut(
        id=snapshot.id,
        round_number=snapshot.round_number,
        status=status_of(snapshot),
        by_me=by_me,
        code=snapshot.error_code if failed and by_me else None,
        created_at=snapshot.created_at,
    )


async def list_snapshots(session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID) -> list[SnapshotOut]:
    """그 테이블의 그림들. 앉지 않은 테이블이면 TableNotFoundError."""
    table = await get_table(session, user_id, table_id)
    return [snapshot_out(snapshot, user_id) for snapshot in await repository.of_table(session, table.id)]


async def snapshot_by_id(
    session_factory: async_sessionmaker[AsyncSession], snapshot_id: uuid.UUID, viewer_id: uuid.UUID
) -> SnapshotOut:
    """한 장의 응답(방금 저장한 것)."""
    async with session_factory() as session:
        snapshot = await repository.get(session, snapshot_id)
    if snapshot is None:
        raise SnapshotNotFoundError
    return snapshot_out(snapshot, viewer_id)


async def kept_image_id(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, table_id: uuid.UUID, snapshot_id: uuid.UUID
) -> uuid.UUID:
    """앉은 테이블의 다 그린 그림의 asset id. 앉지 않았으면 TableNotFoundError, 그림이 없으면 SnapshotNotFoundError."""
    async with session_factory() as session:
        table = await get_table(session, user_id, table_id)
        snapshot = await repository.find_in_table(session, table.id, snapshot_id)
    if snapshot is None or snapshot.outcome != SnapshotOutcome.READY or snapshot.image_id is None:
        raise SnapshotNotFoundError
    return snapshot.image_id


async def snapshot_image(
    session_factory: async_sessionmaker[AsyncSession],
    asset: AssetClient,
    user_id: uuid.UUID,
    table_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> ImageContent:
    """
    그림의 바이트. 앉은 사람만 받는다. asset 서버에서 서명만으로 받아 대신 내준다.
    asset 을 부르는 동안 DB 의 연결을 쥐지 않는다. asset 에서 지웠으면 SnapshotNotFoundError,
    asset 이 안 되면 AssetUnavailableError.
    """
    image_id = await kept_image_id(session_factory, user_id, table_id, snapshot_id)
    try:
        return await asset.fetch_kept(image_id)
    except AssetNotFoundError as error:
        raise SnapshotNotFoundError from error


# 청구가 끝난 상태. 이 상태의 그림만 지운다(끝나지 않은 청구의 기록을 지우면 정리 작업이 맡기지 못한다)
SETTLED_STATUSES = frozenset(
    {SnapshotBilling.CAPTURED, SnapshotBilling.RELEASED, SnapshotBilling.DECLINED, SnapshotBilling.FAILED}
)


def require_removable(snapshot: TableSnapshot) -> None:
    """지울 수 있는 그림인지 본다. 그리는 중이면 SnapshotBusyError, 청구를 정리하는 중이면 SnapshotSettlingError."""
    if snapshot.outcome is None:
        raise SnapshotBusyError
    if snapshot.billing_status not in SETTLED_STATUSES:
        raise SnapshotSettlingError


async def find_removable(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, table_id: uuid.UUID, snapshot_id: uuid.UUID
) -> TableSnapshot:
    """
    지울 그림 한 장. 앉지 않은 테이블이면 TableNotFoundError.
    그 테이블의 그림이 아니거나 남이 그린 것이면 SnapshotNotFoundError(남의 그림은 지우지 못한다).
    지울 수 없으면 require_removable 의 오류.
    """
    async with session_factory() as session:
        table = await get_table(session, user_id, table_id)
        snapshot = await repository.find_in_table(session, table.id, snapshot_id)
    if snapshot is None or snapshot.owner_id != user_id:
        raise SnapshotNotFoundError
    require_removable(snapshot)
    return snapshot


async def delete_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    asset: AssetClient,
    user_id: uuid.UUID,
    token: str,
    table_id: uuid.UUID,
    snapshot_id: uuid.UUID,
) -> None:
    """
    내 그림 한 장을 지운다. asset 의 그림을 먼저 지우고(그린 사람의 토큰으로) 기록을 지운 뒤 테이블에 알린다.
    돈은 돌려주지 않는다(이미 그린 그림이다). asset 을 부르는 동안 DB 의 연결을 쥐지 않는다.
    asset 이 안 되면 AssetUnavailableError 이고 기록은 남는다(다시 지우면 asset 은 없는 그림도 204 로 답한다).
    """
    snapshot = await find_removable(session_factory, user_id, table_id, snapshot_id)
    await remove(session_factory, asset, token, snapshot)


async def remove(
    session_factory: async_sessionmaker[AsyncSession], asset: AssetClient, token: str, snapshot: TableSnapshot
) -> None:
    """
    지울 수 있다고 본 그림 한 장을 지운다. asset 의 그림을 먼저(그린 사람의 토큰으로), 기록을 나중에 지우고
    테이블에 알린다.
    asset 을 부르는 동안 DB 의 연결을 쥐지 않는다. asset 이 안 되면 AssetUnavailableError 이고 기록은 남는다.
    """
    if snapshot.image_id is not None:
        await asset.discard_image(token, snapshot.image_id)
    async with session_factory() as session:
        if await repository.remove_settled(session, snapshot.id, SETTLED_STATUSES):
            await announce(session, snapshot.table_id)
        await session.commit()


async def delete_mine(
    session_factory: async_sessionmaker[AsyncSession],
    asset: AssetClient,
    user_id: uuid.UUID,
    token: str,
    snapshot_id: uuid.UUID,
) -> None:
    """
    갤러리에서 내 그림 한 장을 지운다. 테이블을 보지 않는다(나갔거나 지운 테이블의 그림도 내 그림이다).
    남의 것이나 없는 것이면 SnapshotNotFoundError, 지울 수 없으면 require_removable 의 오류.
    """
    async with session_factory() as session:
        snapshot = await repository.find_mine(session, user_id, snapshot_id)
    if snapshot is None:
        raise SnapshotNotFoundError
    require_removable(snapshot)
    await remove(session_factory, asset, token, snapshot)


def kept_out(snapshot: TableSnapshot, table_title: str | None) -> KeptSnapshotOut:
    """갤러리의 한 장의 응답."""
    return KeptSnapshotOut(
        id=snapshot.id,
        image_id=snapshot.image_id,
        table_id=snapshot.table_id,
        table_title=table_title,
        round_number=snapshot.round_number,
        created_at=snapshot.created_at,
    )


async def list_kept(session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int) -> KeptSnapshotPage:
    """내가 다 그린 그림들(갤러리). 테이블을 넘어 최근에 만든 것부터다."""
    rows, total = await repository.list_kept(session, user_id, limit, offset)
    return KeptSnapshotPage(items=[kept_out(*row) for row in rows], total=total)
