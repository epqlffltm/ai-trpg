# game-server/tests/test_round_checks.py

"""
라운드를 닫을 때의 판정을 검증한다.

선언을 마감하는 순간, 행동을 붙인 선언마다 엔진이 주사위를 굴려 결과를 정한다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다(ScriptedDice). 같은 눈이면 같은 결과가 나와야 한다.

보는 것은 다섯이다.
  - 결과가 규칙과 시트에서 나온다. 선언에 적히고, 모두에게 보인다.
  - 굴릴 것만 굴린다. 행동이 없는 선언, 내지 않은 사람, 떠난 사람은 굴리지 않는다.
  - 결과가 이벤트로 적힌다. 그 판정을 부른 행동에 이어진다.
  - 서술자가 정해진 결과를 받는다.
  - 서술을 다시 맡겨도 다시 굴리지 않는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import ScriptedDice
from app.main import API_PREFIX
from app.rounds import service
from app.rounds.narrator import NarrationRequest, Verdict
from tests.sheets import make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

OPENING = '사이렌이 울린다.'
KICK = '문을 걷어찬다.'
CHARM = '드워프를 구슬린다.'
LAUGH = '크게 웃는다.'

# 모두가 받는 시트. 근력 16(보정 +3), 매력 8(보정 -1), 나머지는 10(보정 0)
STRONG_AND_RUDE = make_sheet(str=16, cha=8)

# 근력으로 보통(목표 15)에, 매력으로 쉬움(목표 10)에 도전한다
KICK_ACTION = {'kind': 'check', 'ability': 'str', 'difficulty': 'medium'}
CHARM_ACTION = {'kind': 'check', 'ability': 'cha', 'difficulty': 'easy'}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 먼저 앉았다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 들어오는 사람의 머리말. 나중에 앉았다. 캐릭터는 '영애'다."""
    return bearer(signing_key, FRIEND)


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    """앱의 주사위를 정해진 눈을 내는 것으로 바꿔 꽂는다. 꽂은 주사위를 돌려준다."""
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


class WatchedDice:
    """굴릴 때마다 몇 면짜리를 굴리라고 했는지 적어 두는 주사위. 늘 1 을 낸다."""

    def __init__(self) -> None:
        self.asked: list[int] = []

    def roll(self, sides: int) -> int:
        self.asked.append(sides)
        return 1


class FlakyNarrator:
    """처음 한 번은 실패하고 그 뒤로는 답하는 서술자. 받은 것을 적어 둔다."""

    def __init__(self) -> None:
        self.requests: list[NarrationRequest] = []

    async def narrate(self, request: NarrationRequest) -> str:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise RuntimeError('서술자가 답하지 못했다')
        return '문이 부서졌다.'


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 시작한다. 규칙은 SRD5 템플릿이고, 둘 다 STRONG_AND_RUDE 시트를 받는다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {
        'title': '추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': [OPENING],
        'default_sheet': STRONG_AND_RUDE,
    }
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return table


async def declare(
    client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None
) -> dict:
    """선언을 내고, 돌아온 라운드를 돌려준다."""
    body = {'content': content} if action is None else {'content': content, 'action': action}
    response = await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def read_round(client: AsyncClient, headers: dict[str, str], table: dict, number: int) -> dict:
    response = await client.get(table_url(table, f'/rounds/{number}'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def outcomes(round_: dict) -> dict[str, dict | None]:
    """라운드의 선언을 {캐릭터 이름: 판정의 결과} 로 바꾼다."""
    return {declaration['character_name']: declaration['outcome'] for declaration in round_['declarations']}


async def read_events(client: AsyncClient, headers: dict[str, str], table: dict) -> list[dict]:
    """첫 라운드를 닫으면서 적힌 이벤트. 시작할 때까지의 다섯은 건너뛴다."""
    response = await client.get(table_url(table, '/events'), params={'after': 5}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


def types(events: list[dict]) -> list[str]:
    return [event['type'] for event in events]


# --- 결과는 규칙과 시트에서 나온다 ---


async def test_closing_a_round_judges_the_actions(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    table = await start_duo(client, me, friend)
    load_dice(app, [12, 10])

    await declare(client, me, table, KICK, KICK_ACTION)
    closing = await declare(client, friend, table, CHARM, CHARM_ACTION)

    assert closing['status'] == 'closing'
    assert outcomes(closing) == {
        # 근력 16 의 보정은 +3 이다. 12 + 3 = 15 는 보통(15) 이상이라 성공이다
        '엘프': {'roll': 12, 'modifier': 3, 'total': 15, 'target': 15, 'success': True},
        # 매력 8 의 보정은 -1 이다. 10 - 1 = 9 는 쉬움(10)에 못 미쳐 실패다
        '영애': {'roll': 10, 'modifier': -1, 'total': 9, 'target': 10, 'success': False},
    }
    # 응답이 아니라 저장된 것을 본다
    stored = await session.scalars(text('SELECT outcome FROM round_declarations ORDER BY character_name'))
    assert [outcome['total'] for outcome in stored] == [15, 9]


async def test_one_short_of_the_target_fails(client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict):
    table = await start_duo(client, me, friend)
    load_dice(app, [11])

    await declare(client, me, table, KICK, KICK_ACTION)
    closing = await declare(client, friend, table, LAUGH)

    assert outcomes(closing)['엘프'] == {'roll': 11, 'modifier': 3, 'total': 14, 'target': 15, 'success': False}


async def test_an_action_without_a_difficulty_is_judged_at_the_default(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [20])

    await declare(client, me, table, KICK, {'kind': 'check', 'ability': 'dex'})
    closing = await declare(client, friend, table, LAUGH)

    # SRD5 의 기본 난이도는 보통(15)이다. 민첩 10 의 보정은 0 이다
    assert outcomes(closing)['엘프'] == {'roll': 20, 'modifier': 0, 'total': 20, 'target': 15, 'success': True}


async def test_the_die_comes_from_the_rules_of_the_table(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = WatchedDice()
    app.state.dice = dice

    await declare(client, me, table, KICK, KICK_ACTION)
    await declare(client, friend, table, CHARM, CHARM_ACTION)

    # 사람마다 한 번씩, 규칙의 주사위(d20)를 굴렸다
    assert dice.asked == [20, 20]


async def test_dice_are_rolled_in_the_order_people_sat_down(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [1, 20])

    # 나중에 앉은 친구가 먼저 선언한다
    await declare(client, friend, table, CHARM, CHARM_ACTION)
    closing = await declare(client, me, table, KICK, KICK_ACTION)

    # 낸 순서가 아니라 앉은 순서로 굴린다. 먼저 앉은 내가 첫 눈을 받는다
    rolls = {name: outcome['roll'] for name, outcome in outcomes(closing).items()}
    assert rolls == {'엘프': 1, '영애': 20}


# --- 결과는 모두에게 보인다 ---


async def test_everyone_sees_the_numbers(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    load_dice(app, [12])
    await declare(client, me, table, KICK, KICK_ACTION)
    await declare(client, friend, table, LAUGH)
    await narrated()

    # 굴리지 않은 친구도 내 굴림을 숫자까지 본다. 닫힌 라운드를 나중에 읽어도 남아 있다
    seen = await read_round(client, friend, table, 1)

    assert seen['status'] == 'closed'
    assert outcomes(seen) == {
        '엘프': {'roll': 12, 'modifier': 3, 'total': 15, 'target': 15, 'success': True},
        '영애': None,
    }


async def test_there_is_no_outcome_while_the_round_is_open(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [12])

    opened = await declare(client, me, table, KICK, KICK_ACTION)

    # 선언을 낼 때는 굴리지 않는다. 다시 낼 수 있는 동안에 굴리면 마음에 들 때까지 다시 낼 수 있다
    assert opened['status'] == 'open'
    assert outcomes(opened) == {'엘프': None}
    assert dice.remaining == 1


@pytest.mark.parametrize(
    'smuggled',
    [
        {'outcome': {'roll': 20, 'modifier': 3, 'total': 23, 'target': 15, 'success': True}},
        {'check': {'roll': 20}},
        {'roll': 20},
    ],
    ids=['outcome', 'check', 'roll'],
)
async def test_a_declaration_cannot_carry_its_own_outcome(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], smuggled: dict
):
    table = await start_duo(client, me, friend)

    body = {'content': KICK, 'action': KICK_ACTION, **smuggled}
    response = await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=me)

    # 결과는 받는 값이 아니다. 주사위는 서버만 굴린다
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 굴릴 것만 굴린다 ---


async def test_a_declaration_without_an_action_rolls_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [12])

    await declare(client, me, table, LAUGH)
    closing = await declare(client, friend, table, LAUGH)

    assert outcomes(closing) == {'엘프': None, '영애': None}
    assert dice.remaining == 1


async def test_someone_who_did_not_declare_rolls_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [12, 7])
    await declare(client, me, table, KICK, KICK_ACTION)

    # 방장이 친구를 기다리지 않고 닫는다
    closing = (await client.post(table_url(table, '/rounds/current/close'), headers=me)).json()

    assert outcomes(closing) == {'엘프': {'roll': 12, 'modifier': 3, 'total': 15, 'target': 15, 'success': True}}
    assert dice.remaining == 1


async def test_someone_who_left_rolls_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [12])
    await declare(client, friend, table, CHARM, CHARM_ACTION)
    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    assert left.status_code == status.HTTP_204_NO_CONTENT

    # 남은 내가 선언을 내서 라운드가 닫기 시작한다
    closing = await declare(client, me, table, LAUGH)

    # 떠난 사람의 선언은 남아 있지만 판정하지 않는다. 이벤트에도 서술에도 들어가지 않는 선언이다
    assert closing['status'] == 'closing'
    assert outcomes(closing) == {'영애': None, '엘프': None}
    assert dice.remaining == 1


async def test_a_round_still_closes_when_someone_has_no_sheet(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession, narrated
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [12, 7])
    # 있을 수 없는 일을 일부러 만든다. 진행 중인 테이블에서 친구의 시트가 사라졌다
    await session.execute(text('DELETE FROM table_sheets WHERE user_id = :user_id'), {'user_id': FRIEND})
    await session.commit()

    await declare(client, me, table, KICK, KICK_ACTION)
    closing = await declare(client, friend, table, CHARM, CHARM_ACTION)
    await narrated()

    # 시트가 없는 사람은 굴리지 못한다. 그래도 라운드는 닫히고 다음 라운드가 열린다
    assert outcomes(closing)['영애'] is None
    assert outcomes(closing)['엘프']['roll'] == 12
    assert dice.remaining == 1
    assert (await read_round(client, me, table, 2))['status'] == 'open'


# --- 이벤트 ---


async def test_a_check_is_recorded_right_after_the_action_that_called_for_it(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [12, 10])
    await declare(client, me, table, KICK, KICK_ACTION)
    await declare(client, friend, table, CHARM, CHARM_ACTION)

    events = await read_events(client, friend, table)

    assert types(events)[:5] == ['player_action', 'check_rolled', 'player_action', 'check_rolled', 'round_closed']
    acted, rolled = events[0], events[1]
    assert rolled['payload'] == {
        'round': 1,
        'character_name': '엘프',
        'ability': 'str',
        'difficulty': 'medium',
        'roll': 12,
        'modifier': 3,
        'total': 15,
        'target': 15,
        'success': True,
    }
    # 판정은 그 행동에서 나왔고, 같은 묶음이다
    assert rolled['caused_by_sequence'] == acted['sequence']
    assert rolled['action_group_id'] == acted['action_group_id']
    # 굴린 것은 플레이어가 아니라 엔진이다
    assert (acted['actor_id'], rolled['actor_id']) == (str(ME), None)
    assert events[3]['payload']['character_name'] == '영애'
    assert events[3]['caused_by_sequence'] == events[2]['sequence']


async def test_an_action_without_a_check_records_no_roll(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [12])
    await declare(client, me, table, LAUGH)
    await declare(client, friend, table, CHARM, CHARM_ACTION)

    events = await read_events(client, me, table)

    assert types(events)[:4] == ['player_action', 'player_action', 'check_rolled', 'round_closed']
    assert events[2]['payload']['character_name'] == '영애'


# --- 서술자는 정해진 결과를 받는다 ---


async def test_the_narrator_is_told_the_verdicts(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    load_dice(app, [12])
    await declare(client, me, table, KICK, KICK_ACTION)
    await declare(client, friend, table, LAUGH)
    await narrated()

    # 가짜 서술자는 받은 것을 그대로 늘어놓는다. 능력은 규칙에 적힌 이름으로 받는다
    scene = (await read_round(client, me, table, 2))['scene']

    assert scene == '[1 라운드의 결과]\n엘프: 문을 걷어찬다. (근력 판정 성공: 12 + 3 = 15, 목표 15)\n영애: 크게 웃는다.'


# --- 다시 맡겨도 다시 굴리지 않는다 ---


async def test_narrating_again_does_not_roll_again(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    friend: dict[str, str],
    narrated,
    monkeypatch: pytest.MonkeyPatch,
):
    table = await start_duo(client, me, friend)
    narrator = FlakyNarrator()
    app.state.narrator = narrator
    load_dice(app, [12])
    await declare(client, me, table, KICK, KICK_ACTION)
    await declare(client, friend, table, LAUGH)
    # 첫 서술이 실패했다. 라운드는 닫는 중에 머문다
    await narrated()
    assert (await read_round(client, me, table, 1))['status'] == 'closing'

    # 이번에 굴리면 20 이 나온다. 굴리지 않아야 한다
    dice = load_dice(app, [20])
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    assert again.status_code == status.HTTP_202_ACCEPTED
    assert dice.remaining == 1
    # 결과는 처음 굴린 그대로다
    closed = await read_round(client, me, table, 1)
    assert (closed['status'], outcomes(closed)['엘프']['roll']) == ('closed', 12)
    # 서술자는 두 번 다 같은 결과를 받았다
    expected = Verdict(ability='근력', difficulty='보통', roll=12, modifier=3, total=15, target=15, success=True)
    assert [request.moves[0].verdict for request in narrator.requests] == [expected, expected]
    # 판정의 이벤트는 하나뿐이다
    assert types(await read_events(client, me, table)).count('check_rolled') == 1
