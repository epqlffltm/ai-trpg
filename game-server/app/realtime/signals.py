# game-server/app/realtime/signals.py

"""
"이 테이블에 새 것이 생겼다"는 신호. 신호를 만들고 보내는 쪽이다.

신호에는 내용을 싣지 않는다. 어느 테이블의 무엇(이벤트, 채팅)이 늘었는지만 알린다.
받은 쪽은 DB 에서 "내가 보낸 마지막 번호 뒤"를 읽는다(app/realtime/service.py).
그래서 신호를 놓치거나 두 번 받아도 틀린 것을 보내지 않는다. 늦어질 뿐이다.

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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# NOTIFY 의 채널 이름 뒤에 붙는 말. 앞에는 스키마 이름이 붙는다(game_table_signals).
# 개발용과 테스트용이 같은 DB 를 쓰므로, 스키마마다 채널을 나눠 서로의 신호를 받지 않게 한다
CHANNEL_SUFFIX = '_table_signals'


class Kind(enum.StrEnum):
    """무엇이 늘었는가."""

    # 이벤트 기록(table_events)
    EVENTS = 'events'
    # 채팅(table_messages)
    MESSAGES = 'messages'


@dataclass(frozen=True)
class Signal:
    """신호 하나. 어느 테이블의 무엇이 늘었는가."""

    table_id: uuid.UUID
    kind: Kind


def channel_name(schema: str) -> str:
    """이 스키마의 신호가 오가는 채널의 이름."""
    return f'{schema}{CHANNEL_SUFFIX}'


def encode(signal: Signal) -> str:
    """신호를 채널에 실을 글자로 바꾼다."""
    return f'{signal.table_id}:{signal.kind}'


def decode(payload: str) -> Signal | None:
    """
    채널에서 받은 글자를 신호로 바꾼다. 알아볼 수 없으면 None.

    채널에는 이 서버의 다른 판(새 종류의 신호를 보내는 판)이 보낸 글자도 올 수 있다. 모르는 것은 버린다.
    """
    table_id, _, kind = payload.partition(':')
    try:
        return Signal(table_id=uuid.UUID(table_id), kind=Kind(kind))
    except ValueError:
        return None


async def publish(session: AsyncSession, signal: Signal) -> None:
    """
    신호를 보낸다. 이 세션의 트랜잭션이 커밋될 때 나간다. 되돌려지면 나가지 않는다.

    커밋하기 전에, 저장하는 것과 같은 세션으로 부른다.
    current_schema(): 이 연결이 쓰는 스키마의 이름이다. 받는 쪽의 채널 이름(channel_name)과 같아진다.
    한 트랜잭션에서 같은 신호를 여러 번 보내면 PostgreSQL 이 하나로 합쳐 보낸다.
    """
    query = text('SELECT pg_notify(current_schema() || :suffix, :payload)')
    await session.execute(query, {'suffix': CHANNEL_SUFFIX, 'payload': encode(signal)})
