# chat-server/app/transcripts/markdown.py

"""
기록을 마크다운 글로 쓴다. DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

  - 구분은 제목(##), 시작 상황은 문단, 말은 인용(> **이름**), 한 줄의 일은 목록(-)이다.
  - 사람과 모델의 글이 맨 앞에 # 을 써도 제목이 되지 않게 글자로 남긴다(\\#).
  - 구분과 문단과 인용의 앞뒤에 빈 줄을 하나 둔다. 둘씩 겹치지 않게 한다(joined).
"""

from collections.abc import Iterable
from datetime import datetime

from app.transcripts.blocks import Block, Heading, Paragraph, Speech, stands_apart
from app.transcripts.story import Head, scope_text

MEDIA_TYPE = 'text/markdown; charset=utf-8'
EXTENSION = 'md'


def safe_line(line: str) -> str:
    """글 한 줄. 맨 앞의 # 은 글자로 남긴다(\\#). 모델이나 사람이 쓴 글이 파일의 제목처럼 보이지 않게 한다."""
    stripped = line.lstrip()
    return '\\' + stripped if stripped.startswith('#') else stripped


def block_lines(block: Block) -> list[str]:
    """조각 하나의 줄들."""
    if isinstance(block, Heading):
        return [f'## {block.text}']
    if isinstance(block, Paragraph):
        return [safe_line(line) for line in block.lines]
    if isinstance(block, Speech):
        return [f'> **{block.speaker}**', *(f'> {safe_line(line)}' if line else '>' for line in block.lines)]
    return [f'- {block.text}']


def block_text(block: Block) -> str:
    """조각 하나의 글. 구분과 문단과 인용은 앞뒤에 빈 줄을 둔다."""
    text = '\n'.join(block_lines(block)) + '\n'
    return f'\n{text}\n' if stands_apart(block) else text


def joined(previous: str, chunk: str) -> str:
    """앞 조각이 이미 빈 줄로 끝났으면 이 조각의 앞 빈 줄을 뺀다. 빈 줄이 둘씩 겹치지 않게 한다."""
    if chunk.startswith('\n') and previous.endswith('\n\n'):
        return chunk[1:]
    return chunk


def header(head: Head, generated_at: datetime) -> str:
    """파일의 머리. 제목, 범위, 내려받은 때."""
    lines = [
        f'# {head.title}',
        '',
        f'- 기록: {scope_text(head)}',
        f'- 내려받은 때: {generated_at.isoformat(timespec="seconds")}',
        '',
    ]
    return '\n'.join(lines) + '\n'


def render(head: Head, blocks: Iterable[Block], generated_at: datetime) -> str:
    """파일 전체의 글."""
    written = [header(head, generated_at)]
    for block in blocks:
        written.append(joined(written[-1], block_text(block)))
    return ''.join(written)
