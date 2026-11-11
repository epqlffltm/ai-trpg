# shared/conversation-core/src/conversation_core/transcripts/text.py

"""
기록을 꾸밈 없는 글(텍스트)로 쓴다. 무엇을 쓸지와 제목, 범위의 말은 서버가 정한다.

  - 어떤 편집기로 열어도 그대로 읽힌다. 표시 문법이 없다.
  - 구분은 "== 대화 ==", 문단은 그대로, 말은 "이름:" 아래에 들여 쓴 글, 한 줄의 일은 "· " 로 시작한다.
  - 구분과 문단과 말의 앞에 빈 줄을 하나 둔다. 한 줄의 일은 이어 쓴다.
파일 전체를 한 번에 쓰는 것(document)과, 흘려 쓰는 쪽(trpg)이 쓰는 조각(header, block_text)이 있다.
"""

from collections.abc import Iterable
from datetime import datetime

from conversation_core.transcripts.blocks import Block, Heading, Paragraph, Speech, stands_apart

MEDIA_TYPE = 'text/plain; charset=utf-8'
EXTENSION = 'txt'
# 말의 글을 들여 쓰는 칸
INDENT = '    '


def block_lines(block: Block) -> list[str]:
    """조각 하나의 줄들."""
    if isinstance(block, Heading):
        return [f'== {block.text} ==']
    if isinstance(block, Paragraph):
        return list(block.lines)
    if isinstance(block, Speech):
        return [f'{block.speaker}:', *(f'{INDENT}{line}' if line else '' for line in block.lines)]
    return [f'· {block.text}']


def block_text(block: Block) -> str:
    """조각 하나의 글. 구분과 문단과 말은 앞에 빈 줄을 둔다."""
    text = '\n'.join(block_lines(block)) + '\n'
    return f'\n{text}' if stands_apart(block) else text


def header(title: str, scope: str, generated_at: datetime) -> str:
    """파일의 머리. 제목, 범위, 내려받은 때."""
    return f'{title}\n기록: {scope}\n내려받은 때: {generated_at.isoformat(timespec="seconds")}\n'


def document(title: str, scope: str, blocks: Iterable[Block], generated_at: datetime) -> str:
    """파일 전체의 글."""
    return header(title, scope, generated_at) + ''.join(block_text(block) for block in blocks)
