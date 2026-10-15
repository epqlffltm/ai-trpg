# game-server/app/calendar/models.py

"""
테이블의 시계(table_clocks). 테이블 하나에 하나다.

게임 안의 지금 시각과, 다음 라운드가 열릴 때 흐를 시간을 방장이 정했으면 그 값을 적는다.
판의 시계(시작 시각, 라운드의 기본 시간)는 판(content)에 있다. 여기에 다시 적지 않는다.

시각을 바꾸는 것은 서버뿐이다. 라운드가 열릴 때 엔진이 흘리고(app/calendar/state.py),
흐를 시간은 방장이 API 로 정한다(app/calendar/service.py). AI 는 시각을 바꾸지 못한다.

테이블의 모델(app/tables/models.py)을 고치지 않고 이쪽에서 테이블에 `clock` 을 붙인다(backref).
테이블을 읽으면 시계도 함께 읽힌다(selectin). 라운드를 여는 일은 DB 를 기다리지 않는 함수라서 미리 읽혀 있어야 한다.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.assets.models import ROUND_MAX_MINUTES
from app.core.database import Base
from app.tables.models import GameTable


class TableClock(Base):
    """
    테이블 하나의 게임 안의 시계.

    minutes 는 1일째 0시부터 흐른 분이다(app/calendar/clock.py 가 푼다). 테이블을 만들 때 판의 시작 시각으로 정한다.
    next_step_minutes 는 다음 라운드가 열릴 때 흐를 분이다. 비어 있으면 판의 기본(라운드 하나에 흐르는 시간)이다.
    라운드가 열리면 흘리고 다시 비운다. 방장이 정한 값은 한 번만 쓴다.
    """

    __tablename__ = 'table_clocks'
    __table_args__ = (
        CheckConstraint('minutes >= 0', name='minutes_not_negative'),
        CheckConstraint(f'next_step_minutes BETWEEN 0 AND {ROUND_MAX_MINUTES}', name='next_step_range'),
    )

    # 테이블 하나에 시계 하나다. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'), primary_key=True)
    minutes: Mapped[int] = mapped_column(Integer)
    next_step_minutes: Mapped[int | None] = mapped_column(Integer)

    table: Mapped[GameTable] = relationship(
        backref=backref('clock', uselist=False, lazy='selectin', cascade='all, delete-orphan', passive_deletes=True)
    )
