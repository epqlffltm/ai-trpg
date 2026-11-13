# trpg-server/tests/test_campaigns_api.py

"""
캠페인 자산(#481 B, app/assets/campaigns/)을 검증한다. 초안, 게시, 게시 검사, 판에 굳히는 것.

보는 것.
  - 초안: 만들기·읽기·고치기(편 목록을 통째로)·지우기. 자기 시나리오만, 같은 시나리오는 한 번만(422). 남의 캠페인은 404.
    편이 가리키는 시나리오는 지우지 못한다(409, used_by 에 캠페인).
  - 게시: 편이 둘보다 적으면, 판이 없는 시나리오가 있으면, 룰북(규칙)이 다르면 409 와 problems.
    게시하면 편마다 그때의 시나리오의 마지막 판 번호와 이름(비웠으면 시나리오의 제목)이 굳는다. 번호는 1 부터.
    시나리오를 다시 게시해도 앞의 판은 그대로, 캠페인을 다시 게시하면 새 번호다.
  - 등급: 성인용 편이 하나라도 있으면 성인용. 성인용을 볼 수 없는 사람은 게시하지 못한다(403).
  - 알림: 룰북에 성장이 없으면 progression_missing, 앞 편의 물건이 뒤 편들에 없으면 items_not_carried.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey

from app.main import API_PREFIX
from tests.narration_model import with_model
from tests.sheets import SHEET
from tests.test_lobby_api import FRIEND, ME, bearer

pytestmark = pytest.mark.usefixtures('clean_tables')

CAMPAIGNS_URL = f'{API_PREFIX}/campaigns'
SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
OPENING = '사이렌이 울린다.'
PROGRESSION = {'levels': [{'xp': 100, 'max_hp': 2, 'points': 1}]}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME)


@pytest.fixture
def adult_me(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, ME, adult_content=True)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    return bearer(signing_key, FRIEND)


async def make_rulebook(client: AsyncClient, headers: dict, **fields) -> str:
    response = await client.post(RULEBOOKS_URL, json={'title': '룰북', **fields}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def make_scenario(client: AsyncClient, headers: dict, rulebook_id: str, title: str, **fields) -> str:
    body = {'title': title, 'rulebook_id': rulebook_id, 'openings': [OPENING], 'default_sheet': SHEET, **fields}
    response = await client.post(SCENARIOS_URL, json=with_model(body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


async def publish_scenario(client: AsyncClient, headers: dict, scenario_id: str) -> None:
    response = await client.post(f'{SCENARIOS_URL}/{scenario_id}/versions', json={}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text


async def published_scenarios(client: AsyncClient, headers: dict, count: int = 2, **rulebook_fields) -> list[str]:
    """같은 룰북의, 게시한 시나리오들. 1편, 2편 … 의 제목이다."""
    rulebook_id = await make_rulebook(client, headers, **rulebook_fields)
    scenario_ids = [await make_scenario(client, headers, rulebook_id, f'{number}편') for number in range(1, count + 1)]
    for scenario_id in scenario_ids:
        await publish_scenario(client, headers, scenario_id)
    return scenario_ids


def episodes(*scenario_ids: str, titles: dict[str, str] | None = None) -> list[dict]:
    return [{'scenario_id': one, 'title': (titles or {}).get(one, '')} for one in scenario_ids]


async def make_campaign(client: AsyncClient, headers: dict, scenario_ids: list[str], **fields) -> dict:
    body = {'title': '추격전', 'episodes': episodes(*scenario_ids), **fields}
    response = await client.post(CAMPAIGNS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish(client: AsyncClient, headers: dict, campaign: dict, note: str = ''):
    return await client.post(f'{CAMPAIGNS_URL}/{campaign["id"]}/versions', json={'note': note}, headers=headers)


async def check(client: AsyncClient, headers: dict, campaign: dict) -> dict:
    response = await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}/publish-check', headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 초안 ---


async def test_a_campaign_lists_its_episodes_in_order(client: AsyncClient, me: dict):
    first, second = await published_scenarios(client, me)
    unpublished = await make_scenario(client, me, await make_rulebook(client, me), '3편')

    campaign = await make_campaign(client, me, [second, first, unpublished])

    assert campaign['episode_count'] == 3
    assert campaign['rating'] == 'all'
    assert campaign['episodes'] == [
        {'scenario_id': second, 'title': '', 'scenario_title': '2편', 'last_version': 1},
        {'scenario_id': first, 'title': '', 'scenario_title': '1편', 'last_version': 1},
        {'scenario_id': unpublished, 'title': '', 'scenario_title': '3편', 'last_version': None},
    ]
    listed = (await client.get(CAMPAIGNS_URL, headers=me)).json()
    assert (listed['total'], listed['items'][0]['id'], listed['items'][0]['episode_count']) == (1, campaign['id'], 3)


async def test_episodes_are_replaced_as_a_whole(client: AsyncClient, me: dict):
    first, second, third = await published_scenarios(client, me, 3)
    campaign = await make_campaign(client, me, [first, second])

    response = await client.patch(
        f'{CAMPAIGNS_URL}/{campaign["id"]}',
        json={'episodes': episodes(third, first, titles={third: ' 톨게이트 '})},
        headers=me,
    )

    assert response.status_code == status.HTTP_200_OK, response.text
    sent = response.json()['episodes']
    assert [(one['scenario_id'], one['title']) for one in sent] == [(third, '톨게이트'), (first, '')]
    # 편을 보내지 않으면 그대로다
    renamed = await client.patch(f'{CAMPAIGNS_URL}/{campaign["id"]}', json={'title': '새 이름'}, headers=me)
    assert (renamed.json()['title'], len(renamed.json()['episodes'])) == ('새 이름', 2)


@pytest.mark.parametrize('which', ['repeated', 'others', 'missing', 'too_many', 'long_title'])
async def test_wrong_episodes_are_refused(client: AsyncClient, me: dict, friend: dict, which: str):
    first, second = await published_scenarios(client, me)
    others = (await published_scenarios(client, friend))[0]
    body = {
        'repeated': episodes(first, second, first),
        'others': episodes(first, others),
        'missing': episodes(first, str(uuid.uuid4())),
        'too_many': episodes(*[str(uuid.uuid4()) for _ in range(11)]),
        'long_title': [{'scenario_id': first, 'title': '가' * 31}],
    }[which]

    response = await client.post(CAMPAIGNS_URL, json={'title': '추격전', 'episodes': body}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
    assert (await client.get(CAMPAIGNS_URL, headers=me)).json()['total'] == 0


async def test_others_cannot_see_or_touch_a_campaign(client: AsyncClient, me: dict, friend: dict):
    campaign = await make_campaign(client, me, [])
    url = f'{CAMPAIGNS_URL}/{campaign["id"]}'

    for method, path, body in (
        ('GET', '', None),
        ('PATCH', '', {'title': 'x'}),
        ('DELETE', '', None),
        ('GET', '/publish-check', None),
        ('POST', '/versions', {}),
        ('GET', '/versions', None),
        ('GET', '/versions/1', None),
    ):
        response = await client.request(method, f'{url}{path}', json=body, headers=friend)
        assert response.status_code == status.HTTP_404_NOT_FOUND, (method, path)


async def test_a_scenario_in_a_campaign_cannot_be_deleted(client: AsyncClient, me: dict):
    first, second = await published_scenarios(client, me)
    campaign = await make_campaign(client, me, [first, second])

    refused = await client.delete(f'{SCENARIOS_URL}/{first}', headers=me)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['used_by'] == [{'id': campaign['id'], 'title': '추격전'}]
    # 캠페인을 지우면 시나리오를 지울 수 있다
    assert (await client.delete(f'{CAMPAIGNS_URL}/{campaign["id"]}', headers=me)).status_code == 204
    assert (await client.delete(f'{SCENARIOS_URL}/{first}', headers=me)).status_code == 204
    assert (await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}', headers=me)).status_code == 404


# --- 게시 ---


async def test_publishing_freezes_the_last_version_of_each_episode(client: AsyncClient, me: dict):
    first, second = await published_scenarios(client, me, progression=PROGRESSION)
    await publish_scenario(client, me, second)
    campaign = await make_campaign(client, me, [first, second])
    await client.patch(
        f'{CAMPAIGNS_URL}/{campaign["id"]}',
        json={'episodes': episodes(first, second, titles={first: '톨게이트'})},
        headers=me,
    )

    response = await publish(client, me, campaign, note='처음')

    assert response.status_code == status.HTTP_201_CREATED, response.text
    version = response.json()
    assert (version['number'], version['note']) == (1, '처음')
    snapshot = version['snapshot']
    assert snapshot['episodes'] == [
        {'scenario_id': first, 'version': 1, 'title': '톨게이트'},
        {'scenario_id': second, 'version': 2, 'title': '2편'},
    ]
    assert (snapshot['format'], snapshot['title'], snapshot['rating']) == (1, '추격전', 'all')

    # 시나리오를 다시 게시해도 앞의 판은 그대로, 캠페인을 다시 게시하면 새 번호다
    await publish_scenario(client, me, first)
    kept = await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}/versions/1', headers=me)
    assert kept.json()['snapshot']['episodes'][0]['version'] == 1
    again = await publish(client, me, campaign)
    assert again.json()['number'] == 2
    assert again.json()['snapshot']['episodes'][0]['version'] == 2
    listed = await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}/versions', headers=me)
    assert [one['number'] for one in listed.json()] == [2, 1]


@pytest.mark.parametrize('which', ['too_few', 'unpublished', 'other_rulebook', 'changed_rules'])
async def test_a_campaign_that_is_not_ready_is_refused(client: AsyncClient, me: dict, which: str):
    first, second = await published_scenarios(client, me)
    if which == 'too_few':
        chosen, expected = [first], ['episodes_too_few']
    elif which == 'unpublished':
        draft = await make_scenario(client, me, await make_rulebook(client, me), '초안')
        chosen, expected = [first, draft], ['episode_unpublished']
    elif which == 'other_rulebook':
        other = (await published_scenarios(client, me, 1))[0]
        chosen, expected = [first, other], ['rulebook_mismatch']
    else:
        # 같은 룰북이라도 규칙을 고친 뒤에 게시한 편은 규칙이 다르다
        rulebook_id = (await client.get(f'{SCENARIOS_URL}/{second}', headers=me)).json()['rulebook_id']
        await client.patch(f'{RULEBOOKS_URL}/{rulebook_id}', json={'progression': PROGRESSION}, headers=me)
        await publish_scenario(client, me, second)
        chosen, expected = [first, second], ['rulebook_mismatch']
    campaign = await make_campaign(client, me, chosen)

    response = await publish(client, me, campaign)

    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()['problems'] == expected
    assert await check(client, me, campaign) == {'ready': False, 'problems': expected, 'warnings': []}
    assert (await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}/versions', headers=me)).json() == []


async def test_an_adult_episode_makes_the_campaign_adult(client: AsyncClient, me: dict, adult_me: dict):
    rulebook_id = await make_rulebook(client, adult_me)
    plain = await make_scenario(client, adult_me, rulebook_id, '1편')
    adult = await make_scenario(client, adult_me, rulebook_id, '2편', rating='adult')
    for scenario_id in (plain, adult):
        await publish_scenario(client, adult_me, scenario_id)
    campaign = await make_campaign(client, adult_me, [plain, adult])

    refused = await publish(client, me, campaign)
    published = await publish(client, adult_me, campaign)

    assert refused.status_code == status.HTTP_403_FORBIDDEN
    assert published.json()['snapshot']['rating'] == 'adult'
    assert (await client.get(f'{CAMPAIGNS_URL}/{campaign["id"]}', headers=adult_me)).json()['rating'] == 'adult'


# --- 알림 ---


async def test_the_check_warns_about_what_will_not_carry(client: AsyncClient, me: dict):
    rulebook_id = await make_rulebook(client, me)
    lorebook = (await client.post(LOREBOOKS_URL, json={'title': '물건'}, headers=me)).json()
    entry = await client.post(
        f'{LOREBOOKS_URL}/{lorebook["id"]}/entries',
        json={'name': '횃불', 'kind': 'item', 'content': '불을 밝힌다.'},
        headers=me,
    )
    assert entry.status_code == status.HTTP_201_CREATED, entry.text
    first = await make_scenario(client, me, rulebook_id, '1편', lorebook_ids=[lorebook['id']])
    second = await make_scenario(client, me, rulebook_id, '2편')
    for scenario_id in (first, second):
        await publish_scenario(client, me, scenario_id)
    campaign = await make_campaign(client, me, [first, second])

    assert await check(client, me, campaign) == {
        'ready': True,
        'problems': [],
        'warnings': ['progression_missing', 'items_not_carried'],
    }
    # 뒤 편에도 그 물건이 있으면 알리지 않는다. 마지막 편의 물건은 보지 않는다
    reversed_order = await make_campaign(client, me, [second, first])
    assert (await check(client, me, reversed_order))['warnings'] == ['progression_missing']


async def test_a_growing_rulebook_has_no_warning(client: AsyncClient, me: dict):
    campaign = await make_campaign(client, me, await published_scenarios(client, me, progression=PROGRESSION))

    assert await check(client, me, campaign) == {'ready': True, 'problems': [], 'warnings': []}
