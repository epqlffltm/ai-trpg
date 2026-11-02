# trpg-server/app/assets/campaigns/models.py

"""
캠페인의 테이블 모델(#481 B, docs/architecture/campaigns.md). 캠페인(Campaign)은 자산이고,
편(CampaignEpisode)은 캠페인에 딸린 행이며, 판(CampaignVersion)은 게시한 순간을 굳힌 것이다.

  - 캠페인은 시나리오를 차례로 묶는다. 편 하나가 시나리오 하나다. 같은 시나리오를 두 번 넣지 못한다.
  - 편은 캠페인의 주인의 시나리오만 가리킨다(입력에서 본다). 편이 가리키는 시나리오는 지우지 못한다(find_referrers).
  - 판에는 편마다 그때의 시나리오의 마지막 판 번호를 굳힌다. 시나리오를 다시 게시해도 캠페인을 다시 게시하기 전까지는
    앞의 판이다. 판은 고치거나 지우지 않는다.

다른 자산의 모델과 파일을 나눈다(자산 공통부 app/assets/models.py 는 여러 일이 함께 고치는 파일이다).
마이그레이션이 이 파일을 불러온다(migrations/env.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assets.models import VERSION_NOTE_MAX_LENGTH, AssetContent, at_most
from app.core.database import Base

# 캠페인의 편의 수. 게시하려면 둘 이상이다. 초안은 비워 둘 수 있다
CAMPAIGN_MIN_EPISODES = 2
CAMPAIGN_MAX_EPISODES = 10
# 편의 이름. 비우면 시나리오의 제목이다
EPISODE_TITLE_MAX_LENGTH = 30


class Campaign(AssetContent):
    """캠페인의 내용. 자신의 칸은 없다. 편은 CampaignEpisode 에, 등급은 공통 부분(assets.rating)에 있다."""

    __tablename__ = 'campaigns'

    # 편들. 차례(position)대로 읽는다. 캠페인을 읽을 때 늘 함께 읽는다(비동기에서는 나중에 따로 읽지 못한다)
    episodes: Mapped[list['CampaignEpisode']] = relationship(
        order_by='CampaignEpisode.position', lazy='selectin', cascade='all, delete-orphan'
    )


class CampaignEpisode(Base):
    """
    캠페인의 편 하나. 차례와 시나리오와 이름이다.

    편은 자산이 아니다. 고칠 때는 캠페인의 편 목록을 통째로 바꾼다(행을 지우고 새로 넣는다).
    """

    __tablename__ = 'campaign_episodes'
    __table_args__ = (
        # 한 캠페인에 같은 시나리오가 두 번, 같은 차례가 두 번 있을 수 없다.
        # 이름을 적는다. 이름의 규칙(첫 칸의 이름)대로면 둘 다 campaign_id 라 이름이 겹친다
        UniqueConstraint('campaign_id', 'scenario_id', name='uq_campaign_episodes_scenario'),
        UniqueConstraint('campaign_id', 'position', name='uq_campaign_episodes_position'),
        CheckConstraint(f'0 <= position AND position < {CAMPAIGN_MAX_EPISODES}', name='position_range'),
        CheckConstraint(at_most('title', EPISODE_TITLE_MAX_LENGTH), name='title_length'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.asset_id', ondelete='CASCADE'))
    # 편의 차례. 0 부터다(0 이 1편)
    position: Mapped[int] = mapped_column(Integer)
    # 가리키는 시나리오. 편이 가리키는 동안 시나리오의 행은 지울 수 없다(지우기는 시각만 적지만, 그것도 막는다).
    # "이 시나리오를 쓰는 캠페인"을 찾는 색인을 건다
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('scenarios.asset_id', ondelete='RESTRICT'), index=True)
    # 편의 이름. 빈 글이면 게시할 때 시나리오의 제목을 굳힌다
    title: Mapped[str] = mapped_column(String(EPISODE_TITLE_MAX_LENGTH), default='')


class CampaignVersion(Base):
    """
    캠페인의 판. 게시한 순간의 편들(시나리오와 그 판 번호, 편의 이름)과 등급을 굳힌 것이다.

    한 판(플레이)은 시작할 때의 캠페인 판에 고정한다. 그래서 판은 고치지 않는다.
    행을 고치거나 지우는 코드를 만들지 않는다.
    """

    __tablename__ = 'campaign_versions'
    __table_args__ = (
        # 한 캠페인에 같은 번호의 판이 둘 있을 수 없다. 동시에 게시해도 하나만 들어간다
        UniqueConstraint('campaign_id', 'number'),
        CheckConstraint('number >= 1', name='number_positive'),
        CheckConstraint(at_most('note', VERSION_NOTE_MAX_LENGTH), name='note_length'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # 어느 캠페인의 판인가. 판이 있는 캠페인의 행은 지울 수 없다
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('campaigns.asset_id', ondelete='RESTRICT'))
    # 판의 번호. 캠페인마다 1 부터 하나씩 올라간다
    number: Mapped[int] = mapped_column(Integer)
    # 변경 내용. 제작자가 적는다
    note: Mapped[str] = mapped_column(Text, default='')
    # 굳힌 내용. 모양은 app/assets/campaigns/schemas.py 의 CampaignSnapshot 이 정한다. 그 모양을 거치지 않고 쓰지 않는다
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
