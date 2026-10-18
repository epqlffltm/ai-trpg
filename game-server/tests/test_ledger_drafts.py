# game-server/tests/test_ledger_drafts.py

"""
테이블의 장부 초안: 서술이 끝나면 장면에서 초안을 쓰고 줄로 적는다. 방장이 본다.

넷을 본다.
  - 켜고 끄기: 방장만, 기본은 끔. 바꾼 것은 모두에게 이벤트로 간다.
  - 쓰기: 켠 테이블만, 서술이 끝난 뒤에. 장부(소지품, 퀘스트)는 바꾸지 않는다. 다음 초안이 오면 앞의 것은 만료된다.
  - 실패: 초안을 쓰다 무엇이 실패해도 라운드는 그대로 닫히고, 로그만 남는다.
  - 보기: 방장만 본다. 숨긴 퀘스트가 드러났다는 줄이 있을 수 있다.
그리고 앱이 설정을 보고 초안을 쓸 것을 고르는지 본다.
"""

import logging
import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.fake import FakeCallLog, FakeProvider
from app.drafts.drafting import NO_DRAFTS
from app.drafts.models import DraftStatus, LedgerDraft
from app.drafts.routed_writer import RoutedDraftWriter
from app.drafts.setup import build_drafter
from app.drafts.writer import DraftRequest, DraftWriter
from app.main import create_app
from tests import test_table_quests as quest_tables
from tests.conftest import make_test_settings
from tests.logs import rendered
from tests.sheets import SHEET
from tests.test_table_items import (
    ME,
    RULEBOOKS_URL,
    SCENARIOS_URL,
    TABLES_URL,
    events_of,
    held,
    post,
    read_table,
    table_url,
)
from tests.test_table_quests import declare_both, start_duo

pytestmark = pytest.mark.usefixtures('clean_tables')

# 퀘스트 테스트의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 사건과 물건이 든 로어북,
# 테이블에 앉지 않는 사람
me = quest_tables.me
friend = quest_tables.friend
lore = quest_tables.lore
stranger = quest_tables.stranger

# 기사(p1)가 치유 물약(i1) 둘을 손에 넣었고, 왕녀 구출(q1)을 이뤘다는 초안. 없는 캐릭터(p9)의 줄은 서버가 버린다
REPLY = (
    '{"found_items": [{"character": "p1", "item": "i1", "count": 2}, {"character": "p9", "item": "i1", "count": 1}], '
    '"quest_changes": [{"quest": "q1", "status": "succeeded"}]}'
)


@pytest.fixture
def provider(app: FastAPI) -> FakeProvider:
    """앱에 꽂은, 정해 둔 초안을 쓰는 모델. 받은 요청이 쌓인다."""
    fake = FakeProvider(reply=REPLY)
    app.state.drafter = DraftWriter(fake, FakeCallLog())
    return fake


async def switch(client: AsyncClient, headers: dict, table: dict, on: bool):
    """장부 초안을 켜거나 끄는 요청. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, '/ledger-drafts'), json={'ledger_drafts': on}, headers=headers)


async def drafts_of(client: AsyncClient, headers: dict, table: dict):
    """기다리는 줄들을 읽는 요청. 응답을 그대로 돌려준다."""
    return await client.get(table_url(table, '/ledger-drafts'), headers=headers)


async def play_round(client: AsyncClient, me: dict, friend: dict, table: dict, narrated) -> None:
    """둘 다 선언해 라운드를 닫고, 서술과 그 뒤의 초안까지 끝나기를 기다린다."""
    await declare_both(client, me, friend, table)
    await narrated()


async def statuses(session: AsyncSession, table: dict) -> list[tuple[int, str]]:
    """테이블의 줄들의 (라운드, 처지). 라운드와 쓴 순서다."""
    query = (
        select(LedgerDraft.round_number, LedgerDraft.status)
        .where(LedgerDraft.table_id == uuid.UUID(table['id']))
        .order_by(LedgerDraft.round_number, LedgerDraft.position)
    )
    return [(number, status) for number, status in (await session.execute(query)).all()]


# --- 켜고 끄기 ---


async def test_drafts_are_off_by_default_and_the_host_turns_them_on(
    client: AsyncClient, me: dict, friend: dict, lore: dict
):
    table = await start_duo(client, me, friend, lore)
    assert table['ledger_drafts'] is False

    response = await switch(client, me, table, True)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['ledger_drafts'] is True
    # 초안은 방장만 보지만, 켜고 끈 것은 모두가 안다
    [event] = await events_of(client, friend, table, 'ledger_drafts_changed')
    assert event['payload'] == {'ledger_drafts': True}


async def test_switching_to_the_same_value_records_nothing(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    response = await switch(client, me, table, False)

    assert response.status_code == status.HTTP_200_OK
    assert await events_of(client, me, table, 'ledger_drafts_changed') == []


async def test_only_the_host_switches_drafts(client: AsyncClient, me: dict, friend: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    assert (await switch(client, friend, table, True)).status_code == status.HTTP_403_FORBIDDEN
    await client.post(table_url(table, '/end'), headers=me)
    ended = await switch(client, me, table, True)
    assert (ended.status_code, ended.json()['reason']) == (status.HTTP_409_CONFLICT, 'already_ended')


async def test_a_table_can_be_made_with_drafts_on(client: AsyncClient, me: dict):
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    body = {'title': '왕녀의 모험', 'rulebook_id': rulebook['id'], 'openings': ['성문 앞이다.'], 'default_sheet': SHEET}
    scenario = await post(client, SCENARIOS_URL, me, **body)
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)

    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2, ledger_drafts=True)

    assert table['ledger_drafts'] is True


# --- 쓰기 ---


async def test_the_scene_is_drafted_after_narration_without_touching_the_ledger(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider: FakeProvider, narrated
):
    table = await start_duo(client, me, friend, lore)
    await switch(client, me, table, True)

    await play_round(client, me, friend, table, narrated)

    # 방금 쓴 장면과 테이블의 목록으로 부른다
    [call] = provider.calls
    assert '- p1: 기사' in call.messages[1].content
    assert '- q1: 왕녀 구출 (진행 중)' in call.messages[1].content
    response = await drafts_of(client, me, table)
    assert response.status_code == status.HTTP_200_OK, response.text
    found, quest = response.json()['items']
    assert {key: found[key] for key in ('kind', 'round', 'user_id', 'character_name', 'name', 'count')} == {
        'kind': 'found_item',
        'round': 1,
        'user_id': str(ME),
        'character_name': '기사',
        'name': '치유 물약',
        'count': 2,
    }
    assert found['entry_id'] == lore['potion']['id']
    assert {key: quest[key] for key in ('kind', 'round', 'entry_id', 'name', 'previous', 'status')} == {
        'kind': 'quest_change',
        'round': 1,
        'entry_id': lore['rescue']['id'],
        'name': '왕녀 구출',
        'previous': 'active',
        'status': 'succeeded',
    }
    # AI 는 장부를 바꾸지 못한다. 방장이 받아들이기 전에는 그대로다
    detail = await read_table(client, me, table)
    assert held(detail, ME) == []
    assert quest_tables.quests_in(detail)[0] == ('왕녀 구출', 'active')


async def test_a_table_with_drafts_off_calls_nobody(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider: FakeProvider, narrated
):
    table = await start_duo(client, me, friend, lore)

    await play_round(client, me, friend, table, narrated)

    assert provider.calls == []
    assert (await drafts_of(client, me, table)).json()['items'] == []


async def test_the_next_drafts_expire_the_undecided_ones(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider: FakeProvider, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend, lore)
    await switch(client, me, table, True)
    await play_round(client, me, friend, table, narrated)

    # 다음 라운드의 모델은 아무 일도 없었다고 쓴다. 그래도 앞의 줄은 낡았다
    provider.reply = '{}'
    await play_round(client, me, friend, table, narrated)

    assert await statuses(session, table) == [(1, DraftStatus.EXPIRED), (1, DraftStatus.EXPIRED)]
    assert (await drafts_of(client, me, table)).json()['items'] == []


async def test_an_unreadable_draft_leaves_no_line_but_the_round_goes_on(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider: FakeProvider, narrated
):
    table = await start_duo(client, me, friend, lore)
    await switch(client, me, table, True)
    provider.reply = '기사가 물약을 찾았다.'

    await play_round(client, me, friend, table, narrated)

    assert (await drafts_of(client, me, table)).json()['items'] == []
    assert (await read_table(client, me, table))['quests'][0]['status'] == 'active'


class BrokenDrafter:
    """초안을 쓰다 예외(버그)를 내는 것."""

    async def draft(self, request: DraftRequest):
        raise RuntimeError('버그')


async def test_a_failing_drafter_is_logged_and_the_round_stays_closed(
    client: AsyncClient,
    app: FastAPI,
    me: dict,
    friend: dict,
    lore: dict,
    narrated,
    caplog: pytest.LogCaptureFixture,
):
    table = await start_duo(client, me, friend, lore)
    await switch(client, me, table, True)
    app.state.drafter = BrokenDrafter()

    with caplog.at_level(logging.WARNING, logger='app.drafts.drafting'):
        await play_round(client, me, friend, table, narrated)

    [line] = rendered(caplog.records, 'app.drafts.drafting')
    assert (line['level'], line['operation'], line['error_code']) == (
        'warning',
        'ledger_draft.write',
        'ledger_draft.failed',
    )
    # 서술은 끝났다. 다음 라운드가 열려 있다
    current = await client.get(table_url(table, '/rounds/current'), headers=me)
    assert current.json()['number'] == 2


# --- 보기 ---


async def test_only_the_host_reads_the_drafts(client: AsyncClient, me: dict, friend: dict, stranger: dict, lore: dict):
    table = await start_duo(client, me, friend, lore)

    assert (await drafts_of(client, friend, table)).status_code == status.HTTP_403_FORBIDDEN
    assert (await drafts_of(client, stranger, table)).status_code == status.HTTP_404_NOT_FOUND


# --- 앱의 설정 ---


def test_the_fake_narrator_drafts_nothing():
    app = create_app(make_test_settings())

    assert build_drafter(make_test_settings(), app.state.model_router, async_sessionmaker()) is NO_DRAFTS
    assert app.state.drafter is NO_DRAFTS


def test_the_language_model_drafts_with_the_first_standard_model():
    settings = make_test_settings(
        narrator='llm', llm_model='gemma4:26b', llm_fallback_models='qwen3.6:27b', ai_log_hmac_key='server-key'
    )
    app = create_app(settings)

    drafter = app.state.drafter

    # 장면을 쓴 모델과 같은 것으로, 같은 기록장에, 같은 키로 서명한다. 넘어갈 모델은 쓰지 않는다.
    # 창구는 서술자와 같은 것이 부를 때마다 고른다
    assert isinstance(drafter, RoutedDraftWriter)
    assert drafter.model == 'gemma4:26b'
    assert drafter.router is app.state.model_router
    assert isinstance(drafter.log, DbCallLog)
    assert drafter.log.session_factory is app.state.session_factory
    assert drafter.digest_key == settings.digest_key()


@pytest.mark.parametrize(
    ('draft_model', 'expected'), [('gemini-3-1-flash-lite', 'gemini-3-1-flash-lite'), ('  ', 'gemma4:26b')]
)
def test_the_drafts_have_their_own_model(draft_model: str, expected: str):
    settings = make_test_settings(narrator='llm', llm_model='gemma4:26b', draft_model=draft_model)

    drafter = build_drafter(settings, create_app(settings).state.model_router, async_sessionmaker())

    # 장부 초안은 청구하지 않는 호출이다. 서술의 기본 모델과 따로 싼 모델로 둘 수 있다. 비우면 서술의 첫 모델이다
    assert drafter.model == expected
