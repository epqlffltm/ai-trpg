# trpg-server/tests/test_signed_signals.py

"""
실시간 신호의 서명(#75, app/realtime/signing.py).

같은 DB 에 붙은 다른 계정이 NOTIFY 로 신호를 꾸며 보내도 스트림에 닿지 않는지 본다.
꾸며 보내는 쪽은 앱의 세션을 거치지 않고 asyncpg 로 직접 맺은 연결이다. 다른 계정의 연결과 같다.
"""

import asyncio
import json
import logging
import uuid

import asyncpg
import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import SecretStr, ValidationError
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import API_PREFIX
from app.realtime import listener, signals
from app.realtime.service import Cursor
from app.realtime.signals import Kind, Signal
from app.realtime.signing import BAD_SIGNATURE_ERROR_CODE, SignalSigner, signer_from
from tests.conftest import make_test_settings
from tests.narration_model import with_model
from tests.sheets import SHEET

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
TABLE = uuid.UUID('aaaaaaaa-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.']
KEY = b'k' * 32
OTHER_KEY = b'o' * 32
LONG_SECRET = 's' * 32
PAYLOAD = f'{TABLE}:events'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 테이블을 여는 방장이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


async def open_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 연다. 이벤트가 둘(만들어짐, 들어옴) 적혀 있다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=with_model(body), headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    response = await client.post(TABLES_URL, json=body, headers=me)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    table = response.json()
    joined = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    assert joined.status_code == status.HTTP_200_OK, joined.text
    return table


async def notify_directly(app: FastAPI, payload: str) -> None:
    """앱을 거치지 않고 이 스키마의 채널로 글자를 보낸다. 같은 DB 에 붙은 다른 계정이 하는 일이다."""
    settings = app.state.settings
    connection = await asyncpg.connect(listener.listen_dsn(settings))
    try:
        await connection.execute('SELECT pg_notify($1, $2)', signals.channel_name(settings.db_schema), payload)
    finally:
        await connection.close()


def typing_of(table: dict, user_id: uuid.UUID) -> str:
    """이 테이블에서 이 사람이 입력 중이라는 신호의 글자. 서명하지 않은 것이다."""
    return signals.encode(Signal(table_id=uuid.UUID(table['id']), kind=Kind.TYPING, user_id=user_id))


# --- 서명하고 맞춰 보기 ---


def test_a_signed_payload_comes_back_as_it_was():
    signer = SignalSigner(KEY)

    assert signer.verify(signer.sign(PAYLOAD)) == PAYLOAD


def test_a_payload_with_a_colon_in_its_text_comes_back_whole():
    # 서술의 조각은 글에 ':' 가 있을 수 있다. 서명 뒤의 것을 나누지 않는다
    signer = SignalSigner(KEY)
    payload = f'{TABLE}:narration:1:1:0:그가 말했다: "가자."'

    assert signer.verify(signer.sign(payload)) == payload


def test_a_changed_payload_is_refused():
    signer = SignalSigner(KEY)
    signature = signer.sign(PAYLOAD).partition(':')[0]

    assert signer.verify(f'{signature}:{TABLE}:messages') is None


def test_a_payload_signed_with_another_key_is_refused():
    assert SignalSigner(KEY).verify(SignalSigner(OTHER_KEY).sign(PAYLOAD)) is None


@pytest.mark.parametrize(
    'raw',
    [
        PAYLOAD,
        '',
        'no-separator',
        f'{"0" * 63}:{PAYLOAD}',
        f'{"0" * 64}:{PAYLOAD}',
        f'{"가" * 64}:{PAYLOAD}',
    ],
    ids=['unsigned', 'empty', 'no-separator', 'short-signature', 'wrong-signature', 'not-ascii'],
)
def test_what_is_not_signed_by_us_is_refused(raw: str):
    assert SignalSigner(KEY).verify(raw) is None


def test_the_signature_fits_in_a_notify_with_the_longest_piece():
    # NOTIFY 에 실을 수 있는 것은 8000 바이트보다 짧아야 한다. 한 글자가 4 바이트인 글로 가장 긴 조각을 만든다
    piece = signals.NarrationPiece(TABLE, 999_999, 999_999, 999_999, '😀' * signals.MAX_PIECE_CHARS)

    signed = SignalSigner(KEY).sign(signals.encode(piece))

    assert len(signed.encode()) < 8000


# --- 서명자를 만들기 ---


def test_servers_with_the_same_secret_accept_each_others_signals():
    settings = make_test_settings(signal_secret=SecretStr(LONG_SECRET))

    one, another = signer_from(settings), signer_from(settings)

    assert another.verify(one.sign(PAYLOAD)) == PAYLOAD


def test_without_a_secret_each_server_makes_its_own_and_warns(caplog: pytest.LogCaptureFixture):
    settings = make_test_settings(signal_secret=SecretStr(''))

    with caplog.at_level(logging.WARNING):
        one, another = signer_from(settings), signer_from(settings)

    assert one.verify(one.sign(PAYLOAD)) == PAYLOAD
    # 서버가 여럿이면 서로의 신호를 버린다. 그래서 경고를 남긴다
    assert another.verify(one.sign(PAYLOAD)) is None
    assert 'SIGNAL_SECRET' in caplog.text


def test_a_short_secret_does_not_start_the_server():
    with pytest.raises(ValidationError, match='SIGNAL_SECRET'):
        make_test_settings(signal_secret=SecretStr('s' * 31))


def test_a_secret_is_not_shown_in_the_settings():
    settings = make_test_settings(signal_secret=SecretStr(LONG_SECRET))

    assert LONG_SECRET not in repr(settings)


# --- 보내기 ---


async def test_publishing_without_a_signer_fails_loudly(app: FastAPI):
    # 서명 없이 보내면 받는 쪽이 모두 버린다. 조용히 사라지지 않고 바로 드러난다
    bare = async_sessionmaker(app.state.engine)

    async with bare() as session:
        with pytest.raises(RuntimeError, match='서명자'):
            await signals.publish(session, Signal(table_id=TABLE, kind=Kind.EVENTS))


async def test_what_the_server_sends_carries_its_signature(app: FastAPI):
    settings = app.state.settings
    received: asyncio.Queue[str] = asyncio.Queue()
    connection = await asyncpg.connect(listener.listen_dsn(settings))
    try:
        await connection.add_listener(
            signals.channel_name(settings.db_schema), lambda *args: received.put_nowait(args[-1])
        )
        async with app.state.session_factory() as session:
            await signals.publish(session, Signal(table_id=TABLE, kind=Kind.EVENTS))
            await session.commit()
        raw = await asyncio.wait_for(received.get(), timeout=5)
    finally:
        await connection.close()

    assert raw != PAYLOAD
    assert app.state.signal_signer.verify(raw) == PAYLOAD


# --- 받기 ---


@pytest.mark.usefixtures('clean_tables')
async def test_a_forged_signal_does_not_reach_the_stream(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, connect
):
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    # 서명 없이, 또는 다른 비밀로 서명해서 내가 입력 중이라고 꾸민다
    await notify_directly(app, typing_of(table, ME))
    await notify_directly(app, SignalSigner(OTHER_KEY).sign(typing_of(table, ME)))

    assert await reader.is_quiet()


@pytest.mark.usefixtures('clean_tables')
async def test_a_signal_signed_with_the_servers_secret_reaches_the_stream(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, connect
):
    # 위의 테스트가 "아무것도 오지 않았다"로 끝나므로, 같은 길로 서명한 것은 온다는 것을 함께 본다
    table = await open_duo(client, me, friend)
    reader = connect(table, FRIEND, Cursor(events=2))
    await reader.settle()

    await notify_directly(app, app.state.signal_signer.sign(typing_of(table, ME)))

    frame = await reader.next()
    assert frame.event == 'typing'
    assert json.loads(frame.data) == {'user_id': str(ME)}


def test_a_forged_signal_is_logged_without_what_it_carried(app: FastAPI, caplog: pytest.LogCaptureFixture):
    # 꾸민 신호에 무엇이 실렸는지는 남기지 않는다. 서술의 글이 들어 있을 수 있다
    source = listener.PostgresListener(make_test_settings(), app.state.hub, app.state.signal_signer)

    with caplog.at_level(logging.WARNING):
        source._on_notify(None, 4242, 'channel', f'{TABLE}:narration:1:1:0:비밀스러운 서술')

    [record] = [record for record in caplog.records if record.name == listener.__name__]
    assert record.error_code == BAD_SIGNATURE_ERROR_CODE
    assert record.sender_pid == 4242
    assert '비밀스러운' not in caplog.text
