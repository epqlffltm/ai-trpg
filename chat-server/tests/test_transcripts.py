# chat-server/tests/test_transcripts.py

"""
대화 기록 내려받기(app/transcripts/, #617 의 chat 몫)를 검증한다. 쓰는 쪽은 DB 없이, API 는 실제 DB(chat_test)에서 돈다.

보는 것.
  - 조각: 시작 상황, 지금 가지의 말, 행동, 끊긴 답, 고친 답, 받아들인 변화(판의 이름으로), 이벤트 씬의 제목.
    글자 하나 없이 실패한 답은 쓰지 않는다. 페르소나가 없으면 사람의 말은 "나"다
  - 형식: 마크다운은 글 맨 앞의 # 을 글자로 남기고, HTML 은 글을 모두 바꿔 쓰고 CSP 를 단다, 텍스트는 말을 들여 쓴다
  - API: 형식마다의 종류와 파일 이름, 남의 대화는 404, 받는 수를 넘으면 429(없는 대화의 요청도 센다)
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

from app.assets.schemas import CharacterDocument
from app.conversations.models import Message, MessageStatus, Role
from app.limits.setup import build_limiting
from app.transcripts import html, markdown, text
from app.transcripts.blocks import Heading, Note, Paragraph, Speech
from app.transcripts.story import Head, change_text, transcript_blocks
from tests.assets import FakeAsset
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, bearer, start_with_luna, turn_on_luna

THEM = uuid.UUID('99999999-2222-4333-8444-555555555555')
AT = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)

DOCUMENT = CharacterDocument.model_validate(
    {
        'format': 1,
        'name': '세라',
        'intro_html': '',
        'greeting': '',
        'speech_examples': '',
        'age': '',
        'gender': '',
        'tags': [],
        'starts': [{'title': '비 오는 밤', 'situation': '문을 두드리는 소리가 난다.'}],
        'image_id': None,
        'rating': 'all',
        'places': [{'id': 'p1', 'name': '카페', 'description': '', 'image_id': None}],
        'items': [{'id': 'i1', 'name': '꽃', 'description': '', 'kind': 'thing', 'image_id': None}],
        'event_scenes': [
            {
                'id': 's1',
                'title': '노을',
                'image_id': '0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e',
                'when': {'kind': 'reach_place', 'target': 'p1'},
            }
        ],
    }
)


def head(persona: str | None = None, count: int = 0) -> Head:
    return Head(
        title='비 오는 밤',
        character='세라',
        version=2,
        start_title='비 오는 밤',
        start_situation='문을 두드리는 소리가 난다.\n\n비가 온다.',
        persona=persona,
        message_count=count,
        document=DOCUMENT,
    )


def message(role: Role, content: str, **extra) -> Message:
    return Message(role=role, content=content, status=extra.pop('status', MessageStatus.COMPLETE), **extra)


# --- 조각 ---


def test_blocks_follow_the_branch_with_what_the_screen_showed():
    messages = [
        message(Role.ASSISTANT, '어서 와요.'),
        message(Role.ACTION, '카페로 갔다.', event_scene='s1'),
        message(Role.ASSISTANT, '여기 좋네요.', changes=[{'kind': 'affection', 'rising': True, 'delta': 3}]),
        message(Role.USER, '고마워'),
        message(Role.ASSISTANT, '그럼', status=MessageStatus.PARTIAL, edited=True),
        message(Role.ASSISTANT, '', status=MessageStatus.FAILED),
    ]

    blocks = list(transcript_blocks(head(), messages))

    assert blocks == [
        Heading('시작 상황: 비 오는 밤'),
        Paragraph(('문을 두드리는 소리가 난다.', '', '비가 온다.')),
        Heading('대화'),
        Speech('세라', ('어서 와요.',)),
        Note('카페로 갔다.'),
        Note('이벤트 씬: 노을'),
        Speech('세라', ('여기 좋네요.',)),
        Note('호감도가 올랐다(+3)'),
        Speech('나', ('고마워',)),
        Speech('세라(고침)', ('그럼',)),
        Note('여기서 끊긴 답이다'),
    ]


def test_a_persona_names_the_person():
    blocks = list(transcript_blocks(head(persona='한서윤'), [message(Role.USER, '안녕')]))

    assert blocks[-1] == Speech('한서윤', ('안녕',))


def test_changes_use_the_names_of_the_version():
    assert change_text({'kind': 'affection', 'rising': False, 'delta': None}, DOCUMENT) == '호감도가 내렸다'
    assert change_text({'kind': 'gift', 'item': 'i1'}, DOCUMENT) == '받은 물건: 꽃'
    assert change_text({'kind': 'move', 'place': 'p1', 'minutes': 30}, DOCUMENT) == '함께 간 곳: 카페(30분)'
    assert change_text({'kind': 'move', 'place': 'gone', 'minutes': 5}, DOCUMENT) == '함께 간 곳: gone(5분)'
    assert change_text({'kind': 'unknown'}, DOCUMENT) is None


# --- 형식 ---

TRICKY = [message(Role.USER, '# 제목 흉내\n<script>alert(1)</script>'), message(Role.ACTION, '꽃을 건넸다.')]


def test_markdown_keeps_a_leading_hash_as_text():
    written = markdown.render(head(count=2), transcript_blocks(head(count=2), TRICKY), AT)

    assert written.startswith('# 비 오는 밤\n\n- 기록: 세라(2번째 판), 지금 보는 가지의 말 2개\n')
    assert '> **나**\n> \\# 제목 흉내\n' in written
    assert '- 꽃을 건넸다.\n' in written
    assert '\n\n\n' not in written


def test_html_escapes_everything_and_blocks_scripts():
    written = html.render(head(), transcript_blocks(head(), TRICKY), AT)

    assert '<script>' not in written
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in written
    assert "default-src 'none'" in written
    assert '<ul>\n<li>꽃을 건넸다.</li>\n</ul>\n</body>' in written


def test_text_indents_what_was_said():
    written = text.render(head(), transcript_blocks(head(), TRICKY), AT)

    assert '\n나:\n    # 제목 흉내\n    <script>alert(1)</script>\n' in written
    assert '· 꽃을 건넸다.\n' in written
    assert '== 대화 ==' in written


# --- API ---


@pytest.fixture
def mine(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key)


@pytest.fixture
async def talked(clean_tables: None, session: AsyncSession, client: AsyncClient, app: FastAPI, asset: FakeAsset, mine):
    """인사말 뒤에 말을 하나 주고받은 대화."""
    app.state.model_router = FakeRouter(ScriptedProvider(pieces=['비가 많이 오네요.']))
    await turn_on_luna(session)
    conversation = await start_with_luna(client, asset, mine)
    response = await client.post(
        f'{CONVERSATIONS_URL}/{conversation["id"]}/messages', json={'content': '들어가도 될까요?'}, headers=mine
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
    body = response.text
    assert '## 시작 상황: ' in body
    assert '> **세라**\n> 어서 와요. 찾는 책이 있나요?' in body
    assert '> **나**\n> 들어가도 될까요?' in body
    assert '> 비가 많이 오네요.' in body


@pytest.mark.parametrize(('chosen', 'kind'), [('html', 'text/html'), ('txt', 'text/plain')])
async def test_other_formats(client: AsyncClient, talked: dict, mine: dict, chosen: str, kind: str):
    response = await client.get(transcript_url(talked), params={'format': chosen}, headers=mine)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers['content-type'] == f'{kind}; charset=utf-8'
    assert f'.{chosen}' in response.headers['content-disposition']
    assert '들어가도 될까요?' in response.text


async def test_someone_elses_conversation_is_404(client: AsyncClient, talked: dict, signing_key: SigningKey):
    response = await client.get(transcript_url(talked), headers=bearer(signing_key, THEM))

    assert response.status_code == status.HTTP_404_NOT_FOUND


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
