# game-server/tests/test_point_buy_mode.py

"""
점수제로 캐릭터를 만드는 방식(point_buy)을 검증한다.

플레이어가 규칙의 총점 안에서 능력치의 점수를 산다. 시나리오의 기본 시트를 쓰지 않는다.
직접 적기(manual)와 적는 칸이 같다. 다른 것은 받을 때 총점을 넘는지를 서버가 본다는 것이다.
총점과 값표는 룰북의 규칙에 있다. 계산 자체는 tests/test_point_buy.py 가 본다.

보는 것은 넷이다.
  - 제작자가 켜야 쓸 수 있고, 방장은 뺄 수 있다. 켜면 최대 HP 를 구하는 값이 있어야 게시된다.
  - 산 점수는 받을 때 이 테이블의 규칙의 총점과 견준다. 계산은 서버가 한다. 보낸 합계를 믿지 않는다.
  - 시작하면 그 점수로 시트가 만들어진다. 최대 HP 를 구하는 법은 직접 적기와 같다.
  - DB 가 새 방식을 받는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import DEFAULT_CHARACTER_MODES, PLAYER_MADE_MODES, CharacterMode
from app.assets.scenarios.publishing import Problem, find_point_buy_problems
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.tables import sheets
from app.tables.schemas import CharacterUpdate
from tests.sheets import make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

# 기본 시트. 산 점수와 섞이지 않았는지 알아볼 수 있게 최대 HP 를 다르게 둔다
DEFAULT_SHEET = make_sheet(max_hp=7)
# 최대 HP 를 구하는 값. 기준 10, 상한 12
HP = {'base': 10, 'cap': 12}

WITH_POINT_BUY = ['custom', 'manual', 'point_buy']

# 27점을 꼭 맞게 쓴 점수. 9 + 7 + 5 + 4 + 2 + 0
SPENT_ALL = {'str': 15, 'dex': 14, 'con': 13, 'int': 12, 'wis': 10, 'cha': 8}

# 점수제가 없는 규칙
NO_POINT_BUY = Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'point_buy': None})


def scores(**changes: int) -> dict[str, int]:
    """모든 능력치가 8 인 점수에서 몇 개만 바꾼 것. 8 은 값이 0 이다."""
    return {'str': 8, 'dex': 8, 'con': 8, 'int': 8, 'wis': 8, 'cha': 8, **changes}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 사람이다."""
    token = make_token(signing_key, make_access_claims(sub=str(ME)))
    return {'Authorization': f'Bearer {token}'}


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
    """점수제를 허용하는 시나리오를 만들고 판을 하나 낸다. 기본 시트 받기와 직접 적기도 함께 허용한다."""
    fields = {'character_modes': WITH_POINT_BUY, 'player_made_hp': HP, **fields}
    scenario = await make_scenario(client, headers, **fields)
    response = await publish(client, headers, scenario)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return scenario


async def create_table(client: AsyncClient, headers: dict[str, str], scenario: dict, **fields):
    """판으로 테이블을 만드는 요청을 보낸다. 응답을 그대로 돌려준다."""
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 1}
    body.update(fields)
    return await client.post(TABLES_URL, json=body, headers=headers)


async def open_table(client: AsyncClient, headers: dict[str, str], scenario: dict | None = None, **fields) -> dict:
    """혼자 앉는 테이블을 연다. 시나리오를 주지 않으면 점수제를 허용하는 시나리오를 새로 만든다."""
    scenario = scenario or await published(client, headers)
    response = await create_table(client, headers, scenario, **fields)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def buy(client: AsyncClient, headers: dict[str, str], table: dict, abilities: dict, **fields):
    """점수제로 캐릭터를 정하는 요청을 보낸다. 응답을 그대로 돌려준다."""
    body = {'mode': 'point_buy', 'name': '엘프', 'abilities': abilities, **fields}
    return await client.put(table_url(table, '/character'), json=body, headers=headers)


async def write(client: AsyncClient, headers: dict[str, str], table: dict, abilities: dict):
    """같은 능력치를 직접 적기로 보낸다. 응답을 그대로 돌려준다."""
    body = {'mode': 'manual', 'name': '엘프', 'abilities': abilities}
    return await client.put(table_url(table, '/character'), json=body, headers=headers)


async def start(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.post(table_url(table, '/start'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def seat_of(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """지금의 테이블에서 내 자리를 읽는다."""
    return (await client.get(table_url(table), headers=headers)).json()['members'][0]


# --- 제작자가 켜야 쓸 수 있다 ---


def test_point_buy_is_a_way_where_the_player_sets_the_numbers():
    # 플레이어가 능력치를 정하는 방식이다. 최대 HP 를 구하는 값이 있어야 하고, 능력치를 적어야 한다
    assert {CharacterMode.MANUAL, CharacterMode.POINT_BUY} == PLAYER_MADE_MODES
    # 방식이 늘어도 고르지 않았을 때 허용하는 것은 처음의 둘이다
    assert DEFAULT_CHARACTER_MODES == [CharacterMode.PREGEN, CharacterMode.CUSTOM]


async def test_a_new_scenario_does_not_allow_point_buy(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me)

    assert scenario['character_modes'] == ['pregen', 'custom']


async def test_the_creator_can_allow_point_buy(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, character_modes=['point_buy', 'pregen'], player_made_hp=HP)

    # 방식은 보낸 순서와 상관없이 정해진 순서로 돌아온다
    assert scenario['character_modes'] == ['pregen', 'point_buy']


async def test_publishing_needs_the_hp_values_when_point_buy_is_allowed(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, character_modes=['point_buy'], default_sheet=None)

    response = await publish(client, me, scenario)

    # 점수제도 플레이어가 능력치를 정하는 방식이다. 최대 HP 를 구하는 값이 없으면 그 캐릭터의 HP 를 정할 수 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['player_made_hp_missing']


async def test_a_scenario_that_only_allows_point_buy_needs_no_default_sheet(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, character_modes=['point_buy'], player_made_hp=HP, default_sheet=None)

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED
    snapshot = response.json()['snapshot']
    assert (snapshot['character_modes'], snapshot['default_sheet']) == (['point_buy'], None)
    # 총점과 값표는 규칙과 함께 판에 굳는다. 뒤에 템플릿이 달라져도 이 판의 점수제는 그대로다
    assert snapshot['rulebook']['rules']['point_buy']['budget'] == 27


@pytest.mark.parametrize(
    ('modes', 'ruleset', 'problems'),
    [
        (['point_buy'], NO_POINT_BUY, [Problem.POINT_BUY_MISSING]),
        (['custom', 'point_buy'], NO_POINT_BUY, [Problem.POINT_BUY_MISSING]),
        (['point_buy'], SRD5, []),
        # 점수제를 허용하지 않았으면 규칙에 점수제가 없어도 된다
        (['custom', 'manual'], NO_POINT_BUY, []),
        # 룰북이 없으면 볼 수 없다. 룰북이 없다는 문제는 다른 곳이 적는다
        (['point_buy'], None, []),
    ],
    ids=['missing', 'missing among others', 'present', 'not allowed', 'no rulebook'],
)
def test_point_buy_needs_rules_that_have_it(modes: list[str], ruleset: Ruleset | None, problems: list[Problem]):
    # 지금의 템플릿(srd5)에는 점수제가 있어서 API 로는 이 문제를 만들 수 없다. 판단하는 함수를 직접 부른다.
    # 이 함수는 시나리오에서 허용한 방식만 읽는다
    scenario = SimpleNamespace(character_modes=modes)

    assert find_point_buy_problems(scenario, ruleset) == problems


# --- 방장은 뺄 수 있다. 넣을 수는 없다 ---


async def test_the_table_shows_the_budget_and_the_costs(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    # 화면이 남은 점수를 계산해 보여 줄 수 있어야 한다. 총점과 값표는 규칙에 있다
    point_buy = table['rules']['point_buy']
    assert table['character_modes'] == WITH_POINT_BUY
    assert point_buy['budget'] == 27
    assert point_buy['costs'][0] == {'score': 8, 'cost': 0}
    assert point_buy['costs'][-1] == {'score': 15, 'cost': 9}
    assert table['player_made_hp'] == HP


async def test_the_host_can_leave_out_point_buy(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, character_modes=['custom', 'manual'])

    refused = await buy(client, me, table, SPENT_ALL)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'character_mode_not_allowed'


async def test_the_host_can_keep_point_buy_and_leave_out_writing(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, character_modes=['point_buy'])

    bought = await buy(client, me, table, SPENT_ALL)
    written = await write(client, me, table, SPENT_ALL)

    # 같은 능력치라도 허용하지 않은 방식으로는 받지 않는다. 방식마다 지키는 제한이 다르다
    assert bought.status_code == status.HTTP_200_OK
    assert written.status_code == status.HTTP_409_CONFLICT
    # 플레이어가 능력치를 정하는 방식이 하나라도 있으면 최대 HP 를 구하는 값을 싣는다
    assert table['player_made_hp'] == HP


async def test_the_host_cannot_add_point_buy(client: AsyncClient, me: dict[str, str]):
    scenario = await published(client, me, character_modes=['custom', 'manual'])

    response = await create_table(client, me, scenario, character_modes=['custom', 'point_buy'])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'character_modes 에 고를 수 없는 값이 있습니다.'}


# --- 점수를 산다 ---


async def test_bought_scores_wait_at_the_seat_until_the_game_starts(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    response = await buy(client, me, table, SPENT_ALL)

    assert response.status_code == status.HTTP_200_OK
    member = response.json()['members'][0]
    assert (member['character_mode'], member['abilities'], member['pregen_index']) == ('point_buy', SPENT_ALL, None)
    # 시트는 아직 없다. 게임을 시작할 때 생긴다
    assert member['sheet'] is None


@pytest.mark.parametrize(
    'abilities',
    [
        SPENT_ALL,
        # 총점을 다 쓰지 않아도 된다
        scores(),
        scores(str=15),
        # 15 셋은 꼭 27 이다
        scores(str=15, dex=15, con=15),
    ],
    ids=['all spent', 'nothing spent', 'some spent', 'three fifteens'],
)
async def test_scores_within_the_budget_are_taken(client: AsyncClient, me: dict[str, str], abilities: dict):
    table = await open_table(client, me)

    response = await buy(client, me, table, abilities)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['members'][0]['abilities'] == abilities


@pytest.mark.parametrize(
    'abilities',
    [
        # 15 셋(27)에 9 하나(1). 한 점이 넘는다
        scores(str=15, dex=15, con=15, int=9),
        # 모두 15 는 54 다
        dict.fromkeys(SPENT_ALL, 15),
        # 값표에 없는 점수. 규칙의 점수 범위(1~20) 안이어도 살 수 없다
        scores(str=16),
        scores(str=20),
        scores(cha=7),
        scores(cha=1),
        # 규칙에 맞지 않는 능력치. 직접 적기와 같이 본다
        scores(str=21),
        {'str': 8, 'dex': 8},
        {**scores(), 'luck': 8},
        {},
    ],
    ids=[
        'one over',
        'far over',
        'sixteen',
        'twenty',
        'seven',
        'one',
        'out of range',
        'missing',
        'unknown',
        'empty',
    ],
)
async def test_scores_that_cannot_be_bought_are_refused(client: AsyncClient, me: dict[str, str], abilities: dict):
    table = await open_table(client, me)

    response = await buy(client, me, table, abilities)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'abilities 에 고를 수 없는 값이 있습니다.'}
    # 캐릭터는 정해지지 않았다
    assert (await seat_of(client, me, table))['character'] is None


async def test_the_same_scores_pass_as_written_but_not_as_bought(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    everything_maxed = dict.fromkeys(SPENT_ALL, 20)

    bought = await buy(client, me, table, everything_maxed)
    written = await write(client, me, table, everything_maxed)

    # 방식이 다르면 제한이 다르다. 그래서 방식을 자리에 적어 둔다. 점수제라고 적힌 캐릭터는 총점을 지킨 것이다
    assert bought.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert written.status_code == status.HTTP_200_OK
    assert written.json()['members'][0]['character_mode'] == 'manual'


@pytest.mark.parametrize(
    'extra',
    [{'spent': 0}, {'cost': 0}, {'budget': 99}, {'max_hp': 99}, {'hp': 99}],
    ids=['spent', 'cost', 'budget', 'max_hp', 'hp'],
)
async def test_the_client_cannot_send_the_sum(client: AsyncClient, me: dict[str, str], extra: dict):
    table = await open_table(client, me)

    response = await buy(client, me, table, SPENT_ALL, **extra)

    # 든 값은 서버가 규칙으로 계산한다. 보낸 합계나 총점을 받는 칸이 없다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_refused_purchase_leaves_the_character_as_it_was(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await buy(client, me, table, SPENT_ALL)

    refused = await buy(client, me, table, dict.fromkeys(SPENT_ALL, 15), name='드워프')

    assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    seat = await seat_of(client, me, table)
    assert (seat['character']['name'], seat['abilities']) == ('엘프', SPENT_ALL)


async def test_buying_again_replaces_the_scores(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await buy(client, me, table, SPENT_ALL)

    again = await buy(client, me, table, scores(con=15))

    assert again.json()['members'][0]['abilities'] == scores(con=15)


async def test_changing_the_way_drops_the_bought_scores(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await buy(client, me, table, SPENT_ALL)

    changed = await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)

    member = changed.json()['members'][0]
    assert (member['character_mode'], member['abilities']) == ('custom', None)


@pytest.mark.parametrize(
    'body',
    [
        {'mode': 'point_buy', 'name': '엘프'},
        {'mode': 'point_buy', 'abilities': SPENT_ALL},
        {'mode': 'point_buy', 'name': '엘프', 'abilities': SPENT_ALL, 'pregen_index': 0},
    ],
    ids=['no abilities', 'no name', 'with a pregen'],
)
def test_rejects_a_purchase_with_a_bad_shape(body: dict):
    with pytest.raises(ValidationError):
        CharacterUpdate.model_validate(body)


def test_reads_point_buy_as_the_way():
    update = CharacterUpdate.model_validate({'mode': 'point_buy', 'name': '엘프', 'abilities': SPENT_ALL})

    assert update.chosen_mode == CharacterMode.POINT_BUY


# --- 시작하면 시트가 된다 ---


@pytest.mark.parametrize(
    ('con', 'max_hp'),
    # 기준 10, 상한 12. 보정은 (건강 - 10) // 2. 살 수 있는 점수는 8~15 다
    [(8, 9), (10, 10), (12, 11), (14, 12), (15, 12)],
)
async def test_starting_turns_bought_scores_into_a_sheet(client: AsyncClient, me: dict[str, str], con: int, max_hp):
    table = await open_table(client, me)
    chosen = scores(str=14, con=con)
    await buy(client, me, table, chosen)

    started = await start(client, me, table)

    # 최대 HP 를 구하는 법은 직접 적기와 같다. 방식이 다른 것은 받을 때의 제한뿐이다
    member = started['members'][0]
    assert member['sheet'] == {'abilities': chosen, 'max_hp': max_hp, 'hp': max_hp}
    assert member['character_mode'] == 'point_buy'


async def test_scores_cannot_be_bought_after_the_game_starts(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await buy(client, me, table, SPENT_ALL)
    await start(client, me, table)

    response = await buy(client, me, table, scores())

    assert response.status_code == status.HTTP_409_CONFLICT


# --- 판단만 하는 작은 것. DB 를 쓰지 않는다 ---


@pytest.mark.parametrize(
    ('mode', 'abilities', 'obeys'),
    [
        (CharacterMode.POINT_BUY, SPENT_ALL, True),
        (CharacterMode.POINT_BUY, dict.fromkeys(SPENT_ALL, 15), False),
        # 직접 적기는 거는 제한이 없다
        (CharacterMode.MANUAL, dict.fromkeys(SPENT_ALL, 20), True),
    ],
    ids=['bought within the budget', 'bought over the budget', 'written'],
)
def test_each_way_has_its_own_limit(mode: CharacterMode, abilities: dict, obeys: bool):
    assert sheets.obeys_mode(SRD5, mode, abilities) is obeys


def test_nothing_can_be_bought_where_the_rules_have_no_point_buy():
    # 게시 조건이 막는 일이다. 그래도 생기면 아무것도 살 수 없다
    assert not sheets.obeys_mode(NO_POINT_BUY, CharacterMode.POINT_BUY, scores())


# --- DB 의 마지막 방어선 ---


async def test_the_database_takes_the_new_way(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = await open_table(client, me)
    await buy(client, me, table, SPENT_ALL)

    assert await session.scalar(text('SELECT character_modes FROM scenarios')) == WITH_POINT_BUY
    assert await session.scalar(text('SELECT character_modes FROM game_tables')) == WITH_POINT_BUY
    assert await session.scalar(text('SELECT character_mode FROM table_members')) == 'point_buy'
