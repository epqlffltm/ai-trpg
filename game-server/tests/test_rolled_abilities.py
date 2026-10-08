# game-server/tests/test_rolled_abilities.py

"""
능력치의 점수를 주사위로 정하는 방식(rolled)을 검증한다.

두 걸음이다. 먼저 굴리고(POST .../character/roll), 그 점수를 원하는 능력치에 놓는다(PUT .../character).
굴리는 것은 서버다. 계산 자체는 tests/test_score_roll.py 가 본다.

보는 것은 다섯이다.
  - 제작자가 켜야 쓸 수 있고, 방장은 뺄 수 있다. 굴리는 법은 룰북의 규칙에 있다.
  - 굴린 점수는 테이블에 적히고 모두에게 보인다. 한 테이블에서 한 사람은 한 번 굴린다.
    나갔다가 다시 들어와도 굴린 것이 남아 있다.
  - 굴린 점수를 남김없이 한 번씩 써서 능력치에 놓는다. 어디에 놓을지는 자유다.
  - 다시 굴리는 길은 하나다. 제작자가 허락했고, 방장이 그 사람에게 "한 번 더"를 줬을 때다.
  - DB 가 새 방식을 받는다.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import DEFAULT_CHARACTER_MODES, PLAYER_MADE_MODES, CharacterMode
from app.assets.scenarios.publishing import Problem, find_score_roll_problems
from app.engine.dice import ScriptedDice
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.tables import sheets
from app.tables.models import TableRoll
from app.tables.schemas import CharacterUpdate
from tests.sheets import handed_out, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

ABILITIES = ['str', 'dex', 'con', 'int', 'wis', 'cha']

# 기본 시트. 굴린 점수와 섞이지 않았는지 알아볼 수 있게 최대 HP 를 다르게 둔다
DEFAULT_SHEET = make_sheet(max_hp=7)
# 최대 HP 를 구하는 값. 기준 10, 상한 12
HP = {'base': 10, 'cap': 12}

WITH_ROLLED = ['custom', 'manual', 'rolled']

# 처음 굴려 나오는 점수와 다시 굴려 나오는 점수
FIRST = [15, 14, 13, 12, 10, 8]
SECOND = [6, 6, 5, 5, 4, 3]

# 굴리는 법이 없는 규칙
NO_SCORE_ROLL = Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'score_roll': None})


def dice_for(score: int) -> list[int]:
    """
    4d6 에서 높은 셋을 더해 이 점수가 나오는 눈 넷. 버려지는 눈(1)을 맨 앞에 둔다.

    셋의 합이 점수가 되게 고르게 나눈다. 14 는 [1, 5, 5, 4] 다.
    """
    kept = [score // 3 + (1 if index < score % 3 else 0) for index in range(3)]
    return [1, *kept]


def dice_for_all(scores: list[int]) -> list[int]:
    """점수 여럿이 차례로 나오는 눈들."""
    return [die for score in scores for die in dice_for(score)]


def place(scores: list[int]) -> dict[str, int]:
    """점수들을 능력치에 차례로 놓는다."""
    return dict(zip(ABILITIES, scores, strict=True))


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 시나리오를 만들고 테이블을 여는 사람이다. 방장이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def dice(app: FastAPI) -> ScriptedDice:
    """
    앱에 꽂은 주사위. 처음 굴리면 FIRST 가, 다시 굴리면 SECOND 가 나온다.

    눈은 두 번 굴릴 만큼만 있다. 그보다 더 굴리면 오류가 난다. 굴리면 안 되는 때에 굴렸는지를 남은 눈으로 본다.
    """
    scripted = ScriptedDice(dice_for_all(FIRST) + dice_for_all(SECOND))
    app.state.dice = scripted
    return scripted


# 한 번 굴리는 데 쓰는 눈의 수. 4d6 여섯 번
ONE_ROLL = 24


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
    """주사위로 정하기를 허용하는 시나리오를 만들고 판을 하나 낸다. 다시 굴리기는 주지 않으면 허락하지 않는다."""
    fields = {'character_modes': WITH_ROLLED, 'player_made_hp': HP, **fields}
    scenario = await make_scenario(client, headers, **fields)
    response = await publish(client, headers, scenario)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return scenario


async def create_table(client: AsyncClient, headers: dict[str, str], scenario: dict, **fields):
    """판으로 테이블을 만드는 요청을 보낸다. 응답을 그대로 돌려준다."""
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    body.update(fields)
    return await client.post(TABLES_URL, json=body, headers=headers)


async def open_table(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    """두 사람이 앉는 테이블을 연다. fields 는 시나리오에 준다(reroll_allowed 같은 것)."""
    scenario = await published(client, headers, **fields)
    response = await create_table(client, headers, scenario)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def join(client: AsyncClient, headers: dict[str, str], table: dict) -> None:
    response = await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text


async def roll(client: AsyncClient, headers: dict[str, str], table: dict):
    """능력치의 점수를 굴리는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.post(table_url(table, '/character/roll'), headers=headers)


async def assign(client: AsyncClient, headers: dict[str, str], table: dict, abilities: dict, **fields):
    """굴린 점수를 능력치에 놓아 캐릭터를 정하는 요청을 보낸다. 응답을 그대로 돌려준다."""
    body = {'mode': 'rolled', 'name': '엘프', 'abilities': abilities, **fields}
    return await client.put(table_url(table, '/character'), json=body, headers=headers)


async def grant(client: AsyncClient, headers: dict[str, str], table: dict, user_id: uuid.UUID):
    """한 사람에게 "한 번 더"를 주는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.post(table_url(table, f'/members/{user_id}/reroll'), headers=headers)


async def start(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.post(table_url(table, '/start'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def seat_of(table: dict, user_id: uuid.UUID) -> dict:
    """테이블의 응답에서 그 사람의 자리를 꺼낸다."""
    return next(member for member in table['members'] if member['user_id'] == str(user_id))


async def read_seat(client: AsyncClient, headers: dict[str, str], table: dict, user_id: uuid.UUID) -> dict:
    """지금의 테이블을 다시 읽어 그 사람의 자리를 꺼낸다."""
    return seat_of((await client.get(table_url(table), headers=headers)).json(), user_id)


async def read_events(client: AsyncClient, headers: dict[str, str], table: dict, type_: str) -> list[dict]:
    """이 테이블의 이벤트 중 그 종류만 꺼낸다."""
    events = (await client.get(table_url(table, '/events'), headers=headers)).json()['items']
    return [event for event in events if event['type'] == type_]


# --- 제작자가 켜야 쓸 수 있다 ---


def test_rolling_is_a_way_where_the_player_ends_up_with_their_own_numbers():
    # 플레이어가 능력치를 정하는 방식이다. 최대 HP 를 구하는 값이 있어야 하고, 능력치를 적어야 한다
    assert CharacterMode.ROLLED in PLAYER_MADE_MODES
    # 방식이 늘어도 고르지 않았을 때 허용하는 것은 처음의 둘이다
    assert DEFAULT_CHARACTER_MODES == [CharacterMode.PREGEN, CharacterMode.CUSTOM]


async def test_a_new_scenario_allows_neither_rolling_nor_rerolling(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me)

    assert scenario['character_modes'] == ['pregen', 'custom']
    assert scenario['reroll_allowed'] is False


async def test_the_creator_can_allow_rolling_and_rerolling(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(
        client, me, character_modes=['rolled', 'pregen'], player_made_hp=HP, reroll_allowed=True
    )

    # 방식은 보낸 순서와 상관없이 정해진 순서로 돌아온다
    assert scenario['character_modes'] == ['pregen', 'rolled']
    assert scenario['reroll_allowed'] is True


async def test_rerolling_can_be_turned_on_and_off(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me)
    url = f'{SCENARIOS_URL}/{scenario["id"]}'

    on = await client.patch(url, json={'reroll_allowed': True}, headers=me)
    untouched = await client.patch(url, json={'title': '새 제목'}, headers=me)
    off = await client.patch(url, json={'reroll_allowed': False}, headers=me)

    assert on.json()['reroll_allowed'] is True
    # 보내지 않으면 그대로다
    assert untouched.json()['reroll_allowed'] is True
    assert off.json()['reroll_allowed'] is False


@pytest.mark.parametrize('value', ['maybe', 2, [True]])
async def test_rejects_a_reroll_setting_that_is_not_true_or_false(client: AsyncClient, me: dict[str, str], value):
    scenario = await make_scenario(client, me)

    response = await client.patch(f'{SCENARIOS_URL}/{scenario["id"]}', json={'reroll_allowed': value}, headers=me)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_publishing_needs_the_hp_values_when_rolling_is_allowed(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(client, me, character_modes=['rolled'], default_sheet=None)

    response = await publish(client, me, scenario)

    # 주사위도 플레이어가 능력치를 갖게 되는 방식이다. 최대 HP 를 구하는 값이 없으면 그 캐릭터의 HP 를 정할 수 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['problems'] == ['player_made_hp_missing']


async def test_the_version_keeps_how_to_roll_and_whether_rerolls_are_allowed(client: AsyncClient, me: dict[str, str]):
    scenario = await make_scenario(
        client, me, character_modes=['rolled'], player_made_hp=HP, default_sheet=None, reroll_allowed=True
    )

    response = await publish(client, me, scenario)

    assert response.status_code == status.HTTP_201_CREATED
    snapshot = response.json()['snapshot']
    assert (snapshot['character_modes'], snapshot['reroll_allowed']) == (['rolled'], True)
    # 굴리는 법은 규칙과 함께 판에 굳는다
    assert snapshot['rulebook']['rules']['score_roll'] == {'count': 4, 'sides': 6, 'keep': 3}


@pytest.mark.parametrize(
    ('modes', 'ruleset', 'problems'),
    [
        (['rolled'], NO_SCORE_ROLL, [Problem.SCORE_ROLL_MISSING]),
        (['custom', 'rolled'], NO_SCORE_ROLL, [Problem.SCORE_ROLL_MISSING]),
        (['rolled'], SRD5, []),
        # 그 방식을 허용하지 않았으면 규칙에 굴리는 법이 없어도 된다
        (['custom', 'manual'], NO_SCORE_ROLL, []),
        # 룰북이 없으면 볼 수 없다. 룰북이 없다는 문제는 다른 곳이 적는다
        (['rolled'], None, []),
    ],
    ids=['missing', 'missing among others', 'present', 'not allowed', 'no rulebook'],
)
def test_rolling_needs_rules_that_say_how(modes: list[str], ruleset: Ruleset | None, problems: list[Problem]):
    # 지금의 템플릿(srd5)에는 굴리는 법이 있어서 API 로는 이 문제를 만들 수 없다. 판단하는 함수를 직접 부른다.
    # 이 함수는 시나리오에서 허용한 방식만 읽는다
    scenario = SimpleNamespace(character_modes=modes)

    assert find_score_roll_problems(scenario, ruleset) == problems


# --- 방장은 뺄 수 있다. 넣을 수는 없다 ---


async def test_the_table_shows_how_scores_are_rolled(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    assert table['character_modes'] == WITH_ROLLED
    assert table['rules']['score_roll'] == {'count': 4, 'sides': 6, 'keep': 3}
    # 제작자가 다시 굴리기를 허락하지 않았다
    assert table['reroll_allowed'] is False
    # 아직 아무도 굴리지 않았다
    assert seat_of(table, ME)['roll'] is None


async def test_the_host_can_leave_out_rolling(client: AsyncClient, me: dict[str, str], dice: ScriptedDice):
    scenario = await published(client, me, reroll_allowed=True)
    table = (await create_table(client, me, scenario, character_modes=['custom', 'manual'])).json()

    refused = await roll(client, me, table)

    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'character_mode_not_allowed'
    # 굴리지 않았다
    assert dice.remaining == 2 * ONE_ROLL
    # 그 방식을 쓰지 않는 테이블에서는 다시 굴리기도 뜻이 없다. 제작자가 허락했어도 켜진 것으로 보이지 않는다
    assert table['reroll_allowed'] is False


async def test_the_host_cannot_add_rolling(client: AsyncClient, me: dict[str, str]):
    scenario = await published(client, me, character_modes=['custom', 'manual'])

    response = await create_table(client, me, scenario, character_modes=['custom', 'rolled'])

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'character_modes 에 고를 수 없는 값이 있습니다.'}


# --- 굴린다 ---


async def test_the_server_rolls_and_everyone_sees_every_die(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)
    await join(client, friend, table)

    response = await roll(client, me, table)

    assert response.status_code == status.HTTP_200_OK
    mine = seat_of(response.json(), ME)['roll']
    assert mine['scores'] == FIRST
    # 버린 눈(1)까지 그대로 보인다. 15 는 5, 5, 5 에서 왔다
    assert mine['dice'][0] == [1, 5, 5, 5]
    assert len(mine['dice']) == 6
    assert (mine['times_rolled'], mine['reroll_granted']) == (1, False)
    # 같은 테이블의 다른 사람도 본다. 그 사람은 아직 굴리지 않았다
    seen = (await client.get(table_url(table), headers=friend)).json()
    assert seat_of(seen, ME)['roll'] == mine
    assert seat_of(seen, FRIEND)['roll'] is None
    assert dice.remaining == ONE_ROLL


async def test_rolling_does_not_make_a_character_yet(client: AsyncClient, me: dict[str, str], dice: ScriptedDice):
    table = await open_table(client, me)

    response = await roll(client, me, table)

    # 굴린 것은 점수의 묶음이다. 어느 능력치에 놓을지는 아직 정하지 않았다
    seat = seat_of(response.json(), ME)
    assert (seat['character'], seat['character_mode'], seat['abilities']) == (None, None, None)


@pytest.mark.parametrize('body', [{'scores': [18] * 6}, {'dice': [[6, 6, 6, 6]] * 6}, {'seed': 1}])
async def test_the_client_cannot_send_what_was_rolled(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice, body: dict
):
    table = await open_table(client, me)

    response = await client.post(table_url(table, '/character/roll'), json=body, headers=me)

    # 본문을 읽지 않는다. 무엇을 보내든 서버가 굴린 것이 적힌다
    assert seat_of(response.json(), ME)['roll']['scores'] == FIRST


async def test_each_player_rolls_their_own(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)
    await join(client, friend, table)

    await roll(client, me, table)
    response = await roll(client, friend, table)

    seen = response.json()
    assert seat_of(seen, ME)['roll']['scores'] == FIRST
    assert seat_of(seen, FRIEND)['roll']['scores'] == SECOND


async def test_a_player_rolls_only_once(client: AsyncClient, me: dict[str, str], dice: ScriptedDice):
    table = await open_table(client, me)
    await roll(client, me, table)

    again = await roll(client, me, table)

    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'already_rolled'
    # 주사위를 건드리지 않았고, 처음의 점수가 그대로다
    assert dice.remaining == ONE_ROLL
    assert (await read_seat(client, me, table, ME))['roll']['scores'] == FIRST


async def test_leaving_and_coming_back_does_not_buy_a_new_roll(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await roll(client, friend, table)

    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    await join(client, friend, table)
    again = await roll(client, friend, table)

    assert left.status_code == status.HTTP_204_NO_CONTENT
    # 한 테이블에서 한 번이다. 자리는 새로 생겼지만 굴린 것은 테이블에 남아 있다
    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'already_rolled'
    assert (await read_seat(client, me, table, FRIEND))['roll']['scores'] == FIRST
    assert dice.remaining == ONE_ROLL


async def test_being_kicked_and_coming_back_does_not_buy_a_new_roll(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await roll(client, friend, table)

    kicked = await client.delete(table_url(table, f'/members/{FRIEND}'), headers=me)
    await join(client, friend, kicked.json())
    again = await roll(client, friend, table)

    assert again.json()['reason'] == 'already_rolled'
    assert dice.remaining == ONE_ROLL


async def test_scores_cannot_be_rolled_after_the_game_starts(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice
):
    scenario = await published(client, me)
    table = (await create_table(client, me, scenario, capacity=1)).json()
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await start(client, me, table)

    response = await roll(client, me, table)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_recruiting'
    assert dice.remaining == 2 * ONE_ROLL


async def test_someone_who_is_not_seated_cannot_roll(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)

    response = await roll(client, friend, table)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert dice.remaining == 2 * ONE_ROLL


async def test_the_roll_is_recorded_with_every_die(client: AsyncClient, me: dict[str, str], dice: ScriptedDice):
    table = await open_table(client, me)

    await roll(client, me, table)

    (event,) = await read_events(client, me, table, 'abilities_rolled')
    # 굴려 달라고 한 사람이 actor 다. 눈과 점수가 모두 남는다
    assert event['actor_id'] == str(ME)
    assert event['payload'] == {
        'dice': [dice_for(score) for score in FIRST],
        'scores': FIRST,
        'times_rolled': 1,
    }


# --- 굴린 점수를 능력치에 놓는다 ---


async def test_the_rolled_scores_are_placed_on_any_ability(client: AsyncClient, me: dict[str, str], dice: ScriptedDice):
    table = await open_table(client, me)
    await roll(client, me, table)
    # 굴린 순서와 다르게 놓는다. 가장 높은 것을 건강에 놓았다
    placed = {'str': 8, 'dex': 12, 'con': 15, 'int': 10, 'wis': 14, 'cha': 13}

    response = await assign(client, me, table, placed)

    assert response.status_code == status.HTTP_200_OK
    seat = seat_of(response.json(), ME)
    assert (seat['character_mode'], seat['abilities']) == ('rolled', placed)
    # 굴린 것은 그대로 남아 있다. 놓은 것과 견주어 볼 수 있다
    assert seat['roll']['scores'] == FIRST
    # 시트는 아직 없다. 게임을 시작할 때 생긴다
    assert seat['sheet'] is None


@pytest.mark.parametrize(
    'placed',
    [
        # 굴리지 않은 점수
        place([16, 14, 13, 12, 10, 8]),
        place([18, 18, 18, 18, 18, 18]),
        # 좋은 점수를 두 번 썼다
        place([15, 15, 13, 12, 10, 8]),
        # 나쁜 점수를 버리고 다른 것을 한 번 더 썼다
        place([15, 14, 13, 12, 10, 10]),
        # 다 놓지 않았다. 규칙의 능력치가 빠졌다
        {'str': 15, 'dex': 14},
        # 규칙에 없는 능력치에 놓았다
        {'str': 15, 'dex': 14, 'con': 13, 'int': 12, 'wis': 10, 'luck': 8},
        {},
    ],
    ids=['not rolled', 'all eighteens', 'used twice', 'dropped the worst', 'not all placed', 'unknown', 'empty'],
)
async def test_every_rolled_score_must_be_used_exactly_once(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice, placed: dict
):
    table = await open_table(client, me)
    await roll(client, me, table)

    response = await assign(client, me, table, placed)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'abilities 에 고를 수 없는 값이 있습니다.'}
    # 캐릭터는 정해지지 않았다
    assert (await read_seat(client, me, table, ME))['character'] is None


async def test_scores_cannot_be_placed_before_they_are_rolled(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)

    response = await assign(client, me, table, place(FIRST))

    # 보낸 값이 틀린 것이 아니라 순서가 틀렸다. 먼저 굴려야 한다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_rolled'
    assert dice.remaining == 2 * ONE_ROLL


async def test_another_players_roll_cannot_be_used(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)
    await join(client, friend, table)
    await roll(client, me, table)
    await roll(client, friend, table)

    # 친구가 내 점수(FIRST)를 자기 것처럼 놓으려 한다
    response = await assign(client, friend, table, place(FIRST))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_the_scores_can_be_placed_again_in_another_order(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)
    await roll(client, me, table)
    await assign(client, me, table, place(FIRST))

    again = await assign(client, me, table, place(list(reversed(FIRST))))

    # 놓는 것은 모집 중에는 몇 번이든 바꿀 수 있다. 바뀌지 않는 것은 굴린 점수다
    assert again.status_code == status.HTTP_200_OK
    assert seat_of(again.json(), ME)['abilities'] == place(list(reversed(FIRST)))
    assert dice.remaining == ONE_ROLL


async def test_the_roll_survives_a_change_of_way(client: AsyncClient, me: dict[str, str], dice: ScriptedDice):
    table = await open_table(client, me)
    await roll(client, me, table)
    await assign(client, me, table, place(FIRST))

    changed = await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    back = await assign(client, me, table, place(FIRST))

    # 다른 방식으로 바꾸면 놓아 둔 능력치는 지워지지만 굴린 것은 남는다. 돌아오면 같은 점수를 다시 놓는다
    seat = seat_of(changed.json(), ME)
    assert (seat['character_mode'], seat['abilities'], seat['roll']['scores']) == ('custom', None, FIRST)
    assert back.status_code == status.HTTP_200_OK
    assert dice.remaining == ONE_ROLL


async def test_the_same_scores_pass_as_written_but_not_as_rolled(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me)
    await roll(client, me, table)
    everything_maxed = dict.fromkeys(ABILITIES, 18)

    rolled = await assign(client, me, table, everything_maxed)
    written = await client.put(
        table_url(table, '/character'),
        json={'mode': 'manual', 'name': '엘프', 'abilities': everything_maxed},
        headers=me,
    )

    # 방식이 다르면 제한이 다르다. 주사위라고 적힌 캐릭터는 서버가 굴린 점수를 그대로 쓴 것이다
    assert rolled.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert written.status_code == status.HTTP_200_OK
    assert seat_of(written.json(), ME)['character_mode'] == 'manual'


@pytest.mark.parametrize(
    'body',
    [
        {'mode': 'rolled', 'name': '엘프'},
        {'mode': 'rolled', 'abilities': place(FIRST)},
        {'mode': 'rolled', 'name': '엘프', 'abilities': place(FIRST), 'pregen_index': 0},
        # 굴린 점수를 함께 적어 보낼 수 없다
        {'mode': 'rolled', 'name': '엘프', 'abilities': place(FIRST), 'scores': FIRST},
        {'mode': 'rolled', 'name': '엘프', 'abilities': place(FIRST), 'roll': {'scores': FIRST}},
    ],
    ids=['no abilities', 'no name', 'with a pregen', 'with scores', 'with a roll'],
)
def test_rejects_a_placement_with_a_bad_shape(body: dict):
    with pytest.raises(ValidationError):
        CharacterUpdate.model_validate(body)


# --- 시작하면 시트가 된다 ---


@pytest.mark.parametrize(
    ('con', 'max_hp'),
    # 기준 10, 상한 12. 보정은 (건강 - 10) // 2. 굴린 점수 중 하나를 건강에 놓는다
    [(15, 12), (14, 12), (13, 11), (12, 11), (10, 10), (8, 9)],
)
async def test_starting_turns_placed_scores_into_a_sheet(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice, con: int, max_hp: int
):
    scenario = await published(client, me)
    table = (await create_table(client, me, scenario, capacity=1)).json()
    await roll(client, me, table)
    others = [score for score in FIRST if score != con]
    placed = dict(zip(['str', 'dex', 'int', 'wis', 'cha'], others, strict=True)) | {'con': con}
    await assign(client, me, table, placed)

    started = await start(client, me, table)

    # 최대 HP 를 구하는 법은 다른 방식과 같다. 방식이 다른 것은 받을 때의 제한뿐이다
    member = started['members'][0]
    assert member['sheet'] == handed_out({'abilities': placed, 'max_hp': max_hp})
    assert member['character_mode'] == 'rolled'


async def test_a_player_who_only_rolled_has_no_character_to_start_with(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice
):
    scenario = await published(client, me)
    table = (await create_table(client, me, scenario, capacity=1)).json()
    await roll(client, me, table)

    response = await client.post(table_url(table, '/start'), headers=me)

    # 굴리기만 하고 놓지 않았다. 캐릭터가 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'characters_missing'


# --- 한 번 더 ---


async def test_the_table_shows_that_rerolls_can_be_granted(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, reroll_allowed=True)

    assert table['reroll_allowed'] is True


async def test_the_host_grants_one_more_roll_to_one_player(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)

    granted = await grant(client, me, table, FRIEND)
    rerolled = await roll(client, friend, table)

    assert granted.status_code == status.HTTP_200_OK
    assert seat_of(granted.json(), FRIEND)['roll']['reroll_granted'] is True
    # 받은 사람이 다시 굴렸다. 새 점수로 바뀌고, 받은 것은 써서 없어졌다
    assert rerolled.status_code == status.HTTP_200_OK
    assert seat_of(rerolled.json(), FRIEND)['roll'] == {
        'dice': [dice_for(score) for score in SECOND],
        'scores': SECOND,
        'times_rolled': 2,
        'reroll_granted': False,
    }
    assert dice.remaining == 0


async def test_one_grant_is_one_roll(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)
    await grant(client, me, table, FRIEND)
    await roll(client, friend, table)

    third = await roll(client, friend, table)

    assert third.status_code == status.HTTP_409_CONFLICT
    assert third.json()['reason'] == 'already_rolled'
    assert (await read_seat(client, me, table, FRIEND))['roll']['scores'] == SECOND


async def test_the_grant_is_for_that_player_only(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, me, table)
    await roll(client, friend, table)
    await grant(client, me, table, FRIEND)

    mine = await roll(client, me, table)

    # 친구에게 준 것이다. 방장 자신은 다시 굴리지 못한다
    assert mine.status_code == status.HTTP_409_CONFLICT
    assert mine.json()['reason'] == 'already_rolled'
    assert dice.remaining == 0


async def test_rerolling_drops_the_character_made_from_the_old_scores(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)
    await assign(client, friend, table, place(FIRST))
    await grant(client, me, table, FRIEND)

    rerolled = await roll(client, friend, table)
    old = await assign(client, friend, table, place(FIRST))
    new = await assign(client, friend, table, place(SECOND))

    # 옛 점수로 만든 캐릭터는 지워진다. 새 점수와 맞지 않는 능력치가 자리에 남지 않는다
    seat = seat_of(rerolled.json(), FRIEND)
    assert (seat['character'], seat['character_mode'], seat['abilities']) == (None, None, None)
    # 옛 점수는 더 쓸 수 없다. 다시 굴린 것은 되돌리지 못한다
    assert old.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert new.status_code == status.HTTP_200_OK


async def test_rerolling_keeps_a_character_made_another_way(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)
    await client.put(table_url(table, '/character'), json={'name': '드워프'}, headers=friend)
    await grant(client, me, table, FRIEND)

    rerolled = await roll(client, friend, table)

    # 기본 시트를 받기로 한 캐릭터는 굴림과 상관없다. 그대로 둔다
    seat = seat_of(rerolled.json(), FRIEND)
    assert (seat['character']['name'], seat['character_mode']) == ('드워프', 'custom')
    assert seat['roll']['scores'] == SECOND


async def test_a_grant_that_was_not_used_does_not_change_the_scores(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)
    await assign(client, friend, table, place(FIRST))

    granted = await grant(client, me, table, FRIEND)

    # 받기만 하고 굴리지 않았다. 점수도 캐릭터도 그대로다. 다시 굴릴지는 받은 사람이 정한다
    seat = seat_of(granted.json(), FRIEND)
    assert (seat['roll']['scores'], seat['abilities']) == (FIRST, place(FIRST))
    assert dice.remaining == ONE_ROLL


async def test_the_host_cannot_grant_what_the_creator_did_not_allow(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    # 제작자가 다시 굴리기를 허락하지 않은 시나리오다
    table = await open_table(client, me)
    await join(client, friend, table)
    await roll(client, friend, table)

    refused = await grant(client, me, table, FRIEND)
    again = await roll(client, friend, table)

    # 나쁜 눈이 나와도 그대로 가는 것이 이 시나리오의 뜻이다. 방장도 바꾸지 못한다
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'reroll_not_allowed'
    assert again.json()['reason'] == 'already_rolled'
    assert dice.remaining == ONE_ROLL


async def test_only_the_host_grants(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)

    # 참가자가 자기 자신에게 주려 한다
    response = await grant(client, friend, table, FRIEND)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert (await read_seat(client, me, table, FRIEND))['roll']['reroll_granted'] is False


async def test_the_host_may_grant_themselves_and_everyone_sees_it(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await roll(client, me, table)

    granted = await grant(client, me, table, ME)

    # 방장도 플레이어다. 막지 않는다. 누가 누구에게 줬는지가 이벤트로 남아 모두에게 보인다
    assert granted.status_code == status.HTTP_200_OK
    (event,) = await read_events(client, me, table, 'reroll_granted')
    assert (event['actor_id'], event['payload']) == (str(ME), {'user_id': str(ME)})


async def test_a_player_who_has_not_rolled_cannot_be_granted_one_more(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)

    response = await grant(client, me, table, FRIEND)

    # 아직 한 번도 굴리지 않았다. "한 번 더"를 줄 것이 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_rolled'


async def test_grants_do_not_pile_up(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], dice: ScriptedDice
):
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)
    await grant(client, me, table, FRIEND)

    twice = await grant(client, me, table, FRIEND)

    # 주어진 것은 한 번에 하나다. 쓰고 나면 다시 줄 수 있다
    assert twice.status_code == status.HTTP_409_CONFLICT
    assert twice.json()['reason'] == 'reroll_already_granted'


async def test_the_host_can_grant_again_after_it_was_used(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], app: FastAPI
):
    # 세 번 굴릴 만큼의 눈을 꽂는다
    app.state.dice = ScriptedDice(dice_for_all(FIRST) + dice_for_all(SECOND) + dice_for_all(FIRST))
    table = await open_table(client, me, reroll_allowed=True)
    await join(client, friend, table)
    await roll(client, friend, table)
    await grant(client, me, table, FRIEND)
    await roll(client, friend, table)

    again = await grant(client, me, table, FRIEND)
    third = await roll(client, friend, table)

    # 몇 번까지 줄지는 방장이 정한다. 몇 번 굴렸는지는 모두에게 보인다
    assert again.status_code == status.HTTP_200_OK
    assert seat_of(third.json(), FRIEND)['roll']['times_rolled'] == 3
    assert len(await read_events(client, me, table, 'abilities_rolled')) == 3


async def test_someone_who_is_not_at_the_table_cannot_be_granted(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me, reroll_allowed=True)

    response = await grant(client, me, table, FRIEND)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_one_more_cannot_be_granted_after_the_game_starts(
    client: AsyncClient, me: dict[str, str], dice: ScriptedDice
):
    scenario = await published(client, me, reroll_allowed=True)
    table = (await create_table(client, me, scenario, capacity=1)).json()
    await roll(client, me, table)
    await assign(client, me, table, place(FIRST))
    await start(client, me, table)

    response = await grant(client, me, table, ME)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_recruiting'


async def test_one_more_cannot_be_granted_where_rolling_is_not_used(client: AsyncClient, me: dict[str, str]):
    scenario = await published(client, me, reroll_allowed=True)
    table = (await create_table(client, me, scenario, character_modes=['custom'])).json()

    response = await grant(client, me, table, ME)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_mode_not_allowed'


# --- 판단만 하는 작은 것. DB 를 쓰지 않는다 ---


def make_roll(scores: list[int], reroll_granted: bool = False) -> TableRoll:
    return TableRoll(user_id=ME, dice=[], scores=scores, times_rolled=1, reroll_granted=reroll_granted)


def test_a_player_may_roll_when_they_have_not_or_were_granted_one_more():
    assert sheets.may_roll(None)
    assert not sheets.may_roll(make_roll(FIRST))
    assert sheets.may_roll(make_roll(FIRST, reroll_granted=True))


def test_rolled_abilities_must_come_from_the_roll():
    assert sheets.obeys_mode(SRD5, CharacterMode.ROLLED, place(FIRST), make_roll(FIRST))
    assert not sheets.obeys_mode(SRD5, CharacterMode.ROLLED, place(SECOND), make_roll(FIRST))
    # 굴린 적이 없으면 지킨 것이 아니다
    assert not sheets.obeys_mode(SRD5, CharacterMode.ROLLED, place(FIRST), None)
    # 굴린 것이 있어도 다른 방식의 제한은 그 방식의 것이다
    assert sheets.obeys_mode(SRD5, CharacterMode.MANUAL, place(SECOND), make_roll(FIRST))


# --- DB 의 마지막 방어선 ---


async def test_the_database_takes_the_new_way(client: AsyncClient, me: dict[str, str], session: AsyncSession, dice):
    table = await open_table(client, me)
    await roll(client, me, table)
    await assign(client, me, table, place(FIRST))

    assert await session.scalar(text('SELECT character_modes FROM scenarios')) == WITH_ROLLED
    assert await session.scalar(text('SELECT character_modes FROM game_tables')) == WITH_ROLLED
    assert await session.scalar(text('SELECT character_mode FROM table_members')) == 'rolled'


async def test_the_database_keeps_one_roll_for_a_player_at_a_table(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, dice
):
    table = await open_table(client, me)
    await roll(client, me, table)

    copy = text(
        'INSERT INTO table_rolls (table_id, user_id, dice, scores, times_rolled) '
        "SELECT table_id, user_id, '[]', '[]', 1 FROM table_rolls"
    )

    with pytest.raises(IntegrityError, match='pk_table_rolls'):
        await session.execute(copy)


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [
        ('times_rolled = 0', 'times_rolled_positive'),
        ("""scores = '{"str": 18}'""", 'rolls_are_arrays'),
        ("dice = 'null'", 'rolls_are_arrays'),
    ],
    ids=['never rolled', 'scores as an object', 'dice as null'],
)
async def test_the_database_rejects_a_bad_roll(
    client: AsyncClient, me: dict[str, str], session: AsyncSession, dice, change: str, constraint: str
):
    table = await open_table(client, me)
    await roll(client, me, table)

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(f'UPDATE table_rolls SET {change}'))


async def test_the_rolls_go_away_with_the_table(client: AsyncClient, me: dict[str, str], session: AsyncSession, dice):
    table = await open_table(client, me)
    await roll(client, me, table)

    await session.execute(text('DELETE FROM game_tables'))

    assert await session.scalar(text('SELECT count(*) FROM table_rolls')) == 0
