# shared/conversation-core/src/conversation_core/relay.py

"""
모델이 흘려 주는 글을 SSE 응답으로 넘기는 통로. 모델을 부르는 작업과 응답을 보내는 쪽을 떼어 놓는다.

모델을 부르는 것은 응답과 따로 도는 작업이다. 사람이 앱을 닫거나 연결이 끊겨도 작업은 끝까지 돌아 답을 저장한다.
돌아온 사람은 저장된 말을 읽는다. 그래서 응답이 이 통로를 읽다가 끊겨도 작업은 모른 채 계속 넣는다.
  - push: 작업이 넣는다. 기다리지 않는다(ai_core 의 TextSink 는 빨리 돌아와야 한다).
  - frames: 응답이 꺼낸다. 오래 조용하면(heartbeat 초) 주석 한 줄을 끼워 연결이 살아 있음을 알린다.
    프록시와 앱이 죽은 연결로 보고 끊지 않게 한다. 마지막 것(끝을 알리는 것)을 꺼내면 멈춘다.
넣는 양은 묶지 않는다. 답 하나의 길이(출력 상한)만큼이라 작다.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from conversation_core.sse import Comment, Frame

# 조용할 때 주석을 끼우는 간격(초). README 의 "스트리밍(정한 것)"과 같다
HEARTBEAT_SECONDS = 15.0


@dataclass
class Relay:
    """작업에서 응답으로 가는 통로 하나. 말 한 번에 하나다."""

    heartbeat: float = HEARTBEAT_SECONDS
    queue: asyncio.Queue[tuple[Frame, bool]] = field(default_factory=asyncio.Queue)

    def push(self, frame: Frame) -> None:
        """보낼 것 하나를 넣는다."""
        self.queue.put_nowait((frame, False))

    def close(self, frame: Frame) -> None:
        """마지막 것을 넣는다. 응답은 이것을 보내고 끝난다."""
        self.queue.put_nowait((frame, True))

    async def next_item(self) -> tuple[Frame | Comment, bool]:
        """다음 것. heartbeat 초 동안 없으면 주석이다."""
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=self.heartbeat)
        except TimeoutError:
            return Comment('heartbeat'), False

    async def frames(self) -> AsyncIterator[Frame | Comment]:
        """보낼 것들. 마지막 것까지 내고 끝난다."""
        while True:
            item, last = await self.next_item()
            yield item
            if last:
                return
