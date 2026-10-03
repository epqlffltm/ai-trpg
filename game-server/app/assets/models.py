# game-server/app/assets/models.py

"""
자산의 테이블 모델.

자산은 사용자가 만들어 두고 플레이할 때 조립해 쓰는 재료다(세계관, 로어북, NPC, 몬스터 등).

테이블을 둘로 나눈다.
  - assets: 모든 자산이 똑같이 갖는 것. 누구 것인가, 무슨 종류인가, 누구에게 보이는가.
  - worlds 등: 그 종류만 갖는 내용. 종류마다 테이블이 하나씩 있고, 모두 AssetContent 를 물려받는다.

자산이 다른 자산을 가리킬 수 있다. 시나리오가 룰북과 세계관을 가리킨다.

공통 부분을 한 테이블에 두면, 권한 검사 같은 규칙을 종류마다 다시 짜지 않아도 되고,
"아무 자산이나 가리키는 것"(방이 쓴 자산, 구매한 자산)이 외래 키 하나로 된다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.core.database import Base

# 글의 길이 제한(글자 수). 꾸밈 문법을 포함한 원문 기준이다
TITLE_MAX_LENGTH = 100
DESCRIPTION_MAX_LENGTH = 1000
# 아래 둘은 턴마다 AI 의 입력에 들어간다. 길이가 곧 비용이다
WORLD_SETTING_MAX_LENGTH = 8000
WORLD_GM_NOTES_MAX_LENGTH = 4000
RULEBOOK_GM_GUIDE_MAX_LENGTH = 4000
# 테이블이 시작될 때 한 번 읽어 주는 글이다. 턴마다 다시 들어가지 않는다
SCENARIO_OPENING_MAX_LENGTH = 2000


class AssetType(enum.StrEnum):
    """자산의 종류. 종류마다 내용을 담는 테이블이 따로 있다."""

    WORLD = 'world'
    RULEBOOK = 'rulebook'
    SCENARIO = 'scenario'


class Visibility(enum.StrEnum):
    """누구에게 보이는가. 지금은 만든 사람만 본다. 공개 기능을 만들 때 값을 늘린다."""

    PRIVATE = 'private'


class Rating(enum.StrEnum):
    """이용 등급."""

    ALL = 'all'
    ADULT = 'adult'


def one_of(column: str, values: type[enum.StrEnum]) -> str:
    """컬럼의 값이 정해진 목록 안에 있어야 한다는 조건을 SQL 로 만든다."""
    allowed = ', '.join(f"'{value}'" for value in values)
    return f'{column} IN ({allowed})'


def at_most(column: str, max_length: int) -> str:
    """컬럼의 글자 수가 제한을 넘지 않아야 한다는 조건을 SQL 로 만든다."""
    return f'char_length({column}) <= {max_length}'


class Asset(Base):
    """모든 자산의 공통 부분."""

    __tablename__ = 'assets'
    __table_args__ = (
        # 값의 종류를 DB 의 enum 타입이 아니라 문자열과 CHECK 로 둔다.
        # enum 타입은 값을 추가하는 마이그레이션이 까다롭고, 자산의 종류는 계속 늘어난다
        CheckConstraint(one_of('type', AssetType), name='type_allowed'),
        CheckConstraint(one_of('visibility', Visibility), name='visibility_allowed'),
        CheckConstraint(one_of('rating', Rating), name='rating_allowed'),
        CheckConstraint(at_most('description', DESCRIPTION_MAX_LENGTH), name='description_length'),
    )

    # API 주소에 드러나는 값이다. 순서대로 늘어나는 정수면 남의 자산이 몇 개인지, 있는지를 추측할 수 있다.
    # DB 가 아니라 파이썬에서 만든다. 저장하기 전에도 ID 를 알 수 있다
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 만든 사람. 인증 서버의 public_id(토큰의 sub)다.
    # 사용자 테이블은 인증 서버에 있으므로 외래 키를 걸 수 없다. "내 자산" 조회를 위해 색인을 건다
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)

    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))

    # 소개글. 사람이 읽는다. AI 의 입력에는 넣지 않는다
    description: Mapped[str] = mapped_column(Text, default='')

    visibility: Mapped[str] = mapped_column(String(20), default=Visibility.PRIVATE)
    rating: Mapped[str] = mapped_column(String(20), default=Rating.ALL)

    # 시각은 DB 의 시계로 적는다. 서버가 여러 대여도 기준이 하나다
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 지운 시각. 비어 있으면 지우지 않은 것이다.
    # 행을 실제로 지우지 않는다. 진행 중인 방이 이 자산을 가리키고 있을 수 있다
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetContent(Base):
    """
    종류별 내용 테이블의 공통 부분. 세계관, 룰북처럼 자산의 내용을 담는 모델이 물려받는다.

    이 클래스 자체는 테이블이 아니다(__abstract__). 물려받은 클래스마다 아래 두 가지가 똑같이 생긴다.
    """

    __abstract__ = True

    # 기본 키이면서 assets 를 가리킨다. 자산 하나에 내용이 둘 붙을 수 없다(1:1).
    # 자산의 행이 지워지면 내용도 함께 지워진다. 내용만 남아 떠도는 일이 없다
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('assets.id', ondelete='CASCADE'), primary_key=True)

    # 내용을 읽을 때 공통 부분도 항상 함께 읽는다.
    # 비동기에서는 나중에 따로 읽어 오는 방식(lazy)을 쓸 수 없어서, 한 번의 조회로 같이 가져오게 한다.
    # 물려받는 클래스마다 관계를 따로 만들어야 해서 declared_attr 로 적는다
    @declared_attr
    def asset(cls) -> Mapped[Asset]:
        return relationship(lazy='joined', innerjoin=True)


class World(AssetContent):
    """세계관의 내용."""

    __tablename__ = 'worlds'
    __table_args__ = (
        CheckConstraint(at_most('setting', WORLD_SETTING_MAX_LENGTH), name='setting_length'),
        CheckConstraint(at_most('gm_notes', WORLD_GM_NOTES_MAX_LENGTH), name='gm_notes_length'),
    )

    # 공개 설정. 플레이어와 AI 가 함께 본다
    setting: Mapped[str] = mapped_column(Text, default='')

    # GM 전용. AI 만 본다. 소유자가 아닌 사람에게 가는 응답에 실으면 안 된다
    gm_notes: Mapped[str] = mapped_column(Text, default='')


class Rulebook(AssetContent):
    """
    룰북의 내용. 시나리오를 만들 때 중심이 되는 자산이다.

    룰북에는 두 가지가 들어간다.
    - 진행 지침: 컨셉, 분위기, GM 의 진행 방식. AI 가 읽는 글이다.
    - 게임 규칙: 능력치, 주사위, 판정. 엔진이 실행하는 데이터다.
    지금은 진행 지침만 있다. 게임 규칙의 칸은 엔진을 만들 때 더한다.
    규칙을 글로 적어 AI 에게 주지 않는다. 그러면 판정을 AI 가 하게 된다.
    """

    __tablename__ = 'rulebooks'
    __table_args__ = (CheckConstraint(at_most('gm_guide', RULEBOOK_GM_GUIDE_MAX_LENGTH), name='gm_guide_length'),)

    # 진행 지침. AI 만 본다. 턴마다 AI 의 입력에 들어간다
    gm_guide: Mapped[str] = mapped_column(Text, default='')


class Scenario(AssetContent):
    """
    시나리오의 내용. 테이블이 고르는 것이다.

    시나리오는 다른 자산을 모아 만든 조립물이다. 룰북을 중심으로 세계관 등을 붙인다.
    지금은 룰북과 세계관만 가리킨다. 로어북, NPC 같은 재료는 그 자산을 만들 때 더한다.

    초안일 때는 룰북을 비워 둘 수 있다(임시 저장). 게시할 때 룰북이 있는지 검사한다.
    """

    __tablename__ = 'scenarios'
    __table_args__ = (CheckConstraint(at_most('opening', SCENARIO_OPENING_MAX_LENGTH), name='opening_length'),)

    # 가리키는 대상이 assets 가 아니라 rulebooks 다. 룰북 자리에 세계관을 넣는 일을 DB 가 막는다.
    # 가리키는 쪽에서 찾는 일("이 룰북을 쓰는 시나리오가 있는가")이 있어서 색인을 건다.
    # RESTRICT: 시나리오가 가리키는 동안에는 룰북의 행을 지울 수 없다
    rulebook_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('rulebooks.asset_id', ondelete='RESTRICT'), index=True
    )

    # 세계관은 없어도 된다. 붙여도 하나만 붙인다
    world_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('worlds.asset_id', ondelete='RESTRICT'), index=True)

    # 도입부. 테이블이 시작될 때 AI 가 처음 읽어 주는 장면이다. 플레이어와 AI 가 함께 본다
    opening: Mapped[str] = mapped_column(Text, default='')
