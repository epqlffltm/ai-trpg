# asset-server/app/observability/formatter.py

"""
로그 한 줄을 공통 규격의 JSON 으로 바꾼다. 표준 logging 의 Formatter 다. 규격은 docs/observability.md 에 있다.

로그를 남기는 코드는 그대로 logging 을 쓴다.

    logger.info('라운드를 닫았다', extra={'operation': 'round.close', 'duration_ms': 12})

여기서 그 한 줄에 시각, 수준, 서비스 이름, 환경, 버전을 붙인다.
식별자(request_id, trace_id, job_id)는 로그가 남는 순간에 이미 붙어 있다(setup.py).
extra 로 넘어온 칸은 민감한 값을 가린 뒤에 싣는다(redaction.py). 예외가 딸려 있으면 종류와 기록(stack trace)을 싣는다.

한 줄에 JSON 하나다. 글 안의 줄바꿈은 JSON 이 \\n 으로 바꿔 적는다. 메시지에 줄바꿈을 넣어 가짜 로그 줄을 만들 수 없다.
"""

import json
import logging
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime

from app.observability.redaction import MAX_MESSAGE_LENGTH, MAX_STACK_LENGTH, safe_value, scrub_text

# logging 의 수준을 규격의 이름으로 바꾼다
LEVEL_NAMES = {
    logging.DEBUG: 'debug',
    logging.INFO: 'info',
    logging.WARNING: 'warning',
    logging.ERROR: 'error',
    logging.CRITICAL: 'critical',
}
# 예외가 딸린 로그에 오류 코드를 적지 않았을 때 쓰는 코드
DEFAULT_ERROR_CODE = 'internal.error'
# LogRecord 가 원래 갖고 있는 이름들. 이 밖의 이름이 extra 로 넘어온 칸이다
_RECORD_FIELDS = frozenset(vars(logging.makeLogRecord({}))) | {'message', 'asctime', 'taskName'}
# 싣지 않는 칸. uvicorn 이 터미널에 색을 입히려고 넘기는 글이다. 같은 내용이 message 에 있다
_IGNORED_FIELDS = frozenset({'color_message'})
# extra 로 덮어쓸 수 없는 칸. 이 서버가 정하는 값이다
_FIXED_FIELDS = frozenset({'timestamp', 'level', 'service', 'environment', 'version', 'logger', 'message'})
# 로그 한 줄에 식별자들을 묶어 붙여 두는 칸의 이름. logging 이 한 줄을 만들 때 붙인다(setup.py)
CONTEXT_IDS_FIELD = 'context_ids'
# 식별자의 이름들
ID_FIELDS = frozenset({'request_id', 'trace_id', 'job_id'})


@dataclass(frozen=True)
class ServiceInfo:
    """모든 로그 줄에 붙는, 이 서버가 누구인지."""

    service: str
    environment: str
    version: str


def timestamp_of(record: logging.LogRecord) -> str:
    """로그가 남은 시각. RFC 3339, UTC, 밀리초까지(2026-10-11T09:00:00.123Z)."""
    moment = datetime.fromtimestamp(record.created, UTC)
    return moment.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def level_of(record: logging.LogRecord) -> str:
    """로그의 수준. 규격에 있는 다섯 이름 중 하나다. 그 사이의 수준은 아래쪽 이름으로 내린다."""
    known = [number for number in LEVEL_NAMES if number <= record.levelno]
    return LEVEL_NAMES[max(known)] if known else LEVEL_NAMES[logging.DEBUG]


def extra_fields(record: logging.LogRecord) -> dict[str, object]:
    """extra 로 넘어온 칸들. 민감한 값은 가려져 있다. 이 서버가 정하는 칸은 덮어쓰지 못한다."""
    return {
        name: safe_value(name, value)
        for name, value in vars(record).items()
        if name not in _RECORD_FIELDS | _FIXED_FIELDS | _IGNORED_FIELDS and name != CONTEXT_IDS_FIELD
    }


def context_ids(record: logging.LogRecord) -> dict[str, str]:
    """로그가 남을 때 걸려 있던 식별자들(request_id, trace_id, job_id). 걸려 있지 않았으면 비어 있다."""
    ids = getattr(record, CONTEXT_IDS_FIELD, None)
    if not isinstance(ids, dict):
        return {}
    return {name: value for name, value in ids.items() if name in ID_FIELDS and isinstance(value, str)}


def error_fields(record: logging.LogRecord) -> dict[str, object]:
    """딸려 온 예외의 종류와 기록. 예외가 없으면 비어 있다. 기록은 서버 안에서만 본다."""
    if not record.exc_info or record.exc_info[1] is None:
        return {}
    error = record.exc_info[1]
    stack = ''.join(traceback.format_exception(error))
    return {
        'error_code': DEFAULT_ERROR_CODE,
        'error_type': type(error).__name__,
        'stack_trace': scrub_text(stack, MAX_STACK_LENGTH),
    }


class JsonFormatter(logging.Formatter):
    """로그 한 줄을 공통 규격의 JSON 한 줄로 바꾼다."""

    def __init__(self, info: ServiceInfo) -> None:
        super().__init__()
        self.info = info

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            'timestamp': timestamp_of(record),
            'level': level_of(record),
            'service': self.info.service,
            'environment': self.info.environment,
            'version': self.info.version,
            'logger': record.name,
            'message': scrub_text(record.getMessage(), MAX_MESSAGE_LENGTH),
        }
        # 뒤에 오는 것이 앞의 것을 덮는다. 예외의 기본 코드 < extra 로 적은 값 < 로그가 남을 때 걸려 있던 식별자.
        # 식별자는 extra 로 바꿔 적을 수 없다. 걸려 있던 것이 이긴다
        entry.update(error_fields(record))
        entry.update(extra_fields(record))
        entry.update(context_ids(record))
        return json.dumps(entry, ensure_ascii=False, default=str)
