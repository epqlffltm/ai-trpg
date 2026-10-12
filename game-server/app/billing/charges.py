# game-server/app/billing/charges.py

"""
청구 기록의 규칙. 누가 내는가, 이름표를 어떻게 짓는가, 언제 어느 상태로 옮기는가. 결제 서버를 부르지 않는다.

DB 를 쓰는 함수는 부른 쪽의 트랜잭션 안에서 돈다. 라운드를 연 것, 닫은 것과 한 묶음으로 저장되게 하려는 것이다.
  - 라운드를 열 때(app/rounds/opener.py): charge_round 가 "걸어야 한다"를 적는다
  - 라운드를 닫을 때(app/rounds/service.py 의 finish_closing): settle_round 가 "확정할 것" 또는 "돌려줄 것"을 적는다
결제 서버를 부르는 것은 그 트랜잭션이 끝난 뒤다(app/billing/settling.py).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import repository
from app.billing.models import ChargeStatus, NarrationCharge
from app.rounds.models import Round
from app.tables.models import GameTable

# 결제 서버의 가격표 이름. 라운드의 AI 서술 한 번이다. 모델마다 다르게 받는 것은 #151 에서 한다
PRICE_CODE = 'narration.standard'

# 결제 서버의 답을 받지 못했을 때 다시 부르기까지 기다리는 시간(초). 부를 때마다 두 배가 되고, 상한에서 멈춘다
RETRY_BASE_SECONDS = 5.0
RETRY_MAX_SECONDS = 300.0


def payers_of(table: GameTable) -> list[uuid.UUID]:
    """
    이 테이블의 라운드 서술 값을 내는 사람들. 지금은 방장 한 명이다.

    테이블을 연 사람이 GM 을 부른 셈이라 방장이 낸다. 나눠 내기로 바꾸려면 여기서 여러 명을 돌려주고,
    결제 서버의 가격표에 한 사람 몫을 더한다. 청구 기록은 라운드 × 내는 사람 한 줄씩이라 그대로 쓴다.
    """
    return [table.host_id]


def reference_for(table_id: uuid.UUID, number: int, payer_id: uuid.UUID) -> str:
    """결제 서버의 이름표. 테이블, 라운드, 내는 사람으로 짓는다. 같은 라운드의 같은 사람이면 언제 지어도 같다."""
    return f'narration:{table_id}:{number}:{payer_id}'


def retry_delay(attempts: int) -> timedelta:
    """attempts 번째로 부르지 못한 뒤에 다시 부르기까지 기다리는 시간."""
    seconds = RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0)
    return timedelta(seconds=min(seconds, RETRY_MAX_SECONDS))


def charge_round(session: AsyncSession, table: GameTable, round_: Round) -> None:
    """
    연 라운드의 서술 값을 걸어야 한다고 적는다. 라운드를 여는 트랜잭션 안에서 부른다. 저장하지는 않는다.

    라운드는 아직 저장하지 않았어도 된다. 저장할 때 라운드를 먼저 넣는다(NarrationCharge.round).
    결제 서버는 부르지 않는다. 정리 작업이 곧 걸고(크레딧이 모자란 것을 일찍 알린다),
    라운드를 닫을 때 걸렸는지 다시 본다.
    """
    charges = [
        NarrationCharge(
            round=round_,
            payer_id=payer,
            reference=reference_for(table.id, round_.number, payer),
            price_code=PRICE_CODE,
            status=ChargeStatus.PENDING,
        )
        for payer in payers_of(table)
    ]
    repository.add_charges(session, charges)


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
