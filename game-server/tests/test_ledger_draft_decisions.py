# game-server/tests/test_ledger_draft_decisions.py

"""
방장이 장부 초안의 줄을 받아들이거나 버린다.

넷을 본다.
  - 받아들이기: 장부가 바뀐다. 방장이 손으로 할 때와 같은 이벤트, 같은 규칙이다.
    성공과 드러내기는 받아들이지 않는다(엔진의 몫).
  - 버리기: 장부는 그대로다. 끝난 테이블에서도 된다.
  - 다시 보기: 초안을 쓴 뒤에 장부가 바뀌었으면 받아들이지 않는다(죽음, 캐릭터 바뀜, 99 개, 끝난 퀘스트).
  - 한 번만: 결정했거나 만료된 줄, 동시에 두 번 받아들이기, 방장이 아닌 사람, 다른 테이블의 줄.
"""

import asyncio
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.drafts.models import DraftStatus, LedgerDraft
from tests import test_ledger_drafts as ledger_tests
from tests import test_table_quests as quest_tables
from tests.test_ledger_drafts import drafts_of, play_round, switch
from tests.test_table_items import FRIEND, ME, NO_SUCH_ID, events_of, give, held, kill, read_table, table_url
from tests.test_table_quests import change, start_duo

pytestmark = pytest.mark.usefixtures('clean_tables')

# 앞의 테스트들의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 사건과 물건이 든 로어북,
# 앉지 않는 사람, 그리고 "기사가 물약 둘을 손에 넣었고 왕녀 구출을 놓쳤다"는 초안을 쓰는 모델
me = quest_tables.me
friend = quest_tables.friend
lore = quest_tables.lore
stranger = quest_tables.stranger
provider = ledger_tests.provider


async def drafted(client: AsyncClient, me: dict, friend: dict, lore: dict, narrated) -> tuple[dict, dict, dict]:
    """초안을 켜고 한 라운드를 돌린 테이블과, 기다리는 두 줄(물건, 퀘스트)."""
    table = await start_duo(client, me, friend, lore)
    await switch(client, me, table, True)
    await play_round(client, me, friend, table, narrated)
    found, quest = (await drafts_of(client, me, table)).json()['items']
    return table, found, quest


async def accept(client: AsyncClient, headers: dict, table: dict, draft: dict):
    """줄 하나를 받아들이는 요청. 응답을 그대로 돌려준다."""
    return await client.post(table_url(table, f'/ledger-drafts/{draft["id"]}/accept'), headers=headers)


async def reject(client: AsyncClient, headers: dict, table: dict, draft: dict):
    """줄 하나를 버리는 요청. 응답을 그대로 돌려준다."""
    return await client.post(table_url(table, f'/ledger-drafts/{draft["id"]}/reject'), headers=headers)


async def status_of(session: AsyncSession, draft: dict) -> tuple[str, bool]:
    """줄의 처지와, 결정한 때가 적혔는지."""
    row = await session.scalar(select(LedgerDraft).where(LedgerDraft.id == uuid.UUID(draft['id'])))
    await session.refresh(row)
    return row.status, row.decided_at is not None


def refused(response, reason: str) -> bool:
    """409 이고 그 까닭인가."""
    return response.status_code == status.HTTP_409_CONFLICT and response.json()['reason'] == reason


# --- 받아들이기 ---


async def test_accepting_a_found_item_puts_it_in_the_ledger(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated, session: AsyncSession
):
    table, found, quest = await drafted(client, me, friend, lore, narrated)

    response = await accept(client, me, table, found)

    assert response.status_code == status.HTTP_200_OK, response.text
    assert held(response.json(), ME) == [('치유 물약', 2)]
    # 방장이 손으로 줄 때와 같은 이벤트다. 모두가 본다
    [event] = await events_of(client, friend, table, 'items_gained')
    assert event['actor_id'] == str(ME)
    assert event['payload'] == {
        'user_id': str(ME),
        'character_name': '기사',
        'entry_id': lore['potion']['id'],
        'name': '치유 물약',
        'count': 2,
        'total': 2,
    }
    assert await status_of(session, found) == (DraftStatus.ACCEPTED, True)
    assert [draft['id'] for draft in (await drafts_of(client, me, table)).json()['items']] == [quest['id']]


async def test_accepting_a_quest_change_changes_the_quest(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, _, quest = await drafted(client, me, friend, lore, narrated)

    response = await accept(client, me, table, quest)

    # 방장이 손으로 바꿀 때와 같은 길이다. 실패에는 보상이 없다
    assert response.status_code == status.HTTP_200_OK, response.text
    assert quest_tables.quests_in(response.json())[0] == ('왕녀 구출', 'failed')
    assert held(response.json(), ME) == held(response.json(), FRIEND) == []
    [event] = await events_of(client, friend, table, 'quest_changed')
    assert (event['payload']['previous'], event['payload']['status']) == ('active', 'failed')
    # 바꾼 사람은 받아들인 방장이다. AI 가 아니다
    assert event['actor_id'] == str(ME)


async def test_an_old_success_draft_is_not_accepted(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated, session: AsyncSession
):
    table, _, quest = await drafted(client, me, friend, lore, narrated)
    # 성공을 엔진의 몫으로 옮기기 전에 쓴 초안이다. 받아들이면 방장이 성공을 정하게 된다
    await session.execute(
        text("UPDATE ledger_drafts SET payload = jsonb_set(payload, '{status}', '\"succeeded\"') WHERE id = :id"),
        {'id': quest['id']},
    )
    await session.commit()

    response = await accept(client, me, table, quest)

    assert refused(response, 'quest_success_by_engine')
    assert quest_tables.quests_in(await read_table(client, me, table))[0] == ('왕녀 구출', 'active')


async def test_an_old_reveal_draft_is_not_accepted(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated, session: AsyncSession
):
    table, _, quest = await drafted(client, me, friend, lore, narrated)
    # 드러내기를 엔진의 몫으로 옮기기 전에 쓴 초안이다(ledger-draft-5 까지). 숨긴 광산의 비밀을 드러내자고 했다
    await session.execute(
        text(
            'UPDATE ledger_drafts SET payload = payload || jsonb_build_object('
            "'entry_id', CAST(:mine AS text), 'name', '광산의 비밀', 'previous', 'hidden', 'status', 'active') "
            'WHERE id = :id'
        ),
        {'id': quest['id'], 'mine': lore['mine']['id']},
    )
    await session.commit()

    response = await accept(client, me, table, quest)

    assert refused(response, 'quest_reveal_by_engine')
    assert quest_tables.quests_in(await read_table(client, me, table)) == [('왕녀 구출', 'active')]


async def test_a_full_stack_takes_only_what_fits(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)
    await give(client, me, table, ME, lore['potion'], 98)

    response = await accept(client, me, table, found)

    assert held(response.json(), ME) == [('치유 물약', 99)]
    # 넘는 만큼은 받지 않는다. 이벤트에는 실제로 받은 개수가 적힌다
    by_hand, by_draft = await events_of(client, me, table, 'items_gained')
    assert (by_hand['payload']['count'], by_draft['payload']['count'], by_draft['payload']['total']) == (98, 1, 99)


# --- 버리기 ---


async def test_rejecting_leaves_the_ledger_alone(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated, session: AsyncSession
):
    table, found, quest = await drafted(client, me, friend, lore, narrated)

    response = await reject(client, me, table, quest)

    assert response.status_code == status.HTTP_204_NO_CONTENT
    detail = await read_table(client, me, table)
    assert quest_tables.quests_in(detail)[0] == ('왕녀 구출', 'active')
    assert await events_of(client, me, table, 'quest_changed') == []
    assert await status_of(session, quest) == (DraftStatus.REJECTED, True)
    assert [draft['id'] for draft in (await drafts_of(client, me, table)).json()['items']] == [found['id']]


async def test_an_ended_table_can_still_reject_but_not_accept(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, found, quest = await drafted(client, me, friend, lore, narrated)
    await client.post(table_url(table, '/end'), headers=me)

    assert refused(await accept(client, me, table, found), 'not_playing')
    assert (await reject(client, me, table, quest)).status_code == status.HTTP_204_NO_CONTENT


# --- 다시 보기 ---


async def test_a_dead_character_gets_nothing(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated, session: AsyncSession
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)
    await kill(session, ME)

    response = await accept(client, me, table, found)

    assert refused(response, 'character_dead')
    assert await status_of(session, found) == (DraftStatus.PENDING, False)


async def test_a_different_character_does_not_get_what_another_found(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated, session: AsyncSession
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)
    # 초안을 쓴 뒤에 그 사람의 캐릭터가 바뀌었다(죽고 새 캐릭터가 들어온 것과 같다)
    await session.execute(
        text('UPDATE table_members SET character_name = :name WHERE user_id = :user_id'),
        {'name': '새 기사', 'user_id': ME},
    )
    await session.commit()

    assert refused(await accept(client, me, table, found), 'draft_stale')


async def test_a_full_stack_refuses_the_item(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)
    await give(client, me, table, ME, lore['potion'], 99)

    assert refused(await accept(client, me, table, found), 'too_many_items')


async def test_a_quest_finished_meanwhile_refuses_the_change(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, _, quest = await drafted(client, me, friend, lore, narrated)
    await change(client, me, table, lore['rescue'], 'failed')

    assert refused(await accept(client, me, table, quest), 'quest_finished')


# --- 한 번만 ---


@pytest.mark.parametrize('second', [accept, reject], ids=['accept-again', 'reject-after'])
async def test_a_decided_line_is_not_decided_again(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated, second
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)
    await accept(client, me, table, found)

    assert refused(await second(client, me, table, found), 'draft_decided')
    assert held(await read_table(client, me, table), ME) == [('치유 물약', 2)]


async def test_an_expired_line_cannot_be_accepted(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)
    provider.reply = '{}'
    await play_round(client, me, friend, table, narrated)

    assert refused(await accept(client, me, table, found), 'draft_decided')


async def test_accepting_twice_at_once_changes_the_ledger_once(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)

    # 잠그지 않으면 둘 다 "기다리는 줄"을 보고 물약을 두 번 준다
    first, second = await asyncio.gather(accept(client, me, table, found), accept(client, me, table, found))

    assert sorted([first.status_code, second.status_code]) == [status.HTTP_200_OK, status.HTTP_409_CONFLICT]
    assert held(await read_table(client, me, table), ME) == [('치유 물약', 2)]


async def test_only_the_host_decides(
    client: AsyncClient, me: dict, friend: dict, stranger: dict, lore: dict, provider, narrated
):
    table, found, quest = await drafted(client, me, friend, lore, narrated)

    assert (await accept(client, friend, table, found)).status_code == status.HTTP_403_FORBIDDEN
    assert (await reject(client, friend, table, quest)).status_code == status.HTTP_403_FORBIDDEN
    assert (await accept(client, stranger, table, found)).status_code == status.HTTP_404_NOT_FOUND
    assert held(await read_table(client, me, table), ME) == []


async def test_a_line_of_another_table_is_not_found(
    client: AsyncClient, me: dict, friend: dict, lore: dict, provider, narrated
):
    table, found, _ = await drafted(client, me, friend, lore, narrated)
    other = await start_duo(client, me, friend, lore)

    response = await accept(client, me, other, found)
    unknown = await accept(client, me, table, {'id': NO_SUCH_ID})

    assert response.status_code == unknown.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': '장부 초안을 찾을 수 없습니다.'}
    assert held(await read_table(client, me, table), ME) == []
