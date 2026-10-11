# game-server/app/realtime/service.py

"""
테이블의 스트림. 앉은 사람 하나에게 새 이벤트와 새 채팅을 생기는 대로 흘려보낸다.

HTTP 를 모른다. 메시지(Frame)를 하나씩 내놓을 뿐이고, 글자로 바꿔 응답에 싣는 것은 라우터가 한다.

스트림은 한 가지 일을 되풀이한다.
  1. "내가 보낸 마지막 번호 뒤"를 DB 에서 읽어 보낸다.
  2. 신호가 오거나 일정 시간이 지날 때까지 기다린다.
처음 붙었을 때 밀린 것을 보내는 것과 실시간으로 새 것을 보내는 것이 같은 코드다.
신호는 "지금 읽어 보라"는 뜻일 뿐이다. 신호를 놓쳐도 다음 차례에 읽는다.
신호가 오면 그 종류만 읽는다. 대신 일정 시간마다 신호와 상관없이 이벤트와 채팅을 모두 읽는다(박자).
박자는 마지막 신호가 아니라 마지막 박자부터 센다. 다른 종류의 신호(입력 중, 서술의 조각)가 쉬지 않고 와도 밀리지 않는다.
조용할 때만 모두 읽으면, 채팅의 신호 하나를 놓친 채로 입력 중 신호가 이어질 때 그 채팅이 한없이 늦어진다.
저장하지 않는 것(입력 중, 쓰이는 중인 서술의 조각)은 신호가 내용의 전부다. 받은 대로 바로 보내고, 놓치면 그만이다.

DB 연결을 붙잡고 있지 않는다. 스트림은 몇 분씩 열려 있는데 풀의 연결은 몇 개뿐이다. 읽을 때만 잠깐 빌린다.
"""

import enum
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.tokens import AccessClaims
from app.chat import repository as chat_repository
from app.chat.router import to_message
from app.events import repository as event_repository
from app.events.router import to_event
from app.realtime.hub import Hub
from app.realtime.listener import SignalSource
from app.realtime.signals import STORED_KINDS, Kind, NarrationPiece, Notice, Signal
from app.realtime.sse import Comment, Frame
from app.tables import repository as table_repository
from app.tables import service as tables
from app.tables.models import TableStatus

# 박자. 이 시간(초)마다 주석을 보내고 DB 에서 이벤트와 채팅을 모두 읽는다. 신호가 오고 있어도 그렇게 한다.
# 주석을 보내는 이유: 써 봐야 연결이 죽었는지 안다. 그리고 중간의 프록시가 조용한 연결을 끊지 않게 한다.
# DB 를 읽는 이유: 신호가 끊겼거나 하나를 놓쳤어도 이 시간 안에는 새 것이 간다
HEARTBEAT_SECONDS = 15.0
# 신호를 듣지 못하는 동안(듣는 연결을 맺지 못함) 깨어나는 간격(초). 신호 대신 자주 읽어 늦음을 줄인다
DEAF_HEARTBEAT_SECONDS = 5.0

# 한 번에 읽는 개수. 밀린 것이 이보다 많으면 여러 번에 나눠 읽는다
READ_BATCH = 100

# 메시지의 종류(SSE 의 event 줄)
EVENT_FRAME = 'table_event'
MESSAGE_FRAME = 'chat_message'
TYPING_FRAME = 'typing'
NARRATION_FRAME = 'narration_preview'
CLOSED_FRAME = 'closed'


class Closed(enum.StrEnum):
    """서버가 스트림을 닫는 이유. 받는 쪽은 이것을 보고 다시 붙을지 정한다."""

    # 이 사람이 더는 앉아 있지 않다. 나갔거나 내보내졌다. 다시 붙어도 404 다
    NOT_SEATED = 'not_seated'
    # 테이블이 끝났다. 더 올 것이 없다
    TABLE_ENDED = 'table_ended'
    # 토큰이 만료됐다. 새 토큰으로 다시 붙으면 된다
    TOKEN_EXPIRED = 'token_expired'
    # 서버가 꺼진다(배포, 재시작). 잠깐 쉬었다가 다시 붙으면 된다
    SERVER_SHUTDOWN = 'server_shutdown'


@dataclass
class Cursor:
    """어디까지 보냈는가. 이벤트와 채팅의 번호를 따로 센다."""

    events: int = 0
    messages: int = 0

    def mark(self) -> str:
        """메시지의 id 에 적을 글자. 받는 쪽이 이 값을 그대로 돌려보내면 그 뒤부터 이어 받는다."""
        return f'{self.events}-{self.messages}'


def seconds_left(viewer: AccessClaims) -> float:
    """토큰이 만료될 때까지 남은 시간(초). 이미 만료됐으면 0 이하다."""
    return (viewer.expires_at - datetime.now(UTC)).total_seconds()


def wake_interval(heartbeat: float, deaf_heartbeat: float, listening: bool) -> float:
    """신호가 없을 때 몇 초 뒤에 깨어날까. 신호를 듣지 못하는 동안에는 더 자주 깨어난다."""
    return heartbeat if listening else min(heartbeat, deaf_heartbeat)


def wait_seconds(beat_at: float, now: float, viewer: AccessClaims) -> float:
    """
    신호를 얼마나(초) 기다릴까. 다음 박자(beat_at)와 토큰이 만료되는 때 중 먼저 오는 쪽까지다.

    beat_at 과 now 는 같은 시계의 시각이다. 이미 지났으면 0 이다. 기다리지 않고 바로 돌아온다.
    """
    return max(min(beat_at - now, seconds_left(viewer)), 0)


def closed_frame(reason: Closed) -> Frame:
    """스트림을 닫는다는 메시지. id 를 붙이지 않는다. 저장된 것이 아니다."""
    return Frame(event=CLOSED_FRAME, data=json.dumps({'reason': reason}))


def typing_frames(received: set[Notice], viewer_id: uuid.UUID) -> list[Frame]:
    """
    받은 신호 중 "입력 중"을 메시지로 바꾼다. id 를 붙이지 않는다. 저장된 것이 아니다.

    자기 자신의 것은 뺀다. 자기가 입력 중이라는 것은 본인이 이미 안다.
    """
    typists = {
        signal.user_id
        for signal in received
        if isinstance(signal, Signal) and signal.kind == Kind.TYPING and signal.user_id != viewer_id
    }
    # 순서를 정해 둔다. 집합은 순서가 없어서 그대로 내보내면 실행할 때마다 달라진다
    return [Frame(event=TYPING_FRAME, data=json.dumps({'user_id': str(user_id)})) for user_id in sorted(typists)]


def narration_frames(received: set[Notice]) -> list[Frame]:
    """
    받은 신호 중 서술의 조각을 메시지로 바꾼다. id 를 붙이지 않는다. 저장된 것이 아니다.

    받은 신호는 순서가 없다(집합). 라운드, 시도, 번호의 순서로 줄 세운다.
    """
    pieces = sorted(
        (signal for signal in received if isinstance(signal, NarrationPiece)),
        key=lambda piece: (piece.round_number, piece.attempt, piece.seq),
    )
    return [
        Frame(
            event=NARRATION_FRAME,
            data=json.dumps(
                {'round': piece.round_number, 'attempt': piece.attempt, 'seq': piece.seq, 'text': piece.text},
                ensure_ascii=False,
            ),
        )
        for piece in pieces
    ]


def live_frames(received: set[Notice], viewer_id: uuid.UUID) -> list[Frame]:
    """받은 신호 중 저장하지 않는 것들을 메시지로 바꾼다. 입력 중을 먼저, 서술의 조각을 나중에."""
    return typing_frames(received, viewer_id) + narration_frames(received)


async def read_events(session: AsyncSession, table_id: uuid.UUID, cursor: Cursor) -> list[Frame]:
    """보낸 번호 뒤의 이벤트를 모두 읽어 메시지로 바꾼다. 읽은 만큼 cursor 를 옮긴다."""
    frames = []
    while True:
        events = await event_repository.list_after(session, table_id, cursor.events, READ_BATCH)
        for event in events:
            cursor.events = event.sequence
            frames.append(Frame(event=EVENT_FRAME, data=to_event(event).model_dump_json(), id=cursor.mark()))
        if len(events) < READ_BATCH:
            return frames


async def read_messages(session: AsyncSession, table_id: uuid.UUID, cursor: Cursor) -> list[Frame]:
    """보낸 번호 뒤의 채팅을 모두 읽어 메시지로 바꾼다. 읽은 만큼 cursor 를 옮긴다."""
    frames = []
    while True:
        messages = await chat_repository.list_after(session, table_id, cursor.messages, READ_BATCH)
        for message in messages:
            cursor.messages = message.sequence
            frames.append(Frame(event=MESSAGE_FRAME, data=to_message(message).model_dump_json(), id=cursor.mark()))
        if len(messages) < READ_BATCH:
            return frames


async def read_new(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, cursor: Cursor, kinds: set[Kind]
) -> tuple[list[Frame], Closed | None]:
    """
    새로 생긴 것을 읽는다. 보낼 메시지들과, 스트림을 닫아야 하면 그 이유를 돌려준다.

    읽을 때마다 아직 앉아 있는지부터 본다. 내보내진 사람에게 그 뒤의 채팅이 가면 안 된다.
    테이블이 끝났으면 남은 것을 다 보낸 뒤에 닫는다.
    kinds 가 비어 있으면(입력 중 신호만 왔을 때) 앉아 있는지만 본다.
    """
    table = await table_repository.find_table(session, table_id)
    if table is None or tables.find_member(table, user_id) is None:
        return [], Closed.NOT_SEATED

    frames = []
    if Kind.EVENTS in kinds:
        frames += await read_events(session, table_id, cursor)
    if Kind.MESSAGES in kinds:
        frames += await read_messages(session, table_id, cursor)
    return frames, Closed.TABLE_ENDED if table.status == TableStatus.ENDED else None


async def stream(
    session_factory: async_sessionmaker[AsyncSession],
    hub: Hub,
    source: SignalSource,
    viewer: AccessClaims,
    table_id: uuid.UUID,
    cursor: Cursor,
    heartbeat: float = HEARTBEAT_SECONDS,
    deaf_heartbeat: float = DEAF_HEARTBEAT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> AsyncIterator[Frame | Comment]:
    """
    테이블의 새 이벤트와 새 채팅을 생기는 대로 내놓는다. 닫아야 할 때까지 끝나지 않는다.

    cursor 는 어디까지 받았는지다. 그 뒤의 것부터 보낸다.
    받는 쪽이 끊으면 이 함수는 기다리던 자리에서 취소되고, with 를 나가며 방송실의 자리를 치운다.

    자리를 먼저 잡고 그다음에 읽는다. 반대로 하면 읽은 뒤 자리를 잡기 전에 생긴 것의 신호를 놓친다.
    신호를 듣지 못해도(listening 이 False) 끝내지 않는다. 더 자주 깨어나 DB 를 직접 읽는다.
    신호가 오면 그 종류만 읽고, 박자마다 모두 읽는다. 박자는 신호가 이어져도 제때 온다.
    clock 은 박자를 재는 시계다. 테스트가 시간을 마음대로 흘리려고 꽂는다.
    방송실이 닫히면(서버가 꺼짐) 닫는다는 메시지를 보내고 끝낸다. 스트림이 끝나야 서버가 꺼진다.
    """
    with hub.subscribe(table_id) as subscription:
        listening = await source.ensure_listening()
        yield Comment('connected')

        kinds: set[Kind] = set(STORED_KINDS)
        live: list[Frame] = []
        # 다음 박자의 시각. 처음 읽기가 모두 읽으므로 거기서부터 센다
        beat_at = clock() + wake_interval(heartbeat, deaf_heartbeat, listening)
        while True:
            async with session_factory() as session:
                frames, closed = await read_new(session, viewer.user_id, table_id, cursor, kinds)
            # 앉아 있지 않게 된 사람에게는 저장하지 않는 것(입력 중, 서술의 조각)도 보내지 않는다.
            # 그것들을 먼저, 저장된 것을 나중에 보낸다. 받는 쪽은 그 사람의 채팅이 오면 입력 중 표시를 지우고,
            # 서술의 이벤트(gm_narration)가 오면 미리 보기를 지운다
            if closed is not Closed.NOT_SEATED:
                frames = live + frames
            for frame in frames:
                yield frame

            if closed is None and seconds_left(viewer) <= 0:
                closed = Closed.TOKEN_EXPIRED
            if closed is not None:
                yield closed_frame(closed)
                return

            # 다음 박자까지 기다린다. 토큰이 만료되는 때에는 신호가 없어도 깨어나야 한다
            received = await subscription.wait(wait_seconds(beat_at, clock(), viewer))
            if subscription.is_closed():
                yield closed_frame(Closed.SERVER_SHUTDOWN)
                return
            kinds = {signal.kind for signal in received or ()} & STORED_KINDS
            live = live_frames(received or set(), viewer.user_id)
            # 신호 없이 깨어났거나(박자가 됐다, 토큰이 만료된다), 신호가 이어져 조용할 틈이 없었어도 박자가 지났다
            if received is None or clock() >= beat_at:
                yield Comment('ping')
                # 듣는 연결이 끊겼으면 다시 맺는다
                listening = await source.ensure_listening()
                kinds = set(STORED_KINDS)
                beat_at = clock() + wake_interval(heartbeat, deaf_heartbeat, listening)
