# trpg-server/app/transcripts/router.py

"""
기록 내려받기 API(#403, #617). 한 판의 공개된 기록과 받는 사람의 채팅, 쪽지를 파일 하나로 흘려 보낸다.

  - GET /tables/{table_id}/transcript: 앉은 사람. 받기 시작한 때까지
  - GET /tables/past/{table_id}/transcript: 떠난 사람. 떠난 때까지(app/tables/past_router.py 와 같은 범위)
형식은 format 으로 고른다(md 기본, html, txt, app/transcripts/formats.py).

테이블의 길(/tables/{table_id})보다 먼저 등록한다(app/main.py). past 를 테이블의 id 로 읽지 않게 한다.
받을 수 있는지는 응답을 시작하기 전에 짧은 세션으로 본다. 시작한 뒤에는 404 를 줄 수 없다.
한 사람이 받는 수를 센다(limits.transcript). 넘으면 429 다. 앉지 않은 사람의 요청도 센다(테이블을 찾아다니지 못하게).
요청의 세션(Session)은 쓰지 않는다. 그 세션은 응답이 끝날 때까지 열려 있어서, 보내는 내내 연결을 붙잡는다.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.limits.routing import Limited
from app.limits.setup import Limiting
from app.transcripts import reading
from app.transcripts.formats import WRITERS, TranscriptFormat, Writer
from app.transcripts.reading import Cut

router = APIRouter(prefix='/tables', tags=['transcripts'])

# 이름에 쓸 수 없는 글자를 고르지 않아도 되게, 머리말의 기본 이름은 글자 하나 없이 둔다. 제목은 filename* 에 싣는다
FALLBACK_NAME = 'transcript'

CutReader = Callable[[AsyncSession, uuid.UUID, uuid.UUID], Awaitable[Cut]]
# 형식을 고르는 칸. 보내지 않으면 마크다운이다
Format = Annotated[TranscriptFormat, Query(alias='format')]


def download_headers(cut: Cut, writer: Writer) -> dict[str, str]:
    """
    파일로 내려받게 하는 머리말. 이름은 테이블의 제목이다.

    filename* 은 UTF-8 로 적은 이름이다(RFC 6266). 한글 제목을 그대로 싣는다. 읽지 못하는 쪽은 filename 을 쓴다.
    nosniff 는 브라우저가 글을 다른 종류로 짐작해 실행하지 않게 한다.
    """
    named = quote(f'{cut.title}.{writer.extension}', safe='')
    fallback = f'{FALLBACK_NAME}.{writer.extension}'
    return {
        'Content-Disposition': f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{named}',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
    }


async def open_transcript(
    request: Request,
    limiting: Limiting,
    read_cut: CutReader,
    user_id: uuid.UUID,
    table_id: uuid.UUID,
    chosen: TranscriptFormat,
) -> StreamingResponse:
    """받는 수를 세고(넘으면 429), 받을 범위를 보고(없으면 404), 그 범위의 기록을 고른 형식으로 흘려 보낸다."""
    await limiting.limiter.count_attempt(limiting.limits.transcript, str(user_id))
    state = request.app.state
    async with state.session_factory() as session:
        cut = await read_cut(session, user_id, table_id)
    writer = WRITERS[chosen]
    chunks = writer.render(cut, reading.iter_items(state.session_factory, cut))
    return StreamingResponse(chunks, media_type=writer.media_type, headers=download_headers(cut, writer))


@router.get('/past/{table_id}/transcript', status_code=status.HTTP_200_OK, response_class=StreamingResponse)
async def download_past_transcript(
    table_id: uuid.UUID,
    user: CurrentUser,
    request: Request,
    limiting: Limited,
    chosen: Format = TranscriptFormat.MARKDOWN,
) -> StreamingResponse:
    """떠난 테이블의 기록. 떠났다는 이벤트까지다. 떠난 적이 없으면 404."""
    return await open_transcript(request, limiting, reading.departed_cut, user.user_id, table_id, chosen)


@router.get('/{table_id}/transcript', status_code=status.HTTP_200_OK, response_class=StreamingResponse)
async def download_transcript(
    table_id: uuid.UUID,
    user: CurrentUser,
    request: Request,
    limiting: Limited,
    chosen: Format = TranscriptFormat.MARKDOWN,
) -> StreamingResponse:
    """앉아 있는 테이블의 기록. 받기 시작한 때의 마지막 이벤트까지다. 앉지 않았으면 404."""
    return await open_transcript(request, limiting, reading.seated_cut, user.user_id, table_id, chosen)
