# chat-server/tests/test_withdrawal.py

"""
인증 서버가 탈퇴를 알리는 주소(app/withdrawal/, #670)를 검증한다. 실제 DB(chat_test)에서 돈다.
asset 서버, 결제 서버, 모델은 가짜다.

보는 것.
  - 그 사람의 대화(지운 것으로 적어 둔 것까지)와 딸린 것(말, 상태, 요약, 기억 메모, 페르소나의 사본),
    캐릭터의 판의 사본을 지운다. 남의 것은 남는다
  - 청구 기록은 남는다. 대화와 말을 가리키는 칸만 비고, 공개 ID 와 모델, 토큰 수, 청구 상태는 그대로다
  - 같은 알림이 다시 와도, 이 서버에 그 사람의 것이 없어도 200 processed 다
  - 인증 서버의 서명이 아니면(없음, 틀림, 다른 주소의 서명, 비밀이 빔) 401 이고 아무것도 지우지 않는다
  - 본문의 모양이 틀리면 422 이고 아무것도 지우지 않는다. 모르는 칸은 버린다
  - 연 이벤트 씬의 기록(#669)도 지운다. 남의 것은 남는다
  - 짧은 비밀은 설정이 받지 않는다
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient, Response
from pydantic import ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, sign
from server_core.testing.tokens import FakeAuthServer, SigningKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.conversations.models import Conversation, ConversationPersona, ImportedCharacter, Message
from app.gallery.models import SceneUnlock
from app.main import API_PREFIX, create_app
from app.memory.models import MemoryNote, Summary
from app.turns.models import Generation
from app.world.models import MessageState
from tests.assets import FakeAsset, make_character, make_persona
from tests.conftest import TEST_AUTH_SECRET, make_client, make_test_settings
from tests.models import FakeRouter, ScriptedProvider
from tests.turns import CONVERSATIONS_URL, ME, bearer, turn_on_luna

pytestmark = pytest.mark.usefixtures('clean_tables')

LEAVER = ME
STAYER = uuid.UUID('99999999-2222-4333-8444-555555555555')
PROCESSED = {'status': 'processed'}
BODY = b'{"withdrawn_at": "2026-10-28T03:00:00Z"}'


def withdrawal_path(public_id: uuid.UUID) -> str:
    """인증 서버가 탈퇴를 알리는 주소."""
    return f'{API_PREFIX}/service/users/{public_id}/withdrawal'


async def notify(
    client: AsyncClient,
    public_id: uuid.UUID,
    body: bytes = BODY,
    *,
    secret: str = TEST_AUTH_SECRET,
    signed_as: str | None = None,
) -> Response:
    """인증 서버처럼 서명해 탈퇴를 알린다. signed_as 를 주면 그 주소로 서명한다(가로챈 서명)."""
    path = withdrawal_path(public_id)
    signature = sign(secret, int(time.time()), 'POST', signed_as or path, body)
    headers = {SIGNATURE_HEADER: signature, 'Content-Type': 'application/json'}
    return await client.post(path, content=body, headers=headers)


@pytest.fixture
def router(app: FastAPI) -> FakeRouter:
    fake = FakeRouter(ScriptedProvider(pieces=['응.']))
    app.state.model_router = fake
    return fake


async def converse(client: AsyncClient, app: FastAPI, asset: FakeAsset, headers: dict) -> dict:
    """페르소나를 골라 대화를 열고, 말을 한 번 주고받고, 기억 메모를 하나 적는다. 청구 기록이 하나 생긴다."""
    character = asset.add_character(make_character())
    persona = asset.add_persona(make_persona())
    body = {'character_id': str(character.id), 'persona_id': str(persona.id), 'model': 'luna'}
    started = await client.post(CONVERSATIONS_URL, json=body, headers=headers)
    assert started.status_code == status.HTTP_201_CREATED, started.text
    conversation = started.json()
    url = f'{CONVERSATIONS_URL}/{conversation["id"]}/messages'
    response = await client.post(url, json={'content': '안녕'}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    await asyncio.gather(*list(app.state.turns))
    notes = f'{CONVERSATIONS_URL}/{conversation["id"]}/notes'
    note = await client.post(notes, json={'text': '비를 좋아한다.'}, headers=headers)
    assert note.status_code == status.HTTP_201_CREATED, note.text
    return conversation


async def attach_state_and_summary(session: AsyncSession, conversation_id: str) -> None:
    """대화의 첫 말에 상태와 요약을 붙인다(이동과 요약을 돌리지 않고 행만 만든다)."""
    first = await session.scalar(
        select(Message.id).where(Message.conversation_id == uuid.UUID(conversation_id)).order_by(Message.created_at)
    )
    session.add(MessageState(message_id=first, minutes=0, inventory=[], visited=[]))
    session.add(Summary(message_id=first, conversation_id=uuid.UUID(conversation_id), text='처음.', model_slug='luna'))
    await session.commit()


@pytest.fixture
async def talks(
    session: AsyncSession, client: AsyncClient, app: FastAPI, asset: FakeAsset, signing_key: SigningKey, router
) -> dict:
    """떠나는 사람은 대화 둘(하나는 지운 것으로 적었다), 남는 사람은 대화 하나. 모두 말을 한 번 주고받았다."""
    await turn_on_luna(session)
    leaving = [await converse(client, app, asset, bearer(signing_key, LEAVER)) for _ in range(2)]
    staying = await converse(client, app, asset, bearer(signing_key, STAYER))
    for conversation in (*leaving, staying):
        await attach_state_and_summary(session, conversation['id'])
    await client.delete(f'{CONVERSATIONS_URL}/{leaving[1]["id"]}', headers=bearer(signing_key, LEAVER))
    return {'leaving': leaving, 'staying': staying}


async def count(session: AsyncSession, model, *where) -> int:
    return await session.scalar(select(func.count()).select_from(model).where(*where))


async def counts(session: AsyncSession) -> dict[str, int]:
    """표마다의 행 수. 지우지 않았는지 볼 때 쓴다."""
    tables = {
        'conversations': Conversation,
        'messages': Message,
        'states': MessageState,
        'summaries': Summary,
        'notes': MemoryNote,
        'personas': ConversationPersona,
        'characters': ImportedCharacter,
        'generations': Generation,
    }
    return {name: await count(session, model) for name, model in tables.items()}


# --- 지우기 ---


async def test_the_leavers_conversations_and_everything_on_them_are_erased(
    client: AsyncClient, session: AsyncSession, talks: dict
):
    response = await notify(client, LEAVER)

    assert (response.status_code, response.json()) == (status.HTTP_200_OK, PROCESSED)
    assert await count(session, Conversation, Conversation.owner_id == LEAVER) == 0
    assert await count(session, ImportedCharacter, ImportedCharacter.owner_id == LEAVER) == 0
    # 남는 사람의 대화 하나와 그 위의 것만 남는다
    staying = uuid.UUID(talks['staying']['id'])
    remaining = await counts(session)
    expected = {'conversations': 1, 'states': 1, 'summaries': 1, 'notes': 1, 'personas': 1, 'characters': 1}
    assert remaining == {**remaining, **expected}
    assert await count(session, Message, Message.conversation_id != staying) == 0
    assert await count(session, ConversationPersona, ConversationPersona.conversation_id == staying) == 1


async def test_billing_records_stay_without_the_conversation(client: AsyncClient, session: AsyncSession, talks: dict):
    before = (await session.execute(select(Generation).where(Generation.owner_id == LEAVER))).scalars().all()
    kept = {(row.id, row.model_slug, row.reference, row.billing_status, row.input_tokens) for row in before}
    session.expunge_all()

    await notify(client, LEAVER)

    after = (await session.execute(select(Generation).where(Generation.owner_id == LEAVER))).scalars().all()
    assert len(after) == 2
    assert {(row.id, row.model_slug, row.reference, row.billing_status, row.input_tokens) for row in after} == kept
    assert {(row.conversation_id, row.parent_id, row.message_id) for row in after} == {(None, None, None)}
    # 남는 사람의 기록은 대화를 가리킨 그대로다
    theirs = await session.scalar(select(Generation).where(Generation.owner_id == STAYER))
    assert (theirs.conversation_id, theirs.parent_id is not None) == (uuid.UUID(talks['staying']['id']), True)


async def test_a_repeated_notice_and_an_unknown_user_are_processed(
    client: AsyncClient, session: AsyncSession, talks: dict
):
    first = await notify(client, LEAVER)
    after_first = await counts(session)

    again = await notify(client, LEAVER)
    stranger = await notify(client, uuid.uuid4())

    assert [r.status_code for r in (first, again, stranger)] == [status.HTTP_200_OK] * 3
    assert again.json() == stranger.json() == PROCESSED
    assert await counts(session) == after_first


async def test_the_staying_user_still_talks(
    client: AsyncClient, app: FastAPI, session: AsyncSession, signing_key: SigningKey, talks: dict
):
    await notify(client, LEAVER)

    url = f'{CONVERSATIONS_URL}/{talks["staying"]["id"]}'
    read = await client.get(url, headers=bearer(signing_key, STAYER))

    assert read.status_code == status.HTTP_200_OK
    assert [message['role'] for message in read.json()['messages']] == ['assistant', 'user', 'assistant']


# --- 서명 ---


@pytest.mark.parametrize(
    'secret',
    ['wrong-auth-secret-0123456789abcdef', 'test-chat-secret-0123456789abcdef'],
    ids=['wrong', 'another_servers'],
)
async def test_a_notice_signed_with_another_secret_is_refused(
    client: AsyncClient, session: AsyncSession, talks: dict, secret: str
):
    before = await counts(session)

    response = await notify(client, LEAVER, secret=secret)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await counts(session) == before


async def test_an_unsigned_notice_is_refused(client: AsyncClient, session: AsyncSession, talks: dict):
    before = await counts(session)

    response = await client.post(withdrawal_path(LEAVER), content=BODY, headers={'Content-Type': 'application/json'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await counts(session) == before


async def test_a_signature_for_someone_else_is_refused(client: AsyncClient, session: AsyncSession, talks: dict):
    before = await counts(session)

    response = await notify(client, LEAVER, signed_as=withdrawal_path(STAYER))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await counts(session) == before


@pytest.fixture
async def closed_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """인증 서버의 비밀을 적지 않은 앱. 탈퇴 알림을 하나도 받지 않는다."""
    app = create_app(make_test_settings(auth_server_secret=''), http_client=auth_server.make_client(), engine=engine)
    yield app
    await app.state.http_client.aclose()


async def test_without_a_secret_no_notice_is_received(closed_app: FastAPI, session: AsyncSession, talks: dict):
    before = await counts(session)

    async with make_client(closed_app) as client:
        response = await notify(client, LEAVER)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert await counts(session) == before


async def test_a_large_body_is_refused_before_the_signature(client: AsyncClient):
    response = await notify(client, LEAVER, body=b'{"withdrawn_at": "' + b'x' * 20_000 + b'"}')

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


# --- 본문 ---


@pytest.mark.parametrize('body', [b'{}', b'{"withdrawn_at": "yesterday"}', b'not json'])
async def test_a_malformed_notice_is_422_and_erases_nothing(
    client: AsyncClient, session: AsyncSession, talks: dict, body: bytes
):
    before = await counts(session)

    response = await notify(client, LEAVER, body=body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await counts(session) == before


async def test_unknown_fields_are_ignored(client: AsyncClient, session: AsyncSession, talks: dict):
    response = await notify(client, LEAVER, body=b'{"withdrawn_at": "2026-10-28T03:00:00Z", "reason": "user"}')

    assert response.status_code == status.HTTP_200_OK
    assert await count(session, Conversation, Conversation.owner_id == LEAVER) == 0


# --- 설정 ---


def test_a_short_auth_server_secret_is_refused():
    with pytest.raises(ValidationError, match='AUTH_SERVER_SECRET'):
        make_test_settings(auth_server_secret='short')


async def test_a_conversation_marked_deleted_is_erased_too(client: AsyncClient, session: AsyncSession, talks: dict):
    deleted = uuid.UUID(talks['leaving'][1]['id'])
    assert await session.scalar(select(Conversation.deleted_at).where(Conversation.id == deleted)) is not None

    await notify(client, LEAVER)

    assert await session.get(Conversation, deleted) is None
    # 지운 것으로 적어 둔 대화의 기록도 대화와 끊겨 남는다
    assert await count(session, Generation, Generation.conversation_id == deleted) == 0
    assert await count(session, Generation, Generation.owner_id == LEAVER) == 2


async def test_the_leavers_unlocked_event_scenes_are_erased(client: AsyncClient, session: AsyncSession):
    character = uuid.uuid4()
    for owner in (LEAVER, STAYER):
        session.add(SceneUnlock(owner_id=owner, character_source=character, scene_id='first-date'))
    await session.commit()

    response = await notify(client, LEAVER)

    assert response.status_code == status.HTTP_200_OK
    owners = (await session.scalars(select(SceneUnlock.owner_id))).all()
    assert owners == [STAYER]
