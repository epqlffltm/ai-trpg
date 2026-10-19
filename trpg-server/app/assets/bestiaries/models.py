# trpg-server/app/assets/bestiaries/models.py

"""
몬스터 도감의 테이블 모델. 도감(Bestiary)은 자산이고, 몬스터(Monster)는 도감에 딸린 행이다.

로어북과 같은 모양이다. 도감은 공통 칸(제목, 메모)만 갖고, 내용은 전부 몬스터에 있다.
몬스터에는 글(이름, AI 가 읽는 내용)과 타입만 둔다. 숫자(시트)는 두지 않는다.
도감은 여러 시나리오가 함께 쓰고, 시나리오마다 룰북이 달라 능력치의 이름표와 범위가 다르다.
NPC 시트와 같은 까닭으로 숫자는 룰북을 정하는 쪽(시나리오)의 것이다(다음 단계에서 시나리오에 붙인다).

로어북의 항목으로 두지 않은 까닭:
  - 같은 몬스터가 한 장면에 여러 마리 나온다. 로어북의 인물은 항목 하나가 하나다.
  - 타입처럼 엔진이 다르게 다룰 값이 있다. 로어북은 AI 가 읽는 글이다.

다른 자산의 모델과 파일을 나눈다. 자산 공통부(app/assets/models.py)는 여러 일이 함께 고치는 파일이라,
새 종류는 자기 파일에 둔다. 마이그레이션이 이 파일을 불러온다(migrations/env.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import AssetContent, at_most, one_of
from app.core.database import Base

# 도감 하나에 둘 수 있는 몬스터의 수. 로어북의 항목과 같다
BESTIARY_MAX_MONSTERS = 100
# 몬스터의 이름. 캐릭터의 이름과 같다
MONSTER_NAME_MAX_LENGTH = 50
# 몬스터의 내용. AI 가 읽는다. 장면에 나온 몬스터마다 들어가므로 길이가 곧 비용이다. 로어북의 항목과 같다
MONSTER_CONTENT_MAX_LENGTH = 500


class MonsterKind(enum.StrEnum):
    """
    몬스터의 타입. 엔진이 다르게 다룰 것만 나눈다. 자유 태그로 두지 않는다. 서버가 타입마다 다르게 다룰 수 없게 된다.

    타입마다 엔진이 하는 일(예: 언데드와 구조물에는 치료가 듣지 않는다)은 판정에 몬스터를 붙일 때 정한다.
    그때 값을 다시 본다. 지금은 값만 받는다. 세세한 생물 분류는 로어북의 종족 항목이 글로 맡는다.
    """

    # 사람처럼 생각하고 말하는 것. 도적, 고블린
    HUMANOID = 'humanoid'
    # 짐승. 늑대, 큰 거미
    BEAST = 'beast'
    # 죽었다가 움직이는 것. 해골, 망령
    UNDEAD = 'undead'
    # 만들어진 것. 골렘, 움직이는 갑옷
    CONSTRUCT = 'construct'
    # 위의 어느 것도 아닌 것. 정하지 않으면 이것이다
    OTHER = 'other'


class Bestiary(AssetContent):
    """도감의 내용. 자신의 칸은 없다. 내용은 전부 몬스터(Monster)에 있다."""

    __tablename__ = 'bestiaries'


class Monster(Base):
    """
    도감의 몬스터 하나. 한 종류의 몬스터다. 테이블에 몇 마리가 나오든 정의는 이것 하나다.

    몬스터는 자산이 아니다. 주인, 공개 범위, 지운 시각이 따로 없고 도감의 것을 따른다.
    지울 때는 행을 실제로 지운다.
    """

    __tablename__ = 'monsters'
    __table_args__ = (
        CheckConstraint(at_most('content', MONSTER_CONTENT_MAX_LENGTH), name='content_length'),
        CheckConstraint(one_of('kind', MonsterKind), name='kind_allowed'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 도감의 몬스터인가. 도감의 행이 지워지면 몬스터도 함께 지워진다.
    # "이 도감의 몬스터들"을 찾는 일이 대부분이라 색인을 건다
    bestiary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('bestiaries.asset_id', ondelete='CASCADE'), index=True)

    # 몬스터의 이름. 플레이어에게도 보일 이름이다(고블린, 해골 병사). 길이는 칸의 크기(varchar)가 막는다
    name: Mapped[str] = mapped_column(String(MONSTER_NAME_MAX_LENGTH))

    # 내용. 생김새, 버릇, 싸우는 방식. AI 가 읽는다. 수치는 적지 않는다. 숫자는 시나리오의 시트가 정한다
    content: Mapped[str] = mapped_column(Text, default='')

    # 타입(MonsterKind)
    kind: Mapped[str] = mapped_column(String(20), default=MonsterKind.OTHER)

    # 네임드 몹인가. 보스나 특별한 몹이다. 이름과 글이 그 한 마리의 것이고, 판 전체에서 한 마리만 둔다(게시할 때 본다).
    # 번호 없이 이름으로 부르고, 서술자에게는 마리마다 자기 글이 간다. 일반 몹은 종류와 마릿수만 간다
    unique: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
