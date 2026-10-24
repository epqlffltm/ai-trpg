# chat-server/app/turns/service.py

"""
말 한 번(docs/architecture/chat-server.md 의 "한 번의 말이 지나가는 길"). 아래 차례의 각 줄이 함수 하나다.

  응답을 시작하기 전(실패하면 HTTP 의 오류로 답한다)
    1. begin_turn: 대화와 모델을 보고, 차례를 잡고(한 대화 한 생성), 사람의 말과 기록(pending)을 한 트랜잭션에 저장한다.
       모델에 보낼 메시지도 여기서 만든다(app/turns/prompt.py).
       그 뒤로 ORM 객체를 들고 다니지 않는다(app/turns/values.py)
    2. route_turn: 모델을 부를 provider 를 고른다. 키가 없거나 쓸 수 없는 모델이면 거절한다
    3. hold_turn: 홀드를 건다. 걸리지 않으면(모자람, 팔지 않음, 결제 서버가 죽음) 거절한다
       거절되면 decline_turn 이 차례를 놓고 기록을 declined 로 둔다. 사람의 말은 남는다(말은 저장하되 생성하지 않는다)
  응답을 시작한 뒤(따로 도는 작업. 사람이 끊어도 끝까지 돈다)
    4. call_model: 모델을 부르고 글을 흘려보낸다(conversation_core/relay.py)
    5. save_result: 받은 만큼 답을 저장하고 차례를 놓는다.
       다 받았으면 complete, 길이에서 잘렸거나 도중에 끊겼으면 partial. 글자 없이 실패했으면 답을 저장하지 않는다
    6. settle_turn: 답이 있으면 확정, 없으면 반환한다.
       결제 서버가 받지 못하면 정리 작업이 마저 한다(app/turns/settler.py)

DB 접근, 바깥 호출(공급자, 결제 서버), 응답 만들기를 한 함수에 섞지 않는다. 바깥을 부르는 동안 DB 의 연결을 쥐지 않는다.
같은 실패를 저절로 되풀이하지 않는다(사람이 다시 보낸다). 다른 모델로 넘어가지 않는다.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from ai_core.costs import charge_of
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError
from ai_core.routing import MODEL_UNAVAILABLE as ROUTE_MODEL_UNAVAILABLE
from ai_core.routing import Route
from conversation_core import continuation
from conversation_core.changes import parse_changes
from conversation_core.continuation import OverlapTrim, continued_text
from conversation_core.expressions import ExpressionHead, match_expression, split_expression
from conversation_core.lorebook import chosen_entries, query_text, ranked, render_lore, with_recalled
from conversation_core.relay import Relay
from conversation_core.suggestions import MarkerHold, parse_suggestions, split_answer
from conversation_core.window import Turn, select_window
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assets.schemas import CharacterDocument
from app.billing.client import Billing
from app.billing.prices import chat_code
from app.catalog import repository as catalog
from app.catalog.choice import is_choosable
from app.catalog.models import AiModel
from app.conversations import repository as conversations
from app.conversations.models import (
    Conversation,
    ConversationPersona,
    ImportedCharacter,
    Message,
    MessageStatus,
    Role,
)
from app.conversations.service import (
    GENERATION_STALE,
    ConversationBusyError,
    MessageNotFoundError,
    ModelUnavailableError,
    NotEditableError,
    get_conversation,
)
from app.core.dependencies import Viewer
from app.gallery import repository as gallery
from app.lore.recall import LoreRecall
from app.lore.texts import keyed_entries
from app.memory import repository as memory_store
from app.memory import service as memory
from app.memory.service import render_memory
from app.memory.summaries import latest_summary, overflow, render_story
from app.ratings import Rating, allowed_ratings
from app.turns import charging, repository
from app.turns.charging import HoldDeclined, Settled, Settlement
from app.turns.frames import delta_frame, done_frame, expression_frame, failed_frame
from app.turns.models import DUE_STATUSES, BillingStatus, Generation, Outcome
from app.turns.prompt import CharacterCard, PersonaCard, build_messages, render_card, with_lore
from app.turns.providers import Router
from app.turns.values import LorePlan, PromptOptions, SavedMessage, TurnResult, TurnStart, WorldBase
from app.world import repository as world_states
from app.world import service as world
from app.world.actions import perform
from app.world.proposals import Applied, apply_proposals, offer_of, render_offer
from app.world.scene import render_scene
from app.world.scenes import find_scene
from app.world.schemas import Action, GiveAction
from app.world.sprites import expression_images
from app.world.state import WorldState

logger = logging.getLogger(__name__)

# 공급자를 부르지 못한 까닭(키가 없다, 부르는 코드가 없다)의 이름. 사람에게는 잠시 뒤에 다시 하라고 알린다
PROVIDER_UNAVAILABLE = 'provider_unavailable'
# 서버가 꺼지며 멈춘 생성, 사람이 멈춘 생성, 예상하지 못한 오류, 글자 없이 끝난 답의 까닭
CANCELLED = 'cancelled'
STOPPED = 'stopped'
SERVER_ERROR = 'server_error'
EMPTY = 'empty'


class ModelRequiredError(Exception):
    """대화에 모델이 없다. 먼저 고른다(409)."""


class NotRegenerableError(Exception):
    """다시 쓸 수 없는 말이다(422). 사람의 말에 답한 것이 아닌 말(캐릭터의 인사말)이다."""


class NotContinuableError(Exception):
    """이어 쓸 수 없는 말이다(422). 끊긴 캐릭터의 답(partial)이 아니거나, 지금 가지의 끝이 아니다."""


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
    모델이 흘려 주는 글을 모으면서 응답으로 넘긴다. 도중에 끊겨도 받은 만큼을 안다.

    본문만 흘린다. 다음 답 추천의 표식 뒤는 흘리지 않는다(conversation_core/suggestions.py 의 MarkerHold).
    고를 수 있는 표정이 있으면 맨 앞의 표정의 표식을 떼고(conversation_core/expressions.py), 고른 표정을 먼저 알린다.
    """

    relay: Relay
    hold: MarkerHold = field(default_factory=MarkerHold)
    # 이어서 출력이면 되풀이한 앞부분을 떼는 것(conversation_core/continuation.py). 표식을 찾기 전에 거친다
    trim: OverlapTrim | None = None
    # 고를 수 있는 표정과 그 캐릭터 그림. 비어 있으면 표정의 표식을 찾지 않는다
    expressions: Mapping[str, uuid.UUID] = field(default_factory=dict)
    head: ExpressionHead | None = None
    announced: bool = False

    def __call__(self, piece: str) -> None:
        self.push(self.hold.feed(self.headless(self.trim.feed(piece) if self.trim is not None else piece)))

    def headless(self, text: str) -> str:
        """맨 앞의 표정의 표식을 떼고 나머지를 돌려준다. 표정이 정해지면 한 번 알린다."""
        if self.head is None:
            return text
        rest = self.head.feed(text)
        self.announce()
        return rest

    def announce(self) -> None:
        """모델이 고를 수 있는 표정을 골랐으면 그 표정과 캐릭터 그림을 한 번 알린다."""
        if self.announced or self.head is None or not self.head.decided:
            return
        self.announced = True
        expression = match_expression(self.head.raw, self.expressions)
        if expression is not None:
            self.relay.push(expression_frame(expression, self.expressions[expression]))

    def push(self, text: str) -> None:
        """본문의 조각을 응답으로. 빈 조각은 보내지 않는다."""
        if text:
            self.relay.push(delta_frame(text))

    def finish(self) -> str:
        """끝났다. 붙잡아 둔 본문을 마저 흘리고, 지금까지 흘린 본문을 돌려준다."""
        if self.trim is not None:
            self.push(self.hold.feed(self.headless(self.trim.release())))
        if self.head is not None:
            self.push(self.hold.feed(self.head.release()))
            self.announce()
        self.push(self.hold.release())
        return self.hold.body()


def collector_for(start: TurnStart, relay: Relay) -> Collector:
    """말 한 번의 Collector. 이어서 출력이면 끊긴 답과 겹친 앞부분을 뗀다. 고를 수 있는 표정이 있으면 표식을 찾는다."""
    trim = OverlapTrim(start.continued.content) if start.continued is not None else None
    head = ExpressionHead() if start.expressions else None
    return Collector(relay, trim=trim, expressions=start.expressions, head=head)


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
        suggestions=tuple(message.suggestions or ()),
        event_scene=message.event_scene,
        expression=message.expression,
        changes=tuple(message.changes or ()),
    )


def character_card(character: ImportedCharacter) -> CharacterCard:
    """판의 사본에서 카드의 캐릭터 칸."""
    document = CharacterDocument.model_validate(character.document)
    return CharacterCard(
        name=document.name,
        intro_html=document.intro_html,
        speech_examples=document.speech_examples,
        age=document.age,
        gender=document.gender,
    )


def persona_card(persona: ConversationPersona | None) -> PersonaCard | None:
    """페르소나의 사본에서 카드의 사용자 칸. 페르소나 없이 시작한 대화면 None."""
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


@dataclass(frozen=True)
class CardExtras:
    """
    카드에 더하는 블록들. story 는 창 밖으로 밀려난 앞부분의 요약, memory 는 기억 메모(app/memory),
    scene 은 장소와 소지품(app/world)이다. 없으면 None.
    expressions 는 모델이 고를 수 있는 표정과 그 캐릭터 그림이다(없으면 표정을 고르지 않는다).
    offer 는 모델이 제안할 수 있는 상태의 변화의 지시(없으면 None), world 는 그 바탕인 판과 상태다(#676).
    lore 는 고른 로어북의 항목이다(없으면 None, #672). lore_plan 은 뜻으로 찾아 더할 바탕이다(로어북이 없으면 None).
    """

    story: str | None
    memory: str | None
    scene: str | None
    expressions: Mapping[str, uuid.UUID] = field(default_factory=dict)
    offer: str | None = None
    world: WorldBase | None = None
    lore: str | None = None
    lore_plan: LorePlan | None = None


def prompt_for(
    conversation: Conversation,
    character: ImportedCharacter,
    persona: ConversationPersona | None,
    path: list[Message],
    options: PromptOptions,
    extras: CardExtras,
    closing: str | None = None,
) -> list[ChatMessage]:
    """
    모델에 보낼 메시지. 카드와, 지금 가지의 말들 가운데 context_chars 안에 드는 최근 것들이다.
    지난 말은 본문(content)만 보낸다. 선택지(suggestions)는 보내지 않는다.
    extras 는 기억 메모와 가지 끝의 장소와 소지품이다. 카드에 들어간다.
    closing 이 있으면 맨 끝에 사람의 차례로 붙인다(이어서 출력의 지시). 창은 늘 그것을 넣는다.
    """
    card = render_card(
        character_card(character),
        persona_card(persona),
        conversation.start_situation,
        options.suggestions,
        scene=extras.scene,
        memory=extras.memory,
        story=extras.story,
        expressions=list(extras.expressions),
        changes=extras.offer,
        lore=extras.lore,
    )
    turns = [Turn(message.role, message.content) for message in path]
    if closing is not None:
        turns.append(Turn(Role.USER, closing))
    return build_messages(card, select_window(turns, options.context_chars))


def lore_plan_of(character: ImportedCharacter, document: CharacterDocument, recent: list[str]) -> LorePlan | None:
    """
    판의 로어북에서 상시와 키워드로 고른 것과, 뜻으로 찾아 더할 바탕. 로어북의 항목이 없으면 None.
    recent 는 최근 말들(오래된 것부터, 이번에 더하는 말까지)이다.
    """
    keyed = keyed_entries(document)
    if not keyed:
        return None
    entries = tuple(item.entry for item in keyed)
    order = tuple(ranked(entries, recent))
    return LorePlan(
        character_id=character.id,
        entries=entries,
        keys=tuple(item.key for item in keyed),
        ranked=order,
        query=query_text(recent),
        block=render_lore(chosen_entries(entries, order)),
    )


async def extras_on(
    session: AsyncSession,
    conversation: Conversation,
    character: ImportedCharacter,
    path: list[Message],
    context_chars: int,
    state: WorldState | None = None,
    scene_id: str | None = None,
    choose_expression: bool = True,
    incoming: Sequence[str] = (),
) -> CardExtras:
    """
    가지(path)의 끝에서 카드에 더할 블록들. state 를 주면 그 상태로 장소와 소지품을 적는다(행동한 뒤의 상태).
    요약은 창(context_chars)에 들지 못하고 밀려난 말 가운데 가장 뒤의 것이다.
    scene_id 는 이번 답에 붙는 이벤트 씬이다. 있으면 그 장면을 "[지금]" 에 적는다(그림과 글이 어긋나지 않게).
    choose_expression 이면 지금 차림에서 고를 수 있는 표정을 함께 준다(이어서 출력은 끊긴 답의 표정을 그대로 둔다).
    모델이 제안할 수 있는 상태의 변화(지금의 상태로 정한다)와 그 바탕도 함께 준다.
    로어북은 가지의 최근 말과 이번에 더하는 말(incoming, 아직 path 에 없다)에서 키워드를 찾아 고른다.
    """
    document = world.document_of(character)
    current = state if state is not None else await world.state_on(session, document, [m.id for m in path])
    plan = lore_plan_of(character, document, [*(message.content for message in path), *incoming])
    notes = await memory.notes_for_prompt(session, conversation.id)
    dropped = overflow(path, context_chars)
    summaries = await memory_store.summaries_on(session, [message.id for message in dropped])
    return CardExtras(
        story=render_story(latest_summary(dropped, summaries)),
        memory=render_memory(notes),
        scene=render_scene(document, current, conversation.start_hour, find_scene(document, scene_id)),
        expressions=expression_images(document, current) if choose_expression else {},
        offer=render_offer(offer_of(document, current)),
        world=WorldBase(document, current),
        lore=plan.block if plan is not None else None,
        lore_plan=plan,
    )


def require_model(conversation: Conversation, model: AiModel | None, rating: Rating, now: datetime) -> str:
    """대화의 모델의 이름표. 고르지 않았으면 ModelRequiredError, 이 대화에 쓸 수 없으면 ModelUnavailableError."""
    if conversation.model_slug is None:
        raise ModelRequiredError
    if model is None or not is_choosable(model, rating, now.date()):
        raise ModelUnavailableError
    return conversation.model_slug


def user_message(
    conversation: Conversation, parent_id: uuid.UUID | None, content: str, now: datetime, role: Role = Role.USER
) -> Message:
    """사람의 말(또는 행동 말, role action). parent_id(보통은 지금 가지의 끝) 아래에 붙는다. 아직 저장하지 않는다."""
    return Message(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        parent_id=parent_id,
        role=role,
        content=content,
        status=MessageStatus.COMPLETE,
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
        price_code=chat_code(slug),
        billing_status=BillingStatus.PENDING,
        settle_attempts=0,
    )


def result_of(
    completion: Completion,
    route: Route,
    previous: str | None = None,
    expressions: Collection[str] = (),
) -> TurnResult:
    """
    다 받은 답. 본문과 선택지로 나눈다. 길이 상한에서 잘렸으면 partial 이고 선택지는 버린다(줄이 잘렸을 수 있다).
    본문이 없으면(선택지만 썼어도) failed 다. 원가는 그날의 단가로 센다.
    다 받았으면 모델이 제안한 상태의 변화도 읽는다(받아들이는 것은 저장할 때다). 잘렸으면 버린다.
    previous 는 이어서 출력의 끊긴 답이다. 있으면 되풀이한 앞부분을 떼고 사이에 끼울 것을 붙인 뒤에 나눈다.
    expressions 가 있으면 맨 앞의 표정의 표식을 떼고 고를 수 있는 표정이면 적는다(이어서 출력에는 비어 있다).
    """
    cost, _ = charge_of(completion, route.price)
    usage = {'input_tokens': completion.input_tokens, 'output_tokens': completion.output_tokens, 'cost_usd': cost}
    text = continued_text(previous, completion.text) if previous is not None else completion.text
    raw, text = split_expression(text) if expressions else (None, text)
    expression = match_expression(raw, expressions)
    body, tail = split_answer(text)
    if not body:
        return TurnResult(text='', outcome=Outcome.FAILED, error_code=EMPTY, **usage)
    if completion.truncated:
        return TurnResult(text=body, outcome=Outcome.PARTIAL, expression=expression, **usage)
    suggestions = tuple(parse_suggestions(tail))
    return TurnResult(
        text=body,
        outcome=Outcome.COMPLETE,
        suggestions=suggestions,
        expression=expression,
        proposed=parse_changes(text),
        **usage,
    )


def failure_of(received: str, code: str) -> TurnResult:
    """도중에 실패했다. 받은 글이 있으면 partial(그만큼 저장하고 청구한다), 없으면 failed."""
    return TurnResult(text=received, outcome=Outcome.PARTIAL if received else Outcome.FAILED, error_code=code)


def answer_of(start: TurnStart, result: TurnResult, now: datetime, changes: tuple[dict, ...] = ()) -> Message | None:
    """저장할 답. 글자가 없으면 None. changes 는 받아들인 상태의 변화(칩)다. 아직 저장하지 않는다."""
    if not result.text:
        return None
    return Message(
        id=uuid.uuid4(),
        conversation_id=start.conversation_id,
        parent_id=start.user_message.id,
        role=Role.ASSISTANT,
        content=result.text,
        status=MessageStatus.PARTIAL if result.outcome == Outcome.PARTIAL else MessageStatus.COMPLETE,
        suggestions=list(result.suggestions),
        expression=result.expression,
        changes=list(changes),
        created_at=now,
    )


def accepted_of(start: TurnStart, result: TurnResult) -> Applied | None:
    """
    모델이 제안한 상태의 변화를 받아들인 결과. 판과 상태를 모르면 None.
    제안은 다 받은 답에만 있다(result_of). 잘리거나 끊긴 답은 빈 제안이라 바뀌는 것이 없다.
    """
    if start.world is None:
        return None
    return apply_proposals(start.world.document, start.world.state, result.proposed)


def log_rejected(start: TurnStart, applied: Applied | None) -> None:
    """버린 제안을 로그로 남긴다(사람에게는 보이지 않는다)."""
    if applied is not None and applied.rejected:
        logger.info(
            '모델의 제안을 버렸습니다',
            extra={'generation_id': str(start.generation_id), 'rejected': list(applied.rejected)},
        )


def extension_of(continued: SavedMessage, result: TurnResult, changes: tuple[dict, ...] = ()) -> SavedMessage | None:
    """
    이어서 출력의 결과로 바뀔 말. 이어 쓴 글이 없으면 None(끊긴 답은 그대로다).
    다 썼으면 complete 이고 선택지와 받아들인 상태의 변화(changes)가 붙는다.
    또 끊겼으면 partial 로 남아 다시 이어 쓸 수 있다.
    """
    if not result.text:
        return None
    status = MessageStatus.PARTIAL if result.outcome == Outcome.PARTIAL else MessageStatus.COMPLETE
    return replace(
        continued,
        content=continued.content + result.text,
        status=status,
        suggestions=result.suggestions,
        changes=changes,
    )


def finished_values(result: TurnResult, answer_id: uuid.UUID | None, now: datetime) -> dict[str, object]:
    """기록에 적을 결과. 답이 있으면 확정할 것, 없으면 돌려줄 것이다."""
    return {
        'billing_status': BillingStatus.CAPTURE_DUE if answer_id is not None else BillingStatus.RELEASE_DUE,
        'message_id': answer_id,
        'outcome': result.outcome,
        'error_code': result.error_code,
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


async def edited_parent(session: AsyncSession, conversation: Conversation, edit_of: uuid.UUID) -> uuid.UUID | None:
    """
    고친 말(내 말 고치기)이 붙을 자리. 고칠 사람의 말의 부모다. 새 말은 그 말의 대안(새 가지)이 되고 원본은 남는다.
    그 대화의 말이 아니면 MessageNotFoundError, 사람의 말이 아니면 NotEditableError.
    """
    original = await session.get(Message, edit_of)
    if original is None or original.conversation_id != conversation.id:
        raise MessageNotFoundError
    if original.role != Role.USER:
        raise NotEditableError
    return original.parent_id


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
    차례를 잡고 사람의 말과 기록(pending)을 저장한다. 모델에 보낼 메시지를 함께 만든다.

    새 말은 지금 가지의 끝에 붙는다. edit_of(고칠 사람의 말)가 있으면 그 말의 부모 아래에 붙는다(새 가지).
    가지의 끝은 차례를 잡은 뒤에 다시 읽는다. 그사이 가지를 바꿨어도 바꾼 곳에 붙는다.
    대화가 없으면 ConversationNotFoundError, 모델이 없으면 ModelRequiredError, 쓸 수 없으면 ModelUnavailableError,
    다른 답을 쓰는 중이면 ConversationBusyError, 고칠 말이 틀리면 MessageNotFoundError, NotEditableError.
    어느 것이든 아무것도 저장하지 않는다. 판매(결제 서버의 가격표)는 여기서 보지 않는다. 홀드를 걸 때 결제 서버가 본다.
    """
    async with session_factory() as session:
        conversation, character, persona = await get_conversation(session, viewer, conversation_id)
        model = await catalog.get_model(session, conversation.model_slug) if conversation.model_slug else None
        slug = require_model(conversation, model, Rating(character.rating), now)
        edited = await edited_parent(session, conversation, edit_of) if edit_of is not None else None
        if not await repository.lock_turn(session, conversation.id, now, GENERATION_STALE):
            raise ConversationBusyError
        await session.refresh(conversation)
        parent_id = edited if edit_of is not None else conversation.active_leaf_id
        path = await conversations.active_path(session, parent_id)
        extras = await extras_on(session, conversation, character, path, options.context_chars, incoming=[content])
        message = user_message(conversation, parent_id, content, now)
        repository.add(session, message)
        await session.flush()
        await repository.move_leaf(session, conversation.id, message.id)
        generation = new_generation(conversation, viewer.claims.user_id, message.id, slug)
        repository.add(session, generation)
        await session.commit()
    return TurnStart(
        conversation_id=conversation.id,
        generation_id=generation.id,
        owner_id=viewer.claims.user_id,
        model_slug=slug,
        reference=generation.reference,
        price_code=generation.price_code,
        user_message=saved(message),
        messages=prompt_for(conversation, character, persona, [*path, message], options, extras),
        expressions=extras.expressions,
        world=extras.world,
        lore=extras.lore_plan,
    )


def action_messages(
    conversation: Conversation, parent_id: uuid.UUID | None, text: str, words: str | None, now: datetime
) -> list[Message]:
    """
    행동 말과(덧붙인 한마디가 있으면) 그 뒤의 사람의 말. 행동 말이 parent_id 아래에, 한마디가 행동 말 아래에 붙는다.
    한마디는 행동 말보다 1 마이크로초 뒤에 생긴 것으로 둔다(가지의 끝을 생긴 차례로 고른다).
    """
    action = user_message(conversation, parent_id, text, now, Role.ACTION)
    if words is None:
        return [action]
    return [action, user_message(conversation, action.id, words, now + timedelta(microseconds=1))]


async def begin_action(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    conversation_id: uuid.UUID,
    action: Action,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    행동한다(지도에서 이동, 물건 쓰기, 건네기). 행동 말(role action)과 그 뒤의 상태, 기록(pending)을 저장한다.
    건넬 때 한마디를 덧붙였으면 행동 말 아래에 사람의 말로 붙는다. 이어서 모델이 반응을 쓴다(한 번 청구한다).

    할 수 있는지는 차례를 잡은 뒤 가지 끝의 상태로 본다(app/world/actions.py). 안 되면 ActionRefusedError 이고
    아무것도 저장하지 않는다(차례도 놓는다). 나머지는 begin_turn 과 같다.
    홀드가 거절되면 행동 말(과 한마디)은 남는다(사람의 말과 같다).
    """
    async with session_factory() as session:
        conversation, character, persona = await get_conversation(session, viewer, conversation_id)
        model = await catalog.get_model(session, conversation.model_slug) if conversation.model_slug else None
        slug = require_model(conversation, model, Rating(character.rating), now)
        if not await repository.lock_turn(session, conversation.id, now, GENERATION_STALE):
            raise ConversationBusyError
        await session.refresh(conversation)
        path = await conversations.active_path(session, conversation.active_leaf_id)
        document = world.document_of(character)
        before = await world.state_on(session, document, [message.id for message in path])
        performed = perform(document, before, action, conversation.start_hour)
        words = action.words if isinstance(action, GiveAction) else None
        added = action_messages(conversation, conversation.active_leaf_id, performed.text, words, now)
        shown = performed.revealed.shown
        added[-1].event_scene = shown.id if shown is not None else None
        for message in added:
            repository.add(session, message)
        await session.flush()
        world_states.add_state(session, added[0].id, performed.state)
        await gallery.add_unlocks(session, viewer.claims.user_id, character.source_id, performed.revealed.collected)
        await repository.move_leaf(session, conversation.id, added[-1].id)
        generation = new_generation(conversation, viewer.claims.user_id, added[-1].id, slug)
        repository.add(session, generation)
        extras = await extras_on(
            session,
            conversation,
            character,
            path,
            options.context_chars,
            performed.state,
            added[-1].event_scene,
            incoming=[message.content for message in added],
        )
        await session.commit()
    return TurnStart(
        conversation_id=conversation.id,
        generation_id=generation.id,
        owner_id=viewer.claims.user_id,
        model_slug=slug,
        reference=generation.reference,
        price_code=generation.price_code,
        user_message=saved(added[-1]),
        messages=prompt_for(conversation, character, persona, [*path, *added], options, extras),
        expressions=extras.expressions,
        action=saved(added[0]) if len(added) > 1 else None,
        world=extras.world,
        lore=extras.lore_plan,
    )


def answered_scene(path: list[Message]) -> str | None:
    """이어 쓰는 답(가지의 끝)이 답하는 말의 이벤트 씬. 그 말은 끝의 바로 앞이다."""
    return path[-2].event_scene if len(path) >= 2 else None


def answered_message(target: Message) -> uuid.UUID:
    """
    다시 쓸 답의 부모(사람의 말). 캐릭터의 답이면 그 부모, 사람의 말이면 그 말 자신이다(답을 못 받은 말에 다시 답한다).

    부모가 없는 캐릭터의 말(인사말)은 다시 쓰지 않는다(NotRegenerableError). 카드가 쓴 글이지 모델이 쓴 글이 아니다.
    """
    if target.role in (Role.USER, Role.ACTION):
        return target.id
    if target.parent_id is None:
        raise NotRegenerableError
    return target.parent_id


async def begin_regenerate(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    message_id: uuid.UUID,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    그 말에 다시 답할 차례를 잡는다. 새 답은 같은 부모 아래의 대안이다. 앞의 답은 그대로 남는다.

    기록(pending)만 저장한다. 사람의 말은 새로 저장하지 않는다.
    가지의 끝은 옮기지 않는다. 새 답을 저장할 때 옮긴다(save_result).
    그래서 거절되거나 글자 없이 실패하면 앞의 답이 그대로 보인다.
    말이 없으면 MessageNotFoundError, 다시 쓸 수 없는 말이면 NotRegenerableError. 나머지는 begin_turn 과 같다.
    """
    async with session_factory() as session:
        found = await conversations.find_visible_message(
            session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
        )
        if found is None:
            raise MessageNotFoundError
        target, (conversation, character, persona) = found
        parent_id = answered_message(target)
        model = await catalog.get_model(session, conversation.model_slug) if conversation.model_slug else None
        slug = require_model(conversation, model, Rating(character.rating), now)
        if not await repository.lock_turn(session, conversation.id, now, GENERATION_STALE):
            raise ConversationBusyError
        path = await conversations.active_path(session, parent_id)
        extras = await extras_on(
            session, conversation, character, path, options.context_chars, scene_id=path[-1].event_scene
        )
        generation = new_generation(conversation, viewer.claims.user_id, parent_id, slug)
        repository.add(session, generation)
        await session.commit()
    return TurnStart(
        conversation_id=conversation.id,
        generation_id=generation.id,
        owner_id=viewer.claims.user_id,
        model_slug=slug,
        reference=generation.reference,
        price_code=generation.price_code,
        user_message=saved(path[-1]),
        messages=prompt_for(conversation, character, persona, path, options, extras),
        expressions=extras.expressions,
        world=extras.world,
        lore=extras.lore_plan,
    )


def require_continuable(target: Message) -> uuid.UUID:
    """
    이어 쓸 끊긴 답의 부모(답한 사람의 말). 끊긴 답(partial)이 아니면 NotContinuableError.
    partial 은 캐릭터의 답에만 있다(사람의 말과 인사말은 complete 다). 그 답에는 늘 부모가 있다.
    """
    if target.status != MessageStatus.PARTIAL or target.parent_id is None:
        raise NotContinuableError
    return target.parent_id


async def begin_continue(
    session_factory: async_sessionmaker[AsyncSession],
    viewer: Viewer,
    message_id: uuid.UUID,
    options: PromptOptions,
    now: datetime,
) -> TurnStart:
    """
    끊긴 답을 이어 쓸 차례를 잡는다. 기록(pending)만 저장한다. 새 글은 저장할 때 그 말 끝에 붙는다(save_result).

    지금 가지의 끝인 끊긴 답만 이어 쓴다. 그 뒤에 말이 붙었거나 다른 가지를 보고 있으면 NotContinuableError.
    가지의 끝은 차례를 잡은 뒤에 다시 읽는다. 차례를 쥔 동안에는 가지를 바꾸지 못한다(conversations 의 choose_branch).
    말이 없으면 MessageNotFoundError. 나머지는 begin_turn 과 같다.
    """
    async with session_factory() as session:
        found = await conversations.find_visible_message(
            session, viewer.claims.user_id, allowed_ratings(viewer.claims), message_id
        )
        if found is None:
            raise MessageNotFoundError
        target, (conversation, character, persona) = found
        parent_id = require_continuable(target)
        model = await catalog.get_model(session, conversation.model_slug) if conversation.model_slug else None
        slug = require_model(conversation, model, Rating(character.rating), now)
        if not await repository.lock_turn(session, conversation.id, now, GENERATION_STALE):
            raise ConversationBusyError
        await session.refresh(conversation)
        if conversation.active_leaf_id != target.id:
            raise NotContinuableError
        path = await conversations.active_path(session, target.id)
        extras = await extras_on(
            session,
            conversation,
            character,
            path,
            options.context_chars,
            scene_id=answered_scene(path),
            choose_expression=False,
        )
        generation = new_generation(conversation, viewer.claims.user_id, parent_id, slug)
        repository.add(session, generation)
        await session.commit()
    return TurnStart(
        conversation_id=conversation.id,
        generation_id=generation.id,
        owner_id=viewer.claims.user_id,
        model_slug=slug,
        reference=generation.reference,
        price_code=generation.price_code,
        user_message=saved(path[-2]),
        messages=prompt_for(conversation, character, persona, path, options, extras, continuation.instruction()),
        continued=saved(target),
        world=extras.world,
        lore=extras.lore_plan,
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
        return failure_of(collector.finish(), str(error))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            '모델을 부르다 예상하지 못한 오류가 났습니다', extra={'generation_id': str(start.generation_id)}
        )
        return failure_of(collector.finish(), SERVER_ERROR)
    collector.finish()
    previous = start.continued.content if start.continued is not None else None
    return result_of(completion, route, previous, start.expressions)


async def store_answer(
    session: AsyncSession, start: TurnStart, result: TurnResult, now: datetime
) -> SavedMessage | None:
    """
    답을 세션에 적는다(커밋하지 않는다). 저장한 답이나, 글이 없으면 None.
    보통은 새 말이고, 이어서 출력이면 끊긴 답을 바꾼다.
    모델이 제안한 상태의 변화를 받아들였으면 칩을 답에 붙이고 바뀐 상태를 그 답에 적는다(가지마다 따로다).
    """
    applied = accepted_of(start, result)
    log_rejected(start, applied)
    changes = applied.changes if applied is not None else ()
    if start.continued is not None:
        stored = extension_of(start.continued, result, changes)
        if stored is not None:
            await repository.extend_message(
                session, stored.id, stored.content, stored.status, list(stored.suggestions), list(stored.changes)
            )
    else:
        answer = answer_of(start, result, now, changes)
        if answer is None:
            return None
        repository.add(session, answer)
        await session.flush()
        stored = saved(answer)
    if stored is not None and changes:
        world_states.add_state(session, stored.id, applied.state)
    return stored


async def save_result(
    session_factory: async_sessionmaker[AsyncSession], start: TurnStart, result: TurnResult, now: datetime
) -> SavedMessage | None:
    """답을 저장하고(있으면) 차례를 놓고 기록에 결과를 적는다. 한 트랜잭션이다. 저장한 답이나 None."""
    async with session_factory() as session:
        answer = await store_answer(session, start, result, now)
        if answer is not None:
            await repository.finish_turn(session, start.conversation_id, answer.id)
        else:
            await repository.unlock_turn(session, start.conversation_id)
        answer_id = answer.id if answer is not None else None
        await repository.move_billing(
            session, start.generation_id, frozenset({BillingStatus.HELD}), finished_values(result, answer_id, now)
        )
        await session.commit()
    return answer


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


@dataclass
class StopSwitch:
    """
    사람이 멈추는 스위치. 모델을 부르는 일(call)만 멈춘다. 저장과 확정은 멈추지 않는다.

    서버가 꺼지며 멈추는 것(작업 전체의 취소)과 가른다. 사람이 멈추면 받은 만큼 저장하고 바로 확정한다.
    """

    requested: bool = False
    call: asyncio.Task | None = None

    def request(self) -> bool:
        """
        멈춘다. 모델을 부르기 전이거나 부르는 중이었으면 True, 이미 다 받았으면 False.
        부르기 전에 멈추면 부르지 않는다(run_generation).
        """
        if self.call is not None and self.call.done():
            return False
        self.requested = True
        if self.call is not None:
            self.call.cancel()
        return True


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

    서버가 꺼지며 멈추면(이 작업의 취소) 부르는 일도 끊고, 받은 만큼 저장한 뒤 그대로 올린다.
    """
    if stop.requested:
        return failure_of('', STOPPED)
    stop.call = asyncio.create_task(call_model(route, start, params, collector))
    try:
        return await stop.call
    except asyncio.CancelledError:
        if stop.requested and not asyncio.current_task().cancelling():
            return failure_of(collector.finish(), STOPPED)
        stop.call.cancel()
        await save_result(session_factory, start, failure_of(collector.finish(), CANCELLED), clock())
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

    사람이 멈추면(stop) 받은 만큼 저장하고 맡긴다(받은 글이 있으면 partial 로 확정, 없으면 반환).
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
