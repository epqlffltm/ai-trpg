# trpg-server/tests/test_scenario_achievements.py

"""
시나리오의 업적(app/achievements/, docs/architecture/achievements.md)을 검증한다. 제작자가 작품에 다는 업적이다.

맵과 픽스처는 tests/test_happenings.py 의 것이다. 성문(시작)-광장 큰길, 광장→지하실 숨긴 길, 탑은 명소,
사건 항목 셋(함정, 휩쓸림, 왕녀 구출), 맵 밖의 장소(지하 감옥).

보는 것.
  - 시나리오: 업적을 저장하고 판에 굳힌다. 잘못 둔 것은 422, 게시할 수 없는 것은 409 의 문제다.
    남의 그림은 422(achievements.image_id)다. 업적이 없던 판은 업적이 없는 것으로 읽는다
  - 라운드: 조건이 채워지면 앉은 플레이어 모두가 받는다(죽은 캐릭터의 사람도). 테이블에서 한 번이다.
    퀘스트를 본 뒤라 같은 라운드의 성공으로 받는다. 이벤트는 achievement_earned 다. 플레이한 사람이 적힌다
  - 되돌리기: 테이블의 기록은 되돌아가고 계정의 기록은 남는다
  - 기록: 같은 사람이 같은 업적을 다시 받거나 같은 시나리오를 다시 플레이해도 줄은 하나다(처음 것이 남는다)
  - 공개: 업적 목록과 받은 수, 플레이한 사람의 수. 숨긴 업적은 받기 전에 가린다. 로그인하지 않아도 본다
  - 탈퇴: 받은 업적과 플레이의 기록을 지운다
기록과 공개의 시험은 기록을 직접 적는다(엔진을 돌리지 않고 수를 정하려고).
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements import repository as achievement_rows
from app.assets.scenarios.snapshot import read_snapshot
from app.main import API_PREFIX
from app.portraits.seats import table_portraits
from app.withdrawal.service import erase_belongings
from tests import test_happenings as happenings
from tests import test_table_map as map_tables
from tests.asset_server import FakeAsset
from tests.narration_model import asset_body
from tests.test_happenings import draft, publish, reach, start
from tests.test_listings_api import listing_url, write_page
from tests.test_map_actions import going, play
from tests.test_table_items import FRIEND, ME, SCENARIOS_URL, events_of, kill
from tests.test_table_map import put_at

pytestmark = pytest.mark.usefixtures('clean_tables')

me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore
more = happenings.more

LISTINGS_URL = f'{API_PREFIX}/listings'
PORTRAITS_URL = f'{API_PREFIX}/portraits'


def achievement(id_: str, when: list[dict], **fields) -> dict:
    return {'id': id_, 'name': fields.pop('name', id_), 'when': when, **fields}


def square_badge(more: dict, **fields) -> dict:
    """광장에 닿으면 받는 업적."""
    return achievement('square', [reach(more['square'])], name='광장에 서다', description='광장에 닿았다', **fields)


def gate_badge(more: dict, **fields) -> dict:
    """성문에 서 있으면 받는 업적. 시작하자마자 채워진다."""
    return achievement('gate', [reach(more['gate'])], name='성문 앞', description='성문에 섰다', **fields)


async def draft_with(client: AsyncClient, me: dict, more: dict, achievements: list[dict]) -> dict:
    """그 업적들을 적은 시나리오. 맵은 the_map 이다. 게시하지 않았다."""
    scenario = await draft(client, me, more, [])
    response = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'achievements': achievements}, headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def listed_with(client: AsyncClient, me: dict, more: dict, achievements: list[dict]) -> str:
    """그 업적들을 적어 판 1 로 게시하고 공개한 시나리오의 id."""
    scenario = await draft_with(client, me, more, achievements)
    assert (await publish(client, me, scenario)).status_code == status.HTTP_201_CREATED
    await write_page(client, me, scenario)
    response = await client.put(f'{listing_url(scenario)}/publication', json={'version': 1}, headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text
    return scenario['id']


async def earned(session: AsyncSession, scenario_id: str, achievement_id: str, *user_ids: uuid.UUID) -> None:
    """그 사람들이 플레이했고 그 업적을 받았다고 적는다. 엔진이 할 일을 테스트가 대신한다."""
    await achievement_rows.mark_played(session, uuid.UUID(scenario_id), list(user_ids))
    await achievement_rows.save_earned(session, uuid.UUID(scenario_id), None, achievement_id, list(user_ids))
    await session.commit()


async def read_public(client: AsyncClient, scenario_id: str, headers: dict | None = None) -> dict:
    response = await client.get(f'{LISTINGS_URL}/{scenario_id}/achievements', headers=headers or {})
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def player_rows(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """그 사람의 업적의 줄 수와 플레이의 줄 수."""
    earned_count = await session.scalar(
        text('SELECT count(*) FROM player_achievements WHERE user_id = :u'), {'u': user_id}
    )
    played = await session.scalar(text('SELECT count(*) FROM scenario_players WHERE user_id = :u'), {'u': user_id})
    return earned_count, played


# --- 시나리오 ---


async def test_achievements_are_saved_and_published(client: AsyncClient, me: dict, more: dict):
    scenario = await draft_with(client, me, more, [square_badge(more, hidden=True)])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED, response.text
    assert scenario['achievements'] == [
        {
            'id': 'square',
            'name': '광장에 서다',
            'description': '광장에 닿았다',
            'hidden': True,
            'image_id': None,
            'when': [{'kind': 'reach_place', 'target': more['square']['id'], 'count': 1, 'consume': False}],
            'match': 'all',
        }
    ]
    (published,) = read_snapshot(response.json()['snapshot']).achievements
    assert (published.id, published.hidden, published.when[0].target) == (
        'square',
        True,
        uuid.UUID(more['square']['id']),
    )


@pytest.mark.parametrize('case', ['no-condition', 'consume', 'twice', 'long-name', 'no-name'])
async def test_a_misplaced_achievement_is_refused(client: AsyncClient, me: dict, more: dict, case: str):
    potion = {'kind': 'hold_item', 'target': more['potion']['id'], 'consume': True}
    rules = {
        'no-condition': [achievement('a', [])],
        'consume': [achievement('a', [potion])],
        'twice': [square_badge(more), square_badge(more)],
        'long-name': [achievement('a', [reach(more['square'])], name='가' * 41)],
        'no-name': [achievement('a', [reach(more['square'])], name=' ')],
    }
    body = {'title': '성의 모험', 'achievements': rules[case]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    ('case', 'problem'),
    [
        ('missing', 'achievement_condition_missing'),
        ('invalid', 'achievement_condition_invalid'),
        ('impossible', 'achievement_condition_impossible'),
    ],
)
async def test_an_achievement_must_be_possible(client: AsyncClient, me: dict, more: dict, case: str, problem: str):
    conditions = {
        'missing': reach({'id': str(uuid.uuid4())}),
        'invalid': reach(more['potion']),
        # 맵에 없는 장소에는 아무도 설 수 없다
        'impossible': reach(more['dungeon']),
    }
    scenario = await draft_with(client, me, more, [achievement('a', [conditions[case]])])

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == [problem]


@pytest.fixture
def asset(app: FastAPI) -> FakeAsset:
    fake = FakeAsset()
    app.state.asset = fake
    return fake


async def upload(client: AsyncClient, headers: dict) -> str:
    response = await client.post(PORTRAITS_URL, content=b'\x89PNG trophy', headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()['id']


@pytest.mark.usefixtures('asset')
async def test_someone_elses_image_is_refused(client: AsyncClient, me: dict, friend: dict, more: dict):
    theirs = await upload(client, friend)
    body = {'title': '성의 모험', 'achievements': [square_badge(more, image_id=theirs)]}

    response = await client.post(SCENARIOS_URL, json=asset_body(SCENARIOS_URL, body), headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'achievements.image_id' in response.json()['detail']


@pytest.mark.usefixtures('asset')
async def test_an_image_in_use_by_an_achievement_is_kept(client: AsyncClient, me: dict, more: dict):
    mine = await upload(client, me)
    await draft_with(client, me, more, [square_badge(more, image_id=mine)])

    response = await client.delete(f'{PORTRAITS_URL}/{mine}', headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT


async def test_a_snapshot_without_achievements_reads_as_none(client: AsyncClient, me: dict, more: dict):
    # 업적이 생기기 전에 굳힌 판에는 칸이 없다. 비워도 되는 칸이라 형식이 그대로이고 빈 목록으로 읽는다
    published = await publish(client, me, await draft(client, me, more, []))
    document = {key: value for key, value in published.json()['snapshot'].items() if key != 'achievements'}

    assert read_snapshot(document).achievements == []


async def started(client: AsyncClient, me: dict, friend: dict, more: dict, achievements: list[dict], **fields):
    """그 업적들로 둘이 앉아 시작한 테이블. 맵은 the_map 이다."""
    return await start(client, me, friend, more, [], achievements=achievements, **fields)


# --- 라운드 ---


async def test_everyone_seated_earns_it_when_the_condition_is_met(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await started(client, me, friend, more, [square_badge(more)])

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    # 광장에 선 것은 기사뿐이지만 앉은 사람 모두가 받는다(협동의 업적)
    (earned,) = await events_of(client, friend, table, 'achievement_earned')
    assert earned['actor_id'] is None
    assert earned['payload'] == {
        'round': 1,
        'achievement_id': 'square',
        'name': '광장에 서다',
        'description': '광장에 닿았다',
        'image_id': None,
        'users': [
            {'user_id': str(ME), 'character_name': '기사'},
            {'user_id': str(FRIEND), 'character_name': '약사'},
        ],
    }


async def test_an_achievement_is_earned_once_per_table(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await started(client, me, friend, more, [square_badge(more)])
    await play(client, me, friend, table, narrated, mine=going(more['square']))

    await put_at(session, table, ME, more['square'])
    await play(client, me, friend, table, narrated)

    assert len(await events_of(client, me, table, 'achievement_earned')) == 1


async def test_nothing_is_earned_until_the_condition_is_met(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await started(client, me, friend, more, [square_badge(more)])

    await play(client, me, friend, table, narrated)

    assert await events_of(client, me, table, 'achievement_earned') == []
    # 플레이한 것은 적힌다(달성률의 분모)
    assert await player_rows(session, ME) == (0, 1)


async def test_the_dead_are_still_at_the_table(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    gate = achievement('gate', [reach(more['gate'])])
    table = await started(client, me, friend, more, [gate])
    await kill(session, FRIEND)

    await happenings.play_alone(client, me, table, narrated)

    (earned,) = await events_of(client, me, table, 'achievement_earned')
    assert [user['character_name'] for user in earned['payload']['users']] == ['기사', '약사']


async def test_a_quest_success_earns_it_in_the_same_round(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    rescue = {'entry_id': more['rescue']['id'], 'start': 'active', 'conditions': [reach(more['square'])]}
    hero = achievement('hero', [{'kind': 'quest_succeeded', 'target': more['rescue']['id']}])
    table = await started(client, me, friend, more, [hero], quests=[rescue])

    await play(client, me, friend, table, narrated, mine=going(more['square']))

    (changed,) = await events_of(client, me, table, 'quest_changed')
    (earned,) = await events_of(client, me, table, 'achievement_earned')
    (closed,) = await events_of(client, me, table, 'round_closed')
    assert changed['sequence'] < earned['sequence'] < closed['sequence']


# --- 기록 ---


async def test_earning_it_again_keeps_the_first(client: AsyncClient, me: dict, more: dict, session: AsyncSession):
    scenario_id = await listed_with(client, me, more, [gate_badge(more)])
    await earned(session, scenario_id, 'gate', ME)
    query = text('SELECT earned_at FROM player_achievements WHERE user_id = :u')
    first = await session.scalar(query, {'u': ME})

    await earned(session, scenario_id, 'gate', ME)

    assert await session.scalar(query, {'u': ME}) == first
    assert await player_rows(session, ME) == (1, 1)


# --- 공개 ---


async def test_the_listing_shows_the_achievements_and_how_many_earned_them(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession
):
    scenario_id = await listed_with(client, me, more, [gate_badge(more), square_badge(more, hidden=True)])
    await earned(session, scenario_id, 'gate', ME, FRIEND)

    anonymous = await read_public(client, scenario_id)
    mine = await read_public(client, scenario_id, me)

    assert anonymous['players'] == 2
    first, hidden = anonymous['items']
    assert (first['id'], first['name'], first['earned_count'], first['earned_at']) == ('gate', '성문 앞', 2, None)
    # 숨긴 업적은 받기 전에 이름과 설명을 가린다. 받은 수는 보인다
    assert (hidden['id'], hidden['hidden'], hidden['name'], hidden['description']) == ('square', True, None, None)
    assert hidden['earned_count'] == 0
    assert mine['items'][0]['earned_at'] is not None
    assert 'when' not in first


async def test_a_hidden_achievement_shows_once_earned(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession
):
    scenario_id = await listed_with(client, me, more, [square_badge(more, hidden=True)])
    await earned(session, scenario_id, 'square', FRIEND)

    (seen,) = (await read_public(client, scenario_id, friend))['items']
    (veiled,) = (await read_public(client, scenario_id, me))['items']

    assert (seen['name'], seen['description'], seen['earned_count']) == ('광장에 서다', '광장에 닿았다', 1)
    assert (veiled['name'], veiled['earned_at']) == (None, None)


async def test_an_achievement_left_out_of_the_version_is_not_shown(
    client: AsyncClient, me: dict, more: dict, session: AsyncSession
):
    scenario_id = await listed_with(client, me, more, [gate_badge(more)])
    await earned(session, scenario_id, 'removed', ME)

    response = await read_public(client, scenario_id, me)

    assert [item['id'] for item in response['items']] == ['gate']


async def test_an_unlisted_scenario_has_no_achievements_to_show(client: AsyncClient, me: dict, more: dict):
    scenario = await draft_with(client, me, more, [square_badge(more)])
    await publish(client, me, scenario)

    response = await client.get(f'{LISTINGS_URL}/{scenario["id"]}/achievements')

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.usefixtures('asset')
async def test_the_image_is_served_with_the_listing(client: AsyncClient, me: dict, more: dict):
    mine = await upload(client, me)
    scenario_id = await listed_with(client, me, more, [square_badge(more, image_id=mine)])

    listed = await client.get(f'{LISTINGS_URL}/{scenario_id}/portraits/{mine}/image')

    assert listed.status_code == status.HTTP_200_OK
    assert uuid.UUID(mine) in table_portraits({'achievements': [{'image_id': mine}]})


# --- 탈퇴 ---


async def test_withdrawal_erases_the_achievements(client: AsyncClient, me: dict, more: dict, session: AsyncSession):
    scenario_id = await listed_with(client, me, more, [gate_badge(more)])
    await earned(session, scenario_id, 'gate', ME, FRIEND)

    await erase_belongings(session, FRIEND)

    assert await player_rows(session, FRIEND) == (0, 0)
    assert await player_rows(session, ME) == (1, 1)


# --- 되돌리기 ---


async def test_reverting_the_round_takes_it_back_from_the_table_but_not_the_account(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession, narrated
):
    table = await started(client, me, friend, more, [achievement('gate', [reach(more['gate'])])])
    await play(client, me, friend, table, narrated)

    reverted = await client.post(f'{API_PREFIX}/tables/{table["id"]}/rounds/current/revert', headers=me)

    assert reverted.status_code == status.HTTP_200_OK, reverted.text
    rows = await session.scalar(text('SELECT count(*) FROM table_achievements WHERE table_id = :t'), {'t': table['id']})
    assert rows == 0
    # 계정에 남은 업적은 되돌리지 않는다
    assert await player_rows(session, ME) == (1, 1)
