# trpg-server/tests/test_campaign_quests.py

"""
캠페인의 앞 편의 퀘스트를 보는 조건(#481 B, campaign_quest_succeeded, campaign_quest_failed)을 검증한다.

판: 1편에 사건 구출이 있고, 2편의 숨긴 퀘스트 보답은 "앞 편에서 구출이 성공했다"면 드러난다.

보는 것.
  - 시나리오: 이 조건은 드러나는 조건, 실패하는 조건, 사건, 장에 쓴다. 이루는 조건에는 쓰지 못한다(422).
    가리키는 것은 이 판 밖의 것이라 시나리오를 게시할 때는 보지 않는다.
  - 캠페인의 게시: 그 편보다 앞의 편의 판에 없는 퀘스트를 가리키면 409 campaign_quest_missing(첫 편에서 쓰면 늘 걸린다).
  - 플레이: 다음 편의 테이블을 열 때 앞 편들에서 끝난 퀘스트가 테이블의 복사본에 적히고, 조건이 그것을 본다.
    캠페인 밖의 테이블에서는 채워지지 않는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import QuestConditionKind
from app.assets.scenarios.snapshot import QuestConditionSnapshot
from app.rounds.quest_goals import is_met
from tests.narration_model import with_model
from tests.test_campaign_runs import RUNS_URL, TABLES_URL, end
from tests.test_campaigns_api import (
    CAMPAIGNS_URL,
    LOREBOOKS_URL,
    SCENARIOS_URL,
    make_campaign,
    make_rulebook,
    make_scenario,
    publish,
    publish_scenario,
)
from tests.test_lobby_api import ME, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

SUCCEEDED = 'campaign_quest_succeeded'


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


async def event_lore(client: AsyncClient, headers: dict, name: str) -> tuple[str, uuid.UUID]:
    """사건 항목 하나를 가진 로어북. 로어북과 그 항목의 ID."""
    lorebook = (await client.post(LOREBOOKS_URL, json={'title': name}, headers=headers)).json()
    entry = await client.post(
        f'{LOREBOOKS_URL}/{lorebook["id"]}/entries', json={'name': name, 'kind': 'event'}, headers=headers
    )
    return lorebook['id'], uuid.UUID(entry.json()['id'])


def hidden_until(entry_id: uuid.UUID, kind: str, target: uuid.UUID) -> dict:
    """숨긴 채 시작해 그 조건이 채워지면 드러나는 퀘스트 규칙."""
    return {'entry_id': str(entry_id), 'start': 'hidden', 'reveal': [{'kind': kind, 'target': str(target)}]}


async def two_episodes(client: AsyncClient, headers: dict, target: str = 'rescue') -> tuple[dict, dict[str, uuid.UUID]]:
    """
    1편(구출)과 2편(보답)의 캠페인. 2편의 보답은 target(구출, 보답 자신, 없는 것)이 앞 편에서 성공하면 드러난다.
    게시하지 않은 캠페인과 사건 항목들을 돌려준다.
    """
    rulebook_id = await make_rulebook(client, headers)
    first_lore, rescue = await event_lore(client, headers, '구출')
    second_lore, thanks = await event_lore(client, headers, '보답')
    aim = {'rescue': rescue, 'self': thanks, 'nowhere': uuid.uuid4()}[target]
    first = await make_scenario(client, headers, rulebook_id, '1편', lorebook_ids=[first_lore])
    second = await make_scenario(
        client, headers, rulebook_id, '2편', lorebook_ids=[second_lore], quests=[hidden_until(thanks, SUCCEEDED, aim)]
    )
    for scenario_id in (first, second):
        await publish_scenario(client, headers, scenario_id)
    return await make_campaign(client, headers, [first, second]), {'rescue': rescue, 'thanks': thanks}


# --- 시나리오 ---


async def test_the_condition_is_not_a_goal(client: AsyncClient, me: dict):
    rulebook_id = await make_rulebook(client, me)
    lore, entry = await event_lore(client, me, '구출')
    rule = {'entry_id': str(entry), 'start': 'active', 'conditions': [{'kind': SUCCEEDED, 'target': str(uuid.uuid4())}]}
    body = {'title': '2편', 'rulebook_id': rulebook_id, 'lorebook_ids': [lore], 'quests': [rule]}

    response = await client.post(SCENARIOS_URL, json=with_model(body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_scenario_publishes_with_a_condition_from_outside(client: AsyncClient, me: dict):
    # 가리키는 사건이 이 판에 없어도 시나리오는 게시된다. 캠페인을 게시할 때 본다
    campaign, _ = await two_episodes(client, me, target='nowhere')

    assert campaign['episodes'][1]['last_version'] == 1


# --- 캠페인의 게시 ---


@pytest.mark.parametrize(('target', 'ready'), [('rescue', True), ('self', False), ('nowhere', False)])
async def test_the_condition_must_point_to_an_earlier_episode(client: AsyncClient, me: dict, target: str, ready: bool):
    campaign, _ = await two_episodes(client, me, target=target)

    checked = (await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}/publish-check', headers=me)).json()
    published = await publish(client, me, campaign)

    assert checked['ready'] is ready
    assert ('campaign_quest_missing' in checked['problems']) is not ready
    expected = status.HTTP_201_CREATED if ready else status.HTTP_409_CONFLICT
    assert published.status_code == expected, published.text


async def test_the_first_episode_cannot_look_back(client: AsyncClient, me: dict):
    campaign, _ = await two_episodes(client, me)
    reversed_order = await client.patch(
        f'{CAMPAIGNS_URL}/{campaign["id"]}',
        json={'episodes': [{'scenario_id': one['scenario_id']} for one in reversed(campaign['episodes'])]},
        headers=me,
    )

    checked = (await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}/publish-check', headers=me)).json()

    assert reversed_order.status_code == status.HTTP_200_OK
    assert 'campaign_quest_missing' in checked['problems']


# --- 플레이 ---


async def test_the_next_episode_knows_how_the_last_one_ended(client: AsyncClient, me: dict, session: AsyncSession):
    campaign, entries = await two_episodes(client, me)
    await publish(client, me, campaign)
    run = (
        await client.post(RUNS_URL, json={'campaign_id': campaign['id'], 'table': {'capacity': 1}}, headers=me)
    ).json()
    first = {'id': run['episodes'][0]['table_id']}
    await client.put(f'{TABLES_URL}/{first["id"]}/character', json={'name': '기사'}, headers=me)
    await client.post(f'{TABLES_URL}/{first["id"]}/start', headers=me)
    await session.execute(
        text("UPDATE table_quests SET status = 'succeeded' WHERE table_id = :table AND entry_id = :entry"),
        {'table': uuid.UUID(first['id']), 'entry': entries['rescue']},
    )
    await session.commit()
    await end(client, me, first)

    opened = await client.post(f'{RUNS_URL}/{run["id"]}/next', json={'capacity': 1}, headers=me)

    assert opened.status_code == status.HTTP_201_CREATED, opened.text
    second_id = uuid.UUID(opened.json()['episodes'][1]['table_id'])
    content = await session.scalar(text('SELECT content FROM game_tables WHERE id = :id'), {'id': second_id})
    assert content['campaign_quests'] == [{'entry_id': str(entries['rescue']), 'result': 'succeeded'}]


# --- 엔진 ---


def condition(kind: QuestConditionKind, target: uuid.UUID) -> QuestConditionSnapshot:
    return QuestConditionSnapshot(kind=kind, target=target)


def test_the_engine_reads_the_handed_down_results():
    rescue, siege = uuid.uuid4(), uuid.uuid4()
    rows = [{'entry_id': str(rescue), 'result': 'succeeded'}, {'entry_id': str(siege), 'result': 'failed'}]
    table = SimpleNamespace(content={'campaign_quests': rows})
    plain = SimpleNamespace(content={})

    assert is_met(condition(QuestConditionKind.CAMPAIGN_QUEST_SUCCEEDED, rescue), table, [], [])
    assert not is_met(condition(QuestConditionKind.CAMPAIGN_QUEST_FAILED, rescue), table, [], [])
    assert is_met(condition(QuestConditionKind.CAMPAIGN_QUEST_FAILED, siege), table, [], [])
    assert not is_met(condition(QuestConditionKind.CAMPAIGN_QUEST_SUCCEEDED, uuid.uuid4()), table, [], [])
    # 캠페인 밖의 테이블에서는 채워지지 않는다
    assert not is_met(condition(QuestConditionKind.CAMPAIGN_QUEST_SUCCEEDED, rescue), plain, [], [])
