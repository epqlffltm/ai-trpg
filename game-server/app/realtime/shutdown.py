# game-server/app/realtime/shutdown.py

"""
서버가 꺼질 때 열린 스트림을 먼저 닫는다.

uvicorn 이 꺼지는 순서.
  1. 종료 신호(Ctrl+C, SIGTERM)를 받는다.
  2. 새 연결을 받지 않는다.
  3. 열린 연결이 모두 끝나기를 기다린다.
  4. 앱의 꺼질 때 할 일(lifespan 의 yield 뒤)을 부른다.
스트림은 스스로 끝나지 않는다. 그래서 3 에서 하염없이 기다리고, 4 에 둔 코드는 불리지도 않는다.
스트림을 닫는 일은 3 보다 앞, 종료 신호를 받는 그때 해야 한다.

방법: 서버가 뜰 때, uvicorn 이 걸어 둔 종료 신호의 처리기를 우리 처리기로 감싼다.
신호가 오면 방송실을 닫는 일을 이벤트 루프에 맡기고, 원래 처리기(uvicorn 의 것)를 그대로 부른다.
표준 라이브러리 signal 만 쓴다. uvicorn 의 코드를 고치지 않는다. 서버가 꺼질 때 원래 처리기를 되돌려 놓는다.

신호 처리기 안에서는 방송실을 직접 닫지 않는다. 처리기는 아무 바이트코드 사이에 끼어들 수 있다.
루프에 맡기면(call_soon_threadsafe) 루프가 안전한 때에 닫는다.

이것이 듣지 못하는 경우(다른 서버 프로그램, 걸려 있던 처리기가 없음)를 위해,
실행 명령에 --timeout-graceful-shutdown 을 함께 준다. 그 시간이 지나면 uvicorn 이 남은 스트림을 끊는다.
"""

import signal
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import FrameType

# 처리기를 감쌀 종료 신호들. uvicorn 이 듣는 것과 같다(윈도우에서는 Ctrl+Break 도)
EXIT_SIGNALS = (signal.SIGINT, signal.SIGTERM)
if sys.platform == 'win32':
    EXIT_SIGNALS += (signal.SIGBREAK,)

Handler = Callable[[int, FrameType | None], None]


def chain(previous: Handler, on_exit: Callable[[], None]) -> Handler:
    """on_exit 을 먼저 부르고 원래 처리기를 부르는 처리기를 만든다."""

    def handle(signum: int, frame: FrameType | None) -> None:
        on_exit()
        previous(signum, frame)

    return handle


@contextmanager
def closing_on_exit(on_exit: Callable[[], None]) -> Iterator[None]:
    """
    with 안에서는 종료 신호가 오면 on_exit 을 먼저 부른다. with 를 나가면 원래 처리기로 되돌린다.

    걸려 있던 처리기가 함수인 신호만 감싼다. 기본 동작(SIG_DFL)이나 무시(SIG_IGN)는 그대로 둔다.
    감싸면 기본 동작을 대신 해 줘야 하는데, 그것은 이 함수의 일이 아니다.
    신호 처리기는 메인 스레드에서만 걸 수 있다. 다른 스레드에서 부르면 아무것도 하지 않는다.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {signum: signal.getsignal(signum) for signum in EXIT_SIGNALS}
    wrapped = {signum: handler for signum, handler in previous.items() if callable(handler)}
    for signum, handler in wrapped.items():
        signal.signal(signum, chain(handler, on_exit))
    try:
        yield
    finally:
        for signum, handler in wrapped.items():
            signal.signal(signum, handler)
