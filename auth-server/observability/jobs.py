# auth-server/observability/jobs.py

"""
요청과 따로 도는 일에 식별자(job_id)를 건다. 규격은 docs/observability.md 에 있다.

인증 서버에서 요청과 따로 도는 일은 관리 명령으로 띄운다. 메일 워커(send_outgoing_mail), 미인증 계정 정리
(delete_unverified_users), 보안 이벤트 요약(send_security_digest)이다. 요청이 아니므로 request_id 가 없다.
일 한 번에 job_id 를 하나 걸어, 그 일이 남긴 로그를 묶는다.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from observability.context import job_scope
from observability.identifiers import new_job_id
from observability.spans import job_span

logger = logging.getLogger(__name__)

# 실패한 작업의 오류 코드
JOB_FAILED_ERROR_CODE = 'job.failed'


def elapsed_ms(started: float) -> int:
    """started(time.perf_counter 의 값)부터 지금까지 걸린 시간(밀리초)."""
    return round((time.perf_counter() - started) * 1000)


@contextmanager
def run_as_job(operation: str) -> Iterator[str]:
    """
    with 안의 일을 작업 하나로 돌린다. 도는 동안 남기는 모든 로그에 그 작업의 식별자가 붙는다.

    operation 은 무슨 종류의 일인지다(mail.deliver_outgoing). 일마다 달라지는 값을 넣지 않는다.
    끝나면 한 줄을 남긴다. 잘 끝난 것은 debug 다. 메일 워커는 1초마다 돈다. info 로 적으면 로그를 메운다.
    예외로 끝난 것은 error 로 적고 예외를 그대로 올린다.
    작업의 span(이름은 operation)도 건다. 그 안의 쿼리와 결제 서버를 부르는 것이 아래에 놓인다(spans.job_span).
    할 일이 없던 바퀴는 처리한 수를 0 으로 적어 두면(spans.record_handled) 그 추적을 보내지 않는다.
    """
    job_id = new_job_id()
    with job_span(operation, job_id), job_scope(job_id):
        started = time.perf_counter()
        try:
            yield job_id
        except Exception:
            logger.error(
                '작업이 실패했다',
                exc_info=True,
                extra={
                    'operation': operation,
                    'duration_ms': elapsed_ms(started),
                    'result': 'server_error',
                    'error_code': JOB_FAILED_ERROR_CODE,
                },
            )
            raise
        logger.debug(
            '작업이 끝났다',
            extra={'operation': operation, 'duration_ms': elapsed_ms(started), 'result': 'success'},
        )
