# story-server/app/transcripts/router.py

"""
세션 기록 내려받기 API(#617 의 story 몫, chat 과 같은 모양).

  - GET /conversations/{conversation_id}/transcript: 내 세션의 지금 보고 있는 가지를 파일 하나로 준다
형식은 format 으로 고른다(md 기본, html, txt, app/transcripts/formats.py).

세션을 읽는 규칙은 세션 읽기(GET /conversations/{id})와 같다. 남의 세션, 지운 세션, 볼 수 없는 등급이면 404 다.
한 사람이 받는 수를 센다(limits.transcripts). 넘으면 429 다. 없는 세션의 요청도 센다(세션을 찾아다니지 못하게).
세션의 말은 지금 가지의 것만이라 한 번에 읽어 쓴다.
"""

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Response, status

from app.conversations import service
from app.conversations.models import ConversationPersona, Message
from app.conversations.repository import ConversationRow
from app.core.dependencies import CurrentViewer, Now, Session
from app.engine.world import read_world
from app.limits.routing import TRANSCRIPT_LIMIT
from app.transcripts.formats import WRITERS, TranscriptFormat, Writer
from app.transcripts.story import Head, transcript_blocks
from app.turns.briefing import read_briefing

router = APIRouter(prefix='/conversations', tags=['transcripts'])

# 머리말의 기본 이름. 이름에 쓸 수 없는 글자를 고르지 않아도 되게 글자 하나 없이 둔다. 제목은 filename* 에 싣는다
FALLBACK_NAME = 'session'
# 형식을 고르는 칸. 보내지 않으면 마크다운이다
Format = Annotated[TranscriptFormat, Query(alias='format')]


def head_of(row: ConversationRow, persona: ConversationPersona | None, messages: list[Message]) -> Head:
    """세션의 머리. 이름은 세션에 가져온 사본의 것이다(지금의 원본이 아니다)."""
    conversation, world = row
    return Head(
        title=conversation.title,
        world=world.name,
        version=world.version,
        persona=persona.name if persona is not None else None,
        message_count=len(messages),
        briefing=read_briefing(world.document),
        rules=read_world(world.document),
    )


def download_headers(head: Head, writer: Writer) -> dict[str, str]:
    """
    파일로 내려받게 하는 머리말. 이름은 세션의 제목이다.

    filename* 은 UTF-8 로 적은 이름이다(RFC 6266). 한글 제목을 그대로 싣는다. 읽지 못하는 쪽은 filename 을 쓴다.
    nosniff 는 브라우저가 글을 다른 종류로 짐작해 실행하지 않게 한다.
    """
    named = quote(f'{head.title}.{writer.extension}', safe='')
    fallback = f'{FALLBACK_NAME}.{writer.extension}'
    return {
        'Content-Disposition': f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{named}',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
    }


@router.get(
    '/{conversation_id}/transcript',
    status_code=status.HTTP_200_OK,
    response_class=Response,
    dependencies=[TRANSCRIPT_LIMIT],
    responses={200: {'content': {'text/markdown': {}, 'text/html': {}, 'text/plain': {}}}},
)
async def download_transcript(
    conversation_id: uuid.UUID,
    viewer: CurrentViewer,
    session: Session,
    now: Now,
    chosen: Format = TranscriptFormat.MARKDOWN,
) -> Response:
    """내 세션의 기록. 지금 보고 있는 가지의 말들이다. 없거나 볼 수 없는 세션이면 404."""
    row = await service.get_conversation(session, viewer, conversation_id)
    persona = await service.conversation_persona(session, row[0])
    messages = await service.conversation_messages(session, row[0])
    head = head_of(row, persona, messages)
    writer = WRITERS[chosen]
    body = writer.render(head, transcript_blocks(head, messages), now)
    return Response(body, media_type=writer.media_type, headers=download_headers(head, writer))
