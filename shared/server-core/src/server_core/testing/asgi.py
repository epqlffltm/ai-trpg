# shared/server-core/src/server_core/testing/asgi.py

"""
서버들과 공용 코드의 테스트가 미들웨어에 넘기는 ASGI 의 받기와 보내기. 부르면 실패한다.

미들웨어가 건드리지 않고 넘기기만 하는 요청(lifespan, 스트림의 앞부분)을 볼 때 쓴다.
None 을 넘기던 자리다. 실제로 부르면 테스트가 무엇을 잘못 가정했는지 바로 드러난다.
"""

from starlette.types import Message


async def no_receive() -> Message:
    """받기. 불리면 안 된다."""
    raise AssertionError('받기를 불렀다')


async def no_send(message: Message) -> None:
    """보내기. 불리면 안 된다."""
    raise AssertionError(f'보내기를 불렀다: {message.get("type")}')
