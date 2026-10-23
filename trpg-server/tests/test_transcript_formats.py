# trpg-server/tests/test_transcript_formats.py

"""
기록 내려받기에 더한 것(#617)을 검증한다. 마크다운의 내용과 범위는 tests/test_transcripts_api.py 가 본다.

픽스처와 도우미는 tests/test_whispers.py 의 것이다. 나(엘프, 방장), 친구(영애), 제삼자(기사)가 앉는다.

보는 것.
  - 쪽지는 보냈거나 받은 사람의 기록에만 있다. 제삼자의 기록에는 그 글도, 쪽지가 있었다는 것도 없다.
  - 채팅은 앉은 사람 모두의 기록에 있다. 떠난 사람의 기록에는 떠난 뒤의 채팅이 없다.
  - 형식(md, html, txt)마다 응답의 종류와 파일의 이름이 다르다. 모르는 형식은 422 다.
  - HTML 은 플레이어가 쓴 글을 태그로 만들지 않는다. 스크립트를 막는 정책이 머리에 있다.
  - 한 사람이 받는 수를 센다. 넘으면 429 다.
  - 쓰는 쪽(HTML, 텍스트)과 흐름을 합치는 것은 DB 없이 본다.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient

from app.limits.setup import build_limiting
from app.transcripts import html, reading, text
from app.transcripts.blocks import Heading, Note, Paragraph, Speech
from tests import test_whispers as whisper_tests
from tests.conftest import make_test_settings
from tests.test_whispers import FRIEND, ME, SECRET, THIRD, open_trio, start, table_url, whisper

pytestmark = pytest.mark.usefixtures('clean_tables')

me = whisper_tests.me
friend = whisper_tests.friend
third = whisper_tests.third
stranger = whisper_tests.stranger

GREETING = '다들 반가워요'
NASTY = '<script>alert(1)</script>'


async def started_trio(client: AsyncClient, me: dict, friend: dict, third: dict) -> dict:
    """셋이 앉아 시작한 테이블."""
    table = await open_trio(client, me, friend, third)
    await start(client, table, {ME: me, FRIEND: friend, THIRD: third})
    return table


async def chat(client: AsyncClient, headers: dict, table: dict, content: str) -> None:
    response = await client.post(table_url(table, '/messages'), json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text


async def record(client: AsyncClient, headers: dict, table: dict, format_: str = 'md', past: bool = False):
    """기록을 내려받는 요청. 응답을 그대로 돌려준다."""
    url = f'{whisper_tests.TABLES_URL}/past/{table["id"]}/transcript' if past else table_url(table, '/transcript')
    return await client.get(url, params={'format': format_}, headers=headers)


async def record_text(client: AsyncClient, headers: dict, table: dict, **options) -> str:
    response = await record(client, headers, table, **options)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.text


# --- 쪽지와 채팅 ---


async def test_a_whisper_is_only_in_the_records_of_its_two_ends(
    client: AsyncClient, me: dict, friend: dict, third: dict
):
    table = await started_trio(client, me, friend, third)
    await whisper(client, me, table, FRIEND)

    mine = await record_text(client, me, table)
    theirs = await record_text(client, friend, table)
    others = await record_text(client, third, table)

    line = f'- 쪽지 · 엘프 → 영애: {SECRET}'
    assert line in mine and line in theirs
    # 제삼자는 글도, 쪽지가 오갔다는 것도 모른다
    assert SECRET not in others and '- 쪽지 ·' not in others


async def test_chat_is_in_everyone_s_record_but_not_after_leaving(
    client: AsyncClient, me: dict, friend: dict, third: dict
):
    table = await started_trio(client, me, friend, third)
    await chat(client, third, table, GREETING)
    left = await client.delete(table_url(table, '/members/me'), headers=third)
    assert left.status_code == status.HTTP_204_NO_CONTENT, left.text
    await chat(client, me, table, '기사가 갔네')

    mine = await record_text(client, me, table)
    gone = await record_text(client, third, table, past=True)

    assert f'- 채팅 · 기사: {GREETING}' in mine and f'- 채팅 · 기사: {GREETING}' in gone
    assert '기사가 갔네' in mine and '기사가 갔네' not in gone


# --- 형식 ---


@pytest.mark.parametrize(
    ('format_', 'media_type', 'extension'),
    [('md', 'text/markdown', 'md'), ('html', 'text/html', 'html'), ('txt', 'text/plain', 'txt')],
)
async def test_each_format_has_its_own_kind_and_name(
    client: AsyncClient, me: dict, friend: dict, third: dict, format_: str, media_type: str, extension: str
):
    table = await started_trio(client, me, friend, third)

    response = await record(client, me, table, format_)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.headers['content-type'] == f'{media_type}; charset=utf-8'
    assert response.headers['content-disposition'].startswith(f'attachment; filename="transcript.{extension}"')
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert '함께한 캐릭터: 엘프, 영애, 기사' in response.text


async def test_an_unknown_format_is_refused(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await started_trio(client, me, friend, third)

    response = await record(client, me, table, 'pdf')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_html_never_turns_what_players_wrote_into_tags(client: AsyncClient, me: dict, friend: dict, third: dict):
    table = await started_trio(client, me, friend, third)
    await chat(client, friend, table, NASTY)

    page = await record_text(client, me, table, format_='html')

    assert NASTY not in page
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
    assert "default-src 'none'" in page
    assert page.startswith('<!doctype html>') and page.rstrip().endswith('</html>')


# --- 받는 수 ---


async def test_too_many_downloads_are_refused(app: FastAPI, client: AsyncClient, me: dict, friend: dict, third: dict):
    app.state.limiting = build_limiting(make_test_settings(limits_enabled=True, transcripts_per_window=2), None)
    table = await started_trio(client, me, friend, third)

    first, second, third_try = [await record(client, me, table) for _ in range(3)]
    others = await record(client, friend, table)

    assert first.status_code == second.status_code == status.HTTP_200_OK
    assert third_try.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert third_try.json()['code'] == 'too_many_attempts'
    # 사람마다 센다
    assert others.status_code == status.HTTP_200_OK


# --- 쓰는 쪽(DB 없이) ---


def test_html_blocks_are_escaped_and_notes_share_one_list():
    listing = False
    pieces = []
    for block in [Heading('라운드 <1>'), Note('a & b'), Note('c'), Speech('엘프 "1"', ('안녕', '', '<b>둘</b>'))]:
        chunk, listing = html.with_list(block, listing)
        pieces.append(chunk)
    written = ''.join(pieces) + html.footer(listing)

    assert written == (
        '<h2>라운드 &lt;1&gt;</h2>\n'
        '<ul>\n<li>a &amp; b</li>\n<li>c</li>\n</ul>\n'
        '<blockquote><p class="who">엘프 &quot;1&quot;</p><p>안녕</p><p>&lt;b&gt;둘&lt;/b&gt;</p></blockquote>\n'
        '</body>\n</html>\n'
    )


def test_html_keeps_line_breaks_inside_a_paragraph():
    assert html.block_html(Paragraph(('첫 줄', '둘째 줄', '', '새 문단'))) == '<p>첫 줄<br>둘째 줄</p><p>새 문단</p>\n'


def test_plain_text_has_no_markup():
    blocks = [Heading('라운드 2'), Paragraph(('# 제목 같은 글',)), Speech('엘프', ('간다.',)), Note('판정: 성공')]

    written = ''.join(text.block_text(block) for block in blocks)

    assert written == '\n== 라운드 2 ==\n\n# 제목 같은 글\n\n엘프:\n    간다.\n· 판정: 성공\n'


async def stream(*stamps: int, kind: str):
    """그 시각(분)들에 적힌 것을 차례로 내놓는 흐름."""
    start = datetime(2026, 10, 22, tzinfo=UTC)
    for stamp in stamps:
        yield SimpleNamespace(created_at=start + timedelta(minutes=stamp), kind=kind, stamp=stamp)


async def test_streams_are_merged_in_the_order_they_were_written():
    items = reading.merged(stream(1, 3, 5, kind='event'), stream(2, 3, kind='chat'), stream(0, kind='whisper'))

    merged = [(item.stamp, item.kind) async for item in items]

    # 같은 시각이면 이벤트, 채팅, 쪽지의 차례다
    assert merged == [(0, 'whisper'), (1, 'event'), (2, 'chat'), (3, 'event'), (3, 'chat'), (5, 'event')]
