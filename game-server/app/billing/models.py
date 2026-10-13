# game-server/app/billing/models.py

"""
청구 기록. 라운드의 서술 값을 결제 서버에 무엇으로 잡았고, 어떻게 끝내야 하는지를 적는다.

라운드를 열 때 내는 사람마다(앉은 사람 모두) 한 줄을 만든다. 결제 서버를 부르는 것은 그 뒤다.
"부르겠다"를 라운드를 연 것과 같은 트랜잭션에 먼저 적고, 부른 결과로 상태를 옮긴다.
"확정해야 한다"도 라운드를 닫은 것과 같은 트랜잭션에 적는다. 그래서 어느 순간에 서버가 꺼져도
해야 할 일이 DB 에 남고, 정리 작업(app/billing/settler.py)이 마저 한다. 결제 서버를 부르는 동안에는 잠금을 쥐지 않는다.

상태는 한 방향으로 간다.

    pending ──걸림──▶ held ──서술이 다음 장면이 됨──▶ capture_due ──확정──▶ captured
       │  ▲            │
       │  └─충전 뒤─┐   └──테이블이 끝남, 떠남──▶ release_due ──반환──▶ released
       └──모자람──▶ short ───────테이블이 끝남, 떠남──┘
    어느 것이든 결제 서버가 거절하면(버그) ──▶ failed

    - pending: 걸어야 한다. 아직 걸지 않았거나, 불렀는데 답을 받지 못해 걸렸는지 모른다
    - short: 크레딧이 모자랐다. 결제 서버에 홀드가 없다. 충전하면 라운드를 닫을 때 다시 걸어 본다
    - capture_due, release_due: 확정할 것, 돌려줄 것. 라운드를 닫거나, 테이블이 끝나거나, 내는 사람이 떠날 때
      정해지고, 부르는 것은 그 뒤다
    - failed: 결제 서버가 받아들이지 않았다. 사람이 봐야 한다. 로그에 오류로 남는다

이름표(reference)는 결제 서버가 이 홀드를 가리키는 이름이다. 라운드와 내는 사람으로 지어 한 번만 쓴다.
서술이 실패해 다시 맡겨도 같은 홀드를 그대로 쓴다.

결제 서버의 홀드에는 만료가 있다(HOLD_TTL, 기본 24시간). 걸린(held) 청구는 정리 작업이 만료까지 남은 시간의 절반이
지날 때마다 연장한다(답의 expires_at 으로 정한다).
연장하려니 만료되어 이미 돌려준 홀드면, 아직 서술 전이므로 새 이름표로 다시 건다(held → pending, renewals 가 하나 는다).
같은 이름표는 결제 서버에서 끝난 홀드라 다시 쓸 수 없다. 서술 뒤의 확정이 만료로 409 를 받으면 failed 다(받지 못한다).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assets.models import one_of
from app.core.database import Base
from app.rounds.models import Round


class ChargeStatus(enum.StrEnum):
    """청구 하나의 상태. 위의 그림의 순서다."""

    PENDING = 'pending'
    HELD = 'held'
    SHORT = 'short'
    CAPTURE_DUE = 'capture_due'
    CAPTURED = 'captured'
    RELEASE_DUE = 'release_due'
    RELEASED = 'released'
    FAILED = 'failed'


# 정리 작업이 결제 서버를 부를 상태들. 걸림(held)은 연장할 때가 됐을 때다.
# short 는 넣지 않는다. 충전했는지는 라운드를 닫을 때 다시 걸어 보며 안다
DUE_STATUSES = (ChargeStatus.PENDING, ChargeStatus.HELD, ChargeStatus.CAPTURE_DUE, ChargeStatus.RELEASE_DUE)
# 결제 서버에 홀드가 있거나 있을 수 있는, 아직 끝나지 않은 상태들. 테이블이 끝나면 돌려준다
OPEN_STATUSES = (ChargeStatus.PENDING, ChargeStatus.HELD, ChargeStatus.SHORT)
# 서술해도 되는 상태들. 값을 잡아 두었다
SECURED_STATUSES = (ChargeStatus.HELD, ChargeStatus.CAPTURE_DUE, ChargeStatus.CAPTURED)


def status_in(statuses: tuple[ChargeStatus, ...]) -> str:
    """상태가 이 목록 안에 있다는 조건을 SQL 로 만든다."""
    return 'status IN ({})'.format(', '.join(f"'{status}'" for status in statuses))


# 조건이 붙은 색인의 조건. 마이그레이션도 같은 글자를 쓴다
DUE_CONDITION = status_in(DUE_STATUSES)
OPEN_CONDITION = status_in(OPEN_STATUSES)


class NarrationCharge(Base):
    """라운드 하나의 서술 값을 한 사람에게서 받는 청구."""

    __tablename__ = 'narration_charges'
    __table_args__ = (
        CheckConstraint(one_of('status', ChargeStatus), name='status_allowed'),
        CheckConstraint('attempts >= 0', name='attempts_not_negative'),
        # 한 라운드에 한 사람에게서 한 번만 받는다
        UniqueConstraint('round_id', 'payer_id'),
        # 정리 작업이 몇 초마다 부를 차례가 된 것을 찾는다. 끝난 청구는 색인에 들지 않는다
        Index('ix_narration_charges_due', 'next_attempt_at', postgresql_where=DUE_CONDITION),
        # 정리 작업이 몇 초마다 끝난 테이블의 끝나지 않은 청구를 찾는다(repository.release_abandoned).
        # 끝나지 않은 청구는 열린 테이블마다 하나쯤이라 색인이 작다. 없으면 바퀴마다 지금까지의 청구를 모두 훑는다
        Index('ix_narration_charges_open', 'round_id', postgresql_where=OPEN_CONDITION),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # 어느 라운드의 서술 값인가. 라운드가 지워지면 함께 지워진다(테이블이 지워질 때)
    # 따로 색인을 두지 않는다. 아래의 유일 조건(round_id, payer_id)이 이것으로 시작하는 색인을 만든다
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('table_rounds.id', ondelete='CASCADE'))
    # 라운드와 함께 저장할 때 라운드를 먼저 넣게 하려고 둔다(라운드를 여는 트랜잭션). 읽을 때 쓰지 않는다.
    # 실수로 읽으면 예외가 난다(비동기 세션은 몰래 DB 를 읽을 수 없다)
    round: Mapped[Round] = relationship(lazy='raise')

    # 내는 사람. 인증 서버의 public_id 다. 라운드를 열 때 앉아 있던 사람이다. 떠나면 돌려준다(charges.release_departed)
    payer_id: Mapped[uuid.UUID] = mapped_column(Uuid)

    # 결제 서버가 이 홀드를 가리키는 이름표. 결제 서버의 규칙(영문자, 숫자, . _ : -, 8~200자)을 따른다
    reference: Mapped[str] = mapped_column(String(200), unique=True)

    # 만료되어 돌려받은 홀드를 새 이름표로 다시 건 횟수. 이름표의 끝에 붙는다(charges.reference_for)
    renewals: Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    # 결제 서버의 가격표 이름. 값은 결제 서버가 정한다. 게임 서버는 금액을 모른다
    price_code: Mapped[str] = mapped_column(String(40))

    status: Mapped[str] = mapped_column(String(20), default=ChargeStatus.PENDING)

    # 결제 서버의 답을 받지 못해 다시 부른 횟수. 다음에 부를 때까지의 간격이 이것으로 늘어난다
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # 정리 작업이 이 시각 뒤에 부른다. 걸린 청구면 연장할 때다.
    # 늘 앱의 시계로 채운다(처음은 charges.charge_round). 정리 작업이 앱의 시계와 비교한다.
    # 기본값(server_default)은 DB 의 시계라 기대지 않는다
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 마지막으로 부르지 못한 까닭(unreachable, timeout, server_error, unauthorized, rejected_409 …). 본문은 적지 않는다
    last_error: Mapped[str | None] = mapped_column(String(40))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
