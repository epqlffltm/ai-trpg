# game-server/app/chat/service.py

"""
채팅을 쓰고 읽는다.

HTTP 를 모른다. SQL 을 모른다. 어디까지를 한 묶음으로 저장할지(커밋)는 여기서 정한다.

테이블의 규칙을 그대로 따른다(app/tables/service.py).
  - 채팅은 테이블에 앉은 사람만 쓰고 읽는다.
  - 쓰는 일은 테이블의 행을 잠그고 한다. 번호를 테이블이 세기 때문이다.

이벤트로 적지 않는다. 채팅은 게임에서 일어난 사실이 아니다.
저장하면서 "새 채팅이 생겼다"는 신호를 보낸다(app/realtime/signals.py). 스트림을 열어 둔 사람들이 받는다.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import repository
from app.chat.models import ChatMessage
from app.chat.schemas import MessageCreate
from app.chat.typing import TypingThrottle
from app.realtime import signals
from app.realtime.signals import Kind, Signal
from app.tables import service as tables
from app.tables.models import GameTable, TableMember


def next_sequence(table: GameTable) -> int:
    """
    이 테이블의 다음 채팅 번호를 받는다. 테이블이 세고 있는 번호를 하나 올린다.

    테이블을 잠근 뒤에 부른다. 잠그지 않으면 두 요청이 같은 번호를 받는다(그때는 DB 의 유일 조건이 막는다).
    """
    table.last_message_sequence += 1
    return table.last_message_sequence


def build_message(table: GameTable, member: TableMember, content: str) -> ChatMessage:
    """
    채팅 한 줄을 만든다. 아직 저장하지 않는다.

    쓸 때의 캐릭터 이름을 함께 적어 둔다. 캐릭터를 정하기 전이면 비어 있다.
    """
    return ChatMessage(
        table_id=table.id,
        sequence=next_sequence(table),
        user_id=member.user_id,
        character_name=member.character_name,
        content=content,
    )


async def post_message(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, data: MessageCreate
) -> ChatMessage:
    """
    채팅을 쓴다. 쓴 글을 돌려준다.

    앉지 않았으면 TableNotFoundError, 끝난 테이블이면 TableConflictError.
    모집 중에도 쓸 수 있다. 캐릭터를 맞추는 이야기를 그때 한다.

    테이블을 잠그고 한다. 두 사람이 동시에 써도 번호가 겹치지 않는다.
    """
    table, member = await tables.lock_seated(session, user_id, table_id)
    tables.require_not_ended(table)

    message = build_message(table, member, data.content)
    repository.add_message(session, message)
    # 신호는 커밋될 때 함께 나간다
    await signals.publish(session, Signal(table_id=table.id, kind=Kind.MESSAGES))
    await session.commit()
    # DB 가 정한 값(쓴 시각)을 읽어 온다
    await session.refresh(message)
    return message


async def announce_typing(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, throttle: TypingThrottle
) -> None:
    """
    "입력 중"이라고 테이블의 다른 사람들에게 알린다. 아무것도 저장하지 않는다.

    앉지 않았으면 TableNotFoundError, 끝난 테이블이면 TableConflictError. 채팅을 쓸 수 있는 때에만 알릴 수 있다.
    너무 자주 보내면 조용히 버린다. 보낸 쪽에는 똑같이 성공으로 답한다. 화면이 따로 처리할 것이 없다.

    테이블을 잠그지 않는다. 번호를 받지 않고, 바꾸는 것이 없다.
    신호는 커밋될 때 나가므로 커밋한다. 저장할 것은 없다.
    """
    table = await tables.get_table(session, user_id, table_id)
    tables.require_not_ended(table)
    if not throttle.allow(table_id, user_id):
        return

    await signals.publish(session, Signal(table_id=table_id, kind=Kind.TYPING, user_id=user_id))
    await session.commit()


async def list_messages(
    session: AsyncSession, user_id: uuid.UUID, table_id: uuid.UUID, after: int, limit: int
) -> tuple[GameTable, list[ChatMessage]]:
    """
    자기가 앉아 있는 테이블의 채팅 중 after 번 뒤의 것을 순서대로 돌려준다. 테이블도 함께 돌려준다.

    앉지 않았으면 TableNotFoundError. 끝난 테이블의 채팅도 읽을 수 있다.
    """
    table = await tables.get_table(session, user_id, table_id)
    messages = await repository.list_after(session, table_id, after, limit)
    return table, messages
