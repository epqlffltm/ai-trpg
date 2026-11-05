# story-server/app/snapshots/counting.py

"""
끝나지 않은 장면 그림의 청구를 상태마다 센다(#983). 정리 작업이 바퀴의 끝에 불러 메트릭(snapshot_charges)에 적는다.
SQL 만 짓고 커밋하지 않는다. 셈은 청구 상태의 색인(ix_snapshots_billing_status_next_settle_at)을 탄다.
게임 서버의 것(trpg-server/app/snapshots/counting.py)과 같은 이름과 상태다.
"""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.snapshots.models import Snapshot
from app.turns.models import BillingStatus

# 끝나지 않은 청구의 상태들. 차례는 메트릭의 이름표의 차례다.
# 끝난 것(captured, released, declined, failed)은 세지 않는다
UNFINISHED_STATUSES = (
    BillingStatus.PENDING,
    BillingStatus.HELD,
    BillingStatus.CAPTURE_DUE,
    BillingStatus.RELEASE_DUE,
)


def unfinished_by_status() -> Select:
    """끝나지 않은 청구를 상태마다 세는 쿼리."""
    return (
        select(Snapshot.billing_status, func.count())
        .where(Snapshot.billing_status.in_([status.value for status in UNFINISHED_STATUSES]))
        .group_by(Snapshot.billing_status)
    )


async def count_unfinished(session: AsyncSession) -> dict[str, int]:
    """끝나지 않은 청구의 수를 상태마다 센다. 없는 상태도 0 으로 넣는다."""
    counted = {status: count for status, count in (await session.execute(unfinished_by_status())).all()}
    return {status.value: counted.get(status.value, 0) for status in UNFINISHED_STATUSES}
