# asset-server/app/observability/pool_metrics.py

"""
DB 연결 풀의 메트릭. 풀을 만드는 곳(app/core/database.py)이 이 풀을 쓴다.
앱이 뜰 때 값을 내보내기 시작한다(app/main.py).

  - db_pool_connections{state=idle|in_use}: 지금의 연결 수. 수집할 때 풀에 묻는다
  - db_pool_connections_max: 풀이 가질 수 있는 가장 많은 연결(pool_size + max_overflow)
  - db_pool_wait_seconds: 연결을 얻으려고 기다린 시간. 새 연결을 맺는 시간도 든다(결제 서버의 pgxpool 과 같다)

SQLAlchemy 의 풀에는 "꺼내기 시작"을 알리는 이벤트가 없다(checkout 은 꺼낸 뒤다). 그래서 풀의 꺼내는 자리(_do_get)를
감싼 풀을 쓴다. _do_get 은 SQLAlchemy 의 안쪽 이름이라 판이 바뀌면 깨질 수 있다. 테스트(tests/test_metrics.py)가 지킨다.
"""

import time

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.observability.metrics import PoolStats, record_pool_wait


class MeteredPool(AsyncAdaptedQueuePool):
    """연결을 얻으려고 기다린 시간을 재는 풀. 그 밖은 SQLAlchemy 의 비동기 풀(AsyncAdaptedQueuePool)과 같다."""

    def _do_get(self):  # noqa: ANN202 - SQLAlchemy 의 안쪽 함수를 그대로 감싼다
        started = time.perf_counter()
        try:
            return super()._do_get()
        finally:
            record_pool_wait(time.perf_counter() - started)


def pool_stats(engine: AsyncEngine, maximum: int) -> PoolStats:
    """엔진의 풀에서 지금의 값을 읽는 것. maximum 은 풀을 만들 때 정한 가장 많은 연결이다."""
    pool = engine.sync_engine.pool
    return PoolStats(idle=pool.checkedin, in_use=pool.checkedout, maximum=maximum)
