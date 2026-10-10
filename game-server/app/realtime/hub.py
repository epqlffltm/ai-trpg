# game-server/app/realtime/hub.py

"""
방송실. 이 서버 프로세스 안에서 "어느 테이블을 누가 기다리고 있나"를 들고 있다가, 신호가 오면 깨운다.

DB 도 네트워크도 모른다. 신호를 어디서 받는지는 app/realtime/listener.py 의 일이다.
서버가 여러 대면 방송실도 서버마다 하나씩 있다. 신호는 모든 서버에 가므로, 각자 자기 방송실의 사람을 깨운다.
"""

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from app.realtime.signals import Notice


class Subscription:
    """
    기다리는 연결 하나의 자리. 스트림 하나가 하나를 가진다.

    깨우는 쪽은 wake 를, 기다리는 쪽은 wait 를 부른다.
    기다리지 않는 동안(DB 를 읽는 중)에 온 신호도 잃지 않는다. 다음 wait 가 바로 돌아온다.
    """

    def __init__(self) -> None:
        self._woken = asyncio.Event()
        self._pending: set[Notice] = set()

    def wake(self, signal: Notice) -> None:
        """
        신호가 왔다고 알린다. 같은 신호가 여러 번 와도 하나로 친다.

        들고 있는 신호는 순서가 없다(집합). 순서가 필요한 것(서술의 조각)은 번호를 싣고, 꺼낸 쪽이 줄 세운다.
        """
        self._pending.add(signal)
        self._woken.set()

    async def wait(self, timeout: float) -> set[Notice] | None:
        """
        신호가 올 때까지 기다린다. 그동안 온 신호들을 돌려준다. timeout 초 안에 오지 않으면 None.

        꺼내 간 신호는 비운다. 비우는 것과 꺼내는 것 사이에 await 가 없어서, 그 틈에 신호가 끼어들지 못한다.
        """
        try:
            await asyncio.wait_for(self._woken.wait(), timeout)
        except TimeoutError:
            return None
        self._woken.clear()
        received, self._pending = self._pending, set()
        return received


class Hub:
    """테이블마다 기다리는 자리들의 목록."""

    def __init__(self) -> None:
        self._subscriptions: dict[uuid.UUID, set[Subscription]] = {}

    @contextmanager
    def subscribe(self, table_id: uuid.UUID) -> Iterator[Subscription]:
        """
        이 테이블을 기다리는 자리를 하나 만든다. with 를 나가면 자리를 치운다.

        연결이 끊기든 예외가 나든 치워진다. 치우지 않으면 떠난 연결의 자리가 쌓인다.
        """
        subscription = Subscription()
        self._subscriptions.setdefault(table_id, set()).add(subscription)
        try:
            yield subscription
        finally:
            waiting = self._subscriptions[table_id]
            waiting.discard(subscription)
            if not waiting:
                del self._subscriptions[table_id]

    def wake(self, signal: Notice) -> None:
        """신호의 테이블을 기다리는 자리를 모두 깨운다. 기다리는 사람이 없으면 아무 일도 없다."""
        for subscription in self._subscriptions.get(signal.table_id, ()):
            subscription.wake(signal)

    def count(self, table_id: uuid.UUID) -> int:
        """이 테이블을 기다리는 자리가 몇인지 센다."""
        return len(self._subscriptions.get(table_id, ()))
