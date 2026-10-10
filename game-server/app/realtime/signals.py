# game-server/app/realtime/signals.py

"""
"이 테이블에 새 것이 생겼다"는 신호. 신호를 만들고 보내는 쪽이다.

신호는 세 가지다.
  - 저장된 것이 늘었다(이벤트, 채팅). 내용을 싣지 않는다. 받은 쪽은 DB 에서 "내가 보낸 마지막 번호 뒤"를 읽는다
    (app/realtime/service.py). 그래서 신호를 놓치거나 두 번 받아도 틀린 것을 보내지 않는다. 늦어질 뿐이다.
  - 누가 입력 중이다. 저장하지 않으므로 신호가 내용의 전부다. 누구인지를 신호에 싣는다. 놓치면 그만이다.
  - 쓰이는 중인 서술의 조각(미리 보기). 이것도 저장하지 않는다. 글을 신호에 싣는다(NarrationPiece).
    놓치면 그만이다. 서술이 끝나면 전부가 이벤트(gm_narration)로 저장되어 간다.

지금은 PostgreSQL 의 NOTIFY 로 보낸다. NOTIFY 는 트랜잭션이 커밋될 때 나가고, 되돌려지면 나가지 않는다.
저장은 안 됐는데 신호만 가는 일이 없다.

다른 것(Redis Pub/Sub 등)으로 바꿀 때 고칠 곳은 둘이다.
  - 이 파일의 publish: 신호를 보낸다.
  - app/realtime/listener.py: 신호를 받아 방송실(hub)에 넘긴다.
publish 는 "커밋된 뒤에 나간다"를 지켜야 한다. Redis 는 트랜잭션을 모르므로, 커밋 뒤에 보내도록 따로 걸어야 한다.
"""

import enum
import uuid
from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# NOTIFY 의 채널 이름 뒤에 붙는 말. 앞에는 스키마 이름이 붙는다(game_table_signals).
# 개발용과 테스트용이 같은 DB 를 쓰므로, 스키마마다 채널을 나눠 서로의 신호를 받지 않게 한다
CHANNEL_SUFFIX = '_table_signals'

# 서술의 조각 하나에 싣는 글자 수의 상한. NOTIFY 에 싣는 글자는 8000 바이트보다 짧아야 한다.
# UTF-8 은 한 글자가 4 바이트까지라 1500 자는 6000 바이트까지다.
# 앞에 붙는 테이블과 번호들(80 바이트 안쪽)을 더해도 남는다
MAX_PIECE_CHARS = 1500


class Kind(enum.StrEnum):
    """무엇이 늘었는가."""

    # 이벤트 기록(table_events)
    EVENTS = 'events'
    # 채팅(table_messages)
    MESSAGES = 'messages'
    # 누가 채팅을 입력 중이다. 저장된 것이 아니다
    TYPING = 'typing'
    # 쓰이는 중인 서술의 조각이다. 저장된 것이 아니다
    NARRATION = 'narration'


# 저장된 것이 늘었다는 종류들. 이 신호를 받으면 DB 를 읽는다
STORED_KINDS = frozenset({Kind.EVENTS, Kind.MESSAGES})


@dataclass(frozen=True)
class Signal:
    """
    신호 하나. 어느 테이블의 무엇이 늘었는가.

    user_id 는 입력 중 신호에만 있다. 누가 입력 중인가다.
    """

    table_id: uuid.UUID
    kind: Kind
    user_id: uuid.UUID | None = None


@dataclass(frozen=True)
class NarrationPiece:
    """
    쓰이는 중인 서술의 조각 하나. 어느 테이블의 몇 라운드의, 몇 번째 시도의, 몇 번째 조각인가.

    시도(attempt)는 1 부터, 조각의 번호(seq)는 시도마다 0 부터 센다.
    받는 쪽은 시도가 바뀌면 보던 글을 지우고, 번호가 비면 그 시도를 끝까지 기다린다(이벤트로 전부가 온다).
    """

    kind: ClassVar[Kind] = Kind.NARRATION

    table_id: uuid.UUID
    round_number: int
    attempt: int
    seq: int
    text: str


# 채널로 오가는 것. 신호이거나 서술의 조각이다
Notice = Signal | NarrationPiece


def narration_pieces(
    table_id: uuid.UUID, round_number: int, attempt: int, first_seq: int, text: str
) -> list[NarrationPiece]:
    """글을 채널에 실을 수 있는 크기의 조각들로 나눈다. 번호는 first_seq 부터 붙는다. 빈 글이면 빈 목록이다."""
    parts = [text[start : start + MAX_PIECE_CHARS] for start in range(0, len(text), MAX_PIECE_CHARS)]
    return [
        NarrationPiece(table_id, round_number, attempt, first_seq + index, part) for index, part in enumerate(parts)
    ]


def channel_name(schema: str) -> str:
    """이 스키마의 신호가 오가는 채널의 이름."""
    return f'{schema}{CHANNEL_SUFFIX}'


def encode_signal(signal: Signal) -> str:
    """신호를 채널에 실을 글자로 바꾼다. '테이블:종류' 또는 '테이블:종류:사람'이다."""
    parts = [str(signal.table_id), signal.kind]
    if signal.user_id is not None:
        parts.append(str(signal.user_id))
    return ':'.join(parts)


def encode_piece(piece: NarrationPiece) -> str:
    """
    서술의 조각을 채널에 실을 글자로 바꾼다. '테이블:narration:라운드:시도:번호:글'이다.

    글을 맨 뒤에 둔다. 글에 ':' 가 있어도 앞의 넷만 나누면 된다.
    """
    numbers = f'{piece.round_number}:{piece.attempt}:{piece.seq}'
    return f'{piece.table_id}:{piece.kind}:{numbers}:{piece.text}'


def encode(notice: Notice) -> str:
    """채널로 보낼 것을 글자로 바꾼다."""
    if isinstance(notice, NarrationPiece):
        return encode_piece(notice)
    return encode_signal(notice)


def decode_signal(table_id: uuid.UUID, kind: Kind, user_id: str) -> Signal | None:
    """테이블과 종류 뒤의 글자로 신호를 만든다. 알아볼 수 없으면 None."""
    try:
        signal = Signal(table_id=table_id, kind=kind, user_id=uuid.UUID(user_id) if user_id else None)
    except ValueError:
        return None
    # 입력 중인데 누구인지 없는 신호는 쓸 수 없다
    if signal.kind == Kind.TYPING and signal.user_id is None:
        return None
    return signal


def decode_piece(table_id: uuid.UUID, rest: str) -> NarrationPiece | None:
    """테이블과 종류 뒤의 글자로 서술의 조각을 만든다. 번호 셋과 글이 없으면 None."""
    try:
        round_number, attempt, seq, piece_text = rest.split(':', 3)
        return NarrationPiece(table_id, int(round_number), int(attempt), int(seq), piece_text)
    except ValueError:
        return None


def decode(payload: str) -> Notice | None:
    """
    채널에서 받은 글자를 신호나 서술의 조각으로 바꾼다. 알아볼 수 없으면 None.

    채널에는 이 서버의 다른 판(새 종류의 신호를 보내는 판)이 보낸 글자도 올 수 있다. 모르는 것은 버린다.
    """
    table_id, _, rest = payload.partition(':')
    kind, _, tail = rest.partition(':')
    try:
        table, found = uuid.UUID(table_id), Kind(kind)
    except ValueError:
        return None
    if found == Kind.NARRATION:
        return decode_piece(table, tail)
    return decode_signal(table, found, tail)


async def publish(session: AsyncSession, notice: Notice) -> None:
    """
    신호나 서술의 조각을 보낸다. 이 세션의 트랜잭션이 커밋될 때 나간다. 되돌려지면 나가지 않는다.

    커밋하기 전에, 저장하는 것과 같은 세션으로 부른다.
    current_schema(): 이 연결이 쓰는 스키마의 이름이다. 받는 쪽의 채널 이름(channel_name)과 같아진다.
    한 트랜잭션에서 같은 신호를 여러 번 보내면 PostgreSQL 이 하나로 합쳐 보낸다. 조각은 번호가 달라서 합쳐지지 않는다.
    """
    query = text('SELECT pg_notify(current_schema() || :suffix, :payload)')
    await session.execute(query, {'suffix': CHANNEL_SUFFIX, 'payload': encode(notice)})
