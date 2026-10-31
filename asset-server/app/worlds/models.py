# asset-server/app/worlds/models.py

"""
story 의 세계관과 그 판의 테이블 모델(#591, docs/architecture/story.md 의 "데이터의 모양").

  - 세계관(World)은 초안이다. 만든 사람이 고친다.
  - 게시하면 판(WorldVersion)이 생긴다. 판은 그때의 초안을 굳힌 문서이고 바뀌지 않는다. 번호가 1 부터 오른다.
  - story 서버는 세션을 시작할 때 판 하나를 가져가 복사해 고정한다(내주는 길은 세 번째 조각에서 만든다).

세계관은 세 조각으로 만든다(2026-10-24 유저 결정).
  1. 초안, 인물, 지도와 물건, 시간대, 보이기, 게시와 판(판의 형식 1)
  2. 이벤트(조건, 효과, 선택지, 판의 형식 2)
  3. 고백과 엔딩, 엔딩의 빠짐 검사, story 에 내주기(판의 형식 3)
인물은 만든 사람의 캐릭터를 가리키고 게시할 때 그 마지막 판을 세계관의 판에 복사한다
(로어북과 같은 방식, 2026-10-24 유저 결정).
캐릭터의 판 가운데 story 에 쓰는 칸(이름, 소개, 말투, 나이, 성별, 대표 그림, 캐릭터 그림)만 복사한다.
chat 에만 쓰는 칸(지도, 시작 상황, 물건, 호감도, 이벤트 씬)은 복사하지 않는다. 그것들은 세계관이 따로 갖는다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.characters.models import Visibility
from app.core.database import Base
from app.genres import GENRE_MAX_LENGTH
from app.ratings import Rating

# 이름, 태그. 캐릭터와 같다
WORLD_NAME_MAX_LENGTH = 50
WORLD_MAX_TAGS = 10
# 판의 변경 내용. 캐릭터의 판과 같다
VERSION_NOTE_MAX_LENGTH = 500
# 기한(D-N)의 날 수의 상한. 1년이다
DEADLINE_MAX_DAYS = 365
# 시간대. 이야기마다 제작자가 정한다(story.md 의 "기본값으로 둔 것"). 시작하는 시각(몇 시)이 차례로 커진다
WORLD_MIN_SLOTS = 1
WORLD_MAX_SLOTS = 8
SLOT_NAME_MAX_LENGTH = 20
HOURS_PER_DAY = 24
# 장소와 길, 물건과 시작 소지품. 여러 인물이 움직이는 무대라 캐릭터보다 넉넉하다
WORLD_MAX_PLACES = 50
WORLD_MAX_PATHS = 150
WORLD_MAX_ITEMS = 100
WORLD_MAX_START_ITEMS = 20
# 인물. 장면에 함께 나오는 것은 4명까지(story.md 의 "기본값으로 둔 것")지만 세계관 전체에는 더 둔다
WORLD_MAX_CAST = 20
# 인물 하나의 일정의 줄 수, 선물의 규칙 수
CAST_MAX_SCHEDULE = 20
CAST_MAX_GIFTS = 50
# 조건 목록 하나의 조건 수(일정의 줄, 나중의 이벤트와 엔딩이 같은 모양을 쓴다)
MAX_CONDITIONS = 10
# 조건의 count 의 상한. 물건의 수(시작 소지품과 같은 99)와 날짜(기한과 같은 365)를 함께 받는다
CONDITION_MAX_COUNT = DEADLINE_MAX_DAYS
# 세계관이 가리키는 로어북의 수. 캐릭터와 같다
WORLD_MAX_LOREBOOKS = 3
# 이벤트(story.md 의 "이벤트"). 개수, 이름, 장면 지시(모델이 읽는다),
# 장면에 불러들이는 인물의 수(장면의 인물 상한과 같다)
WORLD_MAX_EVENTS = 50
EVENT_NAME_MAX_LENGTH = 30
SCENE_TEXT_MAX_LENGTH = 1000
SCENE_MAX_CAST = 4
# 선택지는 0~3개(story.md 의 "정한 것"). 선택지의 글, 효과 목록 하나의 효과 수
EVENT_MAX_CHOICES = 3
CHOICE_TEXT_MAX_LENGTH = 100
MAX_EFFECTS = 10
# 효과 하나가 호감도를 바꾸는 크기의 상한. 이벤트는 큰 장면이라 선물의 규칙(20)보다 넓게 둔다. 값은 0~100 안으로 자른다
EFFECT_MAX_CHANGE = 100
# 물건을 주고 가져가는 수의 상한. 시작 소지품과 같다
EFFECT_MAX_COUNT = 99
# 고백(story.md 의 "고백과 엔딩"). 실패했을 때 내려가는 호감도와 다시 고백하지 못하는 날의 기본과 상한
CONFESSION_FAIL_DROP_DEFAULT = 10
CONFESSION_COOLDOWN_DEFAULT_DAYS = 1
CONFESSION_MAX_COOLDOWN_DAYS = 30
# 엔딩. 개수, 이름, 못 본 사람에게 보이는 힌트의 길이
WORLD_MAX_ENDINGS = 30
ENDING_NAME_MAX_LENGTH = 30
ENDING_HINT_MAX_LENGTH = 100


class AfterEnding(enum.StrEnum):
    """엔딩 뒤에 세션이 어떻게 되는가(story.md 의 "세션과 기록"). 끝(읽기만) 또는 후일담."""

    END = 'end'
    EPILOGUE = 'epilogue'


class Reveal(enum.StrEnum):
    """인물을 사람에게 어떻게 보이는가. 보임, 실루엣(이름과 그림을 가린다), 숨김(목록에 없다)."""

    SHOWN = 'shown'
    SILHOUETTE = 'silhouette'
    HIDDEN = 'hidden'


class MapPresence(enum.StrEnum):
    """지도에 인물이 있는 곳을 보이는가. 보임, 숨김, 호감도가 정한 단계 이상일 때만(stage)."""

    SHOWN = 'shown'
    HIDDEN = 'hidden'
    STAGE = 'stage'


class PanelField(enum.StrEnum):
    """인물 창에 보이는 항목. 소개, 나이, 성별, 호감도."""

    INTRO = 'intro'
    AGE = 'age'
    GENDER = 'gender'
    AFFECTION = 'affection'


class Match(enum.StrEnum):
    """조건 목록을 맞추는 법. 모두, 또는 하나라도(TRPG 의 퀘스트와 같다)."""

    ALL = 'all'
    ANY = 'any'


class ConditionKind(enum.StrEnum):
    """
    조건 하나가 무엇을 보는가(story.md 의 "조건"). 엔진(story 서버)이 이미 아는 사실만 본다.

    종류마다 쓰는 칸이 정해져 있다(app/worlds/schemas.py 의 Condition).
      reach_place        target: 장소          사용자가 그 장소에 있다
      hold_item          target: 물건, count   그 물건을 count 개 이상 가졌다
      gave_item          target: 인물, value: 물건   그 인물에게 그 물건을 건넨 적이 있다
      affection_at_least target: 인물, value: 단계   그 인물의 호감도가 그 단계 이상이다
      affection_below    target: 인물, value: 단계   그 인물의 호감도가 그 단계보다 아래다
      day_at_least       count                 n일째 이상이다
      day_at_most        count                 n일째 이하다
      slot_is            target: 시간대        지금의 시간대가 그것이다
      accompanied        target: 인물          그 인물과 동행 중이다
      event_seen         target: 이벤트        그 이벤트가 열린 적이 있다(판의 형식 2)
    """

    REACH_PLACE = 'reach_place'
    HOLD_ITEM = 'hold_item'
    GAVE_ITEM = 'gave_item'
    AFFECTION_AT_LEAST = 'affection_at_least'
    AFFECTION_BELOW = 'affection_below'
    DAY_AT_LEAST = 'day_at_least'
    DAY_AT_MOST = 'day_at_most'
    SLOT_IS = 'slot_is'
    ACCOMPANIED = 'accompanied'
    EVENT_SEEN = 'event_seen'


class ConfessionFailure(enum.StrEnum):
    """고백에 실패하면 어떻게 되는가. 계속(호감도가 내려가고 정한 날 동안 다시 못 한다) 또는 실패 엔딩으로 끝."""

    CONTINUE = 'continue'
    END = 'end'


class EndingTrigger(enum.StrEnum):
    """
    엔딩의 판정이 무엇으로 시작되는가(story.md 의 "고백과 엔딩").
    그 인물에게 고백 성공(confess_success, target: 인물), 실패(confess_fail, target: 인물),
    기한이 지났다(deadline, target 없음), 그 이벤트가 열렸다(event, target: 이벤트).
    시작이 일어나면 그 시작의 엔딩을 적은 차례로 맞춰 보고 처음 맞는 것 하나를 고른다.
    """

    CONFESS_SUCCESS = 'confess_success'
    CONFESS_FAIL = 'confess_fail'
    DEADLINE = 'deadline'
    EVENT = 'event'


class EffectKind(enum.StrEnum):
    """
    효과 하나가 무엇을 바꾸는가(story.md 의 "효과"). 엔진(story 서버)만 반영한다. 모델의 글에는 효과가 없다.

    종류마다 쓰는 칸이 정해져 있다(app/worlds/schemas.py 의 Effect).
      affection        target: 인물, amount: ±n   그 인물의 호감도를 바꾼다(0~100 안으로 자른다)
      give_item        target: 물건, amount: n    사용자에게 그 물건을 준다
      take_item        target: 물건, amount: n    사용자에게서 그 물건을 가져간다(가진 만큼까지)
      accompany_start  target: 인물               그 인물과 동행을 시작한다
      accompany_end    target: 인물               그 인물과 동행을 끝낸다
      move_to          target: 장소               사용자(와 동행)를 그 장소로 옮긴다. 시간은 흐르지 않는다
    일러스트를 여는 것은 효과가 아니라 장면의 칸(collectible)이다. 이벤트가 열리면 그 장면의 일러스트를 연다.
    """

    AFFECTION = 'affection'
    GIVE_ITEM = 'give_item'
    TAKE_ITEM = 'take_item'
    ACCOMPANY_START = 'accompany_start'
    ACCOMPANY_END = 'accompany_end'
    MOVE_TO = 'move_to'


class World(Base):
    """
    세계관의 초안. 만든 사람만 보고 고친다.

    latest_version 과 published_at 은 마지막으로 게시한 판의 번호와 시각이다. 게시한 적이 없으면 비어 있다.
    목록의 칸(장소, 인물 …)은 세계관에 딸린 짧은 목록이라 문서(JSONB)로 둔다. 모양은 app/worlds/schemas.py 가 정한다.
    서로 가리키는 것이 맞는지는 게시할 때 본다(초안은 고치는 중이라 어긋날 수 있다).
    """

    __tablename__ = 'worlds'
    __table_args__ = (
        CheckConstraint(f"rating IN ('{Rating.ALL}', '{Rating.ADULT}')", name='rating_allowed'),
        CheckConstraint(f"visibility IN ('{Visibility.PRIVATE}', '{Visibility.PUBLIC}')", name='visibility_allowed'),
        CheckConstraint(f"after_ending IN ('{AfterEnding.END}', '{AfterEnding.EPILOGUE}')", name='after_allowed'),
        CheckConstraint(f'cardinality(tags) <= {WORLD_MAX_TAGS}', name='tags_count'),
        CheckConstraint(
            f'deadline_days IS NULL OR deadline_days BETWEEN 1 AND {DEADLINE_MAX_DAYS}', name='deadline_range'
        ),
        CheckConstraint('(latest_version IS NULL) = (published_at IS NULL)', name='published_paired'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 만든 사람. 인증 서버의 public_id 다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    name: Mapped[str] = mapped_column(String(WORLD_NAME_MAX_LENGTH))
    # 소개(HTML). 초안에는 쓴 그대로 둔다. 거르는 것은 게시할 때다(app/content/html.py)
    intro_html: Mapped[str] = mapped_column(Text, default='', server_default='')
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default='{}')
    # 장르(app/genres.py 의 값 하나). 고르지 않았으면 비어 있다. 장면과 소개 화면의 테마를 정한다
    genre: Mapped[str | None] = mapped_column(String(GENRE_MAX_LENGTH), default=None)
    # 대표 그림. 자기가 올린 그림만 붙인다. 그림이 지워지면(탈퇴) 비운다
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('images.id', ondelete='SET NULL'), default=None, index=True
    )

    # 진행. 시간대들 [{"id", "name", "start_hour"}], 시작하는 시간대의 id, 기한(날 수, 없으면 null), 엔딩 뒤
    slots: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    start_slot: Mapped[str | None] = mapped_column(String(40), default=None)
    deadline_days: Mapped[int | None] = mapped_column(Integer, default=None)
    after_ending: Mapped[str] = mapped_column(String(10), default=AfterEnding.END, server_default=AfterEnding.END.value)
    # 보이기의 기본. {"reveal", "map", "panel": [항목]}. 인물마다 덮어쓴다
    show: Mapped[dict] = mapped_column(JSONB, default=dict, server_default='{}')

    # 지도와 물건. 캐릭터의 것과 같은 모양이고 배경의 열쇠만 시간대의 id 다
    places: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    paths: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    start_place: Mapped[str | None] = mapped_column(String(40), default=None)
    items: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    start_items: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    # 인물들 [{"id", "character_id", "home", "schedule", "affection", "reveal", "map", "map_stage", "panel"}].
    # character_id 는 만든 사람의 캐릭터다. 게시할 때 그 마지막 판을 복사한다
    cast: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    # 이벤트들 [{"id", "name", "when", "repeat", "scene", "on_open", "choices"}](판의 형식 2). 적은 차례가 여는 차례다
    events: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    # 엔딩들 [{"id", "name", "trigger", "when", "scene", "unlock", "hint"}](판의 형식 3). 적은 차례가 맞춰 보는 차례다.
    # 인물마다의 고백(confession)은 인물(cast)의 칸이다
    endings: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
    # 가리키는 로어북들의 id(자기 로어북만). 게시할 때 그 마지막 판이 판에 복사된다
    lorebooks: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default='{}')

    rating: Mapped[str] = mapped_column(String(10), default=Rating.ALL, server_default=Rating.ALL.value)
    visibility: Mapped[str] = mapped_column(
        String(10), default=Visibility.PRIVATE, server_default=Visibility.PRIVATE.value
    )

    latest_version: Mapped[int | None] = mapped_column(Integer, default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # 운영자가 숨긴 시각(캐릭터의 hidden_at 과 같다). 숨긴 세계관은 공개여도 공개 목록, 공개 소개,
    # 남의 새 세션(판 내주기), 남이 보는 그림에서 빠진다. 주인은 계속 쓴다. 운영자만 푼다(app/operators/)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorldVersion(Base):
    """
    세계관의 판 하나. 게시할 때의 초안을 굳힌 문서(document)다. 바뀌지 않는다.

    세계관을 지우면 판도 지워진다. 이미 가져간 세션은 사본으로 돈다.
    """

    __tablename__ = 'world_versions'
    __table_args__ = (
        UniqueConstraint('world_id', 'number', name='uq_world_versions_number'),
        CheckConstraint('number >= 1', name='number_positive'),
        CheckConstraint(f"rating IN ('{Rating.ALL}', '{Rating.ADULT}')", name='rating_allowed'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    world_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('worlds.id', ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(VERSION_NOTE_MAX_LENGTH), default='', server_default='')
    # 이 판의 등급. 문서의 rating 과 같다
    rating: Mapped[str] = mapped_column(String(10))
    # 굳힌 문서. 모양은 app/worlds/documents.py 의 WorldDocument 다
    document: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorldImageUse(Base):
    """
    세계관의 판에 쓰인 그림 하나. 바뀌지 않는다. 캐릭터의 판의 것(app/images/models.py 의 ImageUse)과 같은 모양이다.

    표를 따로 둔 까닭: 그림이 쓰인 곳의 외래 키가 판의 표마다 다르다. 한 표에 칸 둘(어느 쪽이든 하나)을 두면
    "둘 가운데 하나만"을 CHECK 로 지켜야 하고, 묻는 쿼리마다 갈래가 생긴다.
    """

    __tablename__ = 'world_image_uses'

    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('world_versions.id', ondelete='CASCADE'), primary_key=True)
    # "이 그림이 공개된 판에 쓰였나"를 그림의 id 로 찾는다. 쓰인 그림은 지우지 못한다(탈퇴 때 남는다)
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('images.id', ondelete='RESTRICT'), primary_key=True, index=True
    )
