# game-server/app/events/models.py

"""
테이블의 이벤트 기록. 테이블에서 일어난 일을 일어난 순서대로 적어 둔 장부다.

사실의 기준은 현재 상태다(game_tables, table_members, table_rounds). 이벤트는 그 옆에 덧붙이는 기록이다.
"지금 어떤가"는 상태에서 읽고, "어떻게 여기까지 왔나"는 이벤트에서 읽는다.
이벤트만으로 상태를 다시 계산하지 않는다(완전한 event sourcing 이 아니다).

규칙 둘.
  - 덧붙이기만 한다. 적은 이벤트는 고치지 않고 지우지 않는다.
  - 상태를 바꾼 것과 같은 묶음(트랜잭션)으로 저장한다. 상태만 바뀌거나 기록만 남는 일이 없다.

스키마 이름을 적지 않는다. 연결의 search_path 가 정한다(app/core/database.py).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EventType(enum.StrEnum):
    """
    이벤트의 종류. 지금 실제로 일어나는 일만 있다.

    주사위, 판정, 상태 변경, AI 호출은 엔진과 AI 를 붙일 때 더한다.

    DB 에는 CHECK 조건을 걸지 않는다. 종류는 계속 늘어나는데, 걸어 두면 늘릴 때마다 마이그레이션이 필요하다.
    이벤트를 적는 길은 하나뿐이고(app/events/recorder.py), 그 함수가 이 형식만 받는다.
    """

    # --- 자리 ---
    # 테이블이 만들어졌다. 만든 사람이 방장이 되어 앉았다
    TABLE_CREATED = 'table_created'
    # 누가 들어와 앉았다
    MEMBER_JOINED = 'member_joined'
    # 누가 스스로 나갔다
    MEMBER_LEFT = 'member_left'
    # 방장이 누구를 내보냈다
    MEMBER_KICKED = 'member_kicked'
    # 방장이 바뀌었다. 넘겼거나, 방장이 나가서 다음 사람이 됐다
    HOST_CHANGED = 'host_changed'

    # --- 진행 ---
    # 방장이 테이블을 시작했다
    TABLE_STARTED = 'table_started'
    # GM 이 장면을 서술했다. 첫 서술은 스타팅이다
    GM_NARRATION = 'gm_narration'
    # 라운드가 열렸다. 선언을 받기 시작했다
    ROUND_OPENED = 'round_opened'
    # 플레이어가 선언한 행동. 라운드가 닫힐 때 마지막 글만 적는다
    PLAYER_ACTION = 'player_action'
    # 엔진이 행동을 판정했다. 주사위의 눈과 성패가 적힌다. 원인은 그 행동의 이벤트다
    CHECK_ROLLED = 'check_rolled'
    # 라운드가 닫혔다
    ROUND_CLOSED = 'round_closed'
    # 테이블이 끝났다
    TABLE_ENDED = 'table_ended'


class TableEvent(Base):
    """
    이벤트 하나.

    sequence 는 테이블 안에서의 순서다. 1 부터 빈 번호 없이 올라간다.
    읽는 쪽은 "17 번 뒤의 것을 달라"고 한다. 시각은 같을 수 있지만 번호는 겹치지 않는다.
    """

    __tablename__ = 'table_events'
    __table_args__ = (
        CheckConstraint('sequence >= 1', name='sequence_positive'),
        # 원인은 결과보다 먼저 일어난다
        CheckConstraint('caused_by_sequence < sequence', name='cause_comes_first'),
        # 한 테이블에 같은 번호의 이벤트가 둘일 수 없다. 번호를 잘못 매기면 DB 가 막는다.
        # 이 조건이 만드는 색인이 "이 테이블의 N 번 뒤"를 찾는 데도 쓰인다
        UniqueConstraint('table_id', 'sequence'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 테이블의 이벤트인가. 테이블의 행이 지워지면 함께 지워진다
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_tables.id', ondelete='CASCADE'))

    # 테이블 안에서의 순서. 테이블이 센다(game_tables.last_sequence)
    sequence: Mapped[int] = mapped_column(Integer)

    type: Mapped[str] = mapped_column(String(40))

    # 이 일을 한 사람. 인증 서버의 public_id 다. 사람이 한 일이 아니면 비어 있다(GM 의 서술, 저절로 닫힌 라운드)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    # 종류마다 다른 내용. 어떤 칸이 들어가는지는 적는 쪽(app/events/recorder.py 를 부르는 곳)이 정한다.
    # 큰 문서를 넣지 않는다. 판의 복사본, GM 전용 글, 초대 코드, 비밀번호는 여기에 적지 않는다
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 이 이벤트를 일으킨 이벤트의 번호. 같은 테이블의 것이다. 없으면 비어 있다.
    # "방장이 나갔다 → 방장이 바뀌었다"처럼 원인과 결과를 잇는다
    caused_by_sequence: Mapped[int | None] = mapped_column(Integer)

    # 요청 하나가 낳은 이벤트들의 묶음. 같은 묶음의 이벤트는 함께 저장됐다.
    # 선언 하나로 라운드가 닫히면 행동, 닫힘, 서술, 열림이 한 묶음이다.
    # 나중에 "마지막 턴 되돌리기"를 만들 때 이 묶음이 단위가 된다
    action_group_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
