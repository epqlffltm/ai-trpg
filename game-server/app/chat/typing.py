# game-server/app/chat/typing.py

"""
"입력 중" 신호를 너무 자주 보내지 못하게 막는다.

화면은 사용자가 글자를 치는 동안 몇 초에 한 번 "입력 중"을 보낸다. 받는 쪽은 몇 초 동안 표시했다가 지운다.
잘못 만든 화면이나 장난이 1초에 수백 번을 보내면, 그만큼의 신호가 테이블의 모든 스트림을 깨운다.
같은 사람이 같은 테이블에 보내는 것을 일정 간격에 한 번으로 줄인다.

기록은 이 서버 프로세스의 메모리에 둔다. 서버가 여러 대면 서버마다 따로 센다. 한 대당 한 번이 되므로 충분하다.
틀려도 잃는 것이 없는 값이라 DB 나 Redis 에 두지 않는다.
"""

import time
import uuid

# 같은 사람이 같은 테이블에 "입력 중"을 다시 보낼 수 있는 간격(초).
# 화면은 3초쯤에 한 번 보내고, 받는 쪽은 5초쯤 표시하면 끊김 없이 이어진다
TYPING_INTERVAL_SECONDS = 2.0

# 기록이 이만큼 쌓이면 오래된 것을 치운다. 치우지 않으면 한 번 입력한 사람의 기록이 영원히 남는다
PRUNE_THRESHOLD = 1000


class TypingThrottle:
    """누가 어느 테이블에 마지막으로 "입력 중"을 보낸 때를 기억한다."""

    def __init__(self, interval: float = TYPING_INTERVAL_SECONDS) -> None:
        self._interval = interval
        self._last_sent: dict[tuple[uuid.UUID, uuid.UUID], float] = {}

    def allow(self, table_id: uuid.UUID, user_id: uuid.UUID, now: float | None = None) -> bool:
        """
        지금 보내도 되는가. 되면 보낸 것으로 적고 True, 간격이 지나지 않았으면 False.

        now 는 지금 시각이다. 테스트가 시간을 마음대로 흘리려고 준다. 주지 않으면 시계를 읽는다.
        monotonic: 거꾸로 가지 않는 시계다. 컴퓨터의 시각을 고쳐도 영향을 받지 않는다.
        """
        now = time.monotonic() if now is None else now
        key = (table_id, user_id)
        last = self._last_sent.get(key)
        if last is not None and now - last < self._interval:
            return False

        if len(self._last_sent) >= PRUNE_THRESHOLD:
            self._prune(now)
        self._last_sent[key] = now
        return True

    def _prune(self, now: float) -> None:
        """간격이 지난 기록을 치운다. 지난 기록은 있으나 없으나 결과가 같다."""
        self._last_sent = {key: sent for key, sent in self._last_sent.items() if now - sent < self._interval}
