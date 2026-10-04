# game-server/app/assets/models.py

"""
자산의 테이블 모델.

자산은 사용자가 만들어 두고 플레이할 때 조립해 쓰는 재료다(세계관, 로어북, NPC, 몬스터 등).

테이블을 둘로 나눈다.
  - assets: 모든 자산이 똑같이 갖는 것. 누구 것인가, 무슨 종류인가, 누구에게 보이는가.
  - worlds 등: 그 종류만 갖는 내용. 종류마다 테이블이 하나씩 있고, 모두 AssetContent 를 물려받는다.

자산이 다른 자산을 가리킬 수 있다. 시나리오가 룰북과 세계관을 하나씩, 로어북을 여러 개 가리킨다.
자산에 딸린 행이 여럿일 수 있다. 로어북에 항목이 딸린다. 항목은 자산이 아니다.

지금까지의 것은 모두 초안이다. 제작자가 언제든 고친다.
시나리오를 게시하면 그 순간의 내용이 판(ScenarioVersion)으로 굳는다. 판은 고치지 않는다.

공통 부분을 한 테이블에 두면, 권한 검사 같은 규칙을 종류마다 다시 짜지 않아도 되고,
"아무 자산이나 가리키는 것"(방이 쓴 자산, 구매한 자산)이 외래 키 하나로 된다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
# 시나리오 하나에 둘 수 있는 스타팅(도입부)의 수. 테이블을 만드는 사람이 한 화면에서 보고 고른다
SCENARIO_MAX_OPENINGS = 5
# 시나리오 하나에 붙일 수 있는 로어북의 수. 플레이할 때 살펴볼 항목의 수가 이 값에 비례한다
SCENARIO_MAX_LOREBOOKS = 10
# 판을 낼 때 적는 변경 내용. 사람이 읽는다
VERSION_NOTE_MAX_LENGTH = 500

# 로어북의 항목. 항목은 통째로 AI 의 입력에 들어가는 단위다. 짧게 쪼개 둘수록 필요한 것만 넣을 수 있다
LOREBOOK_MAX_ENTRIES = 100
LORE_ENTRY_NAME_MAX_LENGTH = 100
LORE_ENTRY_CONTENT_MAX_LENGTH = 500
LORE_ENTRY_MAX_KEYWORDS = 5
LORE_KEYWORD_MAX_LENGTH = 30


class AssetType(enum.StrEnum):
    """자산의 종류. 종류마다 내용을 담는 테이블이 따로 있다."""

    WORLD = 'world'
    RULEBOOK = 'rulebook'
    SCENARIO = 'scenario'
    LOREBOOK = 'lorebook'


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

    # 메모. 만든 사람이 자기 목록에서 알아보려고 적는다. AI 의 입력에는 넣지 않는다.
    # 남에게 보이는 소개글은 소개 페이지(app/listings)에 따로 있다
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
    룰북과 세계관은 하나씩, 로어북은 여러 개 가리킨다. NPC 같은 재료는 그 자산을 만들 때 더한다.

    초안일 때는 룰북과 스타팅을 비워 둘 수 있다(임시 저장). 게시할 때 둘 다 있는지 검사한다.
    """

    __tablename__ = 'scenarios'
    __table_args__ = (
        CheckConstraint(f'cardinality(openings) <= {SCENARIO_MAX_OPENINGS}', name='openings_count'),
        # 배열의 원소 하나하나의 길이는 CHECK 로 볼 수 없다. 전부 이은 길이로 위쪽만 막는다.
        # 하나의 길이는 입력을 받을 때 검사한다(scenarios/schemas.py)
        CheckConstraint(
            f"char_length(array_to_string(openings, '')) <= {SCENARIO_MAX_OPENINGS * SCENARIO_OPENING_MAX_LENGTH}",
            name='openings_length',
        ),
    )

    # 가리키는 대상이 assets 가 아니라 rulebooks 다. 룰북 자리에 세계관을 넣는 일을 DB 가 막는다.
    # 가리키는 쪽에서 찾는 일("이 룰북을 쓰는 시나리오가 있는가")이 있어서 색인을 건다.
    # RESTRICT: 시나리오가 가리키는 동안에는 룰북의 행을 지울 수 없다
    rulebook_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey('rulebooks.asset_id', ondelete='RESTRICT'), index=True
    )

    # 세계관은 없어도 된다. 붙여도 하나만 붙인다
    world_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('worlds.asset_id', ondelete='RESTRICT'), index=True)

    # 스타팅들. 하나하나가 도입부다. 테이블이 시작될 때 AI 가 처음 읽어 주는 장면이고, 플레이어와 AI 가 함께 본다.
    # 테이블을 만드는 사람이 이 중 하나를 고른다. 목록의 순서가 고르는 화면의 순서다.
    # 시나리오 하나에 딸린 짧은 목록이라 테이블을 따로 두지 않고 배열로 둔다
    openings: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    # 붙인 로어북들. 여러 개라 칸 하나에 담지 못하고 연결 테이블(scenario_lorebooks)의 행으로 둔다.
    # selectin: 시나리오를 읽을 때 함께 읽는다. 비동기에서는 나중에 따로 읽어 오는 방식을 쓸 수 없다.
    # delete-orphan: 이 목록에서 빠진 행은 DB 에서도 지운다
    lorebook_links: Mapped[list['ScenarioLorebook']] = relationship(
        lazy='selectin', cascade='all, delete-orphan', order_by='ScenarioLorebook.lorebook_id'
    )

    @property
    def lorebook_ids(self) -> list[uuid.UUID]:
        """붙인 로어북의 ID 목록."""
        return [link.lorebook_id for link in self.lorebook_links]

    @lorebook_ids.setter
    def lorebook_ids(self, lorebook_ids: list[uuid.UUID]) -> None:
        """
        붙인 로어북을 이 목록으로 바꾼다. 목록에 없는 것은 떼고, 새로 생긴 것은 붙인다.

        계속 붙어 있는 것은 행을 그대로 둔다. 지우고 다시 만들면 같은 키의 행을 한 번에 지우고 넣게 되어 부딪힌다.
        """
        kept = [link for link in self.lorebook_links if link.lorebook_id in lorebook_ids]
        attached = {link.lorebook_id for link in kept}
        added = [
            ScenarioLorebook(lorebook_id=lorebook_id) for lorebook_id in lorebook_ids if lorebook_id not in attached
        ]
        self.lorebook_links = kept + added


class Lorebook(AssetContent):
    """
    로어북의 내용. 설정을 항목 단위로 쪼개 담은 사전이다.

    세계관의 설정은 턴마다 통째로 AI 에게 간다. 로어북의 항목은 지금 장면에 관련된 것만 골라서 간다.
    그래서 로어북 자신에게는 칸이 없다. 내용은 전부 항목(LoreEntry)에 있다.
    """

    __tablename__ = 'lorebooks'


class LoreEntry(Base):
    """
    로어북의 항목 하나. 인물, 장소, 물건, 사건 같은 설정 한 토막이다.

    항목은 자산이 아니다. 주인, 공개 범위, 지운 시각이 따로 없고 로어북의 것을 따른다.
    지울 때는 행을 실제로 지운다.
    """

    __tablename__ = 'lore_entries'
    __table_args__ = (
        CheckConstraint(at_most('content', LORE_ENTRY_CONTENT_MAX_LENGTH), name='content_length'),
        CheckConstraint(f'cardinality(keywords) <= {LORE_ENTRY_MAX_KEYWORDS}', name='keywords_count'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 로어북의 항목인가. 로어북의 행이 지워지면 항목도 함께 지워진다.
    # "이 로어북의 항목들"을 찾는 일이 대부분이라 색인을 건다
    lorebook_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('lorebooks.asset_id', ondelete='CASCADE'), index=True)

    # 항목의 이름. 사람이 목록에서 찾을 때 본다. AI 에게도 내용과 함께 간다
    name: Mapped[str] = mapped_column(String(LORE_ENTRY_NAME_MAX_LENGTH))

    # 이 낱말이 대화에 나오면 항목을 AI 의 입력에 넣는다. 고유 명사처럼 글자가 정확히 맞아야 하는 것에 강하다.
    # 뜻이 비슷한 것을 찾는 검색(임베딩)은 나중에 더한다. 그때도 키워드는 함께 쓴다.
    # 항목 하나에 딸린 짧은 목록이라 테이블을 따로 두지 않고 배열로 둔다
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String(LORE_KEYWORD_MAX_LENGTH)), default=list)

    # 내용. AI 가 읽는다. 항목 하나가 검색의 한 토막이 되므로, 한 가지 이야기만 담는다
    content: Mapped[str] = mapped_column(Text, default='')

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScenarioLorebook(Base):
    """
    시나리오와 로어북의 연결. 행 하나가 "이 시나리오에 이 로어북이 붙어 있다"는 뜻이다.

    시나리오 하나에 로어북이 여럿, 로어북 하나가 여러 시나리오에 붙을 수 있다(다대다).
    """

    __tablename__ = 'scenario_lorebooks'

    # 두 칸을 합쳐 기본 키로 삼는다. 같은 로어북을 한 시나리오에 두 번 붙일 수 없다.
    # 시나리오의 행이 지워지면 연결도 함께 지워진다
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('scenarios.asset_id', ondelete='CASCADE'), primary_key=True
    )

    # 붙어 있는 동안에는 로어북의 행을 지울 수 없다.
    # 기본 키의 색인은 시나리오가 앞이라 "이 로어북을 쓰는 시나리오"를 찾는 데 못 쓴다. 따로 색인을 건다
    lorebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('lorebooks.asset_id', ondelete='RESTRICT'), primary_key=True, index=True
    )


class ScenarioVersion(Base):
    """
    시나리오의 판. 게시한 순간의 시나리오와, 그것이 가리키던 룰북, 세계관, 로어북을 통째로 굳힌 것이다.

    테이블(같이 플레이하는 자리)은 만들 때 판 하나를 고르고, 그 내용을 복사해 간다.
    그래서 판은 고치지 않는다. 고칠 것이 있으면 초안을 고치고 새 판을 낸다.
    행을 고치거나 지우는 코드를 만들지 않는다.
    """

    __tablename__ = 'scenario_versions'
    __table_args__ = (
        # 한 시나리오에 같은 번호의 판이 둘 있을 수 없다. 동시에 게시해도 하나만 들어간다
        UniqueConstraint('scenario_id', 'number'),
        CheckConstraint('number >= 1', name='number_positive'),
        CheckConstraint(at_most('note', VERSION_NOTE_MAX_LENGTH), name='note_length'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 시나리오의 판인가. 판이 있는 시나리오의 행은 지울 수 없다.
    # "이 시나리오의 판들"을 찾는 색인은 위의 UNIQUE 가 겸한다(시나리오가 앞에 있다)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('scenarios.asset_id', ondelete='RESTRICT'))

    # 판의 번호. 시나리오마다 1 부터 하나씩 올라간다
    number: Mapped[int] = mapped_column(Integer)

    # 변경 내용. 제작자가 적는다. 새 판이 나왔다고 알릴 때 보여 준다
    note: Mapped[str] = mapped_column(Text, default='')

    # 굳힌 내용. 한 번 쓰고 고치지 않는 기록이라 문서 하나로 둔다.
    # 모양은 app/assets/scenarios/snapshot.py 가 정한다. 그 모양을 거치지 않고 쓰지 않는다
    snapshot: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
