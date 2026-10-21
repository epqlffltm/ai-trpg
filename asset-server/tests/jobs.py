# asset-server/tests/jobs.py

"""
테스트에서만 도는 뒤의 작업 한 바퀴. 작업의 식별자, span, 메트릭이 한 바퀴를 따라가는지 볼 때 쓴다.

서버의 작업(알림 서버의 정리 작업, 게임 서버의 색인)과 같은 모양으로 감싼다. span 을 먼저 걸고,
그 안에서 job_id 를 걸고, 메트릭을 센다. 그 안의 쿼리와 로그가 이 바퀴의 것이 된다.
뼈대의 서버에는 아직 뒤의 작업이 끊긴 세션 목록 받기뿐이다(그것은 바퀴를 따로 감싸지 않는다).
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from sqlalchemy import text

from app.observability.context import job_scope
from app.observability.identifiers import new_job_id
from app.observability.metrics import measured_job
from app.observability.spans import job_span

logger = logging.getLogger(__name__)

# 작업의 이름. 로그의 operation, span 의 이름, 메트릭의 label 이다
PROBE_OPERATION = 'asset.probe'


async def query_once(app: FastAPI) -> None:
    """DB 에 문장 하나를 보낸다."""
    async with app.state.session_factory() as session:
        await session.execute(text('SELECT 1'))


async def run_round(app: FastAPI, work: Callable[[FastAPI], Awaitable[None]] = query_once) -> None:
    """한 바퀴. work 를 하고 끝났다는 줄을 남긴다. work 가 실패하면 그대로 올린다."""
    job_id = new_job_id()
    with job_span(PROBE_OPERATION, job_id), job_scope(job_id), measured_job(PROBE_OPERATION):
        await work(app)
        logger.info('한 바퀴를 돌았다', extra={'operation': PROBE_OPERATION, 'result': 'success'})
