# asset-server/app/characters/models.py

"""
캐릭터와 그 판의 테이블 모델(#567). chat 의 상대가 되는 캐릭터다(docs/architecture/asset-server.md 의 "게시와 판").

  - 캐릭터(Character)는 초안이다. 만든 사람이 고친다.
  - 게시하면 판(CharacterVersion)이 생긴다. 판은 그때의 초안을 굳힌 문서이고 바뀌지 않는다. 번호가 1 부터 오른다.
  - 쓰는 서비스(chat)는 대화를 시작할 때 판 하나를 가져가 복사해 고정한다. 새 판이 나와도 알리기만 한다.
첫 칸은 대화에 필요한 핵심만이다(2026-10-21 유저 결정). 호감도의 규칙, 의복과 물건, 지도, 일러스트는
chat 이 그 단계(장소와 소지품)에 갈 때 판의 형식을 올려 더한다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.ratings import Rating

# 이름. 계정 페르소나, TRPG 의 캐릭터와 같다
CHARACTER_NAME_MAX_LENGTH = 50
# 인사말(대화를 열 때 캐릭터가 먼저 하는 말)과 말투 예시. 모델이 읽는다
CHARACTER_GREETING_MAX_LENGTH = 2000
CHARACTER_SPEECH_MAX_LENGTH = 2000
# 나이와 성별. 적어 두는 글이다. 거르거나 막지 않는다
CHARACTER_AGE_MAX_LENGTH = 20
CHARACTER_GENDER_MAX_LENGTH = 20
# 태그. 목록에서 찾을 때 쓴다
CHARACTER_MAX_TAGS = 10
CHARACTER_TAG_MAX_LENGTH = 20
# 시작 상황. 대화를 열 때 하나를 고른다
CHARACTER_MAX_STARTS = 5
START_TITLE_MAX_LENGTH = 30
START_SITUATION_MAX_LENGTH = 2000
# 판의 변경 내용. 사람이 읽는다. TRPG 의 판과 같다
VERSION_NOTE_MAX_LENGTH = 500


class Visibility(enum.StrEnum):
    """누구에게 보이는가. 비공개는 만든 사람만, 공개는 게시한 판이 있으면 목록에 나온다."""

    PRIVATE = 'private'
    PUBLIC = 'public'


class Character(Base):
    """
    캐릭터의 초안. 만든 사람만 보고 고친다.

    latest_version 과 published_at 은 마지막으로 게시한 판의 번호와 시각이다. 게시한 적이 없으면 비어 있다.
    공개 목록이 판을 뒤지지 않고 이 칸으로 거르고 줄 세운다.
    """

    __tablename__ = 'characters'
    __table_args__ = (
        CheckConstraint(f"rating IN ('{Rating.ALL}', '{Rating.ADULT}')", name='rating_allowed'),
        CheckConstraint(f"visibility IN ('{Visibility.PRIVATE}', '{Visibility.PUBLIC}')", name='visibility_allowed'),
        CheckConstraint(f'cardinality(tags) <= {CHARACTER_MAX_TAGS}', name='tags_count'),
        CheckConstraint('(latest_version IS NULL) = (published_at IS NULL)', name='published_paired'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 만든 사람. 인증 서버의 public_id 다. "내 캐릭터들"을 찾는 일이 많아 색인을 건다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    name: Mapped[str] = mapped_column(String(CHARACTER_NAME_MAX_LENGTH))
    # 소개(HTML). 초안에는 쓴 그대로 둔다. 거르는 것은 게시할 때다(app/content/html.py). 고친 글이 사라지지 않게
    intro_html: Mapped[str] = mapped_column(Text, default='', server_default='')
    greeting: Mapped[str] = mapped_column(Text, default='', server_default='')
    speech_examples: Mapped[str] = mapped_column(Text, default='', server_default='')
    age: Mapped[str] = mapped_column(String(CHARACTER_AGE_MAX_LENGTH), default='', server_default='')
    gender: Mapped[str] = mapped_column(String(CHARACTER_GENDER_MAX_LENGTH), default='', server_default='')
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(CHARACTER_TAG_MAX_LENGTH)), default=list, server_default='{}')
    # 시작 상황들. [{"title", "situation"}]. 모양은 schemas.Start 가 정한다. 캐릭터에 딸린 짧은 목록이라 문서로 둔다
    starts: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    # 대표 그림의 id. 그림(#566)이 생기기 전이라 외래 키를 걸지 않는다
    image_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)

    rating: Mapped[str] = mapped_column(String(10), default=Rating.ALL, server_default=Rating.ALL.value)
    visibility: Mapped[str] = mapped_column(
        String(10), default=Visibility.PRIVATE, server_default=Visibility.PRIVATE.value
    )

    latest_version: Mapped[int | None] = mapped_column(Integer, default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CharacterVersion(Base):
    """
    캐릭터의 판 하나. 게시할 때의 초안을 굳힌 문서(document)다. 바뀌지 않는다.

    캐릭터를 지우면 판도 지워진다. 이미 가져간 대화는 사본으로 돈다.
    """

    __tablename__ = 'character_versions'
    __table_args__ = (
        UniqueConstraint('character_id', 'number', name='uq_character_versions_number'),
        CheckConstraint('number >= 1', name='number_positive'),
        CheckConstraint(f"rating IN ('{Rating.ALL}', '{Rating.ADULT}')", name='rating_allowed'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('characters.id', ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(VERSION_NOTE_MAX_LENGTH), default='', server_default='')
    # 이 판의 등급. 문서의 rating 과 같다. 공개 목록이 판의 등급으로 거른다(초안의 등급을 바꿔도 다음 판까지 이 값이다)
    rating: Mapped[str] = mapped_column(String(10))
    # 굳힌 문서. 모양은 app/characters/documents.py 의 CharacterDocument 다
    document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
