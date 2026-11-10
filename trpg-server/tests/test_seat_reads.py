# trpg-server/tests/test_seat_reads.py

"""
자리만 보면 되는 곳이 테이블을 통째로 읽지 않는 것(#1263)을 검증한다.

판은 스트림의 판이다(tests/test_stream.py). 나(방장)와 친구가 앉은 테이블이다.

보는 것.
  - 스트림이 깨어날 때(read_new) 자리를 쿼리 하나로 본다. 입력 중 신호만 왔으면 그것뿐이다.
    고치기 전에는 테이블과 그 관계를 읽는 12개였다
  - 앉지 않은 사람과 없는 테이블은 None 이고, 끝난 테이블은 상태로 안다
  - 입력 중 알리기와 채팅 읽기도 자리를 쿼리 하나로 본다. 채팅 쓰기는 테이블의 행과 자기 자리의 행만 읽는다
  - 그래도 뜻은 같다: 내보낸 사람에게는 채팅이 가지 않고, 끝난 테이블에는 쓸 수 없다
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.realtime import service as realtime
from app.realtime.service import Closed, Cursor
from app.tables import repository
from app.tables.models import TableStatus
from tests import test_stream as streams

pytestmark = pytest.mark.usefixtures('clean_tables')

me = streams.me
friend = streams.friend


@contextmanager
def statements(app: FastAPI) -> Iterator[list[str]]:
    """그 안에서 DB 에 보낸 SQL 문들. 첫 낱말(SELECT, INSERT …)과 함께 적는다."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    target = app.state.engine.sync_engine
    event.listen(target, 'before_cursor_execute', record)
    try:
        yield seen
    finally:
        event.remove(target, 'before_cursor_execute', record)


def selects(found: list[str]) -> list[str]:
    """읽는 문들. 신호를 보내는 pg_notify 는 뺀다(읽는 것이 아니다)."""
    return [one for one in found if one.lstrip().upper().startswith('SELECT') and 'pg_notify' not in one]


async def seated_table(client: AsyncClient, me: dict, friend: dict) -> dict:
    table = await streams.open_duo(client, me, friend)
    await streams.start(client, me, friend, table)
    return table


async def test_a_waking_stream_checks_the_seat_with_one_query(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    table = await seated_table(client, me, friend)
    table_id = uuid.UUID(table['id'])

    with statements(app) as seen:
        batch = await realtime.read_new(session, streams.ME, table_id, Cursor(), set())

    assert (batch.frames, batch.closed) == ([], None)
    assert len(seen) == 1
    assert 'game_tables' in seen[0] and 'table_members' in seen[0]


async def test_the_seat_says_who_is_not_seated_and_what_ended(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession
):
    table = await seated_table(client, me, friend)
    table_id = uuid.UUID(table['id'])

    seat = await repository.find_seat(session, table_id, streams.ME)
    stranger = await repository.find_seat(session, table_id, uuid.uuid4())
    nowhere = await repository.find_seat(session, uuid.uuid4(), streams.ME)
    ended = await client.post(streams.table_url(table, '/end'), headers=me)
    after = await repository.find_seat(session, table_id, streams.ME)

    assert seat is not None and seat.status == TableStatus.PLAYING
    assert (stranger, nowhere) == (None, None)
    assert ended.status_code == status.HTTP_200_OK, ended.text
    assert after is not None and after.status == TableStatus.ENDED


async def test_a_kicked_person_gets_no_more_from_the_stream(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession
):
    table = await seated_table(client, me, friend)
    kicked = await client.delete(streams.table_url(table, f'/members/{streams.FRIEND}'), headers=me)
    await streams.say(client, me, table, '남은 사람끼리 하자.')

    batch = await realtime.read_new(session, streams.FRIEND, uuid.UUID(table['id']), Cursor(), set(realtime.READ_ORDER))

    assert kicked.status_code == status.HTTP_200_OK, kicked.text
    assert (batch.frames, batch.closed) == ([], Closed.NOT_SEATED)


async def test_typing_and_reading_the_chat_check_the_seat_with_one_query(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    table = await seated_table(client, me, friend)
    await streams.say(client, me, table, streams.HELLO)

    with statements(app) as typing_reads:
        typed = await client.post(streams.table_url(table, '/messages/typing'), headers=me)
    with statements(app) as chat_reads:
        listed = await client.get(streams.table_url(table, '/messages'), headers=friend)

    assert typed.status_code == status.HTTP_204_NO_CONTENT, typed.text
    assert listed.status_code == status.HTTP_200_OK, listed.text
    assert listed.json()['last_sequence'] == 1
    # 입력 중: 자리 하나. 채팅 읽기: 자리 하나와 채팅
    assert len(selects(typing_reads)) == 1
    assert len(selects(chat_reads)) == 2


async def test_writing_to_the_chat_reads_only_the_rows_it_needs(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    table = await seated_table(client, me, friend)

    with statements(app) as seen:
        posted = await client.post(streams.table_url(table, '/messages'), json={'content': '안녕'}, headers=friend)

    assert posted.status_code == status.HTTP_201_CREATED, posted.text
    assert posted.json()['sequence'] == 1
    # 테이블의 행(잠금)과 자기 자리의 행. 쓴 뒤에 쓴 시각을 다시 읽는 것 하나
    tables = [one for one in selects(seen) if 'FROM game_tables' in one]
    assert len(tables) == 1 and 'FOR UPDATE' in tables[0]
    assert len(selects(seen)) == 3


async def test_an_ended_table_takes_no_chat(client: AsyncClient, me: dict, friend: dict):
    table = await seated_table(client, me, friend)
    await client.post(streams.table_url(table, '/end'), headers=me)

    posted = await client.post(streams.table_url(table, '/messages'), json={'content': '끝났나?'}, headers=friend)
    typed = await client.post(streams.table_url(table, '/messages/typing'), headers=friend)

    assert (posted.status_code, typed.status_code) == (status.HTTP_409_CONFLICT, status.HTTP_409_CONFLICT)
