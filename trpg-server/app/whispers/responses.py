# trpg-server/app/whispers/responses.py

"""
쪽지 한 장을 응답의 모양으로 바꾼다. 쪽지함의 주인은 싣지 않는다.

HTTP 를 모른다. API(app/whispers/router.py)와 실시간 스트림(app/realtime/service.py)이 함께 쓴다.
"""

from app.whispers.models import Whisper
from app.whispers.schemas import WhisperOut


def to_whisper(whisper: Whisper) -> WhisperOut:
    """
    쪽지 한 장을 응답으로 바꾼다. 칸을 하나씩 적어 옮긴다.

    쪽지함의 주인(owner_id)은 싣지 않는다. 읽는 사람 자신이다.
    """
    return WhisperOut(
        sequence=whisper.sequence,
        sender_id=whisper.sender_id,
        recipient_id=whisper.recipient_id,
        sender_character_name=whisper.sender_character_name,
        recipient_character_name=whisper.recipient_character_name,
        content=whisper.content,
        gm_visible=whisper.gm_visible,
        round=whisper.round_number,
        created_at=whisper.created_at,
    )
