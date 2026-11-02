# trpg-server/tests/test_campaign_runs.py

"""
캠페인의 플레이(#481 B, app/campaigns/)를 검증한다. 플레이를 시작하고, 편이 끝날 때 넘길 것을 적는다.

보는 것.
  - 시작: 자기 캠페인의 판(비우면 마지막 판)으로 첫 편의 테이블이 열리고 플레이의 1편으로 이어진다.
    남의 캠페인, 게시하지 않은 캠페인은 404. 테이블의 값에 시나리오나 판을 적으면 422.
  - 편의 끝: 방장이 테이블을 끝내면 앉은 사람마다 지금 캐릭터의 넘길 것
    (이름, 능력치, 최대 HP, 경험치, 점수, 돈, 소지품)과
    그 편에서 이루거나 실패한 퀘스트가 적힌다. 죽은 캐릭터는 넘기지 않는다. 캠페인이 아닌 테이블은 적지 않는다.
  - 보기: 방장과 그 플레이의 테이블에 앉은 사람만 본다(남은 404). 넘긴 것은 본인의 것만 싣는다.
  - 마지막 편이 끝나면 플레이가 끝난다(순수 함수).
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.campaigns.schemas import CampaignSnapshot
from app.campaigns.ending import is_last
from app.campaigns.models import CampaignCarry, CampaignRun
from app.main import API_PREFIX
from tests.test_campaigns_api import (
    CAMPAIGNS_URL,
    LOREBOOKS_URL,
    make_campaign,
    make_rulebook,
    make_scenario,
    publish,
    publish_scenario,
    published_scenarios,
)
from tests.test_lobby_api import FRIEND, ME, THIRD, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

RUNS_URL = f'{API_PREFIX}/campaign-runs'
TABLES_URL = f'{API_PREFIX}/tables'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, THIRD)


# 두 편이 함께 붙이는 로어북의 항목. 물건 하나와 사건(퀘스트) 셋
ENTRIES = {
    'torch': ('횃불', 'item'),
    'rescue': ('구출', 'event'),
    'siege': ('공성', 'event'),
    'scout': ('정찰', 'event'),
}


async def shared_lore(client: AsyncClient, headers: dict) -> tuple[str, dict[str, uuid.UUID]]:
    """두 편이 함께 붙이는 로어북과 그 항목들(이름표 → ID)."""
    lorebook = (await client.post(LOREBOOKS_URL, json={'title': '추격전의 것들'}, headers=headers)).json()
    found = {}
    for key, (name, kind) in ENTRIES.items():
        entry = await client.post(
            f'{LOREBOOKS_URL}/{lorebook["id"]}/entries', json={'name': name, 'kind': kind}, headers=headers
        )
        assert entry.status_code == status.HTTP_201_CREATED, entry.text
        found[key] = uuid.UUID(entry.json()['id'])
    return lorebook['id'], found


async def published_campaign(client: AsyncClient, headers: dict) -> tuple[dict, dict[str, uuid.UUID]]:
    """같은 룰북과 로어북의 두 편짜리 캠페인을 게시한다. 캠페인과 로어북의 항목들을 돌려준다."""
    rulebook_id = await make_rulebook(client, headers)
    lorebook_id, entries = await shared_lore(client, headers)
    scenario_ids = [
        await make_scenario(client, headers, rulebook_id, f'{number}편', lorebook_ids=[lorebook_id])
        for number in (1, 2)
    ]
    for scenario_id in scenario_ids:
        await publish_scenario(client, headers, scenario_id)
    campaign = await make_campaign(client, headers, scenario_ids)
    assert (await publish(client, headers, campaign)).status_code == status.HTTP_201_CREATED
    return campaign, entries


async def start(client: AsyncClient, headers: dict, campaign: dict, **fields):
    body = {'campaign_id': campaign['id'], 'table': {'capacity': 2}, **fields}
    return await client.post(RUNS_URL, json=body, headers=headers)


async def started_run(client: AsyncClient, me: dict, friend: dict) -> tuple[dict, dict, dict[str, uuid.UUID]]:
    """둘이 1편을 시작한 플레이와 그 테이블, 로어북의 항목들. 둘 다 이름만 쓴 캐릭터다."""
    campaign, entries = await published_campaign(client, me)
    response = await start(client, me, campaign)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    run = response.json()
    table_id = run['episodes'][0]['table_id']
    table = (await client.get(f'{TABLES_URL}/{table_id}', headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    for headers, name in ((me, '기사'), (friend, '도적')):
        named = await client.put(f'{TABLES_URL}/{table_id}/character', json={'name': name}, headers=headers)
        assert named.status_code == status.HTTP_200_OK, named.text
    begun = await client.post(f'{TABLES_URL}/{table_id}/start', headers=me)
    assert begun.status_code == status.HTTP_200_OK, begun.text
    return run, begun.json(), entries


async def grow(session: AsyncSession, user_id: uuid.UUID, table: dict, item: uuid.UUID) -> None:
    """서비스를 거치지 않고 그 사람의 캐릭터를 키운다. 경험치, 점수, 최대 HP, 돈, 물건 하나."""
    await session.execute(
        text(
            'UPDATE table_sheets SET xp = 150, points = 1, max_hp = 15, hp = 3, money = 40, '
            'abilities = abilities || \'{"str": 13}\' WHERE user_id = :user_id'
        ),
        {'user_id': user_id},
    )
    await session.execute(
        text(
            'INSERT INTO table_items (id, table_id, sheet_id, entry_id, count) '
            'SELECT :id, table_id, id, :entry, 2 FROM table_sheets WHERE user_id = :user_id'
        ),
        {'id': uuid.uuid4(), 'entry': item, 'user_id': user_id},
    )
    await session.commit()


async def finish_quest(session: AsyncSession, table: dict, entry_id: uuid.UUID, state: str) -> None:
    """서비스를 거치지 않고 테이블의 퀘스트 하나의 상태를 바꾼다."""
    await session.execute(
        text('UPDATE table_quests SET status = :state WHERE table_id = :table AND entry_id = :entry'),
        {'table': uuid.UUID(table['id']), 'entry': entry_id, 'state': state},
    )
    await session.commit()


async def end(client: AsyncClient, headers: dict, table: dict):
    return await client.post(f'{TABLES_URL}/{table["id"]}/end', headers=headers)


# --- 시작 ---


async def test_a_run_opens_the_first_episode(client: AsyncClient, me: dict):
    campaign, _ = await published_campaign(client, me)

    response = await start(client, me, campaign)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    run = response.json()
    assert (run['status'], run['position'], run['version'], run['title']) == ('playing', 0, 1, '추격전')
    first, second = run['episodes']
    assert (first['title'], first['version'], second['table_id']) == ('1편', 1, None)
    table = (await client.get(f'{TABLES_URL}/{first["table_id"]}', headers=me)).json()
    assert (table['scenario_id'], table['status'], table['capacity']) == (first['scenario_id'], 'recruiting', 2)
    assert run['my_carry'] is None and run['quest_results'] == []


@pytest.mark.parametrize('which', ['others', 'unpublished', 'missing_version', 'scenario_in_table'])
async def test_a_run_that_cannot_start(client: AsyncClient, me: dict, friend: dict, which: str):
    campaign, _ = await published_campaign(client, me)
    draft = await make_campaign(client, me, [])
    headers, body, code = {
        'others': (friend, {'campaign_id': campaign['id'], 'table': {'capacity': 2}}, 404),
        'unpublished': (me, {'campaign_id': draft['id'], 'table': {'capacity': 2}}, 404),
        'missing_version': (me, {'campaign_id': campaign['id'], 'version': 2, 'table': {'capacity': 2}}, 404),
        'scenario_in_table': (
            me,
            {
                'campaign_id': campaign['id'],
                'table': {'capacity': 2, 'scenario_id': campaign['episodes'][0]['scenario_id']},
            },
            422,
        ),
    }[which]

    response = await client.post(RUNS_URL, json=body, headers=headers)

    assert response.status_code == code, response.text
    assert (await client.get(TABLES_URL, headers=headers)).json()['total'] == 0


# --- 편의 끝 ---


async def test_the_end_of_an_episode_carries_the_living(
    client: AsyncClient, me: dict, friend: dict, session: AsyncSession
):
    run, table, entries = await started_run(client, me, friend)
    torch, rescue, siege = entries['torch'], entries['rescue'], entries['siege']
    await grow(session, ME, table, torch)
    await session.execute(text('UPDATE table_sheets SET died_at = now(), hp = 0 WHERE user_id = :u'), {'u': FRIEND})
    await session.commit()
    await finish_quest(session, table, rescue, 'succeeded')
    await finish_quest(session, table, siege, 'failed')
    await finish_quest(session, table, entries['scout'], 'active')

    ended = await end(client, me, table)

    assert ended.status_code == status.HTTP_200_OK, ended.text
    mine = (await client.get(f'{RUNS_URL}/{run["id"]}', headers=me)).json()
    carry = mine['my_carry']
    assert carry['character_name'] == '기사'
    assert (
        carry['pregen'],
        carry['abilities']['str'],
        carry['max_hp'],
        carry['xp'],
        carry['points'],
        carry['money'],
    ) == (
        False,
        13,
        15,
        150,
        1,
        40,
    )
    assert carry['items'] == [{'entry_id': str(torch), 'count': 2}]
    assert sorted((row['entry_id'], row['result']) for row in mine['quest_results']) == sorted(
        [(str(rescue), 'succeeded'), (str(siege), 'failed')]
    )
    # 죽은 캐릭터는 넘기지 않는다. 그래도 앉았던 사람이라 플레이를 본다
    theirs = await client.get(f'{RUNS_URL}/{run["id"]}', headers=friend)
    assert (theirs.status_code, theirs.json()['my_carry']) == (status.HTTP_200_OK, None)
    assert mine['status'] == 'playing'
    # 다시 끝낼 수 없어 두 번 적히지 않는다
    assert (await end(client, me, table)).status_code == status.HTTP_409_CONFLICT
    assert await session.scalar(select(func.count()).select_from(CampaignCarry)) == 1


async def test_a_plain_table_carries_nothing(client: AsyncClient, me: dict, session: AsyncSession):
    scenario_id = (await published_scenarios(client, me, 1))[0]
    table = (
        await client.post(TABLES_URL, json={'scenario_id': scenario_id, 'version': 1, 'capacity': 1}, headers=me)
    ).json()

    assert (await end(client, me, table)).status_code == status.HTTP_200_OK
    assert await session.scalar(select(func.count()).select_from(CampaignCarry)) == 0


async def test_an_episode_ended_before_it_started_carries_nobody(client: AsyncClient, me: dict, session: AsyncSession):
    run = (await start(client, me, (await published_campaign(client, me))[0])).json()

    assert (await end(client, me, {'id': run['episodes'][0]['table_id']})).status_code == status.HTTP_200_OK
    assert await session.scalar(select(func.count()).select_from(CampaignCarry)) == 0


# --- 보기 ---


async def test_only_the_people_of_a_run_see_it(client: AsyncClient, me: dict, friend: dict, stranger: dict):
    run, _, _ = await started_run(client, me, friend)

    assert (await client.get(f'{RUNS_URL}/{run["id"]}', headers=friend)).status_code == status.HTTP_200_OK
    assert (await client.get(f'{RUNS_URL}/{run["id"]}', headers=stranger)).status_code == status.HTTP_404_NOT_FOUND
    assert (await client.get(f'{RUNS_URL}/{uuid.uuid4()}', headers=me)).status_code == status.HTTP_404_NOT_FOUND


async def test_a_campaign_with_a_run_cannot_lose_its_version(client: AsyncClient, me: dict, session: AsyncSession):
    campaign, _ = await published_campaign(client, me)
    await start(client, me, campaign)

    deleted = await client.delete(f'{CAMPAIGNS_URL}/{campaign["id"]}', headers=me)

    # 캠페인은 지운 것으로 적힐 뿐이다. 플레이는 그 판으로 그대로 간다
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert await session.scalar(select(func.count()).select_from(CampaignRun)) == 1


# --- 마지막 편 ---


def test_the_run_ends_after_the_last_episode():
    snapshot = CampaignSnapshot(
        title='t',
        description='',
        rating='all',
        rulebook_id=uuid.uuid4(),
        episodes=[{'scenario_id': uuid.uuid4(), 'version': 1, 'title': str(number)} for number in range(2)],
    )

    assert not is_last(CampaignRun(position=0), snapshot)
    assert is_last(CampaignRun(position=1), snapshot)
