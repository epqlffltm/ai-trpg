# trpg-server/tests/test_withdrawal.py

"""
인증 서버가 탈퇴를 알리는 주소(app/withdrawal/)를 검증한다. 실제 DB(game_test)에서 돈다.

보는 것.
  - 서명: 인증 서버의 비밀로 서명한 것만 받는다. 없음, 틀림, 오래됨, 남의 주소, 비밀이 빔은 401 이고
    아무것도 하지 않는다.
    본문이 크면 413, 모양이 틀리면 422 다. 모르는 칸은 버린다
  - 정리: 보관함을 지우고, 시나리오의 공개를 내리고(시나리오와 판은 남는다), 보내지 않은 알림을 지운다.
    남의 것은 그대로다
  - 테이블: 모집 중, 진행 중인 테이블에서 나간다(방장이면 넘기고, 혼자면 끝낸다). 끝난 테이블의 자리는 남긴다.
    진행 중인 테이블은 계속 돈다
  - 같은 알림이 다시 와도 200 processed 이고 이벤트가 더 적히지 않는다. 이 서버에 아무것도 없는 사람도 200 이다
"""

import time
import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient, Response
from server_core.service_auth.signing import SIGNATURE_HEADER, TOLERANCE_SECONDS, sign
from server_core.testing.tokens import FakeAuthServer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.assets.models import Asset
from app.core.service_auth import BODY_MAX_BYTES
from app.listings.models import Listing
from app.main import API_PREFIX, create_app
from app.notifications.models import OutgoingNotification
from app.personas.models import Persona
from app.tables import repository as tables
from app.tables import service as seating
from app.tables.models import GameTable, TableMember, TableStatus
from tests import test_events_api as event_tests
from tests import test_listings_api as listing_tests
from tests.conftest import TEST_AUTH_SECRET, make_client, make_test_settings
from tests.test_events_api import FRIEND, ME, join, open_table, read_events, start_duo, table_url, types

pytestmark = pytest.mark.usefixtures('clean_tables')

me = event_tests.me
friend = event_tests.friend
third = event_tests.third

PROCESSED = {'status': 'processed'}
NOTICE = b'{"withdrawn_at": "2026-10-28T03:00:00Z"}'
BAD_SIGNATURE = {'detail': '요청의 서명이 맞지 않습니다.'}


def withdrawal_path(user_id: uuid.UUID | str) -> str:
    return f'{API_PREFIX}/service/users/{user_id}/withdrawal'


async def notify(
    client: AsyncClient,
    user_id: uuid.UUID | str,
    body: bytes = NOTICE,
    *,
    secret: str = TEST_AUTH_SECRET,
    sent_at: int | None = None,
    signed_as: str | None = None,
) -> Response:
    """인증 서버처럼 서명해 탈퇴를 알린다. 한 번 만든 바이트에 서명하고 그것을 보낸다."""
    path = withdrawal_path(user_id)
    when = sent_at if sent_at is not None else int(time.time())
    signature = sign(secret, when, 'POST', signed_as or path, body)
    return await client.post(path, content=body, headers={SIGNATURE_HEADER: signature})


async def make_persona(client: AsyncClient, headers: dict) -> None:
    response = await client.post(f'{API_PREFIX}/personas', json={'name': '엘프'}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text


async def personas_of(session: AsyncSession, owner_id: uuid.UUID) -> int:
    return await session.scalar(select(func.count()).select_from(Persona).where(Persona.owner_id == owner_id))


async def listing_of(session: AsyncSession, scenario: dict) -> tuple:
    """공개 중인 판, 공개한 시각, 한줄소개."""
    query = select(Listing.version_id, Listing.published_at, Listing.tagline).where(
        Listing.scenario_id == uuid.UUID(scenario['id'])
    )
    return tuple((await session.execute(query)).one())


async def queue_notification(session: AsyncSession, user_id: uuid.UUID) -> None:
    session.add(OutgoingNotification(source_key=f'test:{uuid.uuid4()}', user_id=user_id, kind='test.kind', payload={}))
    await session.commit()


async def queued_for(session: AsyncSession, user_id: uuid.UUID) -> int:
    query = select(func.count()).select_from(OutgoingNotification).where(OutgoingNotification.user_id == user_id)
    return await session.scalar(query)


async def stored_table(session: AsyncSession, table: dict) -> tuple[GameTable, set[uuid.UUID]]:
    session.expire_all()
    found = await session.get(GameTable, uuid.UUID(table['id']))
    members = await session.scalars(select(TableMember.user_id).where(TableMember.table_id == found.id))
    return found, set(members)


# --- 서명 ---


async def test_a_signed_notice_is_processed(client: AsyncClient):
    response = await notify(client, ME)

    assert (response.status_code, response.json()) == (status.HTTP_200_OK, PROCESSED)


@pytest.mark.parametrize(
    'wrong',
    [
        {'secret': 'a-different-secret-0123456789abcdef'},
        {'sent_at': int(time.time()) - TOLERANCE_SECONDS - 60},
        {'signed_as': withdrawal_path(FRIEND)},
    ],
    ids=['wrong-secret', 'too-old', 'another-path'],
)
async def test_refuses_signatures_it_cannot_accept(client: AsyncClient, session: AsyncSession, me: dict, wrong: dict):
    await make_persona(client, me)

    response = await notify(client, ME, **wrong)

    assert (response.status_code, response.json()) == (status.HTTP_401_UNAUTHORIZED, BAD_SIGNATURE)
    assert await personas_of(session, ME) == 1


async def test_without_a_signature_it_is_401(client: AsyncClient):
    response = await client.post(withdrawal_path(ME), content=NOTICE)

    assert (response.status_code, response.json()) == (status.HTTP_401_UNAUTHORIZED, BAD_SIGNATURE)


@pytest.fixture
async def closed_app(auth_server: FakeAuthServer, engine: AsyncEngine) -> AsyncIterator[FastAPI]:
    """인증 서버의 비밀을 적지 않은 앱."""
    app = create_app(make_test_settings(auth_server_secret=''), http_client=auth_server.make_client(), engine=engine)
    yield app
    await app.state.http_client.aclose()


async def test_an_empty_secret_accepts_nothing(closed_app: FastAPI):
    async with make_client(closed_app) as client:
        response = await notify(client, ME, secret='')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_a_body_over_the_limit_is_413(client: AsyncClient):
    body = b'x' * (BODY_MAX_BYTES + 1)

    response = await notify(client, ME, body)

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_a_streamed_body_over_the_limit_is_413_too(client: AsyncClient):
    async def chunks() -> AsyncIterator[bytes]:
        # 길이를 알리지 않고(chunked) 보낸다. 머리말을 믿지 않고 읽으면서 센다
        for _ in range(BODY_MAX_BYTES // 1024 + 1):
            yield b'x' * 1024

    response = await client.post(withdrawal_path(ME), content=chunks())

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


async def test_a_declared_length_over_the_limit_is_413_without_reading(client: AsyncClient):
    headers = {'Content-Length': str(BODY_MAX_BYTES + 1)}

    response = await client.post(withdrawal_path(ME), headers=headers)

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE


@pytest.mark.parametrize(
    'body', [b'{}', b'{"withdrawn_at": "not a time"}', b'not json'], ids=['missing', 'bad', 'junk']
)
async def test_a_bad_body_is_422_and_does_nothing(client: AsyncClient, session: AsyncSession, me: dict, body: bytes):
    await make_persona(client, me)

    response = await notify(client, ME, body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert await personas_of(session, ME) == 1


async def test_unknown_fields_in_the_body_are_ignored(client: AsyncClient, session: AsyncSession, me: dict):
    await make_persona(client, me)

    response = await notify(client, ME, b'{"withdrawn_at": "2026-10-28T03:00:00Z", "reason": "later field"}')

    assert response.status_code == status.HTTP_200_OK
    assert await personas_of(session, ME) == 0


# --- 보관함, 공개, 알림 ---


async def test_erases_personas_and_leaves_others(client: AsyncClient, session: AsyncSession, me: dict, friend: dict):
    await make_persona(client, me)
    await make_persona(client, me)
    await make_persona(client, friend)

    await notify(client, ME)

    assert (await personas_of(session, ME), await personas_of(session, FRIEND)) == (0, 1)


async def test_takes_down_listings_but_keeps_scenarios(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict
):
    mine = await listing_tests.make_public(client, me)
    theirs = await listing_tests.make_public(client, friend)

    await notify(client, ME)

    deleted_at = await session.scalar(select(Asset.deleted_at).where(Asset.id == uuid.UUID(mine['id'])))
    # 소개 페이지의 글과 시나리오는 그대로다. 지운 것으로 적지 않는다
    assert await listing_of(session, mine) == (None, None, listing_tests.TAGLINE)
    assert deleted_at is None
    assert (await listing_of(session, theirs))[0] is not None
    listed = await client.get(listing_tests.LISTINGS_URL)
    assert [item['scenario_id'] for item in listed.json()['items']] == [theirs['id']]


async def test_drops_notifications_not_yet_sent(client: AsyncClient, session: AsyncSession):
    await queue_notification(session, ME)
    await queue_notification(session, FRIEND)

    await notify(client, ME)

    assert (await queued_for(session, ME), await queued_for(session, FRIEND)) == (0, 1)


# --- 테이블 ---


async def test_a_host_leaving_a_recruiting_table_hands_it_over(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict
):
    table = await open_table(client, me)
    await join(client, friend, table)

    await notify(client, ME)

    stored, members = await stored_table(session, table)
    assert members == {FRIEND}
    assert (stored.host_id, stored.status) == (FRIEND, TableStatus.RECRUITING)
    assert types(await read_events(client, friend, table))[-2:] == ['member_left', 'host_changed']


async def test_a_playing_table_goes_on_without_them(client: AsyncClient, session: AsyncSession, me: dict, friend: dict):
    table = await start_duo(client, me, friend)

    await notify(client, FRIEND)

    stored, members = await stored_table(session, table)
    assert members == {ME}
    assert (stored.host_id, stored.status) == (ME, TableStatus.PLAYING)
    assert types(await read_events(client, me, table))[-1] == 'member_left'


async def test_a_table_left_empty_ends(client: AsyncClient, session: AsyncSession, me: dict):
    table = await open_table(client, me)

    await notify(client, ME)

    stored, members = await stored_table(session, table)
    assert (members, stored.status) == (set(), TableStatus.ENDED)


async def test_an_ended_table_keeps_the_seat(client: AsyncClient, session: AsyncSession, me: dict, friend: dict):
    table = await start_duo(client, me, friend)
    ended = await client.post(table_url(table, '/end'), headers=me)
    assert ended.status_code == status.HTTP_200_OK, ended.text
    before = await read_events(client, me, table)

    await notify(client, FRIEND)

    _, members = await stored_table(session, table)
    assert members == {ME, FRIEND}
    assert await read_events(client, me, table) == before


async def test_only_unfinished_tables_of_that_person_are_listed(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict
):
    mine = await open_table(client, me)
    shared = await start_duo(client, me, friend)
    ended = await start_duo(client, me, friend)
    await client.post(table_url(ended, '/end'), headers=me)
    await open_table(client, friend)

    listed = await tables.list_unfinished_seated_ids(session, ME)

    assert set(listed) == {uuid.UUID(mine['id']), uuid.UUID(shared['id'])}


async def test_leaving_skips_an_ended_table_even_if_asked(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict
):
    # 고른 뒤 잠그기 전에 방장이 끝냈을 수 있다. 잠근 뒤에 다시 본다
    table = await start_duo(client, me, friend)
    await client.post(table_url(table, '/end'), headers=me)

    await seating.leave_for_withdrawal(session, FRIEND, uuid.UUID(table['id']))

    _, members = await stored_table(session, table)
    assert members == {ME, FRIEND}


async def test_leaving_a_table_not_seated_does_nothing(client: AsyncClient, session: AsyncSession, me: dict):
    table = await open_table(client, me)

    await seating.leave_for_withdrawal(session, FRIEND, uuid.UUID(table['id']))
    await seating.leave_for_withdrawal(session, FRIEND, uuid.uuid4())

    _, members = await stored_table(session, table)
    assert members == {ME}


async def test_leaves_every_unfinished_table(client: AsyncClient, session: AsyncSession, me: dict, friend: dict):
    tables = [await open_table(client, me), await open_table(client, me)]
    for table in tables:
        await join(client, friend, table)

    await notify(client, FRIEND)

    for table in tables:
        _, members = await stored_table(session, table)
        assert members == {ME}


async def test_the_same_notice_again_changes_nothing(
    client: AsyncClient, session: AsyncSession, me: dict, friend: dict
):
    table = await start_duo(client, me, friend)
    await notify(client, FRIEND)
    after_first = await read_events(client, me, table)

    again = await notify(client, FRIEND)

    assert (again.status_code, again.json()) == (status.HTTP_200_OK, PROCESSED)
    assert await read_events(client, me, table) == after_first


async def test_someone_with_nothing_here_is_processed(client: AsyncClient):
    response = await notify(client, uuid.uuid4())

    assert (response.status_code, response.json()) == (status.HTTP_200_OK, PROCESSED)
