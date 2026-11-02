# trpg-server/app/campaigns/models.py

"""
캠페인의 플레이(#481 B, docs/architecture/campaigns.md 의 "한 판(플레이)의 흐름")의 모델.
캠페인 자산과 판은 app/assets/campaigns/ 에 있다. 여기는 그 판으로 하는 한 번의 플레이다.

  - campaign_runs: 플레이 하나. 캠페인의 판 하나에 고정한다. 방장, 지금 편(0 이 1편), 상태.
  - campaign_tables: 플레이의 편마다의 테이블. 편 하나에 테이블 하나다. 테이블 쪽(game_tables)에는 칸을 더하지 않는다.
  - campaign_carries: 편이 끝날 때 앉은 사람마다 적은 넘길 것(app/campaigns/carrying.py). 한 번 적으면 고치지 않는다.
  - campaign_seats: 다음 편의 테이블에서 넘긴 캐릭터로 앉은 자리(app/campaigns/seating.py).
  - campaign_quest_results: 편이 끝날 때 그 편에서 이루거나 실패한 퀘스트(사건 항목).
    다음 편의 조건 campaign_quest 가 읽는다.

모델(AI GM)은 이것들을 바꾸지 못한다. 넘길 것은 엔진이 테이블의 상태에서 적는다.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.campaigns.models import CAMPAIGN_MAX_EPISODES
from app.assets.models import one_of
from app.core.database import Base


class RunStatus(enum.StrEnum):
    """플레이의 상태. 한 방향으로만 나아간다."""

    # 편을 하는 중이다(지금 편의 테이블이 모집 중, 진행 중이거나 끝나 다음 편을 기다린다)
    PLAYING = 'playing'
    # 마지막 편이 끝났다
    ENDED = 'ended'


class QuestResult(enum.StrEnum):
    """편이 끝날 때의 퀘스트의 결과. 숨겨졌거나 진행 중이던 퀘스트는 적지 않는다."""

    SUCCEEDED = 'succeeded'
    FAILED = 'failed'


POSITION_RANGE = f'0 <= position AND position < {CAMPAIGN_MAX_EPISODES}'


class CampaignRun(Base):
    """플레이 하나. 시작할 때의 캠페인 판에 고정한다. 판을 다시 게시해도 이 플레이는 그대로다."""

    __tablename__ = 'campaign_runs'
    __table_args__ = (
        CheckConstraint(one_of('status', RunStatus), name='status_allowed'),
        CheckConstraint(POSITION_RANGE, name='position_range'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 어느 캠페인의 어느 판인가. 판의 행은 지울 수 없다
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.asset_id', ondelete='RESTRICT'), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaign_versions.id', ondelete='RESTRICT'))
    # 플레이를 연 사람. 편마다의 테이블은 방장이 연다. "내가 연 플레이"를 찾는 색인을 건다
    host_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    # 지금 편. 0 이 1편이다
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.PLAYING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CampaignTable(Base):
    """플레이의 편 하나의 테이블. 테이블 하나는 많아야 한 플레이의 한 편이다."""

    __tablename__ = 'campaign_tables'
    __table_args__ = (
        # 한 플레이의 한 편에 테이블은 하나다
        UniqueConstraint('run_id', 'position', name='uq_campaign_tables_position'),
        CheckConstraint(POSITION_RANGE, name='position_range'),
    )

    # 테이블. 테이블의 행은 지우지 않는다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='RESTRICT'), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaign_runs.id', ondelete='CASCADE'))
    position: Mapped[int] = mapped_column(SmallInteger)


class CampaignCarry(Base):
    """
    편이 끝날 때 앉은 사람 하나의 넘길 것. 모양은 app/campaigns/carrying.py 의 Carry 다.

    한 사람은 한 편에 하나다. 다음 편에서 자란 것은 그 편이 끝날 때 새로 적는다. 죽은 캐릭터는 적지 않는다.
    """

    __tablename__ = 'campaign_carries'
    __table_args__ = (
        UniqueConstraint('run_id', 'position', 'user_id', name='uq_campaign_carries_person'),
        CheckConstraint(POSITION_RANGE, name='position_range'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaign_runs.id', ondelete='CASCADE'))
    # 어느 편이 끝날 때 적었는가
    position: Mapped[int] = mapped_column(SmallInteger)
    # 누구의 캐릭터인가. 인증 서버의 public_id 다. "이 사람의 넘긴 캐릭터"를 찾는 색인을 건다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    # 넘길 것. 한 번 쓰고 고치지 않는 기록이라 문서 하나로 둔다
    carry: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignSeat(Base):
    """
    편의 테이블에서 넘긴 캐릭터로 앉은 자리. 시작할 때 이 넘길 것으로 시트를 준다(app/campaigns/seating.py).

    이 자리의 사람은 캐릭터를 바꾸지 못한다. 넘긴 것이 지워지면(탈퇴) 함께 지워진다.
    """

    __tablename__ = 'campaign_seats'

    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='RESTRICT'), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    carry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaign_carries.id', ondelete='CASCADE'), index=True)


class CampaignQuestResult(Base):
    """편이 끝날 때 그 편의 퀘스트(사건 항목) 하나의 결과. 이루었거나 실패한 것만 적는다."""

    __tablename__ = 'campaign_quest_results'
    __table_args__ = (
        CheckConstraint(one_of('result', QuestResult), name='result_allowed'),
        CheckConstraint(POSITION_RANGE, name='position_range'),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaign_runs.id', ondelete='CASCADE'), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # 그 편의 판의 로어북 사건 항목의 id
    entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    result: Mapped[str] = mapped_column(String(20))
