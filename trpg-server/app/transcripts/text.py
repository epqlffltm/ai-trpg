# trpg-server/app/transcripts/text.py

"""
기록을 꾸밈 없는 글(텍스트)로 쓴다(#617). DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

  - 어떤 편집기로 열어도 그대로 읽힌다. 표시 문법이 없다.
  - 구분은 "== 라운드 2 ==", 서술은 그대로, 선언은 "이름:" 아래에 들여 쓴 글, 한 줄의 일은 "· " 로 시작한다.
  - 구분과 서술과 선언의 앞에 빈 줄을 하나 둔다. 한 줄의 일은 이어 쓴다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.transcripts.blocks import Block, Heading, Paragraph, Speech, stands_apart
from app.transcripts.reading import Cut
from app.transcripts.story import Item, blocks_of, scenes_under_rounds, text_of

MEDIA_TYPE = 'text/plain; charset=utf-8'
EXTENSION = 'txt'
# 선언의 글을 들여 쓰는 칸
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
    """조각 하나의 글. 구분과 서술과 선언은 앞에 빈 줄을 둔다."""
    text = '\n'.join(block_lines(block)) + '\n'
    return f'\n{text}' if stands_apart(block) else text


def header(cut: Cut, generated_at: datetime) -> str:
    """파일의 머리. 제목, 범위, 내려받은 때."""
    scope = f'1~{cut.until}번 이벤트, 채팅, 내 쪽지' + (' (떠난 때까지)' if cut.departed else '')
    return f'{text_of(cut.title)}\n기록: {scope}\n내려받은 때: {generated_at.isoformat(timespec="seconds")}\n'


async def render(cut: Cut, items: AsyncIterator[Item]) -> AsyncIterator[str]:
    """파일 전체를 조각으로 흘린다. 머리를 먼저, 그 뒤로 조각마다 한 덩이다."""
    yield header(cut, datetime.now(UTC))
    async for item in scenes_under_rounds(items):
        for block in blocks_of(item, cut.labels):
            yield block_text(block)
