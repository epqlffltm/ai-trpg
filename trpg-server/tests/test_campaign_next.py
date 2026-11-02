# trpg-server/tests/test_campaign_next.py

"""
캠페인의 다음 편(#481 B, app/campaigns/service.py 의 open_next, join_run, app/campaigns/seating.py)을 검증한다.

판: 두 편이 같은 룰북과 같은 로어북(횃불)을 쓰고, 1편만 지도를 더 쓴다. 1편에서 기사(나, 방장)를 키우고(경험치 150,
점수 1, 최대 HP 15, 근력 13, 돈 40, 횃불 둘, 지도 하나) 1편을 끝낸 뒤에 본다.

보는 것.
  - 다음 편: 앞 편이 끝나지 않았으면 409 episode_not_ended, 방장이 아니면 403. 끝났으면 2편의 테이블이 열리고
    방장은 넘긴 캐릭터로 앉는다. 마지막 편이 끝나면 플레이가 끝나고 다음 편은 409 run_ended.
  - 들어오기: 그 플레이의 사람은 초대 코드 없이 앉는다. 넘긴 캐릭터가 있으면 그것으로 앉고
    바꾸지 못한다(409 character_carried).
    죽어 넘긴 것이 없는 사람은 판의 방식대로 새로 만든다. 플레이의 사람이 아니면 404, 이미 앉았으면 409.
  - 시작: 넘긴 캐릭터는 능력치, 최대 HP(지금 HP 는 가득), 경험치, 점수, 돈을 그대로,
    소지품은 2편의 판에 있는 것만 받는다.
  - 탈퇴: 넘길 것을 지운다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.models import CampaignCarry
from app.withdrawal.service import erase_belongings
from tests.test_campaign_runs import RUNS_URL, TABLES_URL, end, grow
from tests.test_campaigns_api import (
    LOREBOOKS_URL,
    make_campaign,
    make_rulebook,
    make_scenario,
    publish,
    publish_scenario,
)
from tests.test_lobby_api import FRIEND, ME, THIRD, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, THIRD)


async def lorebook_with(client: AsyncClient, headers: dict, name: str) -> tuple[str, uuid.UUID]:
    """물건 항목 하나를 가진 로어북. 로어북과 그 항목의 ID."""
    lorebook = (await client.post(LOREBOOKS_URL, json={'title': name}, headers=headers)).json()
    entry = await client.post(
        f'{LOREBOOKS_URL}/{lorebook["id"]}/entries', json={'name': name, 'kind': 'item'}, headers=headers
    )
    return lorebook['id'], uuid.UUID(entry.json()['id'])


async def two_episodes(client: AsyncClient, headers: dict) -> tuple[dict, uuid.UUID, uuid.UUID]:
    """두 편짜리 캠페인을 게시한다. 캠페인과 횃불(두 편 모두), 지도(1편만)의 항목."""
    rulebook_id = await make_rulebook(client, headers)
    shared, torch = await lorebook_with(client, headers, '횃불')
    first_only, map_entry = await lorebook_with(client, headers, '지도')
    first = await make_scenario(client, headers, rulebook_id, '1편', lorebook_ids=[shared, first_only])
    second = await make_scenario(client, headers, rulebook_id, '2편', lorebook_ids=[shared])
    for scenario_id in (first, second):
        await publish_scenario(client, headers, scenario_id)
    campaign = await make_campaign(client, headers, [first, second])
    assert (await publish(client, headers, campaign)).status_code == status.HTTP_201_CREATED
    return campaign, torch, map_entry


async def table_of(client: AsyncClient, headers: dict, run: dict, position: int) -> dict:
    run = (await client.get(f'{RUNS_URL}/{run["id"]}', headers=headers)).json()
    return (await client.get(f'{TABLES_URL}/{run["episodes"][position]["table_id"]}', headers=headers)).json()


async def first_episode(client: AsyncClient, me: dict, friend: dict) -> tuple[dict, dict, uuid.UUID, uuid.UUID]:
    """둘이 1편을 시작한 플레이와 그 테이블, 횃불과 지도의 항목."""
    campaign, torch, map_entry = await two_episodes(client, me)
    body = {'campaign_id': campaign['id'], 'table': {'capacity': 2}}
    run = (await client.post(RUNS_URL, json=body, headers=me)).json()
    table = await table_of(client, me, run, 0)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    for headers, name in ((me, '기사'), (friend, '도적')):
        await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': name}, headers=headers)
    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return run, started.json(), torch, map_entry


async def episode_one_done(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession, friend_dies: bool = False
) -> tuple[dict, uuid.UUID]:
    """1편에서 기사를 키우고(횃불 둘, 지도 하나) 1편을 끝낸 플레이와 횃불의 항목. 도적은 죽을 수도 있다."""
    run, table, torch, map_entry = await first_episode(client, me, friend)
    await grow(session, ME, table, torch)
    await session.execute(
        text(
            'INSERT INTO table_items (id, table_id, sheet_id, entry_id, count) '
            'SELECT :id, table_id, id, :entry, 1 FROM table_sheets WHERE user_id = :user_id'
        ),
        {'id': uuid.uuid4(), 'entry': map_entry, 'user_id': ME},
    )
    if friend_dies:
        await session.execute(text('UPDATE table_sheets SET hp = 0, died_at = now() WHERE user_id = :u'), {'u': FRIEND})
    await session.commit()
    assert (await end(client, me, table)).status_code == status.HTTP_200_OK
    return run, torch


async def next_episode(client: AsyncClient, headers: dict, run: dict):
    return await client.post(f'{RUNS_URL}/{run["id"]}/next', json={'capacity': 2}, headers=headers)


async def join(client: AsyncClient, headers: dict, run: dict):
    return await client.post(f'{RUNS_URL}/{run["id"]}/join', headers=headers)


def seat_of(table: dict, user_id: uuid.UUID) -> dict:
    return next(member for member in table['members'] if member['user_id'] == str(user_id))


# --- 다음 편 ---


async def test_the_next_episode_waits_for_the_last_one(client: AsyncClient, me: dict, friend: dict):
    run, _, _, _ = await first_episode(client, me, friend)

    early = await next_episode(client, me, run)
    not_host = await next_episode(client, friend, run)

    assert (early.status_code, early.json()['reason']) == (status.HTTP_409_CONFLICT, 'episode_not_ended')
    assert not_host.status_code == status.HTTP_403_FORBIDDEN


async def test_the_next_episode_seats_the_host_as_carried(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession
):
    run, _ = await episode_one_done(client, me, friend, session)

    opened = await next_episode(client, me, run)

    assert opened.status_code == status.HTTP_201_CREATED, opened.text
    assert opened.json()['position'] == 1
    table = await table_of(client, me, run, 1)
    assert (table['status'], table['scenario_id']) == ('recruiting', opened.json()['episodes'][1]['scenario_id'])
    host = seat_of(table, ME)
    assert (host['character']['name'], host['character_mode']) == ('기사', 'custom')
    changed = await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '새 사람'}, headers=me)
    assert (changed.status_code, changed.json()['reason']) == (status.HTTP_409_CONFLICT, 'character_carried')
    # 같은 편을 두 번 열지 않는다. 2편이 끝나지 않았다
    again = await next_episode(client, me, run)
    assert (again.status_code, again.json()['reason']) == (status.HTTP_409_CONFLICT, 'episode_not_ended')


# --- 들어오기 ---


async def test_the_people_of_the_run_join_without_a_code(
    client: AsyncClient, me: dict, friend: dict, stranger: dict, session: AsyncSession
):
    run, _ = await episode_one_done(client, me, friend, session)
    await next_episode(client, me, run)

    joined = await join(client, friend, run)

    assert joined.status_code == status.HTTP_200_OK, joined.text
    assert seat_of(joined.json(), FRIEND)['character']['name'] == '도적'
    assert (await join(client, friend, run)).json()['reason'] == 'already_seated'
    assert (await join(client, stranger, run)).status_code == status.HTTP_404_NOT_FOUND


async def test_the_dead_make_a_new_character(client: AsyncClient, me: dict, friend: dict, session: AsyncSession):
    run, _ = await episode_one_done(client, me, friend, session, friend_dies=True)
    await next_episode(client, me, run)

    joined = await join(client, friend, run)
    table = joined.json()
    named = await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '사제'}, headers=friend)

    assert seat_of(table, FRIEND)['character'] is None
    assert named.status_code == status.HTTP_200_OK, named.text


# --- 시작 ---


async def test_the_carried_character_starts_as_it_ended(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession
):
    run, torch = await episode_one_done(client, me, friend, session)
    await next_episode(client, me, run)
    table = (await join(client, friend, run)).json()

    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)

    assert started.status_code == status.HTTP_200_OK, started.text
    sheet = seat_of(started.json(), ME)['sheet']
    assert (sheet['xp'], sheet['points'], sheet['max_hp'], sheet['hp'], sheet['money']) == (150, 1, 15, 15, 40)
    assert sheet['abilities']['str'] == 13
    # 지도는 2편의 판에 없어 옮기지 않는다. 판의 시작 소지품도 받지 않는다
    assert [(item['entry_id'], item['count']) for item in sheet['items']] == [(str(torch), 2)]
    # 넘긴 것이 없던 도적은 보통처럼 판의 기본 시트를 받는다
    assert seat_of(started.json(), FRIEND)['sheet']['xp'] == 0


async def test_the_run_ends_after_the_last_episode(client: AsyncClient, me: dict, friend: dict, session: AsyncSession):
    run, _ = await episode_one_done(client, me, friend, session)
    await next_episode(client, me, run)
    table = await table_of(client, me, run, 1)

    assert (await end(client, me, table)).status_code == status.HTTP_200_OK
    finished = (await client.get(f'{RUNS_URL}/{run["id"]}', headers=me)).json()
    after = await next_episode(client, me, run)

    assert finished['status'] == 'ended'
    assert (after.status_code, after.json()['reason']) == (status.HTTP_409_CONFLICT, 'run_ended')


# --- 탈퇴 ---


async def test_withdrawal_erases_the_carries(client: AsyncClient, me: dict, friend: dict, session: AsyncSession):
    run, _ = await episode_one_done(client, me, friend, session)
    await next_episode(client, me, run)

    await erase_belongings(session, ME)

    left = await session.scalar(select(func.count()).select_from(CampaignCarry).where(CampaignCarry.user_id == ME))
    assert left == 0
    assert await session.scalar(select(func.count()).select_from(CampaignCarry)) == 1
