# game-server/tests/test_rounds_api.py

"""
라운드를 검증한다. 선언을 모으고, 닫고, 다음 라운드로 넘어가는 한 바퀴.

보는 것은 다섯이다.
  - 테이블을 시작하면 첫 라운드가 열린다. 장면은 고른 스타팅이다.
  - 앉은 사람이 모두 선언을 내면 라운드가 닫기 시작하고, 서술이 끝나면 다음 라운드가 열린다.
    방장은 기다리지 않고 닫을 수 있다.
  - 선언을 받는 동안에는 남의 선언의 글이 보이지 않는다. 누가 냈는지만 보인다. 마감하면 모두 보인다.
  - 라운드는 테이블에 앉은 사람만 본다. 선언과 닫기는 진행 중인 테이블에서만 된다.
  - 서술자는 글만 쓴다. 바꿔 끼울 수 있다. 테스트는 가짜 서술자를 쓴다.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType, Scenario, ScenarioVersion
from app.main import API_PREFIX
from app.rounds.models import DECLARATION_MAX_LENGTH, Declaration, Round
from app.rounds.narrator import NarrationRequest
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
NO_SUCH_ID = '00000000-0000-4000-8000-000000000000'

# 테스트에 쓰는 예시. 내용은 아무 뜻이 없다
OPENINGS = ['사이렌이 울린다. 망치를 든 드워프가 쫓아온다.', '법정이다. 17번째 사형 선고가 내려진다.']
GM_GUIDE = '진지한 장면은 금지다. 모든 추격은 바이크로 한다.'
MY_ACTION = '바이크에 시동을 건다.'
FRIENDS_ACTION = '드워프에게 손을 흔든다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 테이블을 여는 방장이다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말. 캐릭터는 '영애'다."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def rounds_url(table: dict, path: str = '') -> str:
    """테이블의 라운드 주소."""
    return f'{TABLES_URL}/{table["id"]}/rounds{path}'


async def open_table(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """내 시나리오를 만들어 그 판으로 테이블을 연다. 아직 시작하지 않은 테이블을 돌려준다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'gm_guide': GM_GUIDE}, headers=headers)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS, 'default_sheet': SHEET}
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=headers)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2, **fields}
    response = await client.post(TABLES_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def start_solo(client: AsyncClient, me: dict[str, str], **fields) -> dict:
    """나 혼자 앉은 테이블을 시작한다."""
    table = await open_table(client, me, **fields)
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '엘프'}, headers=me)
    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str], **fields) -> dict:
    """나와 친구가 앉은 테이블을 시작한다."""
    table = await open_table(client, me, **fields)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '엘프'}, headers=me)
    await client.put(f'{TABLES_URL}/{table["id"]}/character', json={'name': '영애'}, headers=friend)
    started = await client.post(f'{TABLES_URL}/{table["id"]}/start', headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def declare(client: AsyncClient, headers: dict[str, str], table: dict, content: str) -> dict:
    """선언을 내고, 돌아온 라운드를 돌려준다."""
    response = await client.put(rounds_url(table, '/current/declaration'), json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def current(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """가장 최근 라운드를 읽는다."""
    response = await client.get(rounds_url(table, '/current'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def contents(round_: dict) -> dict[str, str | None]:
    """라운드의 선언을 {캐릭터 이름: 글} 로 바꾼다."""
    return {declaration['character_name']: declaration['content'] for declaration in round_['declarations']}


# --- 로그인 ---


@pytest.mark.parametrize(
    ('method', 'path'),
    [('GET', ''), ('GET', '/current'), ('GET', '/1'), ('PUT', '/current/declaration'), ('POST', '/current/close')],
)
async def test_every_address_requires_login(client: AsyncClient, method: str, path: str):
    response = await client.request(method, f'{TABLES_URL}/{NO_SUCH_ID}/rounds{path}', json={})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 테이블을 시작하면 첫 라운드가 열린다 ---


async def test_starting_the_table_opens_the_first_round(client: AsyncClient, me: dict[str, str]):
    table = await start_solo(client, me, opening_index=1)

    round_ = await current(client, me, table)

    # 첫 장면은 테이블을 만들 때 고른 스타팅이다
    assert (round_['number'], round_['scene'], round_['status']) == (1, OPENINGS[1], 'open')
    assert round_['declarations'] == []
    assert round_['waiting_for'] == [str(ME)]
    assert (round_['closing_at'], round_['closed_at']) == (None, None)


async def test_a_table_that_has_not_started_has_no_round(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    responses = [
        await client.get(rounds_url(table, '/current'), headers=me),
        await client.put(rounds_url(table, '/current/declaration'), json={'content': MY_ACTION}, headers=me),
        await client.post(rounds_url(table, '/current/close'), headers=me),
    ]
    listed = await client.get(rounds_url(table), headers=me)

    assert [response.status_code for response in responses] == [status.HTTP_409_CONFLICT] * 3
    assert [response.json()['reason'] for response in responses] == ['not_started'] * 3
    assert listed.json() == {'items': [], 'total': 0}


# --- 선언 ---


async def test_declares_and_changes_the_declaration(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_duo(client, me, friend)

    first = await declare(client, me, table, MY_ACTION)
    changed = await declare(client, me, table, '  마음을 바꿔 뒤로 달린다.\n')

    assert contents(first) == {'엘프': MY_ACTION}
    assert first['waiting_for'] == [str(FRIEND)]
    # 닫히기 전에는 고칠 수 있다. 통째로 바뀐다. 앞뒤 공백은 그대로 둔다
    assert contents(changed) == {'엘프': '  마음을 바꿔 뒤로 달린다.\n'}
    assert (changed['number'], changed['status']) == (1, 'open')


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'content': ''},
        {'content': '   \n  '},
        {'content': '가' * (DECLARATION_MAX_LENGTH + 1)},
        {'content': None},
        # 선언은 하려는 일이다. 결과나 숫자를 함께 적어 보낼 수 없다
        {'content': MY_ACTION, 'result': '성공'},
        {'content': MY_ACTION, 'character_name': '드워프'},
    ],
)
async def test_rejects_a_bad_declaration(client: AsyncClient, me: dict[str, str], friend: dict, body: dict):
    table = await start_duo(client, me, friend)

    response = await client.put(rounds_url(table, '/current/declaration'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await current(client, me, table))['declarations'] == []


async def test_others_declarations_are_hidden_until_the_round_closes(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, MY_ACTION)

    seen_by_friend = await client.get(rounds_url(table, '/current'), headers=friend)
    listed_for_friend = await client.get(rounds_url(table), headers=friend)

    # 누가 냈는지는 보인다. 무엇을 냈는지는 보이지 않는다
    assert contents(seen_by_friend.json()) == {'엘프': None}
    assert seen_by_friend.json()['waiting_for'] == [str(FRIEND)]
    assert MY_ACTION not in seen_by_friend.text
    assert MY_ACTION not in listed_for_friend.text
    # 낸 사람은 자기 것을 본다
    assert contents(await current(client, me, table)) == {'엘프': MY_ACTION}


# --- 모두 내면 닫히고 다음 라운드가 열린다 ---


async def test_the_round_closes_when_everyone_has_declared(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, MY_ACTION)

    after_last = await declare(client, friend, table, FRIENDS_ACTION)

    # 마지막 사람의 선언에 대한 답으로 닫는 중인 라운드가 온다. 서술은 뒤에서 돈다
    assert (after_last['number'], after_last['status']) == (1, 'closing')
    assert after_last['waiting_for'] == []
    # 선언을 마감했으므로 모두의 선언이 보인다
    assert contents(after_last) == {'엘프': MY_ACTION, '영애': FRIENDS_ACTION}

    await narrated()

    # 서술이 끝나면 다음 라운드가 열려 있다. 가짜 서술자의 글이 장면이 된다. 앉은 순서대로 적힌다
    second = await current(client, me, table)
    assert (second['number'], second['status']) == (2, 'open')
    assert second['scene'] == f'[1 라운드의 결과]\n엘프: {MY_ACTION}\n영애: {FRIENDS_ACTION}'
    assert second['declarations'] == []
    assert second['waiting_for'] == [str(ME), str(FRIEND)]
    # 앞의 라운드는 닫혔다
    closed = (await client.get(rounds_url(table, '/1'), headers=friend)).json()
    assert (closed['status'], closed['waiting_for']) == ('closed', [])
    assert closed['closing_at'] is not None
    assert closed['closed_at'] is not None
    assert contents(closed) == {'엘프': MY_ACTION, '영애': FRIENDS_ACTION}


async def test_a_solo_round_closes_at_once(client: AsyncClient, me: dict[str, str], narrated):
    table = await start_solo(client, me)

    first = await declare(client, me, table, MY_ACTION)
    await narrated()
    second = await declare(client, me, table, '속도를 올린다.')
    await narrated()

    # 혼자면 낼 때마다 한 바퀴가 돈다
    assert (first['number'], second['number']) == (1, 2)
    third = await current(client, me, table)
    assert (third['number'], third['scene']) == (3, '[2 라운드의 결과]\n엘프: 속도를 올린다.')


async def test_a_closed_round_takes_no_more_declarations(client: AsyncClient, me: dict[str, str], narrated):
    table = await start_solo(client, me)
    await declare(client, me, table, MY_ACTION)
    await narrated()

    await declare(client, me, table, '속도를 올린다.')

    # 새 선언은 열려 있는 라운드로 간다. 닫힌 라운드는 그대로다
    first = (await client.get(rounds_url(table, '/1'), headers=me)).json()
    assert contents(first) == {'엘프': MY_ACTION}


# --- 방장은 기다리지 않고 닫을 수 있다 ---


async def test_the_host_closes_the_round_without_waiting(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, MY_ACTION)

    by_member = await client.post(rounds_url(table, '/current/close'), headers=friend)
    by_host = await client.post(rounds_url(table, '/current/close'), headers=me)

    assert by_member.status_code == status.HTTP_403_FORBIDDEN
    # 202: 접수했다는 뜻이다. 서술은 뒤에서 돈다
    assert by_host.status_code == status.HTTP_202_ACCEPTED
    assert (by_host.json()['number'], by_host.json()['status']) == (1, 'closing')

    await narrated()

    # 선언을 내지 않은 사람은 아무것도 하지 않은 것으로 넘어간다
    second = await current(client, me, table)
    assert second['number'] == 2
    assert second['scene'] == f'[1 라운드의 결과]\n엘프: {MY_ACTION}\n영애: 아무것도 하지 않았다.'
    assert contents((await client.get(rounds_url(table, '/1'), headers=me)).json()) == {'엘프': MY_ACTION}


async def test_the_host_can_close_a_round_nobody_declared_in(client: AsyncClient, me: dict[str, str], narrated):
    table = await start_solo(client, me)

    response = await client.post(rounds_url(table, '/current/close'), headers=me)
    await narrated()

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert (await current(client, me, table))['scene'] == '[1 라운드의 결과]\n엘프: 아무것도 하지 않았다.'


# --- 진행 중인 테이블에서만 ---


async def test_an_ended_table_keeps_its_rounds_but_takes_nothing_new(client: AsyncClient, me: dict, narrated):
    table = await start_solo(client, me)
    await declare(client, me, table, MY_ACTION)
    await narrated()
    await client.post(f'{TABLES_URL}/{table["id"]}/end', headers=me)

    responses = [
        await client.put(rounds_url(table, '/current/declaration'), json={'content': MY_ACTION}, headers=me),
        await client.post(rounds_url(table, '/current/close'), headers=me),
    ]

    assert [response.status_code for response in responses] == [status.HTTP_409_CONFLICT] * 2
    assert [response.json()['reason'] for response in responses] == ['not_playing'] * 2
    # 지나간 이야기는 그대로 읽을 수 있다
    last = await current(client, me, table)
    assert (last['number'], last['waiting_for']) == (2, [])
    assert (await client.get(rounds_url(table), headers=me)).json()['total'] == 2


async def test_a_member_who_left_stays_in_the_record(client: AsyncClient, me: dict, friend: dict, narrated):
    table = await start_duo(client, me, friend)
    await declare(client, friend, table, FRIENDS_ACTION)

    await client.delete(f'{TABLES_URL}/{table["id"]}/members/me', headers=friend)
    waiting = await current(client, me, table)
    await declare(client, me, table, MY_ACTION)
    await narrated()

    # 떠난 사람을 기다리지 않는다
    assert waiting['waiting_for'] == [str(ME)]
    # 서술자에게는 지금 앉아 있는 사람의 행동만 간다
    assert (await current(client, me, table))['scene'] == f'[1 라운드의 결과]\n엘프: {MY_ACTION}'
    # 떠난 사람이 냈던 선언은 기록에 남는다. 누구의 것이었는지도 남는다
    first = (await client.get(rounds_url(table, '/1'), headers=me)).json()
    assert contents(first) == {'영애': FRIENDS_ACTION, '엘프': MY_ACTION}


# --- 지나간 라운드를 읽는다 ---


async def test_lists_the_rounds_from_the_first(client: AsyncClient, me: dict[str, str], narrated):
    table = await start_solo(client, me)
    await declare(client, me, table, MY_ACTION)
    await narrated()
    await declare(client, me, table, '속도를 올린다.')
    await narrated()

    page = (await client.get(rounds_url(table), headers=me)).json()
    last_only = (await client.get(rounds_url(table), params={'limit': 1, 'offset': 2}, headers=me)).json()

    assert [round_['number'] for round_ in page['items']] == [1, 2, 3]
    assert [round_['status'] for round_ in page['items']] == ['closed', 'closed', 'open']
    assert page['total'] == 3
    assert ([round_['number'] for round_ in last_only['items']], last_only['total']) == ([3], 3)


async def test_reads_a_round_by_its_number(client: AsyncClient, me: dict[str, str]):
    table = await start_solo(client, me)

    found = await client.get(rounds_url(table, '/1'), headers=me)
    missing = await client.get(rounds_url(table, '/2'), headers=me)
    zero = await client.get(rounds_url(table, '/0'), headers=me)
    not_a_number = await client.get(rounds_url(table, '/latest'), headers=me)

    assert found.json()['scene'] == OPENINGS[0]
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert zero.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert not_a_number.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_round_cannot_be_read_through_another_table(client: AsyncClient, me: dict[str, str]):
    played = await start_solo(client, me)
    await declare(client, me, played, MY_ACTION)
    fresh = await start_solo(client, me)

    # 라운드가 하나뿐인 테이블의 주소로 2번 라운드를 읽는다
    response = await client.get(rounds_url(fresh, '/2'), headers=me)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert MY_ACTION not in (await client.get(rounds_url(fresh), headers=me)).text


# --- 라운드는 앉은 사람만 본다 ---


async def test_rounds_look_like_they_do_not_exist_to_those_not_seated(
    client: AsyncClient, me: dict[str, str], stranger: dict[str, str]
):
    table = await start_solo(client, me)

    responses = [
        await client.get(rounds_url(table), headers=stranger),
        await client.get(rounds_url(table, '/current'), headers=stranger),
        await client.get(rounds_url(table, '/1'), headers=stranger),
        await client.put(rounds_url(table, '/current/declaration'), json={'content': '끼어든다.'}, headers=stranger),
        await client.post(rounds_url(table, '/current/close'), headers=stranger),
    ]

    assert [response.status_code for response in responses] == [status.HTTP_404_NOT_FOUND] * len(responses)
    assert OPENINGS[0] not in ''.join(response.text for response in responses)
    assert (await current(client, me, table))['number'] == 1


# --- 서술자는 바꿔 끼울 수 있다 ---


class RecordingNarrator:
    """받은 것을 적어 두고 정해진 글을 돌려주는 서술자. 라운드가 서술자에게 무엇을 주는지 본다."""

    def __init__(self) -> None:
        self.requests: list[NarrationRequest] = []

    async def narrate(self, request: NarrationRequest) -> str:
        self.requests.append(request)
        return '드워프가 넘어졌다.'


async def test_the_narrator_gets_the_closed_round_and_writes_the_next_scene(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    table = await start_duo(client, me, friend)
    await declare(client, me, table, MY_ACTION)

    await client.post(rounds_url(table, '/current/close'), headers=me)
    await narrated()

    # 서술자가 쓴 글이 그대로 다음 장면이 된다
    assert (await current(client, me, table))['scene'] == '드워프가 넘어졌다.'
    # 서술자는 라운드가 닫힐 때 한 번만 불린다. 선언을 낼 때는 불리지 않는다
    assert len(narrator.requests) == 1
    request = narrator.requests[0]
    assert (request.round_number, request.scene) == (1, OPENINGS[0])
    assert [(move.character_name, move.content) for move in request.moves] == [
        ('엘프', MY_ACTION),
        ('영애', None),
    ]


# --- DB 의 마지막 방어선 ---


async def make_table(session: AsyncSession) -> uuid.UUID:
    """서비스를 거치지 않고 테이블 하나를 저장한다."""
    scenario = Scenario(asset=Asset(owner_id=ME, type=AssetType.SCENARIO, title='시나리오'))
    session.add(scenario)
    await session.flush()
    version = ScenarioVersion(scenario_id=scenario.asset_id, number=1, snapshot={})
    session.add(version)
    await session.flush()
    table = GameTable(host_id=ME, version_id=version.id, title='테이블', content={}, opening_index=0)
    table.capacity, table.rating, table.invite_code = 2, 'all', 'test-code-01'
    session.add(table)
    await session.commit()
    return table.id


async def test_the_database_rejects_two_open_rounds_in_one_table(session: AsyncSession):
    table_id = await make_table(session)
    session.add(Round(table_id=table_id, number=1, scene='첫 장면'))
    await session.commit()

    # 앞의 라운드를 닫지 않고 새 라운드를 연다
    session.add(Round(table_id=table_id, number=2, scene='둘째 장면'))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_two_rounds_with_the_same_number(session: AsyncSession):
    table_id = await make_table(session)
    session.add(Round(table_id=table_id, number=1, scene='첫 장면', closed_at=datetime.now(UTC)))
    await session.commit()

    session.add(Round(table_id=table_id, number=1, scene='같은 번호'))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_declaration_that_is_too_long(session: AsyncSession):
    table_id = await make_table(session)
    round_ = Round(table_id=table_id, number=1, scene='첫 장면')
    round_.declarations = [Declaration(user_id=ME, character_name='엘프', content='가' * (DECLARATION_MAX_LENGTH + 1))]
    session.add(round_)

    with pytest.raises(IntegrityError):
        await session.commit()
