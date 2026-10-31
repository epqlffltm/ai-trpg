# story-server/app/turns/service.py

"""
말 한 번(docs/architecture/story.md 의 "한 번의 말").
chat 의 말 한 번(chat-server/app/turns/service.py)과 같은 차례이고,
다른 것은 답이 장면의 인물들과 서술의 말 조각이라는 것이다. 아래 차례의 각 줄이 함수 하나다.

  응답을 시작하기 전(실패하면 HTTP 의 오류로 답한다)
    1. begin_turn, begin_action, begin_regenerate, begin_continue: 세션과 모델을 보고, 차례를 잡고(한 세션 한 생성),
       사람의 말(또는 행동 말과 그 뒤의 상태)과 기록(pending)을 한 트랜잭션에 저장한다.
       다시 생성은 기록만 저장한다. 답한 말에 적힌 장면을 다시 세운다.
       이어서 출력도 기록만 저장한다. 끊긴 답까지의 말과 이어 쓰라는 지시를 보낸다
       행동은 엔진이 판정한다(app/turns/actions.py). 본 엔딩과 연 일러스트는 계정의 기록에 남긴다(app/records/).
       답을 쓰는 장면을 정하고(app/turns/scenes.py) 모델에 보낼 메시지를 만든다(app/turns/prompt.py)
    2. route_turn: 모델을 부를 provider 를 고른다. 키가 없거나 쓸 수 없는 모델이면 거절한다
    3. hold_turn: 홀드를 건다. 걸리지 않으면(모자람, 팔지 않음, 결제 서버가 죽음) 거절한다
       거절되면 decline_turn 이 차례를 놓고 기록을 declined 로 둔다. 사람의 말은 남는다
  응답을 시작한 뒤(따로 도는 작업. 사람이 끊어도 끝까지 돈다)
    4. call_model: 모델을 부르고, 받는 대로 말 조각으로 잘라 흘려보낸다(app/turns/segments.py).
       사람이 멈추면(app/turns/stops.py) 받은 만큼으로 끝낸다(stopped)
    5. save_result: 받은 만큼 답을 저장하고 차례를 놓는다.
       다 받았으면 complete, 길이에서 잘렸거나 도중에 끊겼으면 partial. 남은 조각이 없으면 답을 저장하지 않는다.
       이어서 출력이면 새 말을 만들지 않고 끊긴 답에 붙인다(extension_of)
    6. settle_turn: 답이 있으면 확정, 없으면 반환한다.
       결제 서버가 받지 못하면 정리 작업이 마저 한다(app/turns/settler.py)

모델은 상태를 바꾸지 않는다. 상태는 행동 말에 붙는다. 말은 기다리던 선택지를 지우는 것 말고는 상태를 바꾸지 않는다.
답에는 상태를 붙이지 않는다(그 앞의 말의 상태가 그대로다).
DB 접근, 바깥 호출(공급자, 결제 서버), 응답 만들기를 한 함수에 섞지 않는다. 바깥을 부르는 동안 DB 의 연결을 쥐지 않는다.
같은 실패를 저절로 되풀이하지 않는다(사람이 다시 보낸다). 다른 모델로 넘어가지 않는다.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from ai_core.costs import charge_of
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError
from ai_core.routing import MODEL_UNAVAILABLE as ROUTE_MODEL_UNAVAILABLE
from ai_core.routing import Route
from conversation_core import continuation
from conversation_core.continuation import OverlapTrim
from conversation_core.lorebook import chosen_entries, query_text, ranked, render_lore, with_recalled
from conversation_core.relay import Relay
from conversation_core.suggestions import MarkerHold, parse_suggestions, split_answer
from conversation_core.window import Turn, select_window
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.client import Billing
from app.billing.prices import story_code
from app.catalog import repository as catalog
from app.catalog.choice import is_choosable
from app.catalog.models import AiModel
from app.conversations import repository as conversations
from app.conversations.models import Conversation, ConversationPersona, ImportedWorld, Message, MessageStatus, Role
from app.conversations.service import (
    GENERATION_STALE,
    NOT_EDITABLE,
    ConversationBusyError,
    MessageNotFoundError,
    ModelUnavailableError,
    NotEditableError,
    get_conversation,
)
from app.conversations.views import affection_shown, met_on
from app.core.dependencies import Viewer
from app.engine import play
from app.engine.endings import is_over
from app.engine.events import drop_choice
from app.engine.play import Played
from app.engine.state import StoryState
from app.engine.world import AfterEnding, World, read_world
from app.lore.recall import LoreRecall
from app.memory import repository as memory_store
from app.memory.service import notes_for_prompt, render_memory
from app.memory.summaries import latest_summary, overflow, render_story
from app.ratings import Rating, allowed_ratings
from app.records import repository as records
from app.records.illustrations import unlocked_scenes
from app.turns import charging, repository
from app.turns.actions import action_text, perform
from app.turns.briefing import Briefing, read_briefing
from app.turns.charging import HoldDeclined, Settled, Settlement
from app.turns.frames import delta_frame, done_frame, failed_frame, segment_frame
from app.turns.models import DUE_STATUSES, BillingStatus, Generation, Outcome
from app.turns.prompt import PersonaCard, build_messages, render_card, scene_card, with_lore
from app.turns.providers import Router
from app.turns.scenes import Staging, replayed, staging
from app.turns.segments import (
    Segment,
    SegmentStart,
    SegmentText,
    SpeakerSplitter,
    continuing_splitter,
    merge_events,
    render_segments,
    segment_dicts,
    segments_of,
    speaker_labels,
)
from app.turns.states import state_on_path, state_to_json, state_view
from app.turns.stops import StopSwitch
from app.turns.values import LorePlan, PromptOptions, SavedMessage, TurnResult, TurnStart

logger = logging.getLogger(__name__)

# 공급자를 부르지 못한 까닭(키가 없다, 부르는 코드가 없다)의 이름. 사람에게는 잠시 뒤에 다시 하라고 알린다
PROVIDER_UNAVAILABLE = 'provider_unavailable'
# 서버가 꺼지며 멈춘 생성, 예상하지 못한 오류, 남은 조각이 없는 답의 까닭
CANCELLED = 'cancelled'
SERVER_ERROR = 'server_error'
EMPTY = 'empty'
# 사람이 멈춘 생성의 까닭
STOPPED = 'stopped'


class ModelRequiredError(Exception):
    """세션에 모델이 없다. 먼저 고른다(409)."""


class SessionEndedError(Exception):
    """엔딩을 본 세션이고 세계관이 끝(읽기만)을 골랐다. 말을 받지 않는다(409)."""


class NotRegenerableError(Exception):
    """다시 쓸 수 없는 말이다. 부모가 없는 답은 모델이 답한 것이 아니다(422)."""


class NotContinuableError(Exception):
    """이어 쓸 수 없는 말이다(422). 끊긴 답(partial)이 아니거나, 지금 가지의 끝이 아니다."""


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
    trim 이 있으면(이어서 출력) 끊긴 답의 끝을 되풀이한 앞부분을 떼고 자른다(conversation_core 의 OverlapTrim).
    본문만 자른다. 다음 답 추천의 표식 뒤는 흘리지 않는다(conversation_core/suggestions.py 의 MarkerHold).
    """

    relay: Relay
    splitter: SpeakerSplitter
    trim: OverlapTrim | None = None
    hold: MarkerHold = field(default_factory=MarkerHold)
    finished: bool = field(default=False)

    def __call__(self, piece: str) -> None:
        self.push(self.splitter.feed(self.hold.feed(self.trim.feed(piece) if self.trim is not None else piece)))

    def push(self, events: list[SegmentStart | SegmentText]) -> None:
        """잘린 것들을 응답으로. 잇닿은 글은 하나로 묶어 보낸다."""
        for event in merge_events(events):
            if isinstance(event, SegmentStart):
                self.relay.push(segment_frame(event.speaker, event.expression))
            else:
                self.relay.push(delta_frame(event.text))

    def finish(self) -> tuple[tuple[Segment, ...], int]:
        """끝났다. 남은 줄을 마저 흘리고, 지금까지의 조각과 버린 줄의 수를 돌려준다. 여러 번 불러도 한 번만 끝낸다."""
        if not self.finished:
            self.finished = True
            if self.trim is not None:
                self.push(self.splitter.feed(self.hold.feed(self.trim.release())))
            self.push(self.splitter.feed(self.hold.release()))
            self.push(self.splitter.finish())
        return self.splitter.segments(), self.splitter.dropped


def collector_for(start: TurnStart, relay: Relay) -> Collector:
    """
    말 한 번의 Collector. 장면의 인물의 표식만 받는다.
    이어서 출력이면 끊긴 답의 조각에서 시작하고(첫 줄에 표식이 없으면 마지막 조각을 이어 쓴다) 겹친 앞부분을 뗀다.
    """
    if start.continued is None:
        return Collector(relay, SpeakerSplitter(start.labels, start.expressions))
    splitter = continuing_splitter(start.labels, segments_of(start.continued.segments), start.expressions)
    return Collector(relay, splitter, trim=OverlapTrim(start.continued.content))


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
        event_id=message.event_id,
        ending_id=message.ending_id,
        suggestions=tuple(message.suggestions or ()),
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


def talked_state(state: StoryState) -> StoryState | None:
    """말을 한 뒤의 상태. 기다리던 선택지가 있으면 사라진 상태이고, 바뀌는 것이 없으면 None 이다."""
    return drop_choice(state) if state.choosing is not None else None


def answered_message(target: Message) -> uuid.UUID:
    """
    다시 답할 말(사람의 말이나 행동 말)의 id. 답이면 그 부모, 사람의 말이나 행동 말이면 그 말 자신이다
    (답을 못 받은 말에 답한다). 부모가 없는 답은 다시 쓰지 않는다(NotRegenerableError).
    """
    if target.role in (Role.USER, Role.ACTION):
        return target.id
    if target.parent_id is None:
        raise NotRegenerableError
    return target.parent_id


@dataclass(frozen=True)
class Branch:
    """지금 가지. 판(규칙과 글), 첫 말부터의 말들, 끝의 상태다."""

    world: World
    briefing: Briefing
    path: list[Message]
    state: StoryState
    # 가져온 판의 문서(받은 칸 전부). 상태의 호감도를 보여도 되는 인물을 고를 때 쓴다
    document: Mapping
    # 세션에 가져온 페르소나(카드의 [사용자]). 페르소나 없이 시작했으면 None
    persona: PersonaCard | None = None
    # 판의 사본의 id. 로어북의 벡터가 이것에 붙는다(app/lore/)
    world_id: uuid.UUID | None = None
    # 세션의 기억 메모의 "[기억]" 블록. 메모가 없으면 None(app/memory/)
    memory: str | None = None
    # 가지의 말 가운데 굴리는 요약이 붙은 것(말의 id → 요약의 글, app/memory/summaries.py)
    summaries: Mapping[uuid.UUID, str] = field(default_factory=dict)


def lore_plan_of(branch: Branch, recent: Sequence[str]) -> LorePlan | None:
    """
    판의 로어북에서 상시와 키워드로 고른 것(카드의 "[로어북]")과, 뜻으로 찾아 더할 바탕.
    recent 는 최근 말들(오래된 것부터 이번 말까지)이다. 로어북의 항목이 없으면 None.
    """
    keyed = branch.briefing.keyed_lore()
    if not keyed or branch.world_id is None:
        return None
    entries = tuple(entry for _, entry in keyed)
    order = tuple(ranked(entries, recent))
    return LorePlan(
        world_id=branch.world_id,
        entries=entries,
        keys=tuple(key for key, _ in keyed),
        ranked=order,
        query=query_text(recent),
        block=render_lore(chosen_entries(entries, order)),
    )


def story_of(branch: Branch, chars: int) -> str | None:
    """
    카드의 "[앞의 줄거리]". 지난 말의 창(chars)에 들지 못하고 밀려난 말 가운데 요약이 붙은 가장 뒤의 것이다.
    밀려난 말이 없거나 아직 요약이 없으면 None(app/memory/summaries.py).
    """
    return render_story(latest_summary(overflow(branch.path, chars), branch.summaries))


def card_for(branch: Branch, state: StoryState, stage: Staging, options: PromptOptions, lore: LorePlan | None) -> str:
    """
    카드. state 와 장면으로 만들고, 켜져 있으면 다음 답 추천의 지시를, 로어북이 있으면 고른 항목을 넣는다.
    밀려난 말의 요약이 있으면 앞의 줄거리로 넣는다.
    """
    scene = scene_card(branch.briefing, branch.world, state, stage.cast, stage.direction)
    block = lore.block if lore is not None else None
    story = story_of(branch, options.context_chars)
    return render_card(branch.briefing, scene, options.suggestions, branch.persona, block, branch.memory, story)


def prompt_for(
    branch: Branch, state: StoryState, stage: Staging, added: Message, options: PromptOptions, lore: LorePlan | None
) -> list[ChatMessage]:
    """
    모델에 보낼 메시지. 카드(state 와 장면)와, 가지의 말들에 added 를 더한 것 가운데
    지난 말의 양 안에 드는 최근 것들이다.
    지난 답은 본문(content)만 간다. 다음 답 추천은 가지 않는다(모델이 흉내 내지 않게).
    """
    turns = [Turn(message.role, message.content) for message in [*branch.path, added]]
    card = card_for(branch, state, stage, options, lore)
    return build_messages(card, select_window(turns, options.context_chars))


def shown_in_turn(branch: Branch, stage: Staging) -> frozenset[str]:
    """
    이 말의 상태에 호감도를 보여도 되는 인물. 만난 인물은 가지의 답들의 장면의 인물과, 이번 답의 장면의 인물이다.
    """
    met = met_on(message.cast or () for message in branch.path if message.role == Role.ASSISTANT)
    return affection_shown(branch.document, met | frozenset(stage.cast))


def expressions_for(briefing: Briefing, cast: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """장면의 인물마다 고를 수 있는 표정의 이름들. 표정이 없는 인물은 뺀다."""
    found = {cast_id: briefing.expressions(cast_id) for cast_id in cast}
    return {cast_id: names for cast_id, names in found.items() if names}


def labels_for(briefing: Briefing, cast: tuple[str, ...]) -> dict[str, str]:
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
        event_id=None,
        ending_id=None,
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
    길이 상한에서 잘렸으면 partial 이고 다음 답 추천이 없다. 다 썼으면 표식 뒤의 선택지를 거른다.
    원가는 그날의 단가로 센다.
    """
    cost, _ = charge_of(completion, route.price)
    usage = {'input_tokens': completion.input_tokens, 'output_tokens': completion.output_tokens, 'cost_usd': cost}
    if not segments:
        return TurnResult(segments=(), outcome=Outcome.FAILED, error_code=EMPTY, dropped=dropped, **usage)
    if completion.truncated:
        return TurnResult(segments=segments, outcome=Outcome.PARTIAL, dropped=dropped, **usage)
    suggestions = tuple(parse_suggestions(split_answer(completion.text)[1]))
    return TurnResult(segments=segments, outcome=Outcome.COMPLETE, suggestions=suggestions, dropped=dropped, **usage)


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
        suggestions=list(result.suggestions),
        created_at=now,
    )


def extension_of(start: TurnStart, result: TurnResult) -> SavedMessage | None:
    """
    이어서 출력으로 바뀔 끊긴 답. 이어 쓴 것이 없으면 None(끊긴 답은 그대로다).
    result 의 조각은 끊긴 답의 조각까지 모두다(app/turns/segments.py 의 continuing_splitter).
    다 썼으면 complete 이고 다음 답 추천이 붙는다. 또 끊겼으면 partial 로 남아 다시 이어 쓸 수 있다.
    장면의 인물은 그대로다.
    """
    if start.continued is None or not result.segments:
        return None
    return replace(
        start.continued,
        content=render_segments(result.segments),
        status=MessageStatus.PARTIAL if result.outcome == Outcome.PARTIAL else MessageStatus.COMPLETE,
        segments=tuple(segment_dicts(result.segments)),
        suggestions=result.suggestions,
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


async def state_at(session: AsyncSession, world: World, conversation: Conversation, path: list[Message]) -> StoryState:
    """
    가지의 끝의 상태. 말에 붙은 상태 가운데 끝에서 가장 가까운 것이고, 없으면 처음의 상태다.
    세션에 굳힌 계정의 본 엔딩(회차 혜택)을 붙인다.
    """
    states = await conversations.states_on(session, [message.id for message in path])
    return state_on_path(world, states, frozenset(conversation.cleared_endings or ()))


# 차례를 쥔 채로 말 한 번을 세션에 올리는 것(record_turn, record_action 에 인자를 채운 것)
Recorder = Callable[[AsyncSession, Conversation, ImportedWorld, str], Awaitable[TurnStart]]


async def begin(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    conversation_id: uuid.UUID,
    now: datetime,
    record: Recorder,
) -> TurnStart:
    """
    세션과 모델을 보고 차례를 잡은 뒤 record 로 말 한 번을 올려 저장한다.

    세션이 없으면 ConversationNotFoundError, 모델이 없으면 ModelRequiredError, 쓸 수 없으면 ModelUnavailableError,
    다른 답을 쓰는 중이면 ConversationBusyError.
    record 가 올리는 예외(SessionEndedError, ActionRefusedError)도 그대로다.
    어느 것이든 아무것도 저장하지 않는다(차례도 함께 되돌린다).
    판매(결제 서버의 가격표)는 여기서 보지 않는다. 홀드를 걸 때 결제 서버가 본다.
    """
    async with session_factory() as session:
        conversation, imported = await get_conversation(session, viewer, conversation_id)
        model = await catalog.get_model(session, conversation.model_slug) if conversation.model_slug else None
        slug = require_model(conversation, model, Rating(imported.rating), now)
        if not await repository.lock_turn(session, conversation.id, now, GENERATION_STALE):
            raise ConversationBusyError
        await session.refresh(conversation)
        start = await record(session, conversation, imported, slug)
        await session.commit()
    return start


async def begin_turn(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    conversation_id: uuid.UUID,
    content: str,
    options: PromptOptions,
    now: datetime,
    edit_of: uuid.UUID | None = None,
) -> TurnStart:
    """
    차례를 잡고 사람의 말과 기록(pending)을 저장한다. 장면의 인물을 정하고 모델에 보낼 메시지를 함께 만든다.
    새 말은 지금 가지의 끝에 붙는다. edit_of(고칠 사람의 말)가 있으면 그 말의 부모 아래에 붙는다(새 가지).
    가지의 끝은 차례를 잡은 뒤에 다시 읽는다. 고칠 말이 틀리면 MessageNotFoundError, NotEditableError.
    나머지 실패는 begin 과 같다.
    """

    async def record(session: AsyncSession, conversation: Conversation, imported: ImportedWorld, slug: str):
        return await record_turn(session, viewer, conversation, imported, slug, content, options, now, edit_of)

    return await begin(session_factory, viewer, conversation_id, now, record)


async def begin_action(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    conversation_id: uuid.UUID,
    action: play.Action,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    차례를 잡고 행동을 판정해 행동 말과 그 뒤의 상태, 기록(pending)을 저장한다. 이어서 모델이 반응을 쓴다.
    할 수 없는 행동이면 ActionRefusedError 다. 나머지 실패는 begin 과 같다.
    """

    async def record(session: AsyncSession, conversation: Conversation, imported: ImportedWorld, slug: str):
        return await record_action(session, viewer, conversation, imported, slug, action, options, now)

    return await begin(session_factory, viewer, conversation_id, now, record)


async def answered_in(
    session_factory: async_sessionmaker[AsyncSession], viewer: Viewer, message_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """
    다시 답할 말의 세션과 그 말(answered_message)의 id. 말이 없으면 MessageNotFoundError,
    다시 쓸 수 없는 말이면 NotRegenerableError. 말은 바뀌지 않으므로 차례를 잡기 전에 읽는다.
    """
    async with session_factory() as session:
        target = await conversations.find_visible_message(
            session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
        )
    if target is None:
        raise MessageNotFoundError
    return target.conversation_id, answered_message(target)


async def begin_regenerate(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    message_id: uuid.UUID,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    그 말에 다시 답할 차례를 잡는다. 새 답은 같은 부모 아래의 대안이다. 앞의 답은 그대로 남는다.

    기록(pending)만 저장한다. 사람의 말도 상태도 새로 저장하지 않는다(엔진은 다시 판정하지 않는다).
    가지의 끝은 옮기지 않는다. 새 답을 저장할 때 옮긴다(save_result).
    그래서 거절되거나 조각 없이 실패하면 앞의 답이 그대로 보인다.
    말이 없으면 MessageNotFoundError, 다시 쓸 수 없는 말이면 NotRegenerableError. 나머지는 begin 과 같다.
    """
    conversation_id, answered_id = await answered_in(session_factory, viewer, message_id)

    async def record(session: AsyncSession, conversation: Conversation, imported: ImportedWorld, slug: str):
        return await record_regenerate(session, viewer, conversation, imported, slug, answered_id, options)

    return await begin(session_factory, viewer, conversation_id, now, record)


def persona_card(persona: ConversationPersona | None) -> PersonaCard | None:
    """페르소나의 사본에서 카드의 사용자 칸. 페르소나 없이 시작한 세션이면 None."""
    if persona is None:
        return None
    return PersonaCard(
        name=persona.name,
        description=persona.description,
        age=persona.age,
        gender=persona.gender,
        form_of_address=persona.form_of_address,
        speech_examples=persona.speech_examples,
        personality=persona.personality,
    )


async def branch_at(
    session: AsyncSession, conversation: Conversation, imported: ImportedWorld, leaf_id: uuid.UUID | None
) -> Branch:
    """leaf_id 에서 끝나는 가지. 판을 읽고, 가지의 말들과 끝의 상태, 세션의 페르소나를 읽는다."""
    world = read_world(imported.document)
    path = await conversations.active_path(session, leaf_id)
    state = await state_at(session, world, conversation, path)
    persona = persona_card(await conversations.persona_of(session, conversation.id))
    memory = render_memory(await notes_for_prompt(session, conversation.id))
    summaries = await memory_store.summaries_on(session, [message.id for message in path])
    return Branch(
        world,
        read_briefing(imported.document),
        path,
        state,
        imported.document,
        persona,
        imported.id,
        memory,
        summaries,
    )


async def branch_of(session: AsyncSession, conversation: Conversation, imported: ImportedWorld) -> Branch:
    """세션의 지금 가지."""
    return await branch_at(session, conversation, imported, conversation.active_leaf_id)


async def attach(session: AsyncSession, conversation: Conversation, message: Message, state: StoryState | None) -> None:
    """말을 가지의 끝에 붙인다. state 가 있으면 그 말에 상태를 붙인다. 커밋하지 않는다."""
    repository.add(session, message)
    await session.flush()
    if state is not None:
        conversations.add_state(session, message.id, state_to_json(state))
    await repository.move_leaf(session, conversation.id, message.id)


def add_generation(
    session: AsyncSession, conversation: Conversation, owner_id: uuid.UUID, message: Message, slug: str
) -> Generation:
    """그 말에 답하는 기록(pending)을 세션에 올린다."""
    generation = new_generation(conversation, owner_id, message.id, slug)
    repository.add(session, generation)
    return generation


def turn_start(
    owner_id: uuid.UUID,
    generation: Generation,
    message: Message,
    branch: Branch,
    state: StoryState,
    stage: Staging,
    options: PromptOptions,
) -> TurnStart:
    """말 한 번의 시작. 그 뒤의 일은 이것만 들고 간다. 로어북은 가지의 말과 이번 말에서 고른다."""
    lore = lore_plan_of(branch, [*(item.content for item in branch.path), message.content])
    return TurnStart(
        conversation_id=generation.conversation_id,
        generation_id=generation.id,
        owner_id=owner_id,
        model_slug=generation.model_slug,
        reference=generation.reference,
        price_code=generation.price_code,
        user_message=saved(message),
        messages=prompt_for(branch, state, stage, message, options, lore),
        cast=stage.cast,
        labels=labels_for(branch.briefing, stage.cast),
        expressions=expressions_for(branch.briefing, stage.cast),
        state=state_view(branch.world, state, stage.cast, shown_in_turn(branch, stage)),
        lore=lore,
    )


async def edited_parent(session: AsyncSession, conversation: Conversation, edit_of: uuid.UUID) -> uuid.UUID | None:
    """
    고친 말(내 말 고치기)이 붙을 자리. 고칠 사람의 말의 부모다(첫 말이면 None). 새 말은 그 말의 대안(새 가지)이 되고
    원본은 남는다. 그 세션의 말이 아니면 MessageNotFoundError, 사람의 말이 아니면 NotEditableError(not_editable).
    행동 말은 엔진이 판정한 결과라 고치지 않는다(다른 행동은 그 앞의 가지에서 새로 한다).
    """
    original = await session.get(Message, edit_of)
    if original is None or original.conversation_id != conversation.id:
        raise MessageNotFoundError
    if original.role != Role.USER:
        raise NotEditableError(NOT_EDITABLE)
    return original.parent_id


async def record_turn(
    session: AsyncSession,
    viewer: Viewer,
    conversation: Conversation,
    imported: ImportedWorld,
    slug: str,
    content: str,
    options: PromptOptions,
    now: datetime,
    edit_of: uuid.UUID | None = None,
) -> TurnStart:
    """
    차례를 쥔 채로 사람의 말과 기록을 세션에 올린다(커밋하지 않는다). 끝난 세션이면 SessionEndedError.
    기다리던 선택지가 있으면 사라진다(그 상태를 사람의 말에 붙인다). 그 장소의 인물들이 답한다.
    edit_of 가 있으면 고칠 말의 부모에서 끝나는 가지에 붙는다. 상태, 끝난 세션인지, 모델에 보낼 말들도 그 가지의 것이다.
    """
    parent_id = conversation.active_leaf_id
    if edit_of is not None:
        parent_id = await edited_parent(session, conversation, edit_of)
    branch = await branch_at(session, conversation, imported, parent_id)
    require_open(branch.world, branch.state)
    changed = talked_state(branch.state)
    state = changed or branch.state
    message = user_message(conversation, parent_id, content, now)
    await attach(session, conversation, message, changed)
    generation = add_generation(session, conversation, viewer.claims.user_id, message, slug)
    return turn_start(viewer.claims.user_id, generation, message, branch, state, staging(branch.world, state), options)


def action_message(
    conversation: Conversation, branch: Branch, action: play.Action, played: Played, now: datetime
) -> Message:
    """행동 말. 행동의 글과, 그 행동 뒤에 열린 이벤트와 본 엔딩을 적는다. 아직 저장하지 않는다."""
    text = action_text(branch.briefing, branch.world, action, played)
    message = user_message(conversation, conversation.active_leaf_id, text, now, Role.ACTION)
    message.event_id = played.event.id if played.event is not None else None
    message.ending_id = played.ending.id if played.ending is not None else None
    return message


async def record_ending(
    session: AsyncSession,
    owner_id: uuid.UUID,
    imported: ImportedWorld,
    conversation: Conversation,
    played: Played,
    now: datetime,
) -> None:
    """행동으로 엔딩을 봤고 그 엔딩이 기록에 남는 것이면(unlock) 계정의 기록에 적는다."""
    if played.ending is not None and played.ending.unlock:
        await records.add_ending(session, owner_id, imported.source_id, played.ending.id, conversation.id, now)


async def record_illustrations(
    session: AsyncSession,
    owner_id: uuid.UUID,
    imported: ImportedWorld,
    conversation: Conversation,
    played: Played,
    now: datetime,
) -> None:
    """
    행동 뒤에 열린 이벤트와 본 엔딩의 장면 가운데 해금 대상이고 그림이 있는 것을 계정의 기록에 적는다.
    후일담에서 열린 이벤트도 적는다. 이미 연 장면은 그대로 둔다.
    """
    unlocks = unlocked_scenes(played.event, played.ending)
    await records.add_illustrations(session, owner_id, imported.source_id, unlocks, conversation.id, now)


async def record_action(
    session: AsyncSession,
    viewer: Viewer,
    conversation: Conversation,
    imported: ImportedWorld,
    slug: str,
    action: play.Action,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    차례를 쥔 채로 행동을 판정하고 행동 말, 그 뒤의 상태, 기록을 세션에 올린다(커밋하지 않는다).
    끝난 세션이면 SessionEndedError, 할 수 없는 행동이면 ActionRefusedError.
    답은 열린 이벤트나 본 엔딩의 장면을 쓴다(app/turns/scenes.py).
    """
    branch = await branch_of(session, conversation, imported)
    require_open(branch.world, branch.state)
    played = perform(branch.world, branch.state, action)
    message = action_message(conversation, branch, action, played, now)
    await attach(session, conversation, message, played.state)
    await record_ending(session, viewer.claims.user_id, imported, conversation, played, now)
    await record_illustrations(session, viewer.claims.user_id, imported, conversation, played, now)
    generation = add_generation(session, conversation, viewer.claims.user_id, message, slug)
    stage = staging(branch.world, played.state, played.event, played.ending)
    return turn_start(viewer.claims.user_id, generation, message, branch, played.state, stage, options)


async def record_regenerate(
    session: AsyncSession,
    viewer: Viewer,
    conversation: Conversation,
    imported: ImportedWorld,
    slug: str,
    answered_id: uuid.UUID,
    options: PromptOptions,
) -> TurnStart:
    """
    차례를 쥔 채로 그 말에 다시 답하는 기록을 세션에 올린다(커밋하지 않는다).
    상태는 그 말까지의 가지의 것이고,
    장면은 그 말에 적힌 이벤트와 엔딩으로 다시 세운다(app/turns/scenes.py 의 replayed).
    끝난 세션이어도 된다. 사람의 말이 늘지 않고 상태도 바뀌지 않는다(엔딩의 장면을 다시 쓸 수 있다).
    """
    branch = await branch_at(session, conversation, imported, answered_id)
    answered = branch.path[-1]
    before = replace(branch, path=branch.path[:-1])
    stage = replayed(branch.world, branch.state, answered.event_id, answered.ending_id)
    generation = add_generation(session, conversation, viewer.claims.user_id, answered, slug)
    return turn_start(viewer.claims.user_id, generation, answered, before, branch.state, stage, options)


def require_continuable(target: Message) -> None:
    """
    이어 쓸 수 있는 말인가. 끊긴 답(partial 인 모델의 답)이 아니면 NotContinuableError. 끊긴 답에는 늘 부모가 있다.
    """
    if target.role != Role.ASSISTANT or target.status != MessageStatus.PARTIAL or target.parent_id is None:
        raise NotContinuableError


async def continued_in(
    session_factory: async_sessionmaker[AsyncSession], viewer: Viewer, message_id: uuid.UUID
) -> uuid.UUID:
    """
    이어 쓸 끊긴 답의 세션. 말이 없으면 MessageNotFoundError, 끊긴 답이 아니면 NotContinuableError.
    지금 가지의 끝인지는 차례를 잡은 뒤에 본다(record_continue).
    """
    async with session_factory() as session:
        target = await conversations.find_visible_message(
            session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
        )
    if target is None:
        raise MessageNotFoundError
    require_continuable(target)
    return target.conversation_id


async def begin_continue(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    message_id: uuid.UUID,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    끊긴 답을 이어 쓸 차례를 잡는다. 기록(pending)만 저장한다. 새 조각은 저장할 때 그 답에 붙는다(save_result).
    엔진은 다시 판정하지 않는다. 끝난 세션이어도 된다(사람의 말이 늘지 않는다).
    말이 없으면 MessageNotFoundError, 이어 쓸 수 없으면 NotContinuableError. 나머지는 begin 과 같다.
    """
    conversation_id = await continued_in(session_factory, viewer, message_id)

    async def record(session: AsyncSession, conversation: Conversation, imported: ImportedWorld, slug: str):
        return await record_continue(session, viewer, conversation, imported, slug, message_id, options)

    return await begin(session_factory, viewer, conversation_id, now, record)


def continue_prompt(
    branch: Branch, state: StoryState, stage: Staging, options: PromptOptions, lore: LorePlan | None
) -> list[ChatMessage]:
    """
    이어 쓰는 메시지. 카드와, 끊긴 답까지의 가지의 말들에 이어 쓰라는 지시(사람의 차례)를 더한 것 가운데
    지난 말의 양 안에 드는 최근 것들이다. 끊긴 답은 표식이 붙은 줄 그대로 가서 모델이 같은 모양으로 잇는다.
    다 이어 쓰면 다음 답 추천도 받는다(카드의 지시).
    """
    turns = [Turn(message.role, message.content) for message in branch.path]
    card = card_for(branch, state, stage, options, lore)
    turns.append(Turn(Role.USER, continuation.instruction()))
    return build_messages(card, select_window(turns, options.context_chars))


async def record_continue(
    session: AsyncSession,
    viewer: Viewer,
    conversation: Conversation,
    imported: ImportedWorld,
    slug: str,
    target_id: uuid.UUID,
    options: PromptOptions,
) -> TurnStart:
    """
    차례를 쥔 채로 끊긴 답을 이어 쓰는 기록을 세션에 올린다(커밋하지 않는다).
    지금 가지의 끝인 끊긴 답만 이어 쓴다. 그 뒤에 말이 붙었거나 다른 가지를 보고 있으면 NotContinuableError.
    장면의 인물은 끊긴 답에 적힌 그대로이고, 장면 지시는 답한 말에 적힌 이벤트와 엔딩으로 다시 세운다.
    """
    if conversation.active_leaf_id != target_id:
        raise NotContinuableError
    branch = await branch_at(session, conversation, imported, target_id)
    target, answered = branch.path[-1], branch.path[-2]
    require_continuable(target)
    direction = replayed(branch.world, branch.state, answered.event_id, answered.ending_id).direction
    stage = Staging(cast=tuple(target.cast or ()), direction=direction)
    generation = add_generation(session, conversation, viewer.claims.user_id, answered, slug)
    # 메시지는 이어 쓰는 것으로 바꾼다. turn_start 가 만드는 보통의 메시지는 쓰지 않으므로 빈 가지로 만든다
    empty = replace(branch, path=[])
    start = turn_start(viewer.claims.user_id, generation, answered, empty, branch.state, stage, options)
    lore = lore_plan_of(branch, [message.content for message in branch.path])
    messages = continue_prompt(branch, branch.state, stage, options, lore)
    return replace(start, messages=messages, continued=saved(target), lore=lore)


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
    """
    답을 저장하고(있으면) 차례를 놓고 기록에 결과를 적는다. 한 트랜잭션이다. 저장한 답이나 None.
    이어서 출력이면 끊긴 답을 바꾼 것이 저장한 답이다.
    """
    log_dropped(start, result)
    async with session_factory() as session:
        stored = await store_answer(session, start, result, now)
        if stored is not None:
            await repository.finish_turn(session, start.conversation_id, stored.id)
        else:
            await repository.unlock_turn(session, start.conversation_id)
        answer_id = stored.id if stored is not None else None
        await repository.move_billing(
            session, start.generation_id, frozenset({BillingStatus.HELD}), finished_values(result, answer_id, now)
        )
        await session.commit()
    return stored


async def store_answer(
    session: AsyncSession, start: TurnStart, result: TurnResult, now: datetime
) -> SavedMessage | None:
    """
    답을 세션에 적는다(커밋하지 않는다). 보통은 새 말이고, 이어서 출력이면 끊긴 답을 바꾼다. 적을 것이 없으면 None.
    """
    if start.continued is not None:
        extended = extension_of(start, result)
        if extended is not None:
            segments = list(extended.segments)
            await repository.extend_message(
                session, extended.id, segments, extended.content, extended.status, list(extended.suggestions)
            )
        return extended
    answer = answer_of(start, result, now)
    if answer is None:
        return None
    repository.add(session, answer)
    await session.flush()
    return saved(answer)


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


async def with_recalled_lore(recall: LoreRecall | None, start: TurnStart) -> TurnStart:
    """
    로어북을 뜻으로 찾아 카드의 "[로어북]" 에 더한다(모델을 부르기 직전). 찾을 수 없거나 더할 것이 없으면 그대로다.
    """
    plan = start.lore
    if recall is None or plan is None:
        return start
    recalled = await recall.recall(plan)
    if not recalled:
        return start
    block = render_lore(chosen_entries(plan.entries, with_recalled(plan.ranked, recalled)))
    card = start.messages[0]
    rebuilt = replace(card, content=with_lore(card.content, plan.block, block))
    return replace(start, messages=[rebuilt, *start.messages[1:]])


async def stoppable_call(
    session_factory: async_sessionmaker[AsyncSession],
    route: Route,
    start: TurnStart,
    params: GenerationParams,
    collector: Collector,
    clock: Callable[[], datetime],
    stop: StopSwitch,
) -> TurnResult:
    """
    모델을 부르는 일을 따로 띄우고 기다린다. 사람이 멈추면 받은 만큼의 결과(stopped)를 돌려준다.
    부르기 전에 멈췄으면 부르지 않는다.

    서버가 꺼지며 멈추면(이 작업의 취소) 부르는 일도 끊고, 받은 만큼 저장한 뒤 그대로 올린다.
    맡기는 것은 다음에 뜬 서버의 정리 작업이 한다. 사람이 멈춘 뒤에 서버가 꺼져도 꺼지는 쪽을 따른다.
    """
    if stop.requested:
        return failure_of((), 0, STOPPED)
    stop.call = asyncio.create_task(call_model(route, start, params, collector))
    try:
        return await stop.call
    except asyncio.CancelledError:
        if stop.requested and not asyncio.current_task().cancelling():
            return failure_of(*collector.finish(), STOPPED)
        stop.call.cancel()
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
    stop: StopSwitch,
    recall: LoreRecall | None = None,
) -> None:
    """
    모델을 부르고, 흘려보내고, 저장하고, 맡긴다. 응답과 따로 도는 작업이다. 사람이 끊어도 끝까지 돈다.
    부르기 전에 로어북을 뜻으로 찾아 카드에 더한다(recall 이 있을 때).

    사람이 멈추면(stop) 받은 만큼 저장하고 맡긴다(받은 조각이 있으면 partial 로 확정, 없으면 반환).
    서버가 꺼지며 멈추면 받은 만큼 저장하고 멈춘다. 맡기는 것은 다음에 뜬 서버의 정리 작업이 한다.
    저장하다 실패하면(DB 가 없다) 응답에 실패를 알리고 끝낸다.
    차례와 홀드는 오래되면 풀린다(GENERATION_STALE, 정리 작업).
    """
    start = await with_recalled_lore(recall, start)
    collector = collector_for(start, relay)
    result = await stoppable_call(session_factory, route, start, params, collector, clock, stop)
    try:
        answer = await save_result(session_factory, start, result, clock())
    except Exception:
        logger.exception('답을 저장하지 못했습니다', extra={'generation_id': str(start.generation_id)})
        relay.close(failed_frame(SERVER_ERROR))
        return
    relay.close(done_frame(answer) if answer is not None else failed_frame(result.error_code or SERVER_ERROR))
    await settle_turn(session_factory, billing, start.generation_id, clock())
