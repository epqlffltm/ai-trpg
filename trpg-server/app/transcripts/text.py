# trpg-server/app/transcripts/text.py

"""
기록을 꾸밈 없는 글(텍스트)로 흘려 쓴다(#617). DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

조각을 글로 쓰는 것과 파일의 머리는 chat, story 와 함께 쓰는 공용 코드에 있다
(conversation_core/transcripts/text.py, #1266).
여기는 판의 범위를 머리에 적고 이벤트를 차례로 흘리는 것이다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from conversation_core.transcripts import text

from app.transcripts.reading import Cut, scope_text
from app.transcripts.story import Item, blocks_of, scenes_under_rounds, text_of


def header(cut: Cut, generated_at: datetime) -> str:
    """파일의 머리. 판의 제목, 범위, 내려받은 때."""
    return text.header(text_of(cut.title), scope_text(cut), generated_at)


async def render(cut: Cut, items: AsyncIterator[Item]) -> AsyncIterator[str]:
    """파일 전체를 조각으로 흘린다. 머리를 먼저, 그 뒤로 조각마다 한 덩이다."""
    yield header(cut, datetime.now(UTC))
    async for item in scenes_under_rounds(items):
        for block in blocks_of(item, cut.labels):
            yield text.block_text(block)
