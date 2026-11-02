# story-server/app/turns/stops.py

"""
사람이 답을 멈추는 스위치. chat 서버의 것(chat-server/app/turns/service.py 의 StopSwitch)과 같다.

모델을 부르는 일(call)만 멈춘다. 저장과 확정은 멈추지 않는다.
서버가 꺼지며 멈추는 것(작업 전체의 취소)과 가른다. 사람이 멈추면 받은 만큼 저장하고 바로 맡긴다(app/turns/service.py).
스위치는 그 생성을 돌리는 서버의 메모리에 있다(app.state.stops). 다른 서버에 닿은 멈추기는 DB 의 NOTIFY 로 알려 오고
(server_core/stop_signals.py, #674) stop_here 가 이 서버의 스위치를 찾아 멈춘다.
"""

import asyncio
import uuid
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


# 이 서버에서 도는 생성의 스위치들(app.state.stops). 생성의 id → (주인, 스위치)
Stops = dict[uuid.UUID, tuple[uuid.UUID, StopSwitch]]


def stop_here(stops: Stops, generation_id: uuid.UUID) -> bool:
    """
    다른 서버가 알린 멈추기. 이 서버에서 도는 생성이면 멈추고 True.
    주인은 알린 서버가 DB 로 맞춰 봤다. 이 서버에 없거나 이미 다 받았으면 False 다.
    """
    found = stops.get(generation_id)
    return found is not None and found[1].request()
