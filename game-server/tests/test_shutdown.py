# game-server/tests/test_shutdown.py

"""
서버가 꺼질 때 열린 스트림을 먼저 닫는 것(app/realtime/shutdown.py)을 검증한다.

실제로 신호를 보내지 않는다. 걸린 처리기를 꺼내 직접 부른다. 테스트가 끝나면 원래 처리기로 되돌린다.
진짜 uvicorn 에 신호를 보내 바로 꺼지는 것은 손으로 확인했다(README 의 "서버를 끌 때").
"""

import signal
import threading
from collections.abc import Iterator
from types import FrameType

import pytest

from app.realtime.shutdown import chain, closing_on_exit


class Calls:
    """불린 차례를 적어 두는 곳."""

    def __init__(self) -> None:
        self.order: list[str] = []

    def on_exit(self) -> None:
        self.order.append('on_exit')

    def previous(self, signum: int, frame: FrameType | None) -> None:
        self.order.append(f'previous:{signum}')


@pytest.fixture
def sigterm() -> Iterator[None]:
    """테스트가 SIGTERM 의 처리기를 바꿔도 끝나면 원래대로 돌린다."""
    original = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, original)


def test_the_chain_closes_first_and_then_calls_the_original():
    calls = Calls()

    chain(calls.previous, calls.on_exit)(signal.SIGTERM, None)

    # 방송실을 먼저 닫아야 uvicorn 이 기다리기 시작할 때 스트림이 끝나 있다
    assert calls.order == ['on_exit', f'previous:{signal.SIGTERM}']


@pytest.mark.usefixtures('sigterm')
def test_the_handler_is_wrapped_while_inside_and_restored_after():
    calls = Calls()
    signal.signal(signal.SIGTERM, calls.previous)

    with closing_on_exit(calls.on_exit):
        handler = signal.getsignal(signal.SIGTERM)
        assert handler != calls.previous
        handler(signal.SIGTERM, None)

    assert calls.order == ['on_exit', f'previous:{signal.SIGTERM}']
    assert signal.getsignal(signal.SIGTERM) == calls.previous


@pytest.mark.usefixtures('sigterm')
@pytest.mark.parametrize('default', [signal.SIG_DFL, signal.SIG_IGN])
def test_a_signal_without_a_handler_function_is_left_alone(default: signal.Handlers):
    signal.signal(signal.SIGTERM, default)

    with closing_on_exit(Calls().on_exit):
        # 감싸면 기본 동작(프로세스 종료)을 대신 해 줘야 한다. 그것은 이 함수의 일이 아니다
        assert signal.getsignal(signal.SIGTERM) == default


@pytest.mark.usefixtures('sigterm')
def test_the_original_is_restored_even_when_the_body_fails():
    calls = Calls()
    signal.signal(signal.SIGTERM, calls.previous)

    with pytest.raises(RuntimeError), closing_on_exit(calls.on_exit):
        raise RuntimeError('뜨다가 실패했다')

    assert signal.getsignal(signal.SIGTERM) == calls.previous


@pytest.mark.usefixtures('sigterm')
def test_nothing_is_touched_off_the_main_thread():
    calls = Calls()
    signal.signal(signal.SIGTERM, calls.previous)
    seen = []

    def run() -> None:
        with closing_on_exit(calls.on_exit):
            seen.append(signal.getsignal(signal.SIGTERM))

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    # 신호 처리기는 메인 스레드에서만 걸 수 있다. 다른 스레드에서는 걸려고 하지 않는다
    assert seen == [calls.previous]
