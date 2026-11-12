# story-server/app/transcripts/html.py

"""
기록을 HTML 파일 하나로 쓴다. DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

조각을 쓰는 것과 파일의 머리, 끝은 게임, chat 과 함께 쓰는 공용 코드에 있다
(conversation_core/transcripts/html.py, #1266).
여기는 이 서버의 기록의 제목과 범위를 넘기는 것이다.
"""

from collections.abc import Iterable
from datetime import datetime

from conversation_core.transcripts import html
from conversation_core.transcripts.blocks import Block

from app.transcripts.story import Head, scope_text


def render(head: Head, blocks: Iterable[Block], generated_at: datetime) -> str:
    """파일 전체의 글."""
    return html.document(head.title, scope_text(head), blocks, generated_at)
