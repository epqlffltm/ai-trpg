# trpg-server/app/transcripts/markdown.py

"""
기록을 마크다운 글로 쓴다(#403). DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

  - 구분은 제목(##), 서술은 문단, 선언은 인용(> **이름**), 한 줄의 일은 목록(-)이다.
  - 서술과 선언의 글이 맨 앞에 # 을 써도 제목이 되지 않게 글자로 남긴다(\\#).
  - 구분과 문단과 인용의 앞뒤에 빈 줄을 하나 둔다. 둘씩 겹치지 않게 한다(joined).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.events.models import TableEvent
from app.transcripts.blocks import Block, Heading, Paragraph, Speech, stands_apart
from app.transcripts.labels import Labels
from app.transcripts.reading import Cut
from app.transcripts.story import Item, blocks_of, event_blocks, scenes_under_rounds, text_of

MEDIA_TYPE = 'text/markdown; charset=utf-8'
EXTENSION = 'md'


def safe_line(line: str) -> str:
    """
    서술과 선언의 글 한 줄. 맨 앞의 # 은 글자로 남긴다(\\#).

    모델이나 플레이어가 쓴 글이 파일의 제목(라운드의 구분)처럼 보이지 않게 한다.
    """
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


def render_blocks(blocks: list[Block]) -> str:
    """조각들의 글. 이어 쓴다. 겹친 빈 줄은 하나로 줄인다."""
    previous = ''
    for block in blocks:
        previous += joined(previous, block_text(block))
    return previous


def render_event(event: TableEvent, labels: Labels) -> str:
    """이벤트 하나를 글로. 쓰지 않는 종류면 빈 글자다."""
    return render_blocks(event_blocks(event, labels))


def joined(previous: str, chunk: str) -> str:
    """
    앞 조각이 이미 빈 줄로 끝났으면 이 조각의 앞 빈 줄을 뺀다. 빈 줄이 둘씩 겹치지 않게 한다.

    빈 줄은 빼지 않고 하나는 남긴다. 목록 바로 뒤의 문단은 그 목록에 붙고, 이어진 인용 둘은 하나로 합쳐지기 때문이다.
    """
    if chunk.startswith('\n') and previous.endswith('\n\n'):
        return chunk[1:]
    return chunk


def header(cut: Cut, generated_at: datetime) -> str:
    """파일의 머리. 제목, 범위, 내려받은 때."""
    scope = f'1~{cut.until}번 이벤트, 채팅, 내 쪽지' + (' (떠난 때까지)' if cut.departed else '')
    lines = [
        f'# {text_of(cut.title)}',
        '',
        f'- 기록: {scope}',
        f'- 내려받은 때: {generated_at.isoformat(timespec="seconds")}',
        '',
    ]
    return '\n'.join(lines) + '\n'


async def render(cut: Cut, items: AsyncIterator[Item]) -> AsyncIterator[str]:
    """파일 전체를 조각으로 흘린다. 머리를 먼저, 그 뒤로 조각마다 한 덩이다. 쓰지 않는 것은 건너뛴다."""
    previous = header(cut, datetime.now(UTC))
    yield previous
    async for item in scenes_under_rounds(items):
        for block in blocks_of(item, cut.labels):
            chunk = joined(previous, block_text(block))
            yield chunk
            previous = chunk
