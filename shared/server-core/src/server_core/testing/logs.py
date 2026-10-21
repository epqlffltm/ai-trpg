# shared/server-core/src/server_core/testing/logs.py

"""
테스트가 로그를 읽을 때 함께 쓰는 도구. 서버들의 테스트가 함께 쓴다.

로그는 pytest 의 caplog 로 잡는다. 잡은 것을 실제로 나가는 모양(공통 규격의 JSON)으로 바꿔서 본다.
그래야 "이 칸이 로그에 실리는가", "이 값이 가려지는가"를 서버가 내보내는 그대로 확인한다.
"""

import json
import logging

from server_core.observability.formatter import JsonFormatter, ServiceInfo
from server_core.observability.setup import install_record_factory

# 테스트에서 쓰는, 이 서버가 누구인지. 서버의 이름을 보는 테스트는 render 에 제 것을 넘긴다
TEST_INFO = ServiceInfo(service='test-server', environment='test', version='test-version')


def render(record: logging.LogRecord, info: ServiceInfo = TEST_INFO) -> dict:
    """로그 한 줄을 서버가 내보내는 JSON 으로 바꾼 뒤 다시 읽는다."""
    return json.loads(JsonFormatter(info).format(record))


def rendered(records: list[logging.LogRecord], logger: str) -> list[dict]:
    """그 로거가 남긴 줄들을 서버가 내보내는 모양으로 돌려준다."""
    return [render(record) for record in records if record.name == logger]


def make_record(message: str = '글', level: int = logging.INFO, **extra: object) -> logging.LogRecord:
    """
    로그 한 줄을 logging 이 만드는 것과 같은 길로 만든다. extra 는 logger.info(..., extra=...) 로 넘긴 것과 같다.

    지금 걸려 있는 식별자가 붙는다(server_core/observability/setup.py 의 install_record_factory).
    """
    install_record_factory()
    record = logging.getLogRecordFactory()('tests', level, __file__, 1, message, None, None)
    for name, value in extra.items():
        setattr(record, name, value)
    return record
