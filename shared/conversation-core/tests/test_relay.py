# shared/conversation-core/tests/test_relay.py

"""
모델을 부르는 작업과 응답을 잇는 통로(conversation_core/relay.py).

보는 것.
  - 넣은 차례대로 꺼내고, 마지막 것(close)을 꺼내면 멈춘다
  - 오래 조용하면 주석(하트비트)을 끼운다. 그래도 멈추지 않고 다음 것을 기다린다
"""

from conversation_core.relay import Relay
from conversation_core.sse import Comment, Frame

FIRST = Frame(event='delta', data='{"text":"a"}')
LAST = Frame(event='done', data='{}')


async def collected(relay: Relay) -> list[Frame | Comment]:
    return [item async for item in relay.frames()]


async def test_frames_come_out_in_order_and_stop_after_the_last():
    relay = Relay()
    relay.push(FIRST)
    relay.close(LAST)

    assert await collected(relay) == [FIRST, LAST]


async def test_a_quiet_relay_sends_a_heartbeat_and_keeps_waiting():
    relay = Relay(heartbeat=0.01)
    frames = relay.frames()

    assert await anext(frames) == Comment('heartbeat')

    relay.close(LAST)
    assert [item async for item in frames if item != Comment('heartbeat')] == [LAST]
