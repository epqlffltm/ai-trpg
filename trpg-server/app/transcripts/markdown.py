# trpg-server/app/transcripts/markdown.py

"""
기록을 마크다운 글로 쓴다(#403). DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

조각을 마크다운으로 쓰는 것(# 을 글자로 남기기, 겹친 빈 줄 줄이기)과 파일의 머리는 chat, story 와 함께 쓰는
공용 코드에 있다(conversation_core/transcripts/markdown.py, #1266).
여기는 판의 범위를 머리에 적고 이벤트를 차례로 흘리는 것과, 이벤트 하나를 글로 바꾸는 것(render_event)이다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from conversation_core.transcripts import markdown
from conversation_core.transcripts.blocks import Block

from app.events.models import TableEvent
from app.transcripts.labels import Labels
from app.transcripts.reading import Cut, scope_text
from app.transcripts.story import Item, blocks_of, event_blocks, scenes_under_rounds, text_of


def render_blocks(blocks: list[Block]) -> str:
    """조각들의 글. 이어 쓴다. 겹친 빈 줄은 하나로 줄인다."""
    previous = ''
    for block in blocks:
        previous += markdown.joined(previous, markdown.block_text(block))
    return previous


def render_event(event: TableEvent, labels: Labels) -> str:
    """이벤트 하나를 글로. 쓰지 않는 종류면 빈 글자다."""
    return render_blocks(event_blocks(event, labels))


def header(cut: Cut, generated_at: datetime) -> str:
    """파일의 머리. 판의 제목, 범위, 내려받은 때."""
    return markdown.header(text_of(cut.title), scope_text(cut), generated_at)


async def render(cut: Cut, items: AsyncIterator[Item]) -> AsyncIterator[str]:
    """파일 전체를 조각으로 흘린다. 머리를 먼저, 그 뒤로 조각마다 한 덩이다. 쓰지 않는 것은 건너뛴다."""
    previous = header(cut, datetime.now(UTC))
    yield previous
    async for item in scenes_under_rounds(items):
        for block in blocks_of(item, cut.labels):
            chunk = markdown.joined(previous, markdown.block_text(block))
            yield chunk
            previous = chunk
