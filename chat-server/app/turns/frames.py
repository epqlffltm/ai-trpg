# chat-server/app/turns/frames.py

"""
말 한 번의 SSE 메시지를 만든다(모양은 app/turns/schemas.py). DB 도 HTTP 도 모른다.
"""

from dataclasses import asdict

from app.conversation.sse import Frame
from app.conversations.schemas import MessageOut
from app.turns.schemas import DeltaEvent, DoneEvent, FailedEvent, TurnEvent
from app.turns.values import SavedMessage, TurnStart


def message_out(message: SavedMessage) -> MessageOut:
    """저장한 말을 응답의 모양으로."""
    return MessageOut(**asdict(message))


def turn_frame(start: TurnStart) -> Frame:
    """맨 처음. 답할 사람의 말과 기록의 id. 이어서 출력이면 이어 쓰는 말의 id."""
    continues = start.continued.id if start.continued is not None else None
    action = message_out(start.action) if start.action is not None else None
    body = TurnEvent(
        generation_id=start.generation_id,
        user_message=message_out(start.user_message),
        continues=continues,
        action=action,
    )
    return Frame(event='turn', data=body.model_dump_json())


def delta_frame(text: str) -> Frame:
    """모델이 새로 쓴 글의 조각."""
    return Frame(event='delta', data=DeltaEvent(text=text).model_dump_json())


def done_frame(message: SavedMessage) -> Frame:
    """저장한 답. 마지막이다."""
    return Frame(event='done', data=DoneEvent(message=message_out(message)).model_dump_json())


def failed_frame(code: str) -> Frame:
    """글자 없이 실패했다. 마지막이다."""
    return Frame(event='failed', data=FailedEvent(code=code).model_dump_json())
