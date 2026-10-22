# chat-server/app/conversations/models.py

"""
대화의 테이블(docs/architecture/chat-server.md 의 "데이터의 모양"). 스키마는 chat 이다.

  - characters: asset 서버에서 가져온 캐릭터의 판의 사본. 사람마다, 판마다 하나다. 그 사람의 대화들이 함께 쓴다
  - conversations: 대화 하나. 새로 시작할 때마다 하나. 지우면 지운 시각만 적는다. 대화의 모델을 가리킨다(ai_models)
  - conversation_personas: 대화마다 가져온 페르소나의 사본. 페르소나 없이 시작한 대화에는 없다
  - messages: 말 하나. 트리다(parent_id). parent_id 가 같은 것이 서로의 대안(다시 생성, 고친 말)이다

asset 서버의 행을 가리키는 칸(source_id)에는 외래 키를 걸지 않는다. 다른 서버의 DB 다.
사본은 가져온 뒤 바뀌지 않는다. 원본이 바뀌어도 그대로이고, 새 판이나 새 설정을 쓸지는 사람이 고른다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.ratings import Rating


class Role(enum.StrEnum):
    """누가 한 말인가. 행동(지도에서 이동, 물건 건네기)은 그 단계에서 더한다."""

    USER = 'user'
    ASSISTANT = 'assistant'


class MessageStatus(enum.StrEnum):
    """말이 어디까지 됐는가. partial 은 끊긴 말("이어서"를 보인다), failed 는 글자 하나 없이 실패한 생성이다."""

    COMPLETE = 'complete'
    PARTIAL = 'partial'
    FAILED = 'failed'


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """칸의 값이 그 목록 안에 있다는 CHECK 의 글자."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


class ImportedCharacter(Base):
    """
    asset 서버에서 가져온 캐릭터의 판 하나의 사본. 사람마다, 판마다 하나다.

    같은 판으로 대화를 여러 번 시작해도 사본은 하나다(owner_id, source_id, version 이 고유).
    사람마다 두는 것은 탈퇴할 때 그 사람의 것만 지우기 위해서다. 판의 문서는 받은 그대로(JSON) 둔다.
    """

    __tablename__ = 'characters'
    __table_args__ = (
        UniqueConstraint('owner_id', 'source_id', 'version', name='uq_characters_owner_source_version'),
        CheckConstraint(one_of('rating', Rating), name='rating_allowed'),
        CheckConstraint('version >= 1', name='version_positive'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 가져온 사람. 인증 서버의 public_id 다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # asset 서버의 캐릭터 id 와 판의 번호
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    # 목록에서 문서를 열지 않고 보이고 거르려고 문서에서 꺼내 둔다
    name: Mapped[str] = mapped_column(Text)
    rating: Mapped[str] = mapped_column(String(10))
    # 판의 문서(app/assets/schemas.py 의 CharacterDocument). 받은 그대로다
    document: Mapped[dict] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    """
    대화 하나. 캐릭터의 판 하나와, 시작할 때 고른 시작 상황을 갖는다.

    active_leaf_id 는 지금 보고 있는 가지의 끝 말이다. 읽을 때 거기서 뿌리까지 거슬러 올라간다.
    인사말이 없는 캐릭터면 첫 말이 없어 비어 있다.
    """

    __tablename__ = 'conversations'
    __table_args__ = (
        # 내 대화 목록: 최근에 말한 것부터
        Index('ix_conversations_owner_updated', 'owner_id', 'updated_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # 대화가 쓰는 판의 사본. 대화가 남아 있는 동안 사본을 지우지 못한다
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('characters.id', ondelete='RESTRICT'), index=True)
    title: Mapped[str] = mapped_column(Text)
    # 대화의 모델(app/catalog/models.py 의 이름표). 고르지 않았으면 비어 있다
    # (처음 시작한 대화, 지난번 모델을 쓸 수 없을 때). 모델은 지우지 않으므로 RESTRICT 다.
    # 은퇴하거나 꺼져도 가리킨 채로 두고, 화면이 다시 고르게 한다(몰래 바꾸지 않는다).
    # 색인은 "이 모델을 쓰는 대화"를 찾는 데 쓴다(모델이 끝날 때 알릴 사람)
    model_slug: Mapped[str | None] = mapped_column(
        ForeignKey('ai_models.slug', ondelete='RESTRICT'), index=True, default=None
    )
    # 고른 시작 상황. 제목은 목록에, 상황은 모델에 간다. 판의 것을 복사해 둔다
    start_title: Mapped[str] = mapped_column(Text)
    start_situation: Mapped[str] = mapped_column(Text)
    # 지금 보고 있는 가지의 끝. 말과 대화가 서로 가리키므로 외래 키는 표를 다 만든 뒤에 건다(use_alter)
    active_leaf_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('messages.id', ondelete='SET NULL', use_alter=True, name='fk_conversations_active_leaf_id_messages'),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 지운 시각. 비어 있으면 지우지 않은 것이다. 지운 대화는 목록과 읽기에 나오지 않는다
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ConversationPersona(Base):
    """
    대화에 가져온 페르소나의 사본. asset 서버의 지금 revision 과 다르면 "새 설정으로 바꾸기"를 보인다.

    대화마다 하나다. 대화를 지워도(지운 시각) 남는다. 대화의 행이 지워질 때 함께 지워진다.
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

    본문(content)에는 사람에게 보이는 글만 둔다. 다음 답 선택지는 그 단계에서 따로 칸을 둔다.
    """

    __tablename__ = 'messages'
    __table_args__ = (
        CheckConstraint(one_of('role', Role), name='role_allowed'),
        CheckConstraint(one_of('status', MessageStatus), name='status_allowed'),
        # 한 말의 대안들(같은 부모의 자식들)을 찾는다
        Index('ix_messages_conversation_parent', 'conversation_id', 'parent_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), default=None)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=MessageStatus.COMPLETE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
