# auth-server/observability/heartbeat.py

"""
워커의 심장박동(#258). 워커가 한 바퀴를 DB 에 닿아 끝낼 때마다 파일의 시각을 지금으로 바꾼다.

compose 의 healthcheck 가 그 파일이 정한 시간 안에 바뀌었는지 본다.
그래서 워커의 healthy 는 "DB 에 닿으며 돈다"는 뜻이다.
DB 에 닿지 못한 바퀴는 바꾸지 않는다. 워커가 살아 있어도 그동안은 unhealthy 로 보인다.

파일의 자리는 설정의 HEARTBEAT_FILE 이다. 비어 있으면 아무것도 하지 않는다(PC 에서 돌릴 때).
규격은 docs/observability.md 의 "워커의 상태"에 있다. 결제 서버의 정리 작업도 같은 모양이다.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def beat(path: str) -> None:
    """
    심장박동 파일의 시각을 지금으로 바꾼다. 없으면 만든다. path 가 비어 있으면 아무것도 하지 않는다.

    바꾸지 못해도 워커를 멈추지 않는다. 일은 계속하고, healthcheck 가 unhealthy 로 알린다.
    """
    if not path:
        return
    try:
        Path(path).touch()
    except OSError as exc:
        logger.warning('심장박동 파일을 바꾸지 못했다: %s', type(exc).__name__)
