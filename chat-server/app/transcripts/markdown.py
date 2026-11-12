# chat-server/app/transcripts/markdown.py

"""
기록을 마크다운 글로 쓴다. DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

조각을 쓰는 것과 파일의 머리, 끝은 게임, story 와 함께 쓰는 공용 코드에 있다
(conversation_core/transcripts/markdown.py, #1266).
여기는 이 서버의 기록의 제목과 범위를 넘기는 것이다.
"""

from collections.abc import Iterable
from datetime import datetime

from conversation_core.transcripts import markdown
from conversation_core.transcripts.blocks import Block

from app.transcripts.story import Head, scope_text


def render(head: Head, blocks: Iterable[Block], generated_at: datetime) -> str:
    """파일 전체의 글."""
    return markdown.document(head.title, scope_text(head), blocks, generated_at)
