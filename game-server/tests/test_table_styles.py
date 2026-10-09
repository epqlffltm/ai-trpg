# game-server/tests/test_table_styles.py

"""
테이블의 서술 문체를 검증한다(app/tables/styles.py).

보는 것은 넷이다.
  - 만들 때 고르지 않으면 판의 추천 문체다. 고르면 그것이다.
  - 로비에서 들어가기 전에 문체가 보인다.
  - 방장만 바꾼다. 진행 중에도 되고, 끝난 테이블은 안 된다. null 이면 추천 문체로 돌아간다.
  - 바꾼 것은 이벤트로 남는다. 바뀐 것이 없으면 남기지 않는다.

문체가 서술자에게 어떻게 가는지는 tests/test_round_closing.py 와 tests/test_prompt.py 가 본다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import API_PREFIX
from app.tables.models import GameTable
from tests.sheets import SHEET
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 엘프 폭주족이 톨게이트를 넘는다.']

# 테이블이 만들어질 때 적히는 이벤트의 수(table_created). 그 뒤의 것만 본다
CREATED_EVENTS = 1


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 방장이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


def style_url(table: dict) -> str:
    """테이블의 서술 문체를 바꾸는 주소."""
    return table_url(table, '/narration-style')


async def publish(client: AsyncClient, me: dict, recommended: str) -> dict:
    """제작자가 recommended 를 추천한 시나리오를 게시한다. 판의 번호는 1 이다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {
        'title': '추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': OPENINGS,
        'default_sheet': SHEET,
        'narration_style': recommended,
    }
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    return scenario


async def open_table(client: AsyncClient, me: dict, recommended: str = 'hardboiled', **table_fields) -> dict:
    """제작자가 recommended 를 추천한 시나리오의 1번 판으로 테이블을 연다."""
    scenario = await publish(client, me, recommended)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2, **table_fields}
    response = await client.post(TABLES_URL, json=body, headers=me)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def join(client: AsyncClient, headers: dict[str, str], table: dict) -> None:
    """초대 코드로 테이블에 들어간다."""
    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def start(client: AsyncClient, me: dict, table: dict) -> None:
    """혼자 앉은 테이블을 시작한다."""
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    response = await client.post(table_url(table, '/start'), headers=me)
    assert response.status_code == status.HTTP_200_OK, response.text


async def events_after_creation(client: AsyncClient, headers: dict[str, str], table: dict) -> list[dict]:
    """테이블이 만들어진 뒤에 적힌 이벤트들."""
    params = {'after': CREATED_EVENTS}
    response = await client.get(table_url(table, '/events'), params=params, headers=headers)
    return response.json()['items']


# --- 만들 때 ---


async def test_a_table_takes_the_recommended_style_unless_the_host_chooses(client: AsyncClient, me: dict):
    recommended = await open_table(client, me, recommended='hardboiled')
    chosen = await open_table(client, me, recommended='hardboiled', narration_style='dopamine')

    assert (recommended['narration_style'], recommended['recommended_narration_style']) == (
        'hardboiled',
        'hardboiled',
    )
    # 방장이 고른 것이 이긴다. 추천은 화면이 "추천"을 표시하도록 함께 나간다
    assert (chosen['narration_style'], chosen['recommended_narration_style']) == ('dopamine', 'hardboiled')


async def test_a_table_rejects_a_style_it_does_not_know(client: AsyncClient, me: dict):
    scenario = await publish(client, me, 'hardboiled')
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2, 'narration_style': 'shakespeare'}

    response = await client.post(TABLES_URL, json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_lobby_shows_the_style_before_joining(client: AsyncClient, me: dict, stranger: dict):
    await open_table(client, me, recommended='literary', is_public=True)

    response = await client.get(f'{TABLES_URL}/lobby', headers=stranger)

    (table,) = response.json()['items']
    assert table['narration_style'] == 'literary'


# --- 바꾸기 ---


async def test_the_host_changes_the_style(client: AsyncClient, me: dict, friend: dict):
    table = await open_table(client, me)
    await join(client, friend, table)

    response = await client.put(style_url(table), json={'narration_style': 'web_novel'}, headers=me)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['narration_style'] == 'web_novel'
    # 앉은 사람 모두가 이벤트로 본다. 누가 바꿨는지와 무엇으로 바꿨는지가 적힌다
    changed = (await events_after_creation(client, friend, table))[-1]
    assert (changed['type'], changed['actor_id'], changed['payload']) == (
        'narration_style_changed',
        str(ME),
        {'narration_style': 'web_novel'},
    )


async def test_null_brings_back_the_recommended_style(client: AsyncClient, me: dict):
    table = await open_table(client, me, recommended='hardboiled', narration_style='dopamine')

    response = await client.put(style_url(table), json={'narration_style': None}, headers=me)

    assert response.json()['narration_style'] == 'hardboiled'
    changed = (await events_after_creation(client, me, table))[-1]
    assert changed['payload'] == {'narration_style': 'hardboiled'}


async def test_choosing_the_same_style_records_nothing(client: AsyncClient, me: dict):
    table = await open_table(client, me, recommended='hardboiled')

    same = await client.put(style_url(table), json={'narration_style': 'hardboiled'}, headers=me)
    back = await client.put(style_url(table), json={'narration_style': None}, headers=me)

    # 바뀐 것이 없다. 이벤트가 쌓이지 않는다
    assert (same.status_code, back.status_code) == (status.HTTP_200_OK, status.HTTP_200_OK)
    assert back.json()['narration_style'] == 'hardboiled'
    assert await events_after_creation(client, me, table) == []


async def test_the_style_can_change_while_playing(client: AsyncClient, me: dict):
    table = await open_table(client, me)
    await start(client, me, table)

    response = await client.put(style_url(table), json={'narration_style': 'literary'}, headers=me)

    assert response.status_code == status.HTTP_200_OK
    assert (response.json()['status'], response.json()['narration_style']) == ('playing', 'literary')


async def test_only_the_host_changes_the_style(client: AsyncClient, me: dict, friend: dict, stranger: dict):
    table = await open_table(client, me)
    await join(client, friend, table)

    by_member = await client.put(style_url(table), json={'narration_style': 'action'}, headers=friend)
    by_stranger = await client.put(style_url(table), json={'narration_style': 'action'}, headers=stranger)

    assert by_member.status_code == status.HTTP_403_FORBIDDEN
    # 앉지 않은 사람에게는 테이블이 있는지도 알려 주지 않는다
    assert by_stranger.status_code == status.HTTP_404_NOT_FOUND
    seen = await client.get(table_url(table), headers=me)
    assert seen.json()['narration_style'] == 'hardboiled'


async def test_an_ended_table_keeps_its_style(client: AsyncClient, me: dict):
    table = await open_table(client, me)
    await client.post(table_url(table, '/end'), headers=me)

    response = await client.put(style_url(table), json={'narration_style': 'action'}, headers=me)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'already_ended'


@pytest.mark.parametrize('body', [{}, {'narration_style': 'shakespeare'}, {'narration_style': 'action', 'x': 1}])
async def test_a_bad_style_change_is_refused(client: AsyncClient, me: dict, body: dict):
    table = await open_table(client, me)

    response = await client.put(style_url(table), json=body, headers=me)

    # 칸을 빼먹은 것을 "추천으로 돌려라"로 읽지 않는다. 돌리려면 null 을 적어 보낸다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_database_rejects_a_style_it_does_not_know(client: AsyncClient, me: dict, session: AsyncSession):
    table = await open_table(client, me)

    with pytest.raises(IntegrityError, match='narration_style_allowed'):
        await session.execute(
            update(GameTable).where(GameTable.id == uuid.UUID(table['id'])).values(narration_style='shakespeare')
        )
