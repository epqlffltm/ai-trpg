# story-server/app/snapshots/service.py

"""
장면 그림 한 장의 길(#983). chat 의 것(chat-server/app/snapshots/service.py)과 같은 길이다.
아래 차례의 각 줄이 함수 하나다.

  응답하기 전(실패하면 HTTP 의 오류로 답한다)
    1. begin_snapshot: 모델의 답인지 보고, 그 답까지의 가지의 엔진 상태로 지시를 만들고, 기록(pending)을 저장한다.
       한 세션에 그리는 중인 것은 하나다(부분 유일 색인). 둘째는 SnapshotBusyError
    2. hold_snapshot: 홀드를 건다. 걸리지 않으면 기록을 declined 로 두고 SnapshotDeclinedError
  응답한 뒤(따로 도는 작업. 사람은 목록을 다시 읽는다)
    3. draw_snapshot: 그림을 만들고 asset 서버에 맡긴다. 됐으면 확정할 것, 실패하거나 거절됐으면 돌려줄 것으로 적는다
    4. settle_snapshot: 결제 서버에 확정이나 반환을 맡긴다. 못 했으면 정리 작업(app/snapshots/settler.py)이 마저 한다

  - 그림의 지시는 엔진의 상태로 만든다(app/snapshots/prompt.py). 그림 모델은 상태를 바꾸지 못한다(그림만 돌려준다)
  - 참고 그림(인물의 그림으로 얼굴 맞추기)은 1 에서 고르고 3 에서 asset 에서 받아 넘긴다(snapshots/references.py)
  - 바깥(공급자, asset, 결제 서버)을 부르는 동안 DB 의 연결을 쥐지 않는다
  - 같은 실패를 저절로 되풀이하지 않는다(사람이 다시 누른다). 실패하면 돈은 돌려준다
  - 사람의 토큰은 그 요청이 띄운 작업 안에서 asset 을 부를 때(참고 그림 받기, 맡기기)만 쓰고 저장하지 않는다
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

from app.assets.client import AssetClient, AssetUnavailableError
from app.billing.client import Billing
from app.conversations import repository as conversations
from app.conversations.models import Message, Role
from app.conversations.service import MessageNotFoundError, get_conversation
from app.core.dependencies import Viewer
from app.ratings import allowed_ratings
from app.snapshots import repository
from app.snapshots.models import Snapshot, SnapshotOutcome
from app.snapshots.prompt import snapshot_prompt, with_references
from app.snapshots.providers import price_code_of
from app.snapshots.references import ReferenceTarget, cast_targets, fetch_references
from app.snapshots.schemas import SnapshotOut, SnapshotStatus
from app.turns import charging
from app.turns.charging import HoldDeclined, Settled
from app.turns.models import DUE_STATUSES, BillingStatus
from app.turns.service import branch_at

logger = logging.getLogger(__name__)

# 그리는 중인 채로 이만큼 지나면 서버가 꺼진 것으로 본다(정리 작업이 실패로 적고 돌려준다). 그리는 상한보다 길다
SNAPSHOT_STALE = timedelta(minutes=10)
# 실패의 까닭(공급자의 것 밖의 것)
ASSET_UNAVAILABLE = 'asset_unavailable'
CANCELLED = 'cancelled'
SERVER_ERROR = 'server_error'


class SnapshotUnavailableError(Exception):
    """장면 그림을 만들지 않는 서버다(SNAPSHOT_PROVIDER 가 off 이거나 키가 없다)."""


class NotDrawableError(Exception):
    """그릴 수 없는 말이다(모델의 답이 아니다, 말 조각이 없다)."""


class SnapshotBusyError(Exception):
    """그 세션에서 다른 그림을 그리는 중이다."""


class SnapshotDeclinedError(Exception):
    """홀드가 걸리지 않았다. code 는 까닭이다(credit_short, gold_required, model_unavailable, billing_unavailable)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SnapshotStart:
    """한 장을 그리는 데 드는 것. 저장한 뒤에는 ORM 객체 대신 이것을 들고 다닌다."""

    snapshot_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    owner_id: uuid.UUID
    reference: str
    price_code: str
    prompt: str
    references: tuple[ReferenceTarget, ...] = ()


def hold_reference(snapshot_id: uuid.UUID) -> str:
    """홀드의 이름표. 말 한 번의 것(story:gen:)과 섞이지 않는다."""
    return f'story:img:{snapshot_id}'


def require_drawable(target: Message) -> None:
    """말 조각이 있는 모델의 답이어야 한다. 아니면 NotDrawableError."""
    if target.role != Role.ASSISTANT or not target.segments:
        raise NotDrawableError


def asked_before(path: list[Message]) -> str | None:
    """그 답이 답한 사람의 말. 답의 바로 앞이 사람의 말이 아니면 None."""
    return path[-2].content if len(path) >= 2 and path[-2].role == Role.USER else None


def new_snapshot(start_conversation: uuid.UUID, target: Message, owner_id: uuid.UUID, model: str) -> Snapshot:
    """그리기 전의 기록(pending). 아직 저장하지 않는다."""
    snapshot_id = uuid.uuid4()
    return Snapshot(
        id=snapshot_id,
        conversation_id=start_conversation,
        message_id=target.id,
        owner_id=owner_id,
        model=model,
        reference=hold_reference(snapshot_id),
        price_code=price_code_of(model),
        billing_status=BillingStatus.PENDING,
    )


async def saved(session: AsyncSession, snapshot: Snapshot) -> None:
    """기록을 저장한다. 그 세션에 그리는 중인 것이 있으면 되돌리고 SnapshotBusyError."""
    repository.add(session, snapshot)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise SnapshotBusyError from error


async def begin_snapshot(
    session_factory: async_sessionmaker[AsyncSession], viewer: Viewer, message_id: uuid.UUID, model: str
) -> SnapshotStart:
    """
    그 답의 장면 그림을 그릴 기록을 저장하고 지시를 만든다.
    말이 없거나 남의 것이면 MessageNotFoundError, 그릴 수 없는 말이면 NotDrawableError, 그리는 중이면 SnapshotBusyError.
    """
    async with session_factory() as session:
        target = await conversations.find_visible_message(
            session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
        )
        if target is None:
            raise MessageNotFoundError
        require_drawable(target)
        conversation, imported = await get_conversation(session, viewer, target.conversation_id)
        branch = await branch_at(session, conversation, imported, target.id)
        prompt = snapshot_prompt(
            branch.briefing,
            branch.world,
            branch.state,
            tuple(target.cast or ()),
            list(target.segments or ()),
            asked_before(branch.path),
        )
        references = cast_targets(imported.document, tuple(target.cast or ()))
        snapshot = new_snapshot(conversation.id, target, viewer.claims.user_id, model)
        await saved(session, snapshot)
    return SnapshotStart(
        snapshot_id=snapshot.id,
        conversation_id=conversation.id,
        message_id=target.id,
        owner_id=viewer.claims.user_id,
        reference=snapshot.reference,
        price_code=snapshot.price_code,
        prompt=prompt,
        references=references,
    )


async def mark(
    session_factory: async_sessionmaker[AsyncSession],
    snapshot_id: uuid.UUID,
    expected: frozenset[BillingStatus],
    values: dict[str, object],
) -> bool:
    """청구의 상태를 옮기고 커밋한다. 옮겼으면 True."""
    async with session_factory() as session:
        moved = await repository.move_billing(session, snapshot_id, expected, values)
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
            'billing_status': BillingStatus.DECLINED,
            'outcome': SnapshotOutcome.FAILED,
            'error_code': declined.code,
            'finished_at': now,
        }
        await mark(session_factory, start.snapshot_id, frozenset({BillingStatus.PENDING}), values)
        raise SnapshotDeclinedError(declined.code) from declined
    await mark(
        session_factory, start.snapshot_id, frozenset({BillingStatus.PENDING}), {'billing_status': BillingStatus.HELD}
    )


def ready_values(image_id: uuid.UUID, input_tokens: int | None, output_tokens: int | None, now: datetime) -> dict:
    """다 그리고 맡겼을 때 적을 것. 확정할 차례다."""
    return {
        'billing_status': BillingStatus.CAPTURE_DUE,
        'outcome': SnapshotOutcome.READY,
        'image_id': image_id,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'finished_at': now,
    }


def failed_values(code: str, now: datetime) -> dict:
    """실패했을 때 적을 것. 돌려줄 차례다."""
    return {
        'billing_status': BillingStatus.RELEASE_DUE,
        'outcome': SnapshotOutcome.FAILED,
        'error_code': code,
        'finished_at': now,
    }


async def draw_and_keep(provider: ImageProvider, asset: AssetClient, token: str, start: SnapshotStart, now: datetime):
    """참고 그림을 받아 그림을 만들고 asset 에 맡긴다. 적을 것을 돌려준다(실패해도 올리지 않는다. 멈춤은 올린다)."""
    try:
        fetched = await fetch_references(provider, asset, token, start.references)
        prompt = with_references(start.prompt, [target.name for target, _ in fetched])
        image = await provider.generate(ImageRequest(prompt=prompt, references=tuple(image for _, image in fetched)))
        image_id = await asset.keep_image(token, image.data)
    except ProviderError as error:
        return failed_values(str(error), now)
    except AssetUnavailableError:
        return failed_values(ASSET_UNAVAILABLE, now)
    return ready_values(image_id, image.input_tokens, image.output_tokens, now)


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
    그림을 만들어 맡기고 결과를 적은 뒤 확정이나 반환을 맡긴다. 따로 도는 작업이다.
    서버가 꺼지며 멈추면(취소) 실패로 적고 돌려줄 것으로 둔다(다음에 뜬 서버의 정리 작업이 맡긴다).
    """
    try:
        values = await draw_and_keep(provider, asset, token, start, clock())
    except asyncio.CancelledError:
        await mark(
            session_factory, start.snapshot_id, frozenset({BillingStatus.HELD}), failed_values(CANCELLED, clock())
        )
        raise
    except Exception:
        logger.exception('장면 그림을 만들지 못했습니다', extra={'snapshot_id': str(start.snapshot_id)})
        values = failed_values(SERVER_ERROR, clock())
    await mark(session_factory, start.snapshot_id, frozenset({BillingStatus.HELD}), values)
    async with session_factory() as session:
        snapshot = await repository.get(session, start.snapshot_id)
    if snapshot is not None and snapshot.billing_status in DUE_STATUSES:
        await settle_snapshot(session_factory, billing, snapshot, clock())


def settled_values(snapshot: Snapshot, capture: bool, result: charging.Settlement, now: datetime) -> dict:
    """맡겨 본 결과로 적을 것. 못 맡겼으면 다음에 부를 때와 횟수다."""
    if result.result == Settled.DONE:
        return {'billing_status': BillingStatus.CAPTURED if capture else BillingStatus.RELEASED}
    if result.result == Settled.FAILED:
        return {'billing_status': BillingStatus.FAILED, 'error_code': result.error_code}
    attempts = snapshot.settle_attempts + 1
    return {'settle_attempts': attempts, 'next_settle_at': now + charging.retry_delay(attempts)}


async def settle_snapshot(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, snapshot: Snapshot, now: datetime
) -> None:
    """확정할 것은 확정하고 돌려줄 것은 돌려준다. 결과를 적는다."""
    capture = snapshot.billing_status == BillingStatus.CAPTURE_DUE
    result = await charging.settle(billing, snapshot.reference, capture)
    expected = frozenset({BillingStatus(snapshot.billing_status)})
    await mark(session_factory, snapshot.id, expected, settled_values(snapshot, capture, result, now))


def status_of(snapshot: Snapshot) -> SnapshotStatus:
    """화면의 상태. 끝나지 않았으면 그리는 중이다."""
    if snapshot.outcome == SnapshotOutcome.READY:
        return SnapshotStatus.READY
    if snapshot.outcome == SnapshotOutcome.FAILED:
        return SnapshotStatus.FAILED
    return SnapshotStatus.DRAWING


def snapshot_out(snapshot: Snapshot) -> SnapshotOut:
    """응답의 모양."""
    return SnapshotOut(
        id=snapshot.id,
        message_id=snapshot.message_id,
        status=status_of(snapshot),
        image_id=snapshot.image_id,
        code=snapshot.error_code if snapshot.outcome == SnapshotOutcome.FAILED else None,
        created_at=snapshot.created_at,
    )


async def list_snapshots(session: AsyncSession, viewer: Viewer, conversation_id: uuid.UUID) -> list[SnapshotOut]:
    """그 세션의 그림들. 남의 세션이면 ConversationNotFoundError."""
    conversation, _ = await get_conversation(session, viewer, conversation_id)
    return [snapshot_out(snapshot) for snapshot in await repository.of_conversation(session, conversation.id)]


async def snapshot_by_id(session_factory: async_sessionmaker[AsyncSession], snapshot_id: uuid.UUID) -> SnapshotOut:
    """한 장의 응답(방금 저장한 것)."""
    async with session_factory() as session:
        snapshot = await repository.get(session, snapshot_id)
    if snapshot is None:
        raise MessageNotFoundError
    return snapshot_out(snapshot)


async def discard_images(
    session_factory: async_sessionmaker[AsyncSession], asset: AssetClient, viewer: Viewer, conversation_id: uuid.UUID
) -> None:
    """
    지운 세션의 그림을 asset 에서 지운다. 못 지운 것은 로그만 남긴다(주인만 보는 그림이라 남아도 남에게 보이지 않는다).
    asset 을 부르는 동안 DB 의 연결을 쥐지 않는다.
    """
    async with session_factory() as session:
        image_ids = await repository.kept_images(session, conversation_id)
    for image_id in image_ids:
        try:
            await asset.discard_image(viewer.token, image_id)
        except AssetUnavailableError:
            logger.warning('지운 세션의 장면 그림을 지우지 못했습니다', extra={'image_id': str(image_id)})
