# game-server/tests/test_stale_drafts.py

"""
늦게 도착한 장부 초안을 버리는 규칙(#269)을 검증한다.

초안은 라운드의 서술이 끝나고 다음 라운드가 열린 뒤에 쓴다. 그래서 앞 라운드의 초안이 다음 라운드의 초안보다
늦게 도착할 수 있다. 셋을 본다.
  - 뒤의 라운드가 이미 서술을 마쳤으면 앞 라운드의 초안은 적지 않는다. 새 줄은 그대로 기다린다.
  - 쓰는 사이에 테이블이 끝났거나 방장이 장부 초안을 껐으면 적지 않는다.
  - 만료시키는 것은 적는 라운드보다 앞의 줄만이다.

늦게 도착하는 것은 초안을 적는 함수(save_drafts)를 직접 불러 만든다. 뒤에서 도는 작업을 멈춰 두면
서술이 끝나기를 기다리는 테스트의 도구(narrated)도 함께 멈춘다.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.fake import FakeProvider
from app.drafts import records, repository
from app.drafts.drafting import save_drafts
from app.drafts.models import DraftStatus
from app.drafts.validation import Checked, ItemDraft
from tests import test_ledger_drafts as drafts_tests
from tests.test_ledger_drafts import play_round, statuses, switch
from tests.test_table_items import ME, table_url
from tests.test_table_quests import start_duo

pytestmark = pytest.mark.usefixtures('clean_tables')

# 장부 초안 테스트의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 사건과 물건이 든 로어북,
# 정해 둔 초안(물약 둘을 얻고 왕녀 구출을 이뤘다)을 쓰는 모델
me = drafts_tests.me
friend = drafts_tests.friend
lore = drafts_tests.lore
provider = drafts_tests.provider


def late_draft(lore: dict) -> Checked:
    """늦게 도착한 초안. 기사가 밧줄 하나를 손에 넣었다."""
    return Checked(items=[ItemDraft(ME, '기사', uuid.UUID(lore['rope']['id']), '밧줄', 1)])


async def drafted_table(client: AsyncClient, me: dict, friend: dict, lore: dict) -> dict:
    """장부 초안을 켜고 시작한 테이블."""
    table = await start_duo(client, me, friend, lore)
    await switch(client, me, table, True)
    return table


async def test_a_draft_from_an_older_scene_is_dropped(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider: FakeProvider, narrated, session: AsyncSession
):
    table = await drafted_table(client, me, friend, lore)
    # 1 라운드와 2 라운드가 서술을 마쳤다. 2 라운드의 초안이 먼저 적혀 1 라운드의 줄을 만료시켰다
    await play_round(client, me, friend, table, narrated)
    await play_round(client, me, friend, table, narrated)
    before = await statuses(session, table)

    # 그 뒤에 1 라운드의 초안이 늦게 도착한다
    saved = await save_drafts(session, uuid.UUID(table['id']), 1, late_draft(lore))

    assert saved == 0
    assert await statuses(session, table) == before
    assert before[-2:] == [(2, DraftStatus.PENDING), (2, DraftStatus.PENDING)]


async def test_a_draft_is_still_saved_while_the_next_round_is_open(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider: FakeProvider, narrated, session: AsyncSession
):
    table = await drafted_table(client, me, friend, lore)
    await play_round(client, me, friend, table, narrated)

    # 2 라운드는 열려 있지만 아직 서술하지 않았다. 1 라운드의 초안은 아직 새것이다
    saved = await save_drafts(session, uuid.UUID(table['id']), 1, late_draft(lore))

    assert saved == 1


async def test_a_draft_is_dropped_when_the_table_has_ended(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await drafted_table(client, me, friend, lore)
    await client.post(table_url(table, '/end'), headers=me)

    saved = await save_drafts(session, uuid.UUID(table['id']), 1, late_draft(lore))

    assert saved == 0
    assert await statuses(session, table) == []


async def test_a_draft_is_dropped_when_the_host_turned_drafts_off(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await drafted_table(client, me, friend, lore)
    await switch(client, me, table, False)

    saved = await save_drafts(session, uuid.UUID(table['id']), 1, late_draft(lore))

    assert saved == 0
    assert await statuses(session, table) == []


async def test_only_older_lines_are_expired(
    client: AsyncClient, me: dict, friend: dict, lore: dict, session: AsyncSession
):
    table = await drafted_table(client, me, friend, lore)
    table_id = uuid.UUID(table['id'])
    for number in (1, 2):
        repository.add_drafts(session, records.to_rows(table_id, number, late_draft(lore)))
    await session.commit()

    expired = await repository.expire_pending(session, table_id, before_round=2)
    await session.commit()

    assert expired == 1
    assert await statuses(session, table) == [(1, DraftStatus.EXPIRED), (2, DraftStatus.PENDING)]
