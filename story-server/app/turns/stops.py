# story-server/app/turns/stops.py

"""
사람이 답을 멈추는 스위치. chat 서버의 것(chat-server/app/turns/service.py 의 StopSwitch)과 같다.

모델을 부르는 일(call)만 멈춘다. 저장과 확정은 멈추지 않는다.
서버가 꺼지며 멈추는 것(작업 전체의 취소)과 가른다. 사람이 멈추면 받은 만큼 저장하고 바로 맡긴다(app/turns/service.py).
스위치는 그 생성을 돌리는 서버의 메모리에 있다(app.state.stops). 다른 서버에서 도는 생성은 멈추지 못한다.
"""

import asyncio
from dataclasses import dataclass


@dataclass
class StopSwitch:
    """멈추라는 말을 받았는가(requested)와, 모델을 부르는 일(call)."""

    requested: bool = False
    call: asyncio.Task | None = None

    def request(self) -> bool:
        """
        멈춘다. 모델을 부르기 전이거나 부르는 중이었으면 True, 이미 다 받았으면 False.
        부르기 전에 멈추면 부르지 않는다(app/turns/service.py 의 stoppable_call).
        """
        if self.call is not None and self.call.done():
            return False
        self.requested = True
        if self.call is not None:
            self.call.cancel()
        return True
