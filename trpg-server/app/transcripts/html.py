# trpg-server/app/transcripts/html.py

"""
기록을 읽기용 HTML 파일 하나로 쓴다(#617). DB 와 HTTP 를 모른다. 무엇을 쓸지는 app/transcripts/story.py 가 정한다.

  - 파일 하나로 열린다. 글꼴, 그림, 스크립트를 밖에서 가져오지 않는다. 꾸밈은 머리의 <style> 하나다.
  - 글은 모두 꺾쇠와 따옴표를 바꿔 쓴다(html.escape). 플레이어와 모델이 쓴 글이 태그나 스크립트가 되지 않는다.
    머리의 Content-Security-Policy 가 스크립트와 밖의 자원을 한 번 더 막는다(사람이 브라우저로 여는 파일이다).
  - 구분은 <h2>, 서술은 <p>, 선언은 <blockquote>, 이어진 한 줄의 일들은 <ul> 하나다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from html import escape

from app.transcripts.blocks import Block, Heading, Note, Paragraph, Speech
from app.transcripts.reading import Cut
from app.transcripts.story import Item, blocks_of, scenes_under_rounds, text_of

MEDIA_TYPE = 'text/html; charset=utf-8'
EXTENSION = 'html'

# 스크립트와 밖의 자원을 막고 머리의 꾸밈만 쓴다
POLICY = "default-src 'none'; style-src 'unsafe-inline'"
STYLE = (
    'body{max-width:46rem;margin:2rem auto;padding:0 1rem;font-family:sans-serif;line-height:1.7;color:#222}'
    'h1{font-size:1.6rem}h2{margin-top:2rem;border-bottom:1px solid #ddd;font-size:1.2rem}'
    'blockquote{margin:1rem 0;padding:.25rem 1rem;border-left:3px solid #999;background:#f6f6f6}'
    '.who{font-weight:bold;margin:0}ul{padding-left:1.2rem;color:#444}.scope{color:#666;font-size:.9rem}'
)


def paragraphs(lines: tuple[str, ...]) -> list[list[str]]:
    """빈 줄로 문단을 나눈다. 빈 문단은 버린다."""
    groups: list[list[str]] = [[]]
    for line in lines:
        if line:
            groups[-1].append(line)
        elif groups[-1]:
            groups.append([])
    return [group for group in groups if group]


def paragraph_html(lines: list[str]) -> str:
    """문단 하나. 줄은 <br> 로 잇는다."""
    return '<p>' + '<br>'.join(escape(line) for line in lines) + '</p>'


def block_html(block: Block) -> str:
    """조각 하나의 HTML. 한 줄의 일은 <li> 다(<ul> 은 쓰는 쪽이 연다)."""
    if isinstance(block, Heading):
        return f'<h2>{escape(block.text)}</h2>\n'
    if isinstance(block, Paragraph):
        return ''.join(paragraph_html(group) for group in paragraphs(block.lines)) + '\n'
    if isinstance(block, Speech):
        said = ''.join(paragraph_html(group) for group in paragraphs(block.lines))
        return f'<blockquote><p class="who">{escape(block.speaker)}</p>{said}</blockquote>\n'
    return f'<li>{escape(block.text)}</li>\n'


def with_list(block: Block, listing: bool) -> tuple[str, bool]:
    """
    조각 하나의 HTML 과, 그 뒤에 목록이 열려 있는가. 한 줄의 일이 처음 오면 <ul> 을 열고, 다른 조각이 오면 닫는다.
    """
    is_note = isinstance(block, Note)
    opening = '<ul>\n' if is_note and not listing else ''
    closing = '</ul>\n' if listing and not is_note else ''
    return closing + opening + block_html(block), is_note


def header(cut: Cut, generated_at: datetime) -> str:
    """파일의 머리. 제목, 범위, 내려받은 때."""
    title = escape(text_of(cut.title))
    scope = f'1~{cut.until}번 이벤트, 채팅, 내 쪽지' + (' (떠난 때까지)' if cut.departed else '')
    return (
        '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n'
        f'<h1>{title}</h1>\n'
        f'<p class="scope">기록: {escape(scope)}<br>내려받은 때: {generated_at.isoformat(timespec="seconds")}</p>\n'
    )


def footer(listing: bool) -> str:
    """파일의 끝. 열린 목록을 닫는다."""
    return ('</ul>\n' if listing else '') + '</body>\n</html>\n'


async def render(cut: Cut, items: AsyncIterator[Item]) -> AsyncIterator[str]:
    """파일 전체를 조각으로 흘린다. 머리를 먼저, 그 뒤로 조각마다 한 덩이, 끝을 마지막에."""
    yield header(cut, datetime.now(UTC))
    listing = False
    async for item in scenes_under_rounds(items):
        for block in blocks_of(item, cut.labels):
            chunk, listing = with_list(block, listing)
            yield chunk
    yield footer(listing)
