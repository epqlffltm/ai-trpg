# story-server/tests/test_transcripts.py

"""
세션 기록 내려받기(app/transcripts/, #617 의 story 몫)를 검증한다.
쓰는 쪽은 DB 없이, API 는 실제 DB(story_test)에서 돈다.

보는 것.
  - 조각: 지금 가지의 말, 행동, 열린 이벤트와 본 엔딩(판의 이름으로), 끊긴 답, 고친 답.
    답은 말 조각마다이고, 서술은 문단, 같은 사람이 이어 말한 조각은 하나다. 페르소나가 없으면 사람의 말은 "나"다.
    판에 없는 인물과 이벤트는 id 그대로다. 조각이 없는 답은 본문을 서술로 적는다
  - 형식: 마크다운은 글 맨 앞의 # 을 글자로 남기고, HTML 은 글을 모두 바꿔 쓰고 CSP 를 단다, 텍스트는 말을 들여 쓴다
  - API: 형식마다의 종류와 파일 이름, 남의 세션과 지운 세션은 404, 받는 수를 넘으면 429(없는 세션의 요청도 센다)
"""

import asyncio
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import Message, MessageStatus, Role
from app.engine.world import read_world
from app.limits.setup import build_limiting
from app.transcripts import html, markdown, text
from app.transcripts.blocks import Heading, Note, Paragraph, Speech
from app.transcripts.story import Head, transcript_blocks
from app.turns.briefing import read_briefing
from tests.assets import FakeAsset
from tests.engine_worlds import condition, document, ending, event, member
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

THEM = uuid.UUID('99999999-2222-4333-8444-555555555555')
AT = datetime(2026, 10, 31, 9, 0, tzinfo=UTC)

DOCUMENT = document(
    cast=[{**member('mina', home='home'), 'character': {'name': '미나'}}],
    events=[{**event('shell', condition('reach_place', 'beach')), 'name': '조개 줍기'}],
    endings=[{**ending('solo', 'deadline'), 'name': '혼자인 여름'}],
)


def head(persona: str | None = None, count: int = 0) -> Head:
    return Head(
        title='여름 마을',
        world='여름',
        version=2,
        persona=persona,
        message_count=count,
        briefing=read_briefing(DOCUMENT),
        rules=read_world(DOCUMENT),
    )


def message(role: Role, content: str = '', **extra) -> Message:
    return Message(
        role=role,
        content=content,
        status=extra.pop('status', MessageStatus.COMPLETE),
        edited=extra.pop('edited', False),
        **extra,
    )


def answer(*segments: tuple[str | None, str], **extra) -> Message:
    return message(Role.ASSISTANT, segments=[{'speaker': who, 'text': said} for who, said in segments], **extra)


# --- 조각 ---


def test_blocks_follow_the_branch_with_what_the_screen_showed():
    messages = [
        message(Role.USER, '안녕'),
        answer((None, '해가 기운다.'), ('mina', '왔구나.'), ('mina', '기다렸어.'), ('ghost', '누구지?')),
        message(Role.ACTION, '해변(으)로 갔다. 지금은 1일째 아침.', event_id='shell'),
        answer(('mina', '조개'), status=MessageStatus.PARTIAL, edited=True),
        message(Role.ACTION, '하루를 마쳤다.', ending_id='solo'),
        message(Role.ACTION, '골랐다.', event_id='gone', ending_id='lost'),
        message(Role.ASSISTANT, '옛 답'),
        message(Role.ASSISTANT, ''),
    ]

    blocks = list(transcript_blocks(head(), messages))

    assert blocks == [
        Heading('이야기'),
        Speech('나', ('안녕',)),
        Paragraph(('해가 기운다.',)),
        Speech('미나', ('왔구나.', '기다렸어.')),
        Speech('ghost', ('누구지?',)),
        Note('해변(으)로 갔다. 지금은 1일째 아침.'),
        Note('이벤트: 조개 줍기'),
        Speech('미나', ('조개',)),
        Note('여기서 끊긴 답이다'),
        Note('고친 답이다'),
        Note('하루를 마쳤다.'),
        Note('엔딩: 혼자인 여름'),
        Note('골랐다.'),
        Note('이벤트: gone'),
        Note('엔딩: lost'),
        Paragraph(('옛 답',)),
    ]


def test_a_persona_names_the_person():
    blocks = list(transcript_blocks(head(persona='한서윤'), [message(Role.USER, '안녕')]))

    assert blocks[-1] == Speech('한서윤', ('안녕',))


# --- 형식 ---

TRICKY = [
    message(Role.USER, '# 제목 흉내\n<script>alert(1)</script>'),
    message(Role.ACTION, '꽃을 건넸다.'),
    answer((None, '바람이 분다.')),
]


def test_markdown_keeps_a_leading_hash_as_text():
    written = markdown.render(head(count=3), transcript_blocks(head(count=3), TRICKY), AT)

    assert written.startswith('# 여름 마을\n\n- 기록: 여름(2번째 판), 지금 보는 가지의 말 3개\n')
    assert '> **나**\n> \\# 제목 흉내\n' in written
    assert '- 꽃을 건넸다.\n\n바람이 분다.\n' in written
    assert '\n\n\n' not in written


def test_html_escapes_everything_and_blocks_scripts():
    written = html.render(head(), transcript_blocks(head(), TRICKY), AT)

    assert '<script>' not in written
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in written
    assert "default-src 'none'" in written
    assert '<ul>\n<li>꽃을 건넸다.</li>\n</ul>\n<p>바람이 분다.</p>' in written


def test_html_splits_paragraphs_at_blank_lines():
    said = [message(Role.USER, '첫 줄\n\n\n둘째 문단')]

    written = html.render(head(), transcript_blocks(head(), said), AT)

    assert '<p class="who">나</p><p>첫 줄</p><p>둘째 문단</p>' in written


def test_text_indents_what_was_said():
    written = text.render(head(), transcript_blocks(head(), TRICKY), AT)

    assert '\n나:\n    # 제목 흉내\n    <script>alert(1)</script>\n' in written
    assert '· 꽃을 건넸다.\n' in written
    assert '== 이야기 ==' in written


# --- API ---


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
async def talked(clean_tables: None, session: AsyncSession, client: AsyncClient, app: FastAPI, asset: FakeAsset, mine):
    """말을 하나 주고받은 세션. 답은 서술 하나와 미나의 말 둘이다."""
    app.state.model_router = FakeRouter(
        ScriptedProvider(pieces=['@narration: 해가 진다.\n@mina: 늦었네.\n@mina: 왔어?'])
    )
    await turn_on_luna(session)
    conversation = await start_with_luna(client, asset, mine)
    response = await client.post(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json={'content': '기다렸어?'}, headers=mine
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    return conversation


def transcript_url(conversation: dict) -> str:
    return f'{CONVERSATIONS_URL}/{conversation["id"]}/transcript'


async def test_the_branch_is_downloaded_as_a_markdown_file(client: AsyncClient, talked: dict, mine: dict):
    response = await client.get(transcript_url(talked), headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers['content-type'] == 'text/markdown; charset=utf-8'
    assert quote(f'{talked["title"]}.md', safe='') in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    body = response.text
    assert '## 이야기\n\n> **나**\n> 기다렸어?\n\n해가 진다.\n\n> **미나**\n> 늦었네.\n> 왔어?\n' in body


@pytest.mark.parametrize(('chosen', 'kind'), [('html', 'text/html'), ('txt', 'text/plain')])
async def test_other_formats(client: AsyncClient, talked: dict, mine: dict, chosen: str, kind: str):
    response = await client.get(transcript_url(talked), params={'format': chosen}, headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers['content-type'] == f'{kind}; charset=utf-8'
    assert f'.{chosen}' in response.headers['content-disposition']
    assert '기다렸어?' in response.text


async def test_someone_elses_and_deleted_sessions_are_404(
    client: AsyncClient, talked: dict, mine: dict, signing_key: SigningKey
):
    theirs = await client.get(transcript_url(talked), headers=bearer(signing_key, THEM))
    await client.delete(f'{CONVERSATIONS_URL}/{talked["id"]}', headers=mine)
    deleted = await client.get(transcript_url(talked), headers=mine)

    assert (theirs.status_code, deleted.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_404_NOT_FOUND)


async def test_an_unknown_format_is_422(client: AsyncClient, talked: dict, mine: dict):
    response = await client.get(transcript_url(talked), params={'format': 'pdf'}, headers=mine)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_downloads_over_the_limit_are_429_and_misses_count(
    client: AsyncClient, app: FastAPI, talked: dict, mine: dict
):
    settings = app.state.settings.model_copy(update={'limits_enabled': True, 'transcript_limit': 2})
    app.state.limiting = build_limiting(settings, None)

    missing = await client.get(f'{CONVERSATIONS_URL}/{uuid.uuid4()}/transcript', headers=mine)
    first = await client.get(transcript_url(talked), headers=mine)
    third = await client.get(transcript_url(talked), headers=mine)

    assert (missing.status_code, first.status_code) == (status.HTTP_404_NOT_FOUND, status.HTTP_200_OK)
    assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
