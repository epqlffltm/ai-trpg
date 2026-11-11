# trpg-server/app/transcripts/formats.py

"""
기록을 내려받는 형식(#403, #617). 형식마다 쓰는 쪽(render), 응답의 종류, 파일의 확장자가 하나씩이다.

  - md: 마크다운(#403). 기본이다. 다른 도구에 붙여 넣기 좋다
  - html: 읽기용 HTML 파일 하나(#617). 브라우저로 열어 읽는다
  - txt: 꾸밈 없는 글(#617). 어떤 편집기로도 읽는다
셋은 같은 조각(app/transcripts/story.py)을 쓴다. 내용은 같고 모양만 다르다.
"""

import enum
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from conversation_core.transcripts import html as shared_html
from conversation_core.transcripts import markdown as shared_markdown
from conversation_core.transcripts import text as shared_text

from app.transcripts import html, markdown, text
from app.transcripts.reading import Cut
from app.transcripts.story import Item


class TranscriptFormat(enum.StrEnum):
    """기록의 형식."""

    MARKDOWN = 'md'
    HTML = 'html'
    TEXT = 'txt'


@dataclass(frozen=True)
class Writer:
    """형식 하나를 쓰는 법. 파일 전체를 흘리는 함수, 응답의 종류, 확장자."""

    render: Callable[[Cut, AsyncIterator[Item]], AsyncIterator[str]]
    media_type: str
    extension: str


WRITERS: dict[TranscriptFormat, Writer] = {
    TranscriptFormat.MARKDOWN: Writer(markdown.render, shared_markdown.MEDIA_TYPE, shared_markdown.EXTENSION),
    TranscriptFormat.HTML: Writer(html.render, shared_html.MEDIA_TYPE, shared_html.EXTENSION),
    TranscriptFormat.TEXT: Writer(text.render, shared_text.MEDIA_TYPE, shared_text.EXTENSION),
}
