# game-server/tests/test_preview.py

"""
서술의 미리 보기(app/rounds/preview.py)를 검증한다. DB 를 쓰지 않는다.

보내는 함수 대신 받은 조각을 목록에 쌓는 것을 꽂는다.
진짜 신호(NOTIFY)로 스트림까지 가는 것은 tests/test_stream.py 가 본다.

보는 것은 셋이다.
  - 조각에 시도의 번호와 시도 안의 번호가 붙는다. 시도가 바뀌면 번호가 처음부터다.
  - 모아 두었다가 간격마다 보내고, 닫을 때 남은 것을 보낸다.
  - 보내기가 실패해도 서술은 계속한다.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy.exc import OperationalError

from app.realtime.signals import NarrationPiece
from app.rounds.preview import SignalPreview, open_preview

TABLE = uuid.UUID('aaaaaaaa-2222-4333-8444-555555555555')
ROUND = 3
# 테스트가 기다리는 간격(초). 짧게 잡는다
INTERVAL = 0.02
# 간격 몇 번이 지나도록 기다리는 시간(초)
A_WHILE = 0.15


@dataclass
class Outbox:
    """보낸 조각을 쌓아 두는 곳. 보내는 함수(Send) 노릇을 한다. error 를 두면 보내는 대신 그것을 낸다."""

    sent: list[NarrationPiece] = field(default_factory=list)
    error: Exception | None = None

    async def __call__(self, pieces: list[NarrationPiece]) -> None:
        if self.error is not None:
            raise self.error
        self.sent.extend(pieces)

    def numbered(self) -> list[tuple[int, int, str]]:
        """보낸 조각들의 (시도, 번호, 글)."""
        return [(piece.attempt, piece.seq, piece.text) for piece in self.sent]


def make_preview(outbox: Outbox) -> SignalPreview:
    return SignalPreview(outbox, TABLE, ROUND)


# --- 번호 ---


async def test_what_was_gathered_goes_out_as_one_piece():
    outbox = Outbox()
    preview = make_preview(outbox)
    preview.begin()
    preview.text('엔진 소리가 ')
    preview.text('골목을 메운다.')

    await preview.flush()

    (piece,) = outbox.sent
    assert (piece.table_id, piece.round_number) == (TABLE, ROUND)
    assert outbox.numbered() == [(1, 0, '엔진 소리가 골목을 메운다.')]


async def test_pieces_are_numbered_within_an_attempt():
    outbox = Outbox()
    preview = make_preview(outbox)
    preview.begin()
    preview.text('엔진 소리가 ')
    await preview.flush()
    preview.text('골목을 메운다.')
    await preview.flush()

    assert outbox.numbered() == [(1, 0, '엔진 소리가 '), (1, 1, '골목을 메운다.')]


async def test_a_new_attempt_starts_numbering_again_and_drops_what_was_not_sent():
    outbox = Outbox()
    preview = make_preview(outbox)
    preview.begin()
    preview.text('엔진 소리가 ')
    await preview.flush()
    preview.text('보내기 전에 실패한 글')

    preview.begin()
    preview.text('다시 쓴 글')
    await preview.flush()

    # 실패한 시도의 남은 글은 보내 봐야 받는 쪽이 지울 글이다
    assert outbox.numbered() == [(1, 0, '엔진 소리가 '), (2, 0, '다시 쓴 글')]


async def test_nothing_gathered_sends_nothing():
    outbox = Outbox()
    preview = make_preview(outbox)
    preview.begin()

    await preview.flush()

    assert outbox.sent == []


# --- 실패 ---


@pytest.mark.parametrize('error', [OSError('연결 거부'), OperationalError('SELECT', {}, Exception('끊김'))])
async def test_a_failed_send_does_not_stop_the_narration(error: Exception, caplog: pytest.LogCaptureFixture):
    outbox = Outbox(error=error)
    preview = make_preview(outbox)
    preview.begin()
    preview.text('엔진 소리가 ')

    with caplog.at_level(logging.WARNING):
        await preview.flush()

    assert '미리 보기' in caplog.text
    # 잃은 조각의 번호는 건너뛴다. 받는 쪽은 번호가 빈 것을 보고 이벤트를 기다린다
    outbox.error = None
    preview.text('골목을 메운다.')
    await preview.flush()
    assert outbox.numbered() == [(1, 1, '골목을 메운다.')]


# --- 열고 닫기 ---


async def test_pieces_go_out_while_the_narration_is_still_being_written():
    outbox = Outbox()

    async with open_preview(outbox, TABLE, ROUND, interval=INTERVAL) as preview:
        preview.begin()
        preview.text('엔진 소리가 ')
        await asyncio.sleep(A_WHILE)

        # 서술이 끝나기 전에 나갔다
        assert outbox.numbered() == [(1, 0, '엔진 소리가 ')]


async def test_closing_sends_what_is_left():
    outbox = Outbox()

    async with open_preview(outbox, TABLE, ROUND, interval=60) as preview:
        preview.begin()
        preview.text('엔진 소리가 골목을 메운다.')

    # 간격이 60 초라도 닫을 때 보낸다. 그 뒤에 적는 이벤트가 마지막 조각보다 늦게 간다
    assert outbox.numbered() == [(1, 0, '엔진 소리가 골목을 메운다.')]


async def test_closing_after_a_failure_still_sends_what_is_left_and_lets_the_failure_through():
    outbox = Outbox()

    with pytest.raises(RuntimeError):
        async with open_preview(outbox, TABLE, ROUND, interval=60) as preview:
            preview.begin()
            preview.text('엔진 소리가')
            raise RuntimeError('서술자가 실패했다')

    assert outbox.numbered() == [(1, 0, '엔진 소리가')]


@dataclass
class SlowOutbox(Outbox):
    """보내는 데 시간이 걸리는 곳. 보내기 시작하면 started 가 켜지고, gate 가 열릴 때까지 끝나지 않는다."""

    started: asyncio.Event = field(default_factory=asyncio.Event)
    gate: asyncio.Event = field(default_factory=asyncio.Event)

    async def __call__(self, pieces: list[NarrationPiece]) -> None:
        self.started.set()
        await self.gate.wait()
        self.sent.extend(pieces)


async def test_what_was_written_while_sending_is_not_lost_on_closing():
    outbox = SlowOutbox()

    async with open_preview(outbox, TABLE, ROUND, interval=INTERVAL) as preview:
        preview.begin()
        preview.text('엔진 소리가 ')
        await asyncio.wait_for(outbox.started.wait(), 1)
        # 앞의 조각을 보내는 동안 마지막 글이 오고 서술이 끝난다. 보내기는 서술이 끝난 뒤에야 끝난다
        preview.text('골목을 메운다.')
        asyncio.get_running_loop().call_later(A_WHILE, outbox.gate.set)

    assert outbox.numbered() == [(1, 0, '엔진 소리가 '), (1, 1, '골목을 메운다.')]


async def test_a_send_that_never_returns_does_not_hold_the_closing(caplog: pytest.LogCaptureFixture):
    # gate 를 열지 않는다. 보내기가 끝나지 않는다(응답 없는 DB)
    outbox = SlowOutbox()

    with caplog.at_level(logging.WARNING):
        async with asyncio.timeout(1):
            async with open_preview(outbox, TABLE, ROUND, interval=60, close_timeout=0.05) as preview:
                preview.begin()
                preview.text('엔진 소리가')

    # 잠깐만 기다리고 그만둔다. 미리 보기가 서술의 마무리를 붙잡지 않는다. 그 조각은 잃는다
    assert outbox.started.is_set()
    assert outbox.sent == []
    assert '닫지 못했다' in caplog.text
