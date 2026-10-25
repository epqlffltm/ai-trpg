# board-server/app/core/metrics.py

"""
게시판 서버만의 메트릭(docs/observability.md 의 "서버만의 메트릭"). 대시보드 board-server 와 경보가 읽는다.

| 이름 | label | 뜻 |
| --- | --- | --- |
| board_writes_total | resource(post, comment), action(create, update, delete), result | 글과 댓글을 쓴 수 |
| board_reports_total | target(post, comment), result | 신고한 수 |
| board_searches_total | result(success, timeout) | 글을 검색한 수 |
| board_search_duration_seconds | | 검색 하나가 걸린 시간 |

쓰기와 신고의 result 는 success, rejected(4xx), rate_limited(429) 다. 서버의 잘못(5xx)은 HTTP 메트릭이 센다.
입력의 모양이 틀린 요청(400)은 함수가 불리기 전에 막혀 여기서 세지 않는다. HTTP 메트릭의 400 에 든다.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from fastapi import status
from opentelemetry.metrics import Counter, Histogram, Meter
from server_core.observability.metrics import InstrumentSet, duration_histogram
from starlette.exceptions import HTTPException

from app.core.errors import ApiError

SUCCESS = 'success'
REJECTED = 'rejected'
RATE_LIMITED = 'rate_limited'
SEARCH_SUCCESS = 'success'
SEARCH_TIMEOUT = 'timeout'


@dataclass(frozen=True)
class BoardInstruments:
    writes: Counter
    reports: Counter
    searches: Counter
    search_duration: Histogram


def build(meter: Meter) -> BoardInstruments:
    return BoardInstruments(
        writes=meter.create_counter('board_writes', description='글과 댓글을 쓴 수'),
        reports=meter.create_counter('board_reports', description='글과 댓글을 신고한 수'),
        searches=meter.create_counter('board_searches', description='글을 검색한 수'),
        search_duration=duration_histogram(meter, 'board_search_duration', '검색 하나가 걸린 시간'),
    )


INSTRUMENTS = InstrumentSet(build)


def record_write(resource: str, action: str, result: str) -> None:
    INSTRUMENTS.get().writes.add(1, {'resource': resource, 'action': action, 'result': result})


def record_report(target: str, result: str) -> None:
    INSTRUMENTS.get().reports.add(1, {'target': target, 'result': result})


def record_search(result: str, seconds: float) -> None:
    INSTRUMENTS.get().searches.add(1, {'result': result})
    INSTRUMENTS.get().search_duration.record(seconds)


def result_of_status(status_code: int) -> str | None:
    """거절의 상태 코드를 결과로. 서버의 잘못(5xx)이면 None 이다(세지 않는다)."""
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return RATE_LIMITED
    return REJECTED if status_code < status.HTTP_500_INTERNAL_SERVER_ERROR else None


@contextmanager
def counted(record: Callable[[str], None]) -> Iterator[None]:
    """
    감싼 일의 결과를 센다. 끝까지 가면 success, 거절이면 그 코드의 결과다.

        with counted(partial(record_write, 'post', 'create')):
            ...
    """
    try:
        yield
    except (ApiError, HTTPException) as error:
        result = result_of_status(error.status_code)
        if result is not None:
            record(result)
        raise
    record(SUCCESS)
