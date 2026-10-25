# story-server/app/turns/frames.py

"""
말 한 번의 SSE 메시지를 만든다(모양은 app/turns/schemas.py). DB 도 HTTP 도 모른다.
"""

from dataclasses import asdict

from conversation_core.sse import Frame

from app.conversations.schemas import MessageOut
from app.turns.schemas import DeltaEvent, DoneEvent, FailedEvent, SegmentEvent, TurnEvent
from app.turns.values import SavedMessage, TurnStart


def message_out(message: SavedMessage) -> MessageOut:
    """저장한 말을 응답의 모양으로."""
    values = asdict(message)
    return MessageOut(**{**values, 'segments': list(message.segments), 'cast': list(message.cast)})


def turn_frame(start: TurnStart) -> Frame:
    """맨 처음. 답할 사람의 말, 기록의 id, 장면의 인물."""
    body = TurnEvent(
        generation_id=start.generation_id, user_message=message_out(start.user_message), cast=list(start.cast)
    )
    return Frame(event='turn', data=body.model_dump_json())


def segment_frame(speaker: str | None) -> Frame:
    """새 말 조각이 시작됐다."""
    return Frame(event='segment', data=SegmentEvent(speaker=speaker).model_dump_json())


def delta_frame(text: str) -> Frame:
    """지금 조각에 붙는 글."""
    return Frame(event='delta', data=DeltaEvent(text=text).model_dump_json())


def done_frame(message: SavedMessage) -> Frame:
    """저장한 답. 마지막이다."""
    return Frame(event='done', data=DoneEvent(message=message_out(message)).model_dump_json())


def failed_frame(code: str) -> Frame:
    """답 없이 끝났다. 마지막이다."""
    return Frame(event='failed', data=FailedEvent(code=code).model_dump_json())
