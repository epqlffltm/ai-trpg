# game-server/app/billing/charges.py

"""
청구 기록의 규칙. 누가 내는가, 이름표를 어떻게 짓는가, 언제 어느 상태로 옮기는가. 결제 서버를 부르지 않는다.

DB 를 쓰는 함수는 부른 쪽의 트랜잭션 안에서 돈다. 라운드를 연 것, 닫은 것과 한 묶음으로 저장되게 하려는 것이다.
  - 라운드를 열 때(app/rounds/opener.py): charge_round 가 앉은 사람마다 "걸어야 한다"를 적는다
  - 누가 떠날 때(app/tables/service.py 의 leave_table, kick_member): release_departed 가 그 사람의 것을
    "돌려줄 것"으로 적는다
  - 라운드를 닫을 때(app/rounds/service.py 의 finish_closing): settle_round 가 "확정할 것" 또는 "돌려줄 것"을 적는다
결제 서버를 부르는 것은 그 트랜잭션이 끝난 뒤다(app/billing/settling.py).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import repository
from app.billing.models import ChargeStatus, NarrationCharge
from app.billing.prices import PRICE_CODE_PREFIX, narration_code
from app.rounds.models import Round
from app.tables.models import GameTable

# 결제 서버의 답을 받지 못했을 때 다시 부르기까지 기다리는 시간(초). 부를 때마다 두 배가 되고, 상한에서 멈춘다
RETRY_BASE_SECONDS = 5.0
RETRY_MAX_SECONDS = 300.0

# 결제 서버가 만료 시각을 알려 주지 않을 때(받지 않는 것, 시각이 빠진 답) 연장하는 간격.
# 결제 서버의 HOLD_TTL 기본값(24시간)의 절반이다. 시각을 알면 그것으로 정한다(next_extension)
EXTEND_AFTER = timedelta(hours=12)
# 결제 서버가 연장을 받아들이지 않을 때(버그) 다시 부르기까지 기다리는 시간. 그때마다 오류가 남는다
EXTEND_REJECTED_RETRY = timedelta(hours=1)


# 떠난 사람의 청구 중 라운드가 닫는 중이어도 돌려주는 것. 아직 걸지 못했거나 모자랐다. 서술을 막지 않게 한다
DEPARTED_ALWAYS = (ChargeStatus.PENDING, ChargeStatus.SHORT)
# 떠난 사람의 청구 중 라운드가 선언을 받는 중일 때만 돌려주는 것.
# 닫기 시작한 뒤면 그 사람의 선언도 서술에 들어가므로 받는다
DEPARTED_WHILE_OPEN = (ChargeStatus.HELD,)


def payers_of(table: GameTable) -> list[uuid.UUID]:
    """
    이 테이블의 라운드 서술 값을 내는 사람들. 라운드를 열 때 앉아 있는 사람 모두다(쓰러진 사람도). 앉은 차례다.

    각자 그 모델의 값을 낸다. 나눠 내지 않는다(#180). 사람마다 이름표가 달라 결제 서버는 홀드를 따로 받는다.
    """
    return [member.user_id for member in table.members]


# 모델이 없는 라운드의 가격표 이름. 서술 등급이 있던 때의 standard 의 것이다.
# 모델을 고르는 규칙 전에 만든 테이블과 연 라운드만 쓴다. 결제 서버가 이 이름을 팔지 않으면 홀드를 받지 않고,
# 방장이 모델을 고르면 풀린다(app/tables/narration_models.py)
LEGACY_PRICE_CODE = f'{PRICE_CODE_PREFIX}.standard'


def price_code_of(round_: Round) -> str:
    """
    그 라운드의 서술 값의 가격표 이름. 그 모델의 것(narration.<이름표>.i0.o0)이다. 값은 결제 서버의 가격표가 정한다.

    모델이 없는 옛 라운드는 LEGACY_PRICE_CODE 다.
    """
    if round_.narration_model is not None:
        return narration_code(round_.narration_model)
    return LEGACY_PRICE_CODE


# 방장이 라운드의 모델을 바꿀 때 새 가격표로 다시 걸 청구들. 아직 서술 값을 받지 않았다.
# 걸어야 함, 걸림, 모자람, 그리고 가격표를 팔지 않아 실패한 것이다. 확정할 것·확정한 것은 이미 서술했다
REPRICEABLE = (ChargeStatus.PENDING, ChargeStatus.HELD, ChargeStatus.SHORT, ChargeStatus.FAILED)


async def reprice_round(session: AsyncSession, round_: Round, now: datetime) -> int:
    """
    라운드의 모델을 바꾼 뒤 그 라운드의 청구를 새 가격표(price_code_of)로 다시 걸게 적는다. 옮긴 수.

    같은 이름표로는 다른 가격표를 걸 수 없다(결제 서버의 hold.reference_reused). 그래서 옛 홀드를 돌려줄 것으로
    적고, 서술 전에 새 이름표로 새 가격표를 건다(app/billing/settling.py 의 restore). 크레딧을 기다리다 돌려준 청구를
    다시 거는 길과 같다. 부른 쪽의 트랜잭션 안에서 돈다. 결제 서버는 부르지 않는다.
    """
    return await repository.reprice_round(session, round_.id, REPRICEABLE, price_code_of(round_), now)


def reference_for(table_id: uuid.UUID, number: int, payer_id: uuid.UUID, renewals: int = 0) -> str:
    """
    결제 서버의 이름표. 테이블, 라운드, 내는 사람으로 짓는다. 같은 라운드의 같은 사람이면 언제 지어도 같다.

    만료되어 다시 건 홀드는 그 횟수를 끝에 붙인다(:r1, :r2 …). 처음 건 홀드는 붙이지 않는다(그 전에 지은 이름표와 같다).
    """
    base = f'narration:{table_id}:{number}:{payer_id}'
    return f'{base}:r{renewals}' if renewals else base


def retry_delay(attempts: int) -> timedelta:
    """attempts 번째로 부르지 못한 뒤에 다시 부르기까지 기다리는 시간."""
    seconds = RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0)
    return timedelta(seconds=min(seconds, RETRY_MAX_SECONDS))


def next_extension(now: datetime, expires_at: datetime | None) -> datetime:
    """
    걸린 홀드를 다음에 연장할 시각. 만료까지 남은 시간의 절반이 지났을 때다. 한 번 놓쳐도 만료 전에 한 번 더 부른다.

    결제 서버의 HOLD_TTL 은 설정이라 환경마다 다르다(최소 1분). 그래서 고정 간격이 아니라 답의 만료 시각으로 정한다.
    이미 지났으면 바로 다시 연장한다. 만료 시각을 모르면 정해 둔 간격(EXTEND_AFTER)이다.
    """
    if expires_at is None:
        return now + EXTEND_AFTER
    return now + max((expires_at - now) / 2, timedelta(0))


def charge_round(session: AsyncSession, table: GameTable, round_: Round, now: datetime) -> None:
    """
    연 라운드의 서술 값을 걸어야 한다고 적는다. 라운드를 여는 트랜잭션 안에서 부른다. 저장하지는 않는다.

    라운드는 아직 저장하지 않았어도 된다. 저장할 때 라운드를 먼저 넣는다(NarrationCharge.round).
    결제 서버는 부르지 않는다. 정리 작업이 곧 걸고(크레딧이 모자란 것을 일찍 알린다),
    라운드를 닫을 때 걸렸는지 다시 본다. 값은 라운드의 서술 모델이나 등급의 것이다(price_code_of).

    처음 부를 시각은 now(라운드를 연 시각, 앱의 시계)다. DB 의 now() 에 맡기지 않는다.
    정리 작업은 앱의 시계로 부를 차례를 고른다(repository.find_due). DB 의 시계가 앞서면 그만큼 늦게 건다.
    """
    charges = [
        NarrationCharge(
            round=round_,
            payer_id=payer,
            reference=reference_for(table.id, round_.number, payer),
            price_code=price_code_of(round_),
            status=ChargeStatus.PENDING,
            next_attempt_at=now,
        )
        for payer in payers_of(table)
    ]
    repository.add_charges(session, charges)


async def release_departed(session: AsyncSession, table_id: uuid.UUID, user_id: uuid.UUID, now: datetime) -> int:
    """
    테이블을 떠난(나갔거나 내보내진) 사람의 닫히지 않은 라운드의 청구를 돌려줄 것으로 적는다.
    떠나는 트랜잭션 안에서 부른다.

      - 아직 걸지 못했거나 모자란 청구: 늘 돌려준다. 떠난 사람 때문에 남은 사람의 서술이 막히지 않는다.
        방장이 모자란 사람을 내보내면 바로 다시 맡겨 서술할 수 있다
      - 걸린 청구: 라운드가 선언을 받는 중이면 돌려준다. 닫기 시작한 뒤면 그대로 두고 서술되면 확정한다.
        그 사람의 선언이 이미 굳어 장면에 들어간다
    결제 서버는 부르지 않는다. 정리 작업이 곧 돌려준다. 바꾼 수를 돌려준다.
    """
    return await repository.release_departed(session, table_id, user_id, DEPARTED_ALWAYS, DEPARTED_WHILE_OPEN, now)


def settled_status(delivered: bool) -> ChargeStatus:
    """라운드를 닫으며 정한 청구의 다음 상태. 서술이 다음 장면이 됐으면 확정, 아니면 반환이다."""
    return ChargeStatus.CAPTURE_DUE if delivered else ChargeStatus.RELEASE_DUE


async def settle_round(session: AsyncSession, round_id: uuid.UUID, delivered: bool, now: datetime) -> int:
    """
    닫은 라운드의 걸린 청구를 확정할 것(delivered) 또는 돌려줄 것으로 적는다. 라운드를 닫는 트랜잭션 안에서 부른다.

    걸린(held) 것만 옮긴다. 서술은 값을 잡아 둔 뒤에만 하므로(settling.secure_round) 닫는 라운드의 청구는 걸려 있다.
    걸리지 않은 것은 테이블이 끝나 이미 돌려줄 것이 됐거나, 이 기록이 생기기 전에 연 라운드라 청구가 없다.
    """
    return await repository.move_round(session, round_id, (ChargeStatus.HELD,), settled_status(delivered), now)
