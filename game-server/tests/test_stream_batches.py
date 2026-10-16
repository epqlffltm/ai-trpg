# game-server/tests/test_stream_batches.py

"""
스트림이 밀린 기록을 한 묶음씩 읽고 보내는 규칙(#270)을 검증한다.

셋을 본다.
  - 한 번 읽을 때 종류마다 한 묶음(READ_BATCH)까지만 읽는다. 꽉 찬 종류는 아직 남은 것으로 알린다.
  - 남은 것이 있으면 기다리지 않고 그 종류만 다시 읽는다. 묶음마다 앉아 있는지와 토큰 만료를 본다.
  - 테이블이 끝났어도 남은 기록을 다 보낸 뒤에 닫는다.

묶음 사이의 확인은 읽는 함수(read_new)를 정해 둔 결과를 내는 것으로 바꿔 본다. 진짜 기록으로는
"한 묶음을 보낸 뒤, 다음 묶음을 읽기 전"이라는 틈을 맞출 수 없다.
"""

import asyncio
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.realtime import service
from app.realtime.service import Batch, Closed, Cursor
from app.realtime.signals import Kind
from app.realtime.sse import Frame
from tests import test_stream as stream_tests
from tests.signing import make_viewer
from tests.test_stream import FRIEND, kinds, open_duo, say, table_url

pytestmark = pytest.mark.usefixtures('clean_tables')

# 스트림 테스트의 픽스처를 그대로 쓴다. 테이블을 여는 방장과 들어오는 사람
me = stream_tests.me
friend = stream_tests.friend

EVERYTHING = {Kind.EVENTS, Kind.MESSAGES, Kind.WHISPERS}


class ScriptedReads:
    """정해 둔 결과를 차례로 내는 읽기. 무엇을 읽으라고 했는지 적어 둔다."""

    def __init__(self, *batches: Batch, delay: float = 0.0) -> None:
        self.batches = list(batches)
        self.asked: list[set[Kind]] = []
        self.delay = delay

    async def __call__(self, session, user_id, table_id, cursor, kinds) -> Batch:
        self.asked.append(set(kinds))
        await asyncio.sleep(self.delay)
        return self.batches.pop(0)


def chat_frame(number: int) -> Frame:
    return Frame(event=service.MESSAGE_FRAME, data='{}', id=f'0-{number}-0')


async def test_one_read_takes_at_most_one_batch_of_each_kind(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    table = await open_duo(client, me, friend)
    for number in range(1, 6):
        await say(client, me, table, f'{number}번째 말')
    monkeypatch.setattr(service, 'READ_BATCH', 2)
    cursor = Cursor(events=2)

    batch = await service.read_new(session, FRIEND, uuid.UUID(table['id']), cursor, EVERYTHING)

    # 다섯 중 둘만 읽었다. 채팅은 아직 남았고, 이벤트와 쪽지는 남은 것이 없다
    assert kinds(batch.frames) == ['chat_message', 'chat_message']
    assert batch.pending == {Kind.MESSAGES}
    assert batch.closed is None
    assert (cursor.events, cursor.messages, cursor.whispers) == (2, 2, 0)


async def test_an_ended_table_closes_only_after_the_whole_backlog(
    client: AsyncClient, me: dict, friend: dict, connect, monkeypatch: pytest.MonkeyPatch
):
    table = await open_duo(client, me, friend)
    for number in range(1, 6):
        await say(client, me, table, f'{number}번째 말')
    await client.post(table_url(table, '/end'), headers=me)
    monkeypatch.setattr(service, 'READ_BATCH', 2)

    reader = connect(table, FRIEND, Cursor(events=2))

    frames = await reader.take(7)
    # 끝났다는 이벤트와 채팅 다섯을 세 번에 나눠 다 보내고 나서 닫는다
    assert kinds(frames[:6]) == ['table_ended'] + ['chat_message'] * 5
    assert [frame.id for frame in frames[1:6]] == ['3-1-0', '3-2-0', '3-3-0', '3-4-0', '3-5-0']
    assert json.loads(frames[6].data) == {'reason': 'table_ended'}
    assert await reader.next() is None


async def test_a_full_batch_is_followed_at_once_and_the_seat_is_checked_each_time(
    client: AsyncClient, me: dict, friend: dict, connect, monkeypatch: pytest.MonkeyPatch
):
    table = await open_duo(client, me, friend)
    # 채팅 한 묶음을 보낸 뒤, 다음 묶음을 읽을 때는 내보내져 있다
    reads = ScriptedReads(
        Batch(frames=[chat_frame(1)], pending=frozenset({Kind.MESSAGES})),
        Batch(frames=[], closed=Closed.NOT_SEATED),
    )
    monkeypatch.setattr(service, 'read_new', reads)

    reader = connect(table, FRIEND)

    # 스스로 깨어나는 것은 60 초 뒤다. 기다리지 않고 바로 다음 묶음을 읽었다
    assert await reader.next_comment() == 'connected'
    sent, closed = await reader.take(2)
    assert sent.id == '0-1-0'
    assert json.loads(closed.data) == {'reason': 'not_seated'}
    assert await reader.next() is None
    # 두 번째에는 남은 종류(채팅)만 읽었다
    assert reads.asked == [EVERYTHING, {Kind.MESSAGES}]


async def test_a_token_that_expires_during_the_backlog_closes_the_stream(
    client: AsyncClient, me: dict, friend: dict, connect, monkeypatch: pytest.MonkeyPatch
):
    table = await open_duo(client, me, friend)
    # 한 묶음을 읽는 사이에 토큰이 만료된다. 남은 것이 있어도 더 읽지 않는다
    reads = ScriptedReads(Batch(frames=[chat_frame(1)], pending=frozenset({Kind.MESSAGES})), delay=0.5)
    monkeypatch.setattr(service, 'read_new', reads)

    reader = connect(table, FRIEND, viewer=make_viewer(FRIEND, seconds=0.3))

    sent, closed = await reader.take(2)
    assert sent.id == '0-1-0'
    assert json.loads(closed.data) == {'reason': 'token_expired'}
    assert len(reads.asked) == 1
