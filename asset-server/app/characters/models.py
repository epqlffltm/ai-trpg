# asset-server/app/characters/models.py

"""
캐릭터와 그 판의 테이블 모델(#567). chat 의 상대가 되는 캐릭터다(docs/architecture/asset-server.md 의 "게시와 판").

  - 캐릭터(Character)는 초안이다. 만든 사람이 고친다.
  - 게시하면 판(CharacterVersion)이 생긴다. 판은 그때의 초안을 굳힌 문서이고 바뀌지 않는다. 번호가 1 부터 오른다.
  - 쓰는 서비스(chat)는 대화를 시작할 때 판 하나를 가져가 복사해 고정한다. 새 판이 나와도 알리기만 한다.
첫 칸은 대화에 필요한 핵심만이었다(2026-10-21 유저 결정). 장소와 길(지도), 물건과 시작 소지품은
chat 의 만드는 순서 4 에서 캐릭터에 넣었다(2026-10-22 유저 결정, 판의 형식 2).
호감도(보이는 방식, 시작 값, 단계, 오르내리는 규칙)는 판의 형식 3 에서 더했다(2026-10-22).
시작 상황의 시작 시각과 장소의 시간대 배경은 판의 형식 4 에서 더했다(2026-10-22, #668).
상대의 시작 차림, 일러스트는 chat 이 그 단계에 갈 때 판의 형식을 올려 더한다.
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
# 장소, 물건의 id. 캐릭터 안에서만 고유한 짧은 글이다. 길과 시작 소지품이 가리키고, chat 의 상태가 적어 둔다.
# 판이 바뀌어도 같은 것은 같은 id 로 둔다(만드는 화면이 정해 붙인다)
KEY_MAX_LENGTH = 40
KEY_PATTERN = r'^[A-Za-z0-9_-]+$'
# 장소(지도의 점)와 길(두 장소 사이, 걸리는 시간)
CHARACTER_MAX_PLACES = 30
PLACE_NAME_MAX_LENGTH = 30
PLACE_DESCRIPTION_MAX_LENGTH = 1000
CHARACTER_MAX_PATHS = 100
# 길 하나에 걸리는 시간의 상한(분). 하루다
PATH_MAX_MINUTES = 1440
# 물건과 시작 소지품(사용자가 처음에 가진 것)
CHARACTER_MAX_ITEMS = 50
ITEM_NAME_MAX_LENGTH = 30
ITEM_DESCRIPTION_MAX_LENGTH = 500
CHARACTER_MAX_START_ITEMS = 20
START_ITEM_MAX_COUNT = 99


# 호감도. 값은 0~100 이다. 단계와 규칙의 개수, 단계 이름의 길이, 규칙 하나가 바꾸는 크기의 상한
AFFECTION_MAX = 100
AFFECTION_MAX_STAGES = 10
STAGE_NAME_MAX_LENGTH = 20
AFFECTION_MAX_RULES = 50
AFFECTION_MAX_CHANGE = 20
# 시작 상황의 시작 시각(몇 시, 0~23). 적지 않으면 정오다. 형식 3 까지의 판도 이 값으로 읽는다
START_HOUR_DEFAULT = 12
HOURS_PER_DAY = 24


class TimeOfDay(enum.StrEnum):
    """
    하루의 어느 때. 장소의 시간대 배경을 고르는 열쇠다.
    경계는 TRPG 와 같다(trpg-server 의 app/calendar/clock.py, 2026-10-22 유저 결정). 계산은 chat 이 한다.
    """

    DAWN = 'dawn'
    MORNING = 'morning'
    DAY = 'day'
    EVENING = 'evening'
    NIGHT = 'night'


class AffectionDisplay(enum.StrEnum):
    """호감도를 사람에게 보이는 방식. 숫자와 게이지, 또는 단계 이름과 게이지(숫자는 숨긴다)."""

    NUMBER = 'number'
    STAGE = 'stage'


class TriggerKind(enum.StrEnum):
    """
    호감도를 바꾸는 사용자의 행동. TRPG 의 퀘스트 조건과 같은 (종류, 대상) 모양이다.
    물건을 건넸다(give_item), 장소에 갔다(reach_place), 물건을 썼다(use_item).
    """

    GIVE_ITEM = 'give_item'
    REACH_PLACE = 'reach_place'
    USE_ITEM = 'use_item'


class ItemKind(enum.StrEnum):
    """물건의 종류. 옷은 건네면 상대의 차림에 들어간다(chat 의 장소와 소지품). 나머지는 그냥 물건이다."""

    THING = 'thing'
    CLOTHING = 'clothing'


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
    # 시작 상황들. [{"title", "situation", "hour"}]. 모양은 schemas.Start 가 정한다.
    # 캐릭터에 딸린 짧은 목록이라 문서로 둔다
    starts: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    # 대표 그림의 id. 자기가 올린 그림만 붙인다(app/characters/service.py). 그림이 지워지면(탈퇴) 비운다
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('images.id', ondelete='SET NULL'), default=None, index=True
    )
    # 지도. 장소들 [{"id", "name", "description", "image_id", "backgrounds": {시간대: 그림 id}}],
    # 길들 [{"a", "b", "minutes"}], 처음 있는 장소의 id.
    # 물건들 [{"id", "name", "description", "kind", "consumable", "image_id"}], 시작 소지품 [{"item", "count"}].
    # 모양은 schemas 가 정한다. 서로 가리키는 것이 맞는지는 게시할 때 본다(초안은 고치는 중이라 어긋날 수 있다)
    places: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    paths: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    start_place: Mapped[str | None] = mapped_column(String(KEY_MAX_LENGTH), default=None)
    items: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    start_items: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    # 호감도. {"display", "start", "stages": [{"name", "at"}],
    #         "rules": [{"id", "on": {"kind", "target"}, "change", "once"}]}.
    # 없으면(null) 호감도가 없는 캐릭터다. 모양은 schemas.Affection 이 정한다
    affection: Mapped[dict | None] = mapped_column(JSONB, default=None)

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
