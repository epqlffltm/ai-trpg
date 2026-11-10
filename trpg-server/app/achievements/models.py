# trpg-server/app/achievements/models.py

"""
시나리오 업적의 계정마다의 기록. 제작자가 작품에 단 업적이다(스팀의 업적과 같다). 인증 서버의 활동 배지와는 다른 것이다.

  - player_achievements: 누가(계정) 어느 시나리오의 어느 업적을 언제 받았는가. 계정마다, 시나리오마다 한 번이다
  - scenario_players: 누가 그 시나리오를 플레이했는가. 업적마다의 달성률의 분모다

업적의 정의는 시나리오의 문서(scenarios.achievements)와 판(snapshot.achievements)에 있다. 여기에는 id 만 적는다.
판이 바뀌어도 id 가 같으면 같은 업적이다. 판에서 업적을 빼도 받은 기록은 남는다(목록에는 보이지 않는다).
탈퇴하면 그 사람의 것을 지운다(app/withdrawal/service.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.assets.models import ACHIEVEMENT_ID_MAX_LENGTH
from app.core.database import Base


class PlayerAchievement(Base):
    """한 사람이 받은 시나리오의 업적 하나. 처음 받은 때와 그 테이블이다. 다른 테이블에서 또 받아도 그대로다."""

    __tablename__ = 'player_achievements'
    __table_args__ = (
        # 업적마다의 달성률: 그 시나리오의 업적마다 받은 사람의 수
        Index('ix_player_achievements_scenario_achievement', 'scenario_id', 'achievement_id'),
    )

    # 인증 서버의 public_id 다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('scenarios.asset_id', ondelete='CASCADE'), primary_key=True
    )
    achievement_id: Mapped[str] = mapped_column(String(ACHIEVEMENT_ID_MAX_LENGTH), primary_key=True)
    # 받은 테이블. 테이블의 행이 지워져도 기록은 남는다
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('game_tables.id', ondelete='SET NULL'), index=True)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScenarioPlayer(Base):
    """
    한 사람이 그 시나리오를 플레이했다. 캐릭터를 갖고 앉은 테이블에서 라운드가 한 번이라도 닫혔다.

    업적마다의 달성률의 분모다. 한 사람에 한 번이다(기본 키).
    """

    __tablename__ = 'scenario_players'

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('scenarios.asset_id', ondelete='CASCADE'), primary_key=True
    )
    # 인증 서버의 public_id 다. 탈퇴하면 지운다
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, index=True)
    first_played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
