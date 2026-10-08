# game-server/tests/test_manual_abilities.py

"""
능력치를 직접 적는 방식(manual)을 검증한다.

플레이어가 능력치의 점수를 직접 적는다. 시나리오의 기본 시트를 쓰지 않는다.
규칙의 점수 범위만 지키면 무엇이든 적을 수 있다. 최대 HP 는 적지 못하고 규칙으로 구한다.

보는 것은 넷이다.
  - 제작자가 켜야 쓸 수 있다. 켜면 최대 HP 를 구하는 값(기준값과 상한)이 있어야 게시된다.
  - 방장은 테이블을 만들 때 이 방식을 뺄 수 있다. 넣을 수는 없다.
  - 적은 능력치는 받을 때 이 테이블의 규칙과 견준다. 시작하면 그것으로 시트가 만들어진다.
  - DB 가 마지막으로 막는다.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import CharacterMode
from app.assets.scenarios.snapshot import Snapshot, read_snapshot
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.tables import sheets
from app.tables.models import TableMember
from app.tables.schemas import CharacterUpdate
from tests.sheets import SHEET, handed_out, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

# 기본 시트. 직접 적은 능력치와 섞이지 않았는지 알아볼 수 있게 최대 HP 를 다르게 둔다
DEFAULT_SHEET = make_sheet(max_hp=7)
# 최대 HP 를 구하는 값. 기준 10, 상한 12
HP = {'base': 10, 'cap': 12}

WITH_MANUAL = ['custom', 'manual']


def scores(**changes: int) -> dict[str, int]:
    """모든 능력치가 10 인 점수에서 몇 개만 바꾼 것."""
    return {**SHEET['abilities'], **changes}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 사람이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def make_scenario(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """룰북과 스타팅, 기본 시트가 있는 시나리오의 초안을 만든다. 방식은 주지 않으면 처음의 둘이다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=headers)
    body = {
        'title': '17개 행성의 추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': DEFAULT_SHEET,
    }
    body.update(fields)
    response = await client.post(SCENARIOS_URL, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def publish(client: AsyncClient, headers: dict[str, str], scenario: dict):
    """판을 내는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=headers)


async def published(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """직접 적기를 허용하는 시나리오를 만들고 판을 하나 낸다. 기본 시트 받기도 함께 허용한다."""
    fields = {'character_modes': WITH_MANUAL, 'player_made_hp': HP, **fields}
    scenario = await make_scenario(client, headers, **fields)
    response = await publish(client, headers, scenario)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return scenario


async def create_table(client: AsyncClient, headers: dict[str, str], scenario: dict, **fields):
    """판으로 테이블을 만드는 요청을 보낸다. 응답을 그대로 돌려준다."""
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    body.update(fields)
    return await client.post(TABLES_URL, json=body, headers=headers)


async def open_table(client: AsyncClient, headers: dict[str, str], scenario: dict | None = None, **fields) -> dict:
    """테이블을 연다. 시나리오를 주지 않으면 직접 적기를 허용하는 시나리오를 새로 만든다."""
    scenario = scenario or await published(client, headers)
    response = await create_table(client, headers, scenario, **fields)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def join(client: AsyncClient, headers: dict[str, str], table: dict) -> None:
    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def set_character(client: AsyncClient, headers: dict[str, str], table: dict, **fields):
    """캐릭터를 정하는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, '/character'), json=fields, headers=headers)


async def write_abilities(client: AsyncClient, headers: dict[str, str], table: dict, abilities: dict, name='엘프'):
    """능력치를 직접 적어 캐릭터를 정하는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await set_character(client, headers, table, mode='manual', name=name, abilities=abilities)


async def start(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.post(table_url(table, '/start'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


# --- 제작자가 켜야 쓸 수 있다 ---


async def test_a_new_scenario_does_not_allow_writing_abilities(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me)

    # 방식이 늘어도 기본값은 처음의 둘이다. 플레이어가 숫자를 정하는 방식은 제작자가 직접 켠다
    assert scenario['character_modes'] == ['pregen', 'custom']
    assert scenario['player_made_hp'] is None


async def test_the_creator_can_allow_writing_abilities(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, character_modes=['manual', 'pregen'], player_made_hp=HP)

    # 방식은 보낸 순서와 상관없이 정해진 순서로 돌아온다
    assert scenario['character_modes'] == ['pregen', 'manual']
    assert scenario['player_made_hp'] == HP


async def test_the_hp_values_can_be_changed_and_cleared(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, player_made_hp=HP)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    changed = await client.patch(url, json={'player_made_hp': {'base': 6, 'cap': 6}}, headers=me)
    untouched = await client.patch(url, json={'title': '새 제목'}, headers=me)
    cleared = await client.patch(url, json={'player_made_hp': None}, headers=me)

    assert changed.json()['player_made_hp'] == {'base': 6, 'cap': 6}
    # 보내지 않으면 그대로다. null 을 보내면 비운다
    assert untouched.json()['player_made_hp'] == {'base': 6, 'cap': 6}
    assert cleared.json()['player_made_hp'] is None


@pytest.mark.parametrize(
    'hp',
    [
        # 기준값이 상한보다 크다
        {'base': 13, 'cap': 12},
        {'base': 0, 'cap': 12},
        {'base': 10, 'cap': 1000},
        # 둘은 함께 보낸다
        {'base': 10},
        {'cap': 12},
        {'base': 10, 'cap': 12, 'ability': 'con'},
    ],
)
async def test_rejects_bad_hp_values(client: AsyncClient, me: dict[str, str], hp: dict):
    response = await client.post(SCENARIOS_URL, json={'title': '추격전', 'player_made_hp': hp}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_publishing_needs_the_hp_values_when_abilities_can_be_written(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, character_modes=WITH_MANUAL)

    response = await publish(client, me, scenario)

    # 플레이어는 최대 HP 를 직접 적지 못한다. 구하는 값이 없으면 그 캐릭터의 HP 를 정할 수 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['player_made_hp_missing']


async def test_publishing_does_not_need_the_hp_values_otherwise(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['snapshot']['player_made_hp'] is None


async def test_a_scenario_that_only_allows_writing_needs_no_default_sheet(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, character_modes=['manual'], player_made_hp=HP, default_sheet=None)

    response = await publish(client, me, scenario)

    # 기본 시트를 받는 방식을 허용하지 않았다. 받을 사람이 없으니 없어도 된다
    assert response.status_code == status.HTTP_201_CREATED
    snapshot = response.json()['snapshot']
    assert (snapshot['character_modes'], snapshot['default_sheet'], snapshot['player_made_hp']) == (
        ['manual'],
        None,
        HP,
    )


# --- 방장은 뺄 수 있다. 넣을 수는 없다 ---


async def test_the_table_shows_how_max_hp_is_worked_out(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    assert table['character_modes'] == WITH_MANUAL
    assert table['player_made_hp'] == HP
    # 어느 능력치의 보정을 더하는지는 규칙에 있다
    assert table['rules']['hp_ability'] == 'con'


async def test_the_host_can_leave_out_writing_abilities(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, character_modes=['custom'])

    refused = await write_abilities(client, me, table, scores())

    assert table['character_modes'] == ['custom']
    # 쓰지 않는 방식의 값은 싣지 않는다
    assert table['player_made_hp'] is None
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'character_mode_not_allowed'


async def test_the_host_cannot_add_what_the_creator_did_not_allow(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me)
    await publish(client, me, scenario)

    response = await create_table(client, me, scenario, character_modes=['custom', 'manual'])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'character_modes 에 고를 수 없는 값이 있습니다.'}


async def test_writing_is_refused_where_the_creator_did_not_allow_it(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me)
    await publish(client, me, scenario)
    table = await open_table(client, me, scenario)

    refused = await write_abilities(client, me, table, scores())

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'character_mode_not_allowed'


# --- 능력치를 적는다 ---


async def test_written_abilities_wait_at_the_seat_until_the_game_starts(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    chosen = scores(str=15, con=14)

    response = await write_abilities(client, me, table, chosen)

    assert response.status_code == status.HTTP_200_OK
    member = response.json()['members'][0]
    assert (member['character']['name'], member['abilities'], member['pregen_index']) == ('엘프', chosen, None)
    # 시트는 아직 없다. 게임을 시작할 때 생긴다
    assert member['sheet'] is None


@pytest.mark.parametrize(
    ('con', 'max_hp'),
    # 기준 10, 상한 12. 보정은 (건강 - 10) // 2
    [(10, 10), (14, 12), (20, 12), (8, 9), (1, 5)],
)
async def test_starting_turns_written_abilities_into_a_sheet(client: AsyncClient, me: dict[str, str], con: int, max_hp):
    table = await open_table(client, me, capacity=1)
    chosen = scores(str=15, con=con)
    await write_abilities(client, me, table, chosen)

    started = await start(client, me, table)

    # 능력치는 적은 그대로, 최대 HP 는 규칙으로 구한 값, HP 는 가득 찬 채로 시작한다. 기본 시트(최대 HP 7)가 아니다
    assert started['members'][0]['sheet'] == handed_out({'abilities': chosen, 'max_hp': max_hp})


async def test_each_player_gets_the_sheet_of_the_way_they_chose(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await write_abilities(client, me, table, scores(con=14))
    await set_character(client, friend, table, name='영애')

    started = await start(client, me, table)

    mine, theirs = (member['sheet'] for member in started['members'])
    assert (mine['abilities']['con'], mine['max_hp']) == (14, 12)
    # 기본 시트를 받은 사람은 제작자가 적은 숫자 그대로다
    assert theirs == handed_out(DEFAULT_SHEET)


async def test_any_scores_within_the_range_of_the_rules_are_taken(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    everything_maxed = dict.fromkeys(SHEET['abilities'], 20)

    response = await write_abilities(client, me, table, everything_maxed)

    # 균형을 서버가 따지지 않는다. 이 방식을 켠 제작자와, 그렇게 적은 플레이어의 몫이다
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['members'][0]['abilities'] == everything_maxed


@pytest.mark.parametrize(
    'abilities',
    [
        # 범위 밖(1~20)
        scores(str=21),
        scores(str=0),
        # 빠진 능력치, 규칙에 없는 능력치
        {'str': 10, 'dex': 10},
        {**scores(), 'luck': 10},
        {},
    ],
    ids=['too high', 'too low', 'missing', 'unknown', 'empty'],
)
async def test_written_abilities_must_fit_the_rules_of_the_table(client: AsyncClient, me: dict[str, str], abilities):
    table = await open_table(client, me, capacity=1)

    response = await write_abilities(client, me, table, abilities)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'abilities 에 고를 수 없는 값이 있습니다.'}
    # 캐릭터는 정해지지 않았다
    assert (await client.get(table_url(table), headers=me)).json()['members'][0]['character'] is None


@pytest.mark.parametrize(
    'body',
    [
        # 능력치를 적을 때는 방식을 반드시 적는다
        {'name': '엘프', 'abilities': scores()},
        # 방식에 맞는 칸만 적는다
        {'mode': 'manual', 'name': '엘프'},
        {'mode': 'manual', 'abilities': scores()},
        {'mode': 'manual', 'name': '엘프', 'abilities': scores(), 'pregen_index': 0},
        {'mode': 'custom', 'name': '엘프', 'abilities': scores()},
        {'mode': 'pregen', 'name': '엘프'},
        {'mode': 'custom', 'pregen_index': 0},
        {'mode': 'cheat', 'name': '엘프'},
        # 최대 HP 와 지금의 HP 는 적지 못한다
        {'mode': 'manual', 'name': '엘프', 'abilities': scores(), 'max_hp': 99},
        {'mode': 'manual', 'name': '엘프', 'abilities': scores(), 'hp': 99},
        {'mode': 'manual', 'name': '엘프', 'abilities': {'Str': 10}},
        {'mode': 'manual', 'name': '엘프', 'abilities': {'str': '열'}},
    ],
)
async def test_rejects_a_character_with_a_bad_shape(client: AsyncClient, me: dict[str, str], body: dict):
    table = await open_table(client, me, capacity=1)

    response = await client.put(table_url(table, '/character'), json=body, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_changing_the_way_drops_the_written_abilities(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    table = await open_table(client, me, capacity=1)
    await write_abilities(client, me, table, scores(str=18))

    changed = await set_character(client, me, table, name='엘프')
    started = await start(client, me, table)

    # 기본 시트를 받는 방식으로 바꿨다. 적어 둔 능력치는 지워지고, 시작하면 기본 시트를 받는다
    assert changed.json()['members'][0]['abilities'] is None
    assert await session.scalar(text('SELECT abilities FROM table_members')) is None
    assert started['members'][0]['sheet']['max_hp'] == DEFAULT_SHEET['max_hp']


async def test_writing_again_replaces_the_abilities(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    await write_abilities(client, me, table, scores(str=18))

    again = await write_abilities(client, me, table, scores(dex=18))

    assert again.json()['members'][0]['abilities'] == scores(dex=18)


async def test_abilities_cannot_be_written_after_the_game_starts(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    await write_abilities(client, me, table, scores())
    await start(client, me, table)

    response = await write_abilities(client, me, table, scores(str=20))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_recruiting'


async def test_the_start_is_recorded_with_the_sheet_that_was_worked_out(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, capacity=1)
    await write_abilities(client, me, table, scores(con=14))
    await start(client, me, table)

    events = (await client.get(table_url(table, '/events'), headers=me)).json()['items']

    started = next(event for event in events if event['type'] == 'table_started')
    assert started['payload']['members'][0]['sheet'] == {'abilities': scores(con=14), 'max_hp': 12}


# --- 판단만 하는 작은 것들. DB 를 쓰지 않는다 ---


def make_snapshot(player_made_hp: dict | None = HP) -> Snapshot:
    """직접 적기를 허용하는 판. 최대 HP 를 구하는 값은 바꿔 볼 수 있다."""
    return read_snapshot(
        {
            'format': 10,
            'title': '판',
            'description': '',
            'rating': 'all',
            'openings': ['도입부'],
            'recommended_players': {'min': 1, 'max': 4},
            'pregens': [{'name': '폭주족 엘프', 'description': '', 'sheet': make_sheet(max_hp=8)}],
            'character_modes': ['pregen', 'custom', 'manual'],
            'default_sheet': DEFAULT_SHEET,
            'player_made_hp': player_made_hp,
            'reroll_allowed': False,
            'rulebook': {'id': str(ME), 'title': '룰북', 'gm_guide': '', 'rules': SRD5.model_dump(mode='json')},
            'world': None,
            'lorebooks': [],
        }
    )


def make_member(**fields) -> TableMember:
    return TableMember(user_id=uuid.uuid4(), character_name='아무개', **fields)


def test_a_member_who_wrote_abilities_gets_a_sheet_built_from_them():
    member = make_member(abilities=scores(con=16))

    sheet = sheets.find_source(make_snapshot(), member)

    assert (sheet.abilities['con'], sheet.max_hp) == (16, 12)


def test_the_three_sources_do_not_mix():
    snapshot = make_snapshot()

    assert sheets.find_source(snapshot, make_member(pregen_index=0)).max_hp == 8
    assert sheets.find_source(snapshot, make_member()).max_hp == DEFAULT_SHEET['max_hp']
    assert sheets.find_source(snapshot, make_member(abilities=scores())).max_hp == 10


def test_without_the_hp_values_no_sheet_can_be_built():
    # 게시 조건이 막는 일이다. 그래도 생기면 시트를 만들지 않고 알린다. 시작이 거절된다
    assert sheets.find_source(make_snapshot(player_made_hp=None), make_member(abilities=scores())) is None


@pytest.mark.parametrize(
    ('fields', 'mode'),
    [
        ({'name': '엘프'}, CharacterMode.CUSTOM),
        ({'pregen_index': 0}, CharacterMode.PREGEN),
        ({'mode': 'custom', 'name': '엘프'}, CharacterMode.CUSTOM),
        ({'mode': 'pregen', 'pregen_index': 0}, CharacterMode.PREGEN),
        ({'mode': 'manual', 'name': '엘프', 'abilities': {'str': 10}}, CharacterMode.MANUAL),
    ],
)
def test_reads_the_way_a_character_is_made(fields: dict, mode: CharacterMode):
    # 방식을 적지 않으면 프리젠을 골랐는지로 정한다. 이 방식이 생기기 전의 요청이 그대로 통한다
    assert CharacterUpdate.model_validate(fields).chosen_mode == mode


def test_abilities_without_a_way_are_not_read():
    with pytest.raises(ValidationError):
        CharacterUpdate.model_validate({'name': '엘프', 'abilities': {'str': 10}})


# --- DB 의 마지막 방어선 ---


async def test_the_database_takes_the_new_way(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    await make_scenario(client, me)

    await session.execute(text("UPDATE scenarios SET character_modes = '{pregen,custom,manual}'"))
    await session.commit()

    assert await session.scalar(text('SELECT character_modes FROM scenarios')) == ['pregen', 'custom', 'manual']


@pytest.mark.parametrize(
    ('base', 'cap'),
    [(10, None), (None, 12), (13, 12), (0, 12), (10, 1000)],
    ids=['base alone', 'cap alone', 'base over cap', 'zero', 'too big'],
)
async def test_the_database_rejects_bad_hp_values(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, base: int | None, cap: int | None
):
    await make_scenario(client, me)

    with pytest.raises(IntegrityError, match='player_made_hp'):
        await session.execute(text('UPDATE scenarios SET hp_base = :base, hp_cap = :cap'), {'base': base, 'cap': cap})


async def test_the_database_rejects_abilities_on_a_pregen(client: AsyncClient, me: dict[str, str], session):
    scenario = await published(
        client, me, character_modes=['pregen', 'manual'], pregens=[{'name': '폭주족 엘프', 'sheet': SHEET}]
    )
    table = await open_table(client, me, scenario, capacity=1)
    await set_character(client, me, table, pregen_index=0)

    # 프리젠의 숫자는 제작자가 적은 것이다. 그 위에 직접 적은 능력치가 얹힐 수 없다
    with pytest.raises(IntegrityError, match='abilities_need_player_made_mode'):
        await session.execute(text("""UPDATE table_members SET abilities = '{"str": 20}'"""))


async def test_the_database_rejects_abilities_without_a_character(client: AsyncClient, me: dict[str, str], session):
    await open_table(client, me, capacity=1)

    with pytest.raises(IntegrityError, match='abilities_need_player_made_mode'):
        await session.execute(text("""UPDATE table_members SET abilities = '{"str": 20}'"""))
