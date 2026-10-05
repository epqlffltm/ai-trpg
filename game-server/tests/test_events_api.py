# game-server/tests/test_events_api.py

"""
테이블의 이벤트 기록을 검증한다.

보는 것은 다섯이다.
  - 테이블을 바꾸는 일마다 이벤트가 적힌다. 번호는 1 부터 빈 번호 없이 올라간다.
  - 요청 하나가 낳은 이벤트는 한 묶음이고, 원인과 결과가 이어져 있다.
  - 선언은 라운드가 닫힐 때 적힌다. 열려 있는 동안에는 이벤트로도 남의 선언을 볼 수 없다.
  - 이벤트는 테이블에 앉은 사람만 읽는다. 정해 둔 칸만 나간다.
  - 상태를 바꾼 것과 이벤트는 함께 저장된다. 이벤트를 못 적으면 상태도 바뀌지 않는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Asset, AssetType, Scenario, ScenarioVersion
from app.events import recorder
from app.events.models import EventType, TableEvent
from app.main import API_PREFIX
from app.tables.models import GameTable
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
THIRD = uuid.UUID('33333333-2222-4333-8444-555555555555')
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
def third(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 세 번째로 들어오는 사람의 머리말."""
    return bearer(signing_key, THIRD)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않는 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def table_url(table: dict, path: str = '') -> str:
    """테이블의 주소."""
    return f'{TABLES_URL}/{table["id"]}{path}'


async def open_table(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """내 시나리오를 만들어 그 판으로 테이블을 연다. 아직 시작하지 않은 테이블을 돌려준다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북', 'gm_guide': GM_GUIDE}, headers=headers)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': OPENINGS}
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=headers)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 3, **fields}
    response = await client.post(TABLES_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def join(client: AsyncClient, headers: dict[str, str], table: dict) -> None:
    """초대 코드로 테이블에 들어간다."""
    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str], **fields) -> dict:
    """나와 친구가 앉은 테이블을 시작한다. 여기까지 이벤트가 다섯 개 적힌다."""
    table = await open_table(client, me, **fields)
    await join(client, friend, table)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def declare(client: AsyncClient, headers: dict[str, str], table: dict, content: str) -> None:
    """선언을 낸다."""
    url = table_url(table, '/rounds/current/declaration')
    response = await client.put(url, json={'content': content}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def read_events(client: AsyncClient, headers: dict[str, str], table: dict, **params) -> list[dict]:
    """테이블의 이벤트를 읽는다."""
    response = await client.get(table_url(table, '/events'), params=params, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


def types(events: list[dict]) -> list[str]:
    """이벤트들의 종류를 순서대로."""
    return [event['type'] for event in events]


async def stored_events(session: AsyncSession, table: dict) -> list[TableEvent]:
    """DB 에 저장된 이벤트를 순서대로 읽는다. 아무도 앉아 있지 않아 API 로 읽을 수 없을 때 쓴다."""
    query = select(TableEvent).where(TableEvent.table_id == uuid.UUID(table['id'])).order_by(TableEvent.sequence)
    return list(await session.scalars(query))


# --- 로그인 ---


async def test_reading_events_requires_login(client: AsyncClient):
    response = await client.get(f'{TABLES_URL}/{NO_SUCH_ID}/events')

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- 자리 ---


async def test_creating_a_table_writes_the_first_event(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    response = await client.get(table_url(table, '/events'), headers=me)

    page = response.json()
    assert page['last_sequence'] == 1
    (event,) = page['items']
    assert (event['sequence'], event['type'], event['actor_id']) == (1, 'table_created', str(ME))
    assert (event['payload'], event['caused_by_sequence']) == ({}, None)
    assert event['created_at'] is not None


async def test_joining_is_recorded_with_the_way_in(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], third: dict[str, str]
):
    table = await open_table(client, me, is_public=True)

    await join(client, friend, table)
    await client.post(table_url(table, '/join'), json={}, headers=third)

    events = await read_events(client, me, table)
    assert types(events) == ['table_created', 'member_joined', 'member_joined']
    assert [(event['actor_id'], event['payload']) for event in events[1:]] == [
        (str(FRIEND), {'via': 'invite'}),
        (str(THIRD), {'via': 'lobby'}),
    ]


async def test_a_refused_request_writes_nothing(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me, capacity=1)

    refused = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert types(await read_events(client, me, table)) == ['table_created']


async def test_setting_a_character_is_not_recorded(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)

    # 모집 중에 캐릭터를 몇 번 고치든 적지 않는다. 시작할 때 한 번 적는다
    assert types(await read_events(client, me, table)) == ['table_created']


async def test_leaving_is_recorded_with_the_character(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)

    await client.delete(table_url(table, '/members/me'), headers=friend)

    last = (await read_events(client, me, table))[-1]
    # 캐릭터 이름을 함께 적는다. 자리는 지워졌지만 누가 나갔는지 남는다
    assert (last['type'], last['actor_id'], last['payload']) == ('member_left', str(FRIEND), {'character_name': '영애'})


async def test_the_host_leaving_causes_a_new_host(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)

    await client.delete(table_url(table, '/members/me'), headers=me)

    left, changed = (await read_events(client, friend, table))[-2:]
    assert (left['type'], left['actor_id']) == ('member_left', str(ME))
    # 방장이 바뀐 것은 사람이 한 일이 아니다. 방장이 나간 것이 원인이다
    assert (changed['type'], changed['actor_id'], changed['payload']) == (
        'host_changed',
        None,
        {'user_id': str(FRIEND)},
    )
    assert changed['caused_by_sequence'] == left['sequence']
    assert changed['action_group_id'] == left['action_group_id']


async def test_the_last_one_leaving_causes_the_end(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = await open_table(client, me)

    await client.delete(table_url(table, '/members/me'), headers=me)

    created, left, ended = await stored_events(session, table)
    assert (left.type, ended.type, ended.actor_id) == ('member_left', 'table_ended', None)
    assert (ended.caused_by_sequence, ended.action_group_id) == (left.sequence, left.action_group_id)
    assert created.action_group_id != left.action_group_id


async def test_leaving_an_ended_table_does_not_end_it_again(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    table = await open_table(client, me)
    await client.post(table_url(table, '/end'), headers=me)

    await client.delete(table_url(table, '/members/me'), headers=me)

    events = await stored_events(session, table)
    assert [event.type for event in events] == ['table_created', 'table_ended', 'member_left']


async def test_kicking_is_recorded_without_the_new_invite_code(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_table(client, me)
    await join(client, friend, table)

    kicked = await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)

    response = await client.get(table_url(table, '/events'), headers=me)
    last = response.json()['items'][-1]
    assert (last['type'], last['actor_id']) == ('member_kicked', str(ME))
    assert last['payload'] == {'user_id': str(FRIEND), 'character_name': None}
    # 이벤트는 앉은 사람 모두가 읽는다. 방장만 아는 초대 코드가 실리면 안 된다
    assert kicked.json()['invite_code'] not in response.text
    assert table['invite_code'] not in response.text


async def test_handing_over_the_host_is_recorded(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)

    await client.put(table_url(table, '/host'), json={'user_id': str(FRIEND)}, headers=me)

    last = (await read_events(client, me, table))[-1]
    assert (last['type'], last['actor_id'], last['payload']) == ('host_changed', str(ME), {'user_id': str(FRIEND)})
    assert last['caused_by_sequence'] is None


async def test_ending_the_table_is_recorded(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    await client.post(table_url(table, '/end'), headers=me)

    last = (await read_events(client, me, table))[-1]
    assert (last['type'], last['actor_id'], last['payload']) == ('table_ended', str(ME), {})


# --- 진행 ---


async def test_starting_writes_the_roster_the_scene_and_the_round(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend, opening_index=1)

    started, narration, opened = (await read_events(client, friend, table))[-3:]

    assert (started['type'], started['actor_id']) == ('table_started', str(ME))
    # 시작할 때 누가 어떤 캐릭터였는지를 적는다
    assert started['payload'] == {
        'members': [
            {'user_id': str(ME), 'character_name': '엘프'},
            {'user_id': str(FRIEND), 'character_name': '영애'},
        ]
    }
    # 첫 서술은 고른 스타팅이다. GM 이 한 일이라 actor_id 가 없다
    assert (narration['type'], narration['actor_id'], narration['payload']) == (
        'gm_narration',
        None,
        {'text': OPENINGS[1]},
    )
    assert (opened['type'], opened['actor_id'], opened['payload']) == ('round_opened', None, {'number': 1})
    # 시작 → 서술 → 열림. 원인으로 이어지고 한 묶음이다
    assert narration['caused_by_sequence'] == started['sequence']
    assert opened['caused_by_sequence'] == narration['sequence']
    assert {event['action_group_id'] for event in (started, narration, opened)} == {started['action_group_id']}


async def test_a_declaration_is_not_recorded_while_the_round_is_open(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    before = await read_events(client, friend, table)

    await declare(client, me, table, MY_ACTION)
    await declare(client, me, table, '마음을 바꿔 뒤로 달린다.')

    response = await client.get(table_url(table, '/events'), headers=friend)
    assert response.json()['items'] == before
    # 열려 있는 라운드에서 남의 선언은 보이지 않는다. 이벤트가 뒷문이 되면 안 된다
    assert MY_ACTION not in response.text
    assert '마음을 바꿔' not in response.text


async def test_closing_a_round_writes_the_actions_the_result_and_the_next_round(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, '처음 생각.')
    await declare(client, me, table, MY_ACTION)

    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()

    mine, friends, closed, narration, opened = await read_events(client, me, table, after=5)
    # 행동은 마지막 글만 적힌다. 앉은 순서다
    assert (mine['type'], mine['actor_id']) == ('player_action', str(ME))
    assert mine['payload'] == {'round': 1, 'character_name': '엘프', 'content': MY_ACTION}
    assert (friends['actor_id'], friends['payload']['content']) == (str(FRIEND), FRIENDS_ACTION)
    # 모두가 내서 저절로 닫혔다. 닫은 사람이 없다
    assert (closed['type'], closed['actor_id'], closed['payload']) == ('round_closed', None, {'number': 1, 'idle': []})
    expected = f'[1 라운드의 결과]\n엘프: {MY_ACTION}\n영애: {FRIENDS_ACTION}'
    assert (narration['type'], narration['payload']) == ('gm_narration', {'text': expected})
    assert (opened['type'], opened['payload']) == ('round_opened', {'number': 2})
    # 닫힘 → 서술 → 열림. 다섯이 한 묶음이다. 닫힘까지와 서술부터는 따로 저장되지만 묶음은 같다
    assert narration['caused_by_sequence'] == closed['sequence']
    assert opened['caused_by_sequence'] == narration['sequence']
    groups = {event['action_group_id'] for event in (mine, friends, closed, narration, opened)}
    assert len(groups) == 1


async def test_the_host_closing_a_round_records_who_did_nothing(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, MY_ACTION)

    await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    events = await read_events(client, friend, table, after=5)
    assert types(events) == ['player_action', 'round_closed', 'gm_narration', 'round_opened']
    closed = events[1]
    # 방장이 닫았다. 선언을 내지 않은 사람이 적힌다
    assert (closed['actor_id'], closed['payload']) == (str(ME), {'number': 1, 'idle': [str(FRIEND)]})


async def test_the_action_of_someone_who_left_is_not_recorded(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await declare(client, friend, table, FRIENDS_ACTION)
    await client.delete(table_url(table, '/members/me'), headers=friend)

    await declare(client, me, table, MY_ACTION)
    await narrated()

    events = await read_events(client, me, table, after=5)
    # 떠난 사람의 선언은 서술자에게 가지 않았다. 이벤트는 서술자가 받은 것과 같다
    assert types(events) == ['member_left', 'player_action', 'round_closed', 'gm_narration', 'round_opened']
    assert events[1]['actor_id'] == str(ME)
    assert FRIENDS_ACTION not in str(events)


# --- 번호와 읽기 ---


async def test_sequences_go_up_from_one_without_gaps(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await declare(client, me, table, MY_ACTION)
    await declare(client, friend, table, FRIENDS_ACTION)
    await narrated()
    await client.post(table_url(table, '/end'), headers=me)

    response = await client.get(table_url(table, '/events'), headers=me)

    page = response.json()
    assert [event['sequence'] for event in page['items']] == list(range(1, 12))
    assert page['last_sequence'] == 11
    assert types(page['items']) == [
        'table_created',
        'member_joined',
        'table_started',
        'gm_narration',
        'round_opened',
        'player_action',
        'player_action',
        'round_closed',
        'gm_narration',
        'round_opened',
        'table_ended',
    ]


async def test_reads_only_what_comes_after(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_duo(client, me, friend)

    newer = await client.get(table_url(table, '/events'), params={'after': 3}, headers=me)
    first_two = await client.get(table_url(table, '/events'), params={'limit': 2}, headers=me)
    nothing = await client.get(table_url(table, '/events'), params={'after': 5}, headers=me)

    assert [event['sequence'] for event in newer.json()['items']] == [4, 5]
    # 잘라 읽어도 마지막 번호는 테이블의 것이다. 더 읽을 것이 있는지 알 수 있다
    assert [event['sequence'] for event in first_two.json()['items']] == [1, 2]
    assert first_two.json()['last_sequence'] == 5
    assert nothing.json() == {'items': [], 'last_sequence': 5}


@pytest.mark.parametrize('params', [{'after': -1}, {'after': 'abc'}, {'limit': 0}, {'limit': 101}])
async def test_rejects_bad_reading_options(client: AsyncClient, me: dict[str, str], params: dict):
    table = await open_table(client, me)

    response = await client.get(table_url(table, '/events'), params=params, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 누가 읽나 ---


async def test_events_look_like_they_do_not_exist_to_those_not_seated(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], stranger: dict[str, str]
):
    table = await start_duo(client, me, friend)

    outsider = await client.get(table_url(table, '/events'), headers=stranger)
    missing = await client.get(f'{TABLES_URL}/{NO_SUCH_ID}/events', headers=me)

    # 앉지 않은 사람에게는 없는 테이블과 똑같이 보인다
    assert outsider.status_code == status.HTTP_404_NOT_FOUND
    assert outsider.json() == missing.json()
    assert OPENINGS[0] not in outsider.text


async def test_someone_kicked_reads_no_more(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me)
    await join(client, friend, table)
    assert (await client.get(table_url(table, '/events'), headers=friend)).status_code == status.HTTP_200_OK

    await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)

    response = await client.get(table_url(table, '/events'), headers=friend)
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_gm_only_text_never_leaves(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_duo(client, me, friend)

    response = await client.get(table_url(table, '/events'), headers=me)

    # 방장에게도 나가지 않는다
    assert GM_GUIDE not in response.text


async def test_only_listed_payload_fields_leave(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = await open_table(client, me)
    stored = await session.get(GameTable, uuid.UUID(table['id']))
    payload = {'text': '문이 열린다.', 'hidden_roll': 17}
    recorder.record(session, stored, EventType.GM_NARRATION, payload=payload)
    await session.commit()

    response = await client.get(table_url(table, '/events'), headers=me)

    # 내보내기로 정한 칸(text)만 나간다. 누가 payload 에 다른 것을 적어도 플레이어에게 가지 않는다
    assert response.json()['items'][-1]['payload'] == {'text': '문이 열린다.'}
    assert 'hidden_roll' not in response.text


# --- 함께 저장된다 ---


async def test_nothing_changes_when_the_event_cannot_be_written(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    table = await open_table(client, me)

    def fail(*args, **kwargs):
        raise RuntimeError('이벤트를 적지 못했다')

    monkeypatch.setattr(recorder, 'record', fail)
    with pytest.raises(RuntimeError):
        await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    monkeypatch.undo()

    # 자리에 앉히는 것까지는 했지만 저장하지 않았다. 친구는 앉아 있지 않다
    seated = (await client.get(table_url(table), headers=me)).json()['members']
    assert [member['user_id'] for member in seated] == [str(ME)]
    assert types(await read_events(client, me, table)) == ['table_created']


# --- DB 의 마지막 방어선 ---


async def make_table(session: AsyncSession) -> GameTable:
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
    return table


def make_event(table: GameTable, sequence: int, **fields) -> TableEvent:
    """번호를 직접 정한 이벤트를 만든다. recorder 를 거치지 않는다."""
    values = {'type': EventType.TABLE_CREATED, 'payload': {}, 'action_group_id': uuid.uuid4(), **fields}
    return TableEvent(table_id=table.id, sequence=sequence, **values)


async def test_the_database_rejects_two_events_with_the_same_sequence(session: AsyncSession):
    table = await make_table(session)
    session.add(make_event(table, 1))
    await session.commit()

    session.add(make_event(table, 1))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_the_database_rejects_a_sequence_below_one(session: AsyncSession):
    table = await make_table(session)

    session.add(make_event(table, 0))

    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.parametrize('cause', [2, 3])
async def test_the_database_rejects_a_cause_that_does_not_come_first(session: AsyncSession, cause: int):
    table = await make_table(session)

    session.add(make_event(table, 2, caused_by_sequence=cause))

    with pytest.raises(IntegrityError):
        await session.commit()
