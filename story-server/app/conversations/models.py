# story-server/app/conversations/models.py

"""
세션의 테이블(docs/architecture/story.md 의 "데이터의 모양"). 스키마는 story 다.

  - worlds: asset 서버에서 가져온 세계관의 판의 사본. 사람마다, 판마다 하나다. 그 사람의 세션들이 함께 쓴다
  - conversations: 세션 하나. 세계관을 새로 시작할 때마다 하나다. 지난 세션은 목록에 남는다
  - messages: 말 하나. 트리다(parent_id). parent_id 가 같은 것이 서로의 대안(다시 생성)이다
  - message_states: 말에 붙은 엔진의 상태. 상태가 바뀐 말에만 있다(app/turns/states.py)

asset 서버의 행을 가리키는 칸(source_id)에는 외래 키를 걸지 않는다. 다른 서버의 DB 다.
사본은 가져온 뒤 바뀌지 않는다. 원본이 다시 게시돼도 그 세션은 처음의 판으로 돈다. 새 판은 새 세션에서 쓴다.
세션의 끝(엔딩, 후일담)은 그것을 쓰는 조각에서 더한다(만드는 순서 5).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.ratings import Rating


class Role(enum.StrEnum):
    """
    누가 한 말인가. action 은 사람이 한 행동(이동, 시간, 선택지, 고백)이다. 행동 말은 서버가 쓴 글이다.
    assistant 는 모델의 답이다. 장면의 인물들과 서술의 말 조각(segments)으로 되어 있다.
    """

    USER = 'user'
    ASSISTANT = 'assistant'
    ACTION = 'action'


class MessageStatus(enum.StrEnum):
    """말이 어디까지 됐는가. partial 은 끊긴 답이다(chat 과 같다)."""

    COMPLETE = 'complete'
    PARTIAL = 'partial'


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 그 목록 안에 있다는 CHECK 의 글자."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


class ImportedWorld(Base):
    """
    asset 서버에서 가져온 세계관의 판 하나의 사본. 사람마다, 판마다 하나다.

    같은 판으로 세션을 여러 번 시작해도 사본은 하나다(owner_id, source_id, version 이 고유).
    사람마다 두는 것은 탈퇴할 때 그 사람의 것만 지우기 위해서다(chat 의 캐릭터 사본과 같다).
    판의 문서는 받은 그대로(JSON) 둔다. 세션마다 엔진이 문서 전체를 읽으므로 표로 쪼개지 않는다.
    """

    __tablename__ = 'worlds'
    __table_args__ = (
        UniqueConstraint('owner_id', 'source_id', 'version', name='uq_worlds_owner_source_version'),
        CheckConstraint(one_of('rating', Rating), name='rating_allowed'),
        CheckConstraint('version >= 1', name='version_positive'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 가져온 사람. 인증 서버의 public_id 다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # asset 서버의 세계관 id 와 판의 번호
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    # 목록에서 문서를 열지 않고 보이고 거르려고 문서에서 꺼내 둔다
    name: Mapped[str] = mapped_column(Text)
    rating: Mapped[str] = mapped_column(String(10))
    # 판의 문서(app/assets/schemas.py 의 WorldDocument, 받은 칸 전부). 받은 그대로다
    document: Mapped[dict] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    """
    세션 하나. 세계관의 판 하나를 가리킨다. 제목은 세계관의 이름이다.

    지우는 길은 아직 없다(지난 세션은 목록에 남는다). 지우기를 더할 때 chat 처럼 지운 시각의 칸을 함께 더한다.
    """

    __tablename__ = 'conversations'
    __table_args__ = (
        # 내 세션 목록: 최근의 것부터
        Index('ix_conversations_owner_updated', 'owner_id', 'updated_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 세션이 쓰는 판의 사본. 세션이 남아 있는 동안 사본을 지우지 못한다
    world_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('worlds.id', ondelete='RESTRICT'), index=True)
    title: Mapped[str] = mapped_column(Text)
    # 세션의 모델(app/catalog/models.py 의 이름표). 고르지 않았으면 비어 있다
    # (처음 시작한 세션, 지난번 모델을 쓸 수 없을 때). 모델은 지우지 않으므로 RESTRICT 다.
    # 은퇴하거나 꺼져도 가리킨 채로 두고, 화면이 다시 고르게 한다(몰래 바꾸지 않는다, chat 과 같다)
    model_slug: Mapped[str | None] = mapped_column(
        ForeignKey('ai_models.slug', ondelete='RESTRICT'), index=True, default=None
    )
    # 지금 보고 있는 가지의 끝. 첫 말을 보내기 전에는 비어 있다(세션을 시작할 때 말이 없다).
    # 말과 세션이 서로 가리키므로 외래 키는 표를 다 만든 뒤에 건다(use_alter)
    active_leaf_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('messages.id', ondelete='SET NULL', use_alter=True, name='fk_conversations_active_leaf_id_messages'),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 모델이 답을 쓰는 중이면 그 시작 시각. 한 세션에 한 번에 하나의 생성만 받는다(app/turns/repository.py).
    # 서버가 도중에 꺼져 남아도 오래되면(GENERATION_STALE) 다음 말이 다시 잡는다(chat 과 같다)
    generating_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ConversationPersona(Base):
    """
    세션에 가져온 계정 페르소나의 사본(chat 과 같은 모양). 모델에게 사용자가 누구인지 알린다(카드의 [사용자]).

    세션마다 하나이고, 페르소나 없이 시작한 세션에는 없다. 시작할 때 복사해 두므로 asset 서버에서 고치거나 지워도
    이 세션은 그대로다. 세션의 행이 지워질 때 함께 지워진다.
    """

    __tablename__ = 'conversation_personas'

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True
    )
    # asset 서버의 페르소나 id 와 가져올 때의 revision
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    revision: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    age: Mapped[str] = mapped_column(Text)
    gender: Mapped[str] = mapped_column(Text)
    form_of_address: Mapped[str] = mapped_column(Text)
    speech_examples: Mapped[str] = mapped_column(Text)
    personality: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    """
    말 하나. parent_id 가 같은 말들이 서로의 대안이다. 첫 말은 parent_id 가 없다.

    모델의 답은 말 조각(segments)의 목록이다: [{"speaker": 인물의 id 또는 null(서술), "text"}].
    본문(content)은 그 조각들을 표식이 붙은 줄로 쓴 것이다(app/turns/segments.py 의 render_segments).
    다음 호출의 프롬프트에 그대로 들어가 모델이 같은 모양으로 이어 쓴다. 사람의 말은 조각 없이 본문만 있다.
    cast 는 그 답을 쓸 때의 장면의 인물이다(app/engine/scene.py). 화면이 그 자리에 있던 인물을 보인다.
    edited 는 사람이 답의 글을 고쳤는가다(조각마다 글만 고친다. app/conversations/service.py 의 edit_message).
    suggestions 는 다음 답 추천의 선택지다(셋까지). 본문에 섞지 않아 다음 호출의 프롬프트에 들어가지 않는다.
    """

    __tablename__ = 'messages'
    __table_args__ = (
        CheckConstraint(one_of('role', Role), name='role_allowed'),
        CheckConstraint(one_of('status', MessageStatus), name='status_allowed'),
        # 선택지는 셋까지다(conversation_core/suggestions.py 의 MAX_SUGGESTIONS)
        CheckConstraint('cardinality(suggestions) <= 3', name='suggestions_at_most_three'),
        # 한 말의 대안들(같은 부모의 자식들)을 찾는다
        Index('ix_messages_conversation_parent', 'conversation_id', 'parent_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), default=None)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=MessageStatus.COMPLETE)
    segments: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    cast: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default='{}')
    # 행동 말에서 그 행동 뒤에 열린 이벤트와 본 엔딩(판의 id). 화면이 선택지와 엔딩을 보이고,
    # 그 행동에 다시 답할 때 같은 장면을 쓴다. 열린 것이 없으면 비어 있다
    event_id: Mapped[str | None] = mapped_column(String(40), default=None)
    ending_id: Mapped[str | None] = mapped_column(String(40), default=None)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    suggestions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageState(Base):
    """
    말에 붙은 엔진의 상태(app/engine/state.py 의 StoryState 를 JSON 으로, app/turns/states.py).
    상태가 바뀐 말에만 있다. 가지의 끝의 상태는 끝에서 뿌리 쪽으로 처음 만나는 상태다. 말이 지워지면 함께 지워진다.
    """

    __tablename__ = 'message_states'

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), primary_key=True)
    state: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
