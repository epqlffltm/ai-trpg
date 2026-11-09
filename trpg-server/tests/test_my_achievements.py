# trpg-server/tests/test_my_achievements.py

"""
내가 받은 시나리오의 업적 전부(GET /achievements/mine, app/achievements/)를 검증한다. 마이페이지의 "내 업적"이 읽는다.

맵과 픽스처는 tests/test_scenario_achievements.py(그 안의 tests/test_happenings.py)의 것이다.

보는 것.
  - 모든 시나리오의 것을 받은 때가 늦은 것부터 쪽으로 준다. total 은 모두의 수다. 남의 것은 없다. 로그인해야 한다
  - 받았으므로 숨긴 업적도 이름과 그림이 있다. 이름은 받은 테이블의 판, 없으면 공개 중인 판의 것이다
  - 두 판 모두에 없으면(판에서 뺐다, 공개하지 않았다) 이름이 null 이고 기록은 남는다
  - listed: 공개 중이고 내가 볼 수 있으면 참. 공개하지 않음, 볼 수 없는 등급, 지운 시나리오는 거짓이다
  - 엔진이 테이블에서 준 업적은 공개하지 않은 시나리오여도 그 테이블의 판으로 이름을 안다
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from server_core.auth.tokens import AccessClaims
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.achievements.repository import EarnedRow
from app.achievements.service import find_definition, to_mine
from app.main import API_PREFIX
from tests import test_scenario_achievements as badges
from tests.test_happenings import publish
from tests.test_map_actions import going, play
from tests.test_table_items import FRIEND, ME

pytestmark = pytest.mark.usefixtures('clean_tables')

me = badges.me
friend = badges.friend
lore = badges.lore
more = badges.more

MINE_URL = f'{API_PREFIX}/achievements/mine'
EARLY = datetime(2026, 11, 1, tzinfo=UTC)


async def read_mine(client: AsyncClient, headers: dict, **query) -> dict:
    response = await client.get(MINE_URL, params=query, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def earned_at(session: AsyncSession, scenario_id: str, achievement_id: str, when: datetime) -> None:
    """받은 때를 정한다(차례를 시험하려고)."""
    await session.execute(
        text('UPDATE player_achievements SET earned_at = :when WHERE scenario_id = :s AND achievement_id = :a'),
        {'when': when, 's': uuid.UUID(scenario_id), 'a': achievement_id},
    )
    await session.commit()


async def test_it_lists_mine_from_every_scenario_latest_first(
    client: AsyncClient, me: dict, friend: dict, more: dict, session: AsyncSession
):
    first = await badges.listed_with(
        client, me, more, [badges.gate_badge(more), badges.square_badge(more, hidden=True)]
    )
    second = await badges.listed_with(client, me, more, [badges.gate_badge(more)])
    await badges.earned(session, first, 'gate', ME)
    await badges.earned(session, first, 'square', ME, FRIEND)
    await badges.earned(session, second, 'gate', ME)
    await earned_at(session, first, 'gate', EARLY)
    await earned_at(session, first, 'square', EARLY + timedelta(days=2))
    await earned_at(session, second, 'gate', EARLY + timedelta(days=1))

    page = await read_mine(client, me)

    assert page['total'] == 3
    assert [(item['scenario_id'], item['achievement_id']) for item in page['items']] == [
        (first, 'square'),
        (second, 'gate'),
        (first, 'gate'),
    ]
    hidden = page['items'][0]
    # 받았으므로 숨긴 업적도 이름과 설명이 있다
    assert (hidden['name'], hidden['description'], hidden['listed']) == ('광장에 서다', '광장에 닿았다', True)
    assert hidden['scenario_title'] == '성의 모험'
    assert 'when' not in hidden
    friends = await read_mine(client, friend)
    assert [(item['scenario_id'], item['achievement_id']) for item in friends['items']] == [(first, 'square')]


async def test_it_pages_with_limit_and_offset(client: AsyncClient, me: dict, more: dict, session: AsyncSession):
    scenario = await badges.listed_with(client, me, more, [badges.gate_badge(more), badges.square_badge(more)])
    await badges.earned(session, scenario, 'gate', ME)
    await badges.earned(session, scenario, 'square', ME)
    await earned_at(session, scenario, 'gate', EARLY)
    await earned_at(session, scenario, 'square', EARLY)

    one = await read_mine(client, me, limit=1)
    two = await read_mine(client, me, limit=1, offset=1)

    # 같은 때면 업적의 이름표 차례다. 쪽이 흔들리지 않는다
    assert [item['achievement_id'] for item in one['items'] + two['items']] == ['gate', 'square']
    assert (one['total'], two['total']) == (2, 2)
    assert (await read_mine(client, me, offset=5))['items'] == []


async def test_it_needs_a_login_and_a_sane_page(client: AsyncClient, me: dict):
    assert (await client.get(MINE_URL)).status_code == 401
    assert (await client.get(MINE_URL, params={'limit': 0}, headers=me)).status_code == 422
    assert (await client.get(MINE_URL, params={'limit': 101}, headers=me)).status_code == 422
    assert (await client.get(MINE_URL, params={'offset': -1}, headers=me)).status_code == 422
    assert await read_mine(client, me) == {'items': [], 'total': 0}


async def test_an_achievement_the_version_left_out_keeps_the_record_without_a_name(
    client: AsyncClient, me: dict, more: dict, session: AsyncSession
):
    scenario = await badges.listed_with(client, me, more, [badges.gate_badge(more)])
    await badges.earned(session, scenario, 'removed', ME)

    (item,) = (await read_mine(client, me))['items']

    assert (item['achievement_id'], item['name'], item['description'], item['image_id']) == (
        'removed',
        None,
        None,
        None,
    )
    assert item['listed'] is True


async def test_unlisted_adult_and_deleted_scenarios_are_not_listed(
    client: AsyncClient, me: dict, more: dict, session: AsyncSession
):
    draft = await badges.draft_with(client, me, more, [badges.gate_badge(more)])
    await publish(client, me, draft)
    adult = await badges.listed_with(client, me, more, [badges.gate_badge(more)])
    deleted = await badges.listed_with(client, me, more, [badges.gate_badge(more)])
    for scenario in (draft['id'], adult, deleted):
        await badges.earned(session, scenario, 'gate', ME)
    await session.execute(
        text('UPDATE listings SET rating = :r WHERE scenario_id = :s'), {'r': 'adult', 's': uuid.UUID(adult)}
    )
    await session.execute(text('UPDATE assets SET deleted_at = now() WHERE id = :s'), {'s': uuid.UUID(deleted)})
    await session.commit()

    items = {item['scenario_id']: item for item in (await read_mine(client, me))['items']}

    # 공개하지 않았고 테이블도 없으면 판을 알 수 없어 이름이 없다
    assert (items[draft['id']]['listed'], items[draft['id']]['name']) == (False, None)
    # 볼 수 없는 등급이어도 받은 것은 보인다. 소개를 열 수 없을 뿐이다
    assert (items[adult]['listed'], items[adult]['name']) == (False, '성문 앞')
    assert (items[deleted]['listed'], items[deleted]['name']) == (False, '성문 앞')


async def test_the_table_where_it_was_earned_names_it(
    client: AsyncClient, me: dict, friend: dict, more: dict, narrated
):
    table = await badges.started(client, me, friend, more, [badges.square_badge(more, hidden=True)])
    await play(client, me, friend, table, narrated, mine=going(more['square']))

    (item,) = (await read_mine(client, friend))['items']

    # 공개하지 않은 시나리오지만 받은 테이블의 판이 있다
    assert (item['achievement_id'], item['name'], item['listed']) == ('square', '광장에 서다', False)


def row(played: list | None, listed: list | None, **fields) -> EarnedRow:
    values = {
        'scenario_id': uuid.uuid4(),
        'achievement_id': 'gate',
        'earned_at': EARLY,
        'title': '제목',
        'deleted': False,
        'played': played,
        'listed': listed,
        'listing_rating': 'all' if listed is not None else None,
    }
    return EarnedRow(**{**values, **fields})


def test_the_table_version_comes_before_the_listed_one():
    viewer = AccessClaims(user_id=ME, expires_at=EARLY)
    then = [{'id': 'gate', 'name': '그때의 이름', 'when': []}]
    now = [{'id': 'gate', 'name': '지금의 이름', 'when': []}, 'broken']

    assert to_mine(row(then, now), viewer).name == '그때의 이름'
    assert to_mine(row(None, now), viewer).name == '지금의 이름'
    assert to_mine(row([{'id': 'other', 'name': 'x', 'when': []}], now), viewer).name == '지금의 이름'
    assert to_mine(row(None, None), viewer).name is None
    assert find_definition(now, 'missing') is None
    assert to_mine(row(None, now, listing_rating=None), viewer).listed is False
