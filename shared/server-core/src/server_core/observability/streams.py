# shared/server-core/src/server_core/observability/streams.py

"""
스트림(SSE)을 여는 주소들. 서버가 정해 요청의 span 과 메트릭을 거는 미들웨어에 넘긴다.

스트림은 응답이 몇 초에서 몇 시간 동안 끝나지 않는다. 다른 요청처럼 다루면 둘이 망가진다.
  - span: 그동안 도는 쿼리가 모두 한 span 아래에 쌓여 추적 하나가 끝없이 길어진다(request_spans.py)
  - 메트릭: 걸린 시간의 분포와 처리 중인 수를 덮는다(request_metrics.py). 스트림은 sse_* 가 따로 센다(metrics.py)

경로의 틀은 라우터가 처리를 끝내야 알 수 있다. 그래서 실제 경로를 정규식으로 본다.

    STREAMS = StreamRoutes.of(r'/api/v1/game/tables/[^/]+/stream')
    app.add_middleware(RequestSpanMiddleware, streams=STREAMS)

스트림이 없는 서버(알림, asset)는 넘기지 않는다(NO_STREAMS).
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StreamRoutes:
    """스트림을 여는 주소들. 실제 경로 전체가 맞아야 한다(fullmatch)."""

    patterns: tuple[re.Pattern[str], ...] = ()

    @classmethod
    def of(cls, *patterns: str) -> 'StreamRoutes':
        """정규식의 글자들로 만든다."""
        return cls(tuple(re.compile(pattern) for pattern in patterns))

    def matches(self, path: str) -> bool:
        """이 경로가 스트림을 여는가."""
        return any(pattern.fullmatch(path) is not None for pattern in self.patterns)


# 스트림이 없는 서버의 기본값
NO_STREAMS = StreamRoutes()
