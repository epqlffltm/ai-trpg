# story-server/app/turns/service.py

"""
말 한 번(docs/architecture/story.md 의 "한 번의 말").
chat 의 말 한 번(chat-server/app/turns/service.py)과 같은 차례이고,
다른 것은 답이 장면의 인물들과 서술의 말 조각이라는 것이다. 아래 차례의 각 줄이 함수 하나다.

  응답을 시작하기 전(실패하면 HTTP 의 오류로 답한다)
    1. begin_turn: 세션과 모델을 보고, 차례를 잡고(한 세션 한 생성), 사람의 말과 기록(pending)을 한 트랜잭션에 저장한다.
       가지의 끝의 상태로 장면의 인물을 정하고(app/engine/scene.py) 모델에 보낼 메시지를 만든다(app/turns/prompt.py)
    2. route_turn: 모델을 부를 provider 를 고른다. 키가 없거나 쓸 수 없는 모델이면 거절한다
    3. hold_turn: 홀드를 건다. 걸리지 않으면(모자람, 팔지 않음, 결제 서버가 죽음) 거절한다
       거절되면 decline_turn 이 차례를 놓고 기록을 declined 로 둔다. 사람의 말은 남는다
  응답을 시작한 뒤(따로 도는 작업. 사람이 끊어도 끝까지 돈다)
    4. call_model: 모델을 부르고, 받는 대로 말 조각으로 잘라 흘려보낸다(app/turns/segments.py)
    5. save_result: 받은 만큼 답을 저장하고 차례를 놓는다.
       다 받았으면 complete, 길이에서 잘렸거나 도중에 끊겼으면 partial. 남은 조각이 없으면 답을 저장하지 않는다
    6. settle_turn: 답이 있으면 확정, 없으면 반환한다.
       결제 서버가 받지 못하면 정리 작업이 마저 한다(app/turns/settler.py)

모델은 상태를 바꾸지 않는다. 말은 상태를 바꾸지 않으므로 답에는 상태를 붙이지 않는다(가지의 끝의 상태가 그대로다).
DB 접근, 바깥 호출(공급자, 결제 서버), 응답 만들기를 한 함수에 섞지 않는다. 바깥을 부르는 동안 DB 의 연결을 쥐지 않는다.
같은 실패를 저절로 되풀이하지 않는다(사람이 다시 보낸다). 다른 모델로 넘어가지 않는다.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from ai_core.costs import charge_of
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError
from ai_core.routing import MODEL_UNAVAILABLE as ROUTE_MODEL_UNAVAILABLE
from ai_core.routing import Route
from conversation_core.relay import Relay
from conversation_core.window import Turn, select_window
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.client import Billing
from app.billing.prices import story_code
from app.catalog import repository as catalog
from app.catalog.choice import is_choosable
from app.catalog.models import AiModel
from app.conversations import repository as conversations
from app.conversations.models import Conversation, ImportedWorld, Message, MessageStatus, Role
from app.conversations.service import (
    GENERATION_STALE,
    ConversationBusyError,
    ModelUnavailableError,
    get_conversation,
)
from app.core.dependencies import Viewer
from app.engine.endings import is_over
from app.engine.scene import scene_cast
from app.engine.state import StoryState
from app.engine.world import AfterEnding, Scene, World, read_world
from app.ratings import Rating
from app.turns import charging, repository
from app.turns.briefing import Briefing, read_briefing
from app.turns.charging import HoldDeclined, Settled, Settlement
from app.turns.frames import delta_frame, done_frame, failed_frame, segment_frame
from app.turns.models import DUE_STATUSES, BillingStatus, Generation, Outcome
from app.turns.prompt import build_messages, render_card, scene_card
from app.turns.providers import Router
from app.turns.segments import (
    Segment,
    SegmentStart,
    SegmentText,
    SpeakerSplitter,
    merge_events,
    render_segments,
    segment_dicts,
    speaker_labels,
)
from app.turns.states import state_on_path
from app.turns.values import PromptOptions, SavedMessage, TurnResult, TurnStart

logger = logging.getLogger(__name__)

# 공급자를 부르지 못한 까닭(키가 없다, 부르는 코드가 없다)의 이름. 사람에게는 잠시 뒤에 다시 하라고 알린다
PROVIDER_UNAVAILABLE = 'provider_unavailable'
# 서버가 꺼지며 멈춘 생성, 예상하지 못한 오류, 남은 조각이 없는 답의 까닭
CANCELLED = 'cancelled'
SERVER_ERROR = 'server_error'
EMPTY = 'empty'


class ModelRequiredError(Exception):
    """세션에 모델이 없다. 먼저 고른다(409)."""


class SessionEndedError(Exception):
    """엔딩을 본 세션이고 세계관이 끝(읽기만)을 골랐다. 말을 받지 않는다(409)."""


class TurnDeclinedError(Exception):
    """
    사람의 말은 저장했지만 답을 쓰지 않는다. code 는 까닭(credit_short, model_unavailable …), message_id 는 저장한
    말이다.
    """

    def __init__(self, code: str, message_id: uuid.UUID) -> None:
        super().__init__(code)
        self.code = code
        self.message_id = message_id


@dataclass
class Collector:
    """
    모델이 흘려 주는 글을 말 조각으로 자르면서 응답으로 넘긴다. 도중에 끊겨도 받은 만큼을 안다.
    장면에 없는 인물의 줄은 넘기지 않는다(app/turns/segments.py).
    """

    relay: Relay
    splitter: SpeakerSplitter
    finished: bool = field(default=False)

    def __call__(self, piece: str) -> None:
        self.push(self.splitter.feed(piece))

    def push(self, events: list[SegmentStart | SegmentText]) -> None:
        """잘린 것들을 응답으로. 잇닿은 글은 하나로 묶어 보낸다."""
        for event in merge_events(events):
            if isinstance(event, SegmentStart):
                self.relay.push(segment_frame(event.speaker))
            else:
                self.relay.push(delta_frame(event.text))

    def finish(self) -> tuple[tuple[Segment, ...], int]:
        """끝났다. 남은 줄을 마저 흘리고, 지금까지의 조각과 버린 줄의 수를 돌려준다. 여러 번 불러도 한 번만 끝낸다."""
        if not self.finished:
            self.finished = True
            self.push(self.splitter.finish())
        return self.splitter.segments(), self.splitter.dropped


def collector_for(start: TurnStart, relay: Relay) -> Collector:
    """말 한 번의 Collector. 장면의 인물의 표식만 받는다."""
    return Collector(relay, SpeakerSplitter(start.labels))


# --- 만들기. DB 와 바깥을 모른다 ---


def saved(message: Message) -> SavedMessage:
    """저장한 말을 세션과 떨어진 값으로."""
    return SavedMessage(
        id=message.id,
        parent_id=message.parent_id,
        role=message.role,
        content=message.content,
        status=message.status,
        created_at=message.created_at,
        segments=tuple(message.segments or ()),
        cast=tuple(message.cast or ()),
    )


def require_model(conversation: Conversation, model: AiModel | None, rating: Rating, now: datetime) -> str:
    """세션의 모델의 이름표. 고르지 않았으면 ModelRequiredError, 이 세션에 쓸 수 없으면 ModelUnavailableError."""
    if conversation.model_slug is None:
        raise ModelRequiredError
    if model is None or not is_choosable(model, rating, now.date()):
        raise ModelUnavailableError
    return conversation.model_slug


def require_open(world: World, state: StoryState) -> None:
    """엔딩을 본 세션이고 세계관이 끝(읽기만)을 골랐으면 SessionEndedError. 후일담이면 말을 받는다."""
    if is_over(state) and world.after_ending == AfterEnding.END:
        raise SessionEndedError


def waiting_scene(world: World, state: StoryState) -> Scene | None:
    """선택지를 고르기를 기다리는 이벤트의 장면 지시. 없으면 None. 그 장면이 부른 인물이 장면에 들어온다."""
    event = world.event(state.choosing) if state.choosing is not None else None
    return event.scene if event is not None else None


def scene_now(world: World, state: StoryState) -> tuple[list[str], str]:
    """지금의 장면의 인물과 장면 지시의 글. 기다리는 이벤트가 없으면 장면 지시는 빈 글이다."""
    scene = waiting_scene(world, state)
    called = scene.cast if scene is not None else ()
    return scene_cast(world, state, called), scene.text if scene is not None else ''


def prompt_for(
    briefing: Briefing, world: World, state: StoryState, cast: list[str], event: str, path: list[Message], chars: int
) -> list[ChatMessage]:
    """모델에 보낼 메시지. 카드와, 지금 가지의 말들 가운데 chars 글자 안에 드는 최근 것들이다."""
    card = render_card(briefing, scene_card(briefing, world, state, cast, event))
    turns = [Turn(message.role, message.content) for message in path]
    return build_messages(card, select_window(turns, chars))


def labels_for(briefing: Briefing, cast: list[str]) -> dict[str, str]:
    """장면의 인물들의 표식의 이름(id 와 이름) → 인물의 id."""
    return speaker_labels((cast_id, briefing.cast_name(cast_id)) for cast_id in cast)


def user_message(
    conversation: Conversation, parent_id: uuid.UUID | None, content: str, now: datetime, role: Role = Role.USER
) -> Message:
    """사람의 말. parent_id(보통은 지금 가지의 끝) 아래에 붙는다. 아직 저장하지 않는다."""
    return Message(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        parent_id=parent_id,
        role=role,
        content=content,
        status=MessageStatus.COMPLETE,
        segments=[],
        cast=[],
        created_at=now,
    )


def new_generation(conversation: Conversation, owner_id: uuid.UUID, parent_id: uuid.UUID, slug: str) -> Generation:
    """기록(pending). 이름표와 가격표 이름을 정한다. 아직 저장하지 않는다."""
    generation_id = uuid.uuid4()
    return Generation(
        id=generation_id,
        conversation_id=conversation.id,
        owner_id=owner_id,
        parent_id=parent_id,
        model_slug=slug,
        reference=charging.hold_reference(generation_id),
        price_code=story_code(slug),
        billing_status=BillingStatus.PENDING,
        settle_attempts=0,
        dropped_segments=0,
    )


def result_of(completion: Completion, route: Route, segments: tuple[Segment, ...], dropped: int) -> TurnResult:
    """
    다 받은 답. segments 는 흘려보내며 자른 조각이다. 남은 조각이 없으면(모두 장면 밖의 인물이었어도) failed 다.
    길이 상한에서 잘렸으면 partial 이다. 원가는 그날의 단가로 센다.
    """
    cost, _ = charge_of(completion, route.price)
    usage = {'input_tokens': completion.input_tokens, 'output_tokens': completion.output_tokens, 'cost_usd': cost}
    if not segments:
        return TurnResult(segments=(), outcome=Outcome.FAILED, error_code=EMPTY, dropped=dropped, **usage)
    outcome = Outcome.PARTIAL if completion.truncated else Outcome.COMPLETE
    return TurnResult(segments=segments, outcome=outcome, dropped=dropped, **usage)


def failure_of(segments: tuple[Segment, ...], dropped: int, code: str) -> TurnResult:
    """도중에 실패했다. 받은 조각이 있으면 partial(그만큼 저장하고 청구한다), 없으면 failed."""
    outcome = Outcome.PARTIAL if segments else Outcome.FAILED
    return TurnResult(segments=segments, outcome=outcome, error_code=code, dropped=dropped)


def answer_of(start: TurnStart, result: TurnResult, now: datetime) -> Message | None:
    """저장할 답. 조각이 없으면 None. 그때의 장면의 인물을 함께 적는다. 아직 저장하지 않는다."""
    if not result.segments:
        return None
    return Message(
        id=uuid.uuid4(),
        conversation_id=start.conversation_id,
        parent_id=start.user_message.id,
        role=Role.ASSISTANT,
        content=render_segments(result.segments),
        status=MessageStatus.PARTIAL if result.outcome == Outcome.PARTIAL else MessageStatus.COMPLETE,
        segments=segment_dicts(result.segments),
        cast=list(start.cast),
        created_at=now,
    )


def finished_values(result: TurnResult, answer_id: uuid.UUID | None, now: datetime) -> dict[str, object]:
    """기록에 적을 결과. 답이 있으면 확정할 것, 없으면 돌려줄 것이다."""
    return {
        'billing_status': BillingStatus.CAPTURE_DUE if answer_id is not None else BillingStatus.RELEASE_DUE,
        'message_id': answer_id,
        'outcome': result.outcome,
        'error_code': result.error_code,
        'dropped_segments': result.dropped,
        'input_tokens': result.input_tokens,
        'output_tokens': result.output_tokens,
        'cost_usd': result.cost_usd,
        'finished_at': now,
    }


def settled_values(generation: Generation, capture: bool, settlement: Settlement, now: datetime) -> dict[str, object]:
    """맡겨 본 결과를 기록에 적을 값. 다시 부를 일이면 다음에 부를 때를 미룬다."""
    if settlement.result == Settled.DONE:
        return {'billing_status': BillingStatus.CAPTURED if capture else BillingStatus.RELEASED}
    if settlement.result == Settled.FAILED:
        return {'billing_status': BillingStatus.FAILED, 'error_code': settlement.error_code}
    return {
        'settle_attempts': generation.settle_attempts + 1,
        'next_settle_at': now + charging.retry_delay(generation.settle_attempts),
    }


# --- 응답을 시작하기 전 ---


async def state_at(session: AsyncSession, world: World, path: list[Message]) -> StoryState:
    """가지의 끝의 상태. 말에 붙은 상태 가운데 끝에서 가장 가까운 것이고, 없으면 처음의 상태다."""
    return state_on_path(world, await repository.states_on(session, [message.id for message in path]))


async def begin_turn(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    conversation_id: uuid.UUID,
    content: str,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    차례를 잡고 사람의 말과 기록(pending)을 저장한다. 장면의 인물을 정하고 모델에 보낼 메시지를 함께 만든다.

    새 말은 지금 가지의 끝에 붙는다. 가지의 끝은 차례를 잡은 뒤에 다시 읽는다.
    세션이 없으면 ConversationNotFoundError, 모델이 없으면 ModelRequiredError, 쓸 수 없으면 ModelUnavailableError,
    다른 답을 쓰는 중이면 ConversationBusyError, 끝난 세션이면 SessionEndedError. 어느 것이든 아무것도 저장하지 않는다.
    판매(결제 서버의 가격표)는 여기서 보지 않는다. 홀드를 걸 때 결제 서버가 본다.
    """
    async with session_factory() as session:
        conversation, imported = await get_conversation(session, viewer, conversation_id)
        model = await catalog.get_model(session, conversation.model_slug) if conversation.model_slug else None
        slug = require_model(conversation, model, Rating(imported.rating), now)
        if not await repository.lock_turn(session, conversation.id, now, GENERATION_STALE):
            raise ConversationBusyError
        await session.refresh(conversation)
        start = await record_turn(session, viewer, conversation, imported, slug, content, options, now)
        await session.commit()
    return start


async def record_turn(
    session: AsyncSession,
    viewer: Viewer,
    conversation: Conversation,
    imported: ImportedWorld,
    slug: str,
    content: str,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    차례를 쥔 채로 사람의 말과 기록을 세션에 올린다(커밋하지 않는다). 끝난 세션이면 SessionEndedError.
    판, 가지의 끝의 상태, 장면의 인물로 모델에 보낼 메시지를 만든다.
    """
    world, briefing = read_world(imported.document), read_briefing(imported.document)
    path = await conversations.active_path(session, conversation.active_leaf_id)
    state = await state_at(session, world, path)
    require_open(world, state)
    cast, event = scene_now(world, state)
    message = user_message(conversation, conversation.active_leaf_id, content, now)
    repository.add(session, message)
    await session.flush()
    await repository.move_leaf(session, conversation.id, message.id)
    generation = new_generation(conversation, viewer.claims.user_id, message.id, slug)
    repository.add(session, generation)
    return TurnStart(
        conversation_id=conversation.id,
        generation_id=generation.id,
        owner_id=viewer.claims.user_id,
        model_slug=slug,
        reference=generation.reference,
        price_code=generation.price_code,
        user_message=saved(message),
        messages=prompt_for(briefing, world, state, cast, event, [*path, message], options.context_chars),
        cast=tuple(cast),
        labels=labels_for(briefing, cast),
    )


async def route_turn(router: Router, start: TurnStart) -> Route:
    """모델을 부를 provider. 부를 수 없으면 HoldDeclined(model_unavailable, provider_unavailable). 부르지는 않는다."""
    try:
        return await router.route(start.model_slug)
    except ProviderError as error:
        code = charging.MODEL_UNAVAILABLE if str(error) == ROUTE_MODEL_UNAVAILABLE else PROVIDER_UNAVAILABLE
        raise HoldDeclined(code) from error


async def mark_held(session_factory: async_sessionmaker[AsyncSession], start: TurnStart) -> None:
    """기록을 held 로 옮긴다. 이제부터 서버가 꺼지면 정리 작업이 돌려준다."""
    async with session_factory() as session:
        await repository.move_billing(
            session, start.generation_id, frozenset({BillingStatus.PENDING}), {'billing_status': BillingStatus.HELD}
        )
        await session.commit()


async def decline_turn(
    session_factory: async_sessionmaker[AsyncSession], start: TurnStart, code: str, now: datetime
) -> None:
    """답을 쓰지 않는다. 차례를 놓고 기록을 declined 로 둔다. 사람의 말은 남는다."""
    async with session_factory() as session:
        await repository.unlock_turn(session, start.conversation_id)
        await repository.move_billing(
            session,
            start.generation_id,
            frozenset({BillingStatus.PENDING}),
            {'billing_status': BillingStatus.DECLINED, 'error_code': code, 'finished_at': now},
        )
        await session.commit()


async def prepare_turn(
    session_factory: async_sessionmaker[AsyncSession], router: Router, billing: Billing, start: TurnStart, now: datetime
) -> Route:
    """provider 를 고르고 홀드를 건다. 어느 하나라도 안 되면 차례를 놓고 TurnDeclinedError."""
    try:
        route = await route_turn(router, start)
        await charging.place_hold(billing, start.reference, start.owner_id, start.price_code)
    except HoldDeclined as declined:
        await decline_turn(session_factory, start, declined.code, now)
        raise TurnDeclinedError(declined.code, start.user_message.id) from declined
    await mark_held(session_factory, start)
    return route


# --- 응답을 시작한 뒤(따로 도는 작업) ---


async def call_model(route: Route, start: TurnStart, params: GenerationParams, collector: Collector) -> TurnResult:
    """
    모델을 부른다. 받는 대로 collector 에 넘긴다. 실패해도 예외를 올리지 않고 결과로 돌려준다.

    서버가 꺼지며 멈추면(취소) 그대로 올린다. 받은 만큼은 collector 가 안다.
    """
    try:
        completion = await route.provider.complete(start.messages, params, collector)
    except ProviderError as error:
        return failure_of(*collector.finish(), str(error))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            '모델을 부르다 예상하지 못한 오류가 났습니다', extra={'generation_id': str(start.generation_id)}
        )
        return failure_of(*collector.finish(), SERVER_ERROR)
    return result_of(completion, route, *collector.finish())


def log_dropped(start: TurnStart, result: TurnResult) -> None:
    """장면에 없는 인물의 줄을 버렸으면 로그로 남긴다(사람에게는 보이지 않는다)."""
    if result.dropped:
        logger.info(
            '장면에 없는 인물의 줄을 버렸습니다',
            extra={'generation_id': str(start.generation_id), 'dropped': result.dropped},
        )


async def save_result(
    session_factory: async_sessionmaker[AsyncSession], start: TurnStart, result: TurnResult, now: datetime
) -> SavedMessage | None:
    """답을 저장하고(있으면) 차례를 놓고 기록에 결과를 적는다. 한 트랜잭션이다. 저장한 답이나 None."""
    log_dropped(start, result)
    answer = answer_of(start, result, now)
    stored = saved(answer) if answer is not None else None
    async with session_factory() as session:
        if answer is not None:
            repository.add(session, answer)
            await session.flush()
            await repository.finish_turn(session, start.conversation_id, answer.id)
        else:
            await repository.unlock_turn(session, start.conversation_id)
        answer_id = answer.id if answer is not None else None
        await repository.move_billing(
            session, start.generation_id, frozenset({BillingStatus.HELD}), finished_values(result, answer_id, now)
        )
        await session.commit()
    return stored


async def settle_generation(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, generation: Generation, now: datetime
) -> Settlement:
    """
    확정할 것이나 돌려줄 것 하나를 결제 서버에 맡기고 결과를 적는다. 말 한 번의 끝과 정리 작업이 함께 쓴다.

    상태가 그사이에 바뀌었으면(다른 쪽이 먼저 끝냈다) 적지 않는다.
    """
    capture = generation.billing_status == BillingStatus.CAPTURE_DUE
    settlement = await charging.settle(billing, generation.reference, capture)
    async with session_factory() as session:
        await repository.move_billing(
            session,
            generation.id,
            frozenset({BillingStatus(generation.billing_status)}),
            settled_values(generation, capture, settlement, now),
        )
        await session.commit()
    return settlement


async def settle_turn(
    session_factory: async_sessionmaker[AsyncSession], billing: Billing, generation_id: uuid.UUID, now: datetime
) -> None:
    """말 한 번이 끝난 뒤 바로 맡긴다. 맡길 것이 아니면(이미 끝났다) 아무것도 하지 않는다."""
    async with session_factory() as session:
        generation = await repository.get_generation(session, generation_id)
    if generation is not None and generation.billing_status in DUE_STATUSES:
        await settle_generation(session_factory, billing, generation, now)


async def guarded_call(
    session_factory: async_sessionmaker[AsyncSession],
    route: Route,
    start: TurnStart,
    params: GenerationParams,
    collector: Collector,
    clock: Callable[[], datetime],
) -> TurnResult:
    """
    모델을 부른다. 서버가 꺼지며 멈추면(이 작업의 취소) 받은 만큼 저장한 뒤 그대로 올린다.
    맡기는 것은 다음에 뜬 서버의 정리 작업이 한다.
    """
    try:
        return await call_model(route, start, params, collector)
    except asyncio.CancelledError:
        await save_result(session_factory, start, failure_of(*collector.finish(), CANCELLED), clock())
        raise


async def run_generation(
    session_factory: async_sessionmaker[AsyncSession],
    billing: Billing,
    route: Route,
    start: TurnStart,
    params: GenerationParams,
    relay: Relay,
    clock: Callable[[], datetime],
) -> None:
    """
    모델을 부르고, 흘려보내고, 저장하고, 맡긴다. 응답과 따로 도는 작업이다. 사람이 끊어도 끝까지 돈다.

    저장하다 실패하면(DB 가 없다) 응답에 실패를 알리고 끝낸다.
    차례와 홀드는 오래되면 풀린다(GENERATION_STALE, 정리 작업).
    """
    collector = collector_for(start, relay)
    result = await guarded_call(session_factory, route, start, params, collector, clock)
    try:
        answer = await save_result(session_factory, start, result, clock())
    except Exception:
        logger.exception('답을 저장하지 못했습니다', extra={'generation_id': str(start.generation_id)})
        relay.close(failed_frame(SERVER_ERROR))
        return
    relay.close(done_frame(answer) if answer is not None else failed_frame(result.error_code or SERVER_ERROR))
    await settle_turn(session_factory, billing, start.generation_id, clock())
