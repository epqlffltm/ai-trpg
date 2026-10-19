# trpg-server/app/chat/responses.py

"""
채팅 한 줄을 응답의 모양으로 바꾼다.

HTTP 를 모른다. API(app/chat/router.py)와 실시간 스트림(app/realtime/service.py)이 함께 쓴다.
"""

from app.chat.models import ChatMessage
from app.chat.schemas import MessageOut


def to_message(message: ChatMessage) -> MessageOut:
    """채팅 한 줄을 응답으로 바꾼다. 칸을 하나씩 적어 옮긴다."""
    return MessageOut(
        sequence=message.sequence,
        user_id=message.user_id,
        character_name=message.character_name,
        content=message.content,
        created_at=message.created_at,
    )
