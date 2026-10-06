# game-server/tests/test_round_health.py

"""
라운드를 닫을 때 HP 가 바뀌는 것과, 쓰러진 캐릭터를 검증한다.

행동에는 판정의 결과에 따라 일어날 일을 붙일 수 있다. 실패의 대가(risk)와 성공의 보상(recover)이다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 한 사람마다 판정의 눈을 먼저, 양의 눈을 그다음에 쓴다.

보는 것은 다섯이다.
  - 실패하면 대가만큼 다치고, 성공하면 대상이 보상만큼 회복한다. HP 는 0 과 최대 사이에 머문다.
  - 받을 때 검사한다. 규칙에 없는 등급, 앉지 않은 대상.
  - 쓰러진 사람은 글만 낼 수 있고, 라운드는 그 사람을 기다리지 않는다.
  - 바뀐 것이 이벤트와 서술에 실린다.
  - 서술을 다시 맡겨도 HP 가 다시 바뀌지 않는다.
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
from app.rounds.narrator import NarrationRequest
from tests.sheets import make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

JUMP = '달리는 바이크에서 뛰어내린다.'
TEND = '상처를 싸맨다.'
LAUGH = '크게 웃는다.'
GROAN = '신음한다.'

# 모두가 받는 시트. 모든 능력치가 10(보정 0)이고 최대 HP 가 10 이다. 눈이 곧 합이다
PLAIN = make_sheet()

# 판정의 눈. 보통(목표 15)에 도전한다
FAIL = 1
PASS = 20


def jump(risk: str = 'light') -> dict:
    """민첩으로 보통에 도전한다. 실패하면 다친다."""
    return {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium', 'risk': risk}


def tend(target: uuid.UUID | None = None, recover: str = 'light') -> dict:
    """지혜로 보통에 도전한다. 성공하면 대상이 회복한다. 대상을 주지 않으면 그 칸을 보내지 않는다."""
    action = {'kind': 'check', 'ability': 'wis', 'difficulty': 'medium', 'recover': recover}
    return action if target is None else {**action, 'target': str(target)}


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


class FlakyNarrator:
    """처음 한 번은 실패하고 그 뒤로는 답하는 서술자. 받은 것을 적어 둔다."""

    def __init__(self) -> None:
        self.requests: list[NarrationRequest] = []

    async def narrate(self, request: NarrationRequest) -> str:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise RuntimeError('서술자가 답하지 못했다')
        return '먼지가 가라앉는다.'


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 시작한다. 규칙은 SRD5 템플릿이고, 둘 다 PLAIN 시트를 받는다. HP 는 10 이다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {
        'title': '추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': PLAIN,
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


async def send(client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None):
    """선언을 내는 요청을 보낸다. 응답을 그대로 돌려준다."""
    body = {'content': content} if action is None else {'content': content, 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


async def declare(
    client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None
) -> dict:
    """선언을 내고, 돌아온 라운드를 돌려준다."""
    response = await send(client, headers, table, content, action)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def current(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.get(table_url(table, '/rounds/current'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def read_round(client: AsyncClient, headers: dict[str, str], table: dict, number: int) -> dict:
    response = await client.get(table_url(table, f'/rounds/{number}'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def hp_of(client: AsyncClient, headers: dict[str, str], table: dict) -> dict[str, int]:
    """테이블에 앉은 사람들의 지금 HP 를 {캐릭터 이름: HP} 로 읽는다. 테이블의 응답에서 읽는다."""
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return {member['character']['name']: member['sheet']['hp'] for member in response.json()['members']}


def effects(round_: dict) -> dict[str, dict | None]:
    """라운드의 선언을 {선언한 캐릭터의 이름: HP 의 변화} 로 바꾼다. 판정이 없던 선언은 빠진다."""
    return {
        declaration['character_name']: declaration['outcome']['effect']
        for declaration in round_['declarations']
        if declaration['outcome'] is not None
    }


async def read_events(client: AsyncClient, headers: dict[str, str], table: dict) -> list[dict]:
    """첫 라운드를 닫으면서 적힌 이벤트. 시작할 때까지의 다섯은 건너뛴다."""
    response = await client.get(table_url(table, '/events'), params={'after': 5}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


def types(events: list[dict]) -> list[str]:
    return [event['type'] for event in events]


async def knock_me_down(client: AsyncClient, app: FastAPI, me: dict, friend: dict, table: dict, narrated) -> None:
    """한 라운드를 써서 나(엘프)를 쓰러뜨린다. 심한 대가가 붙은 행동에 실패해 16 의 피해를 입는다."""
    load_dice(app, [FAIL, 8, 8])
    await declare(client, me, table, JUMP, jump('heavy'))
    await declare(client, friend, table, LAUGH)
    await narrated()
    assert await hp_of(client, me, table) == {'엘프': 0, '영애': 10}


# --- 실패의 대가 ---


async def test_failing_a_risky_action_hurts_the_one_who_tried(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 3])

    await declare(client, me, table, JUMP, jump('light'))
    closing = await declare(client, friend, table, LAUGH)

    assert effects(closing) == {
        '엘프': {
            'kind': 'damage',
            'magnitude': 'light',
            'user_id': str(ME),
            'character_name': '엘프',
            'rolls': [3],
            'amount': 3,
            'before': 10,
            'after': 7,
            'max_hp': 10,
            'downed': False,
        }
    }
    assert await hp_of(client, friend, table) == {'엘프': 7, '영애': 10}
    # 응답이 아니라 저장된 것을 본다
    stored = await session.scalars(text('SELECT hp FROM table_sheets ORDER BY hp'))
    assert list(stored) == [7, 10]


async def test_succeeding_at_a_risky_action_costs_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [PASS, 4])

    await declare(client, me, table, JUMP, jump('heavy'))
    closing = await declare(client, friend, table, LAUGH)

    assert effects(closing) == {'엘프': None}
    assert await hp_of(client, me, table) == {'엘프': 10, '영애': 10}
    # 양을 정하는 주사위는 굴리지 않았다
    assert dice.remaining == 1


async def test_failing_without_a_risk_costs_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [FAIL, 4])

    await declare(client, me, table, JUMP, {'kind': 'check', 'ability': 'dex'})
    closing = await declare(client, friend, table, LAUGH)

    assert effects(closing) == {'엘프': None}
    assert await hp_of(client, me, table) == {'엘프': 10, '영애': 10}
    assert dice.remaining == 1


async def test_a_heavy_risk_rolls_two_dice(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 2, 5])

    await declare(client, me, table, JUMP, jump('heavy'))
    closing = await declare(client, friend, table, LAUGH)

    effect = effects(closing)['엘프']
    assert (effect['rolls'], effect['amount'], effect['after']) == ([2, 5], 7, 3)


async def test_damage_stops_at_zero_and_downs_the_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 8, 8])

    await declare(client, me, table, JUMP, jump('heavy'))
    closing = await declare(client, friend, table, LAUGH)

    effect = effects(closing)['엘프']
    # 주사위가 정한 양은 16 이지만 HP 는 0 에서 멈춘다. DB 의 조건(0 이상)에 부딪히지 않는다
    assert (effect['amount'], effect['before'], effect['after'], effect['downed']) == (16, 10, 0, True)
    assert await hp_of(client, me, table) == {'엘프': 0, '영애': 10}


# --- 성공의 보상 ---


async def test_succeeding_heals_the_target(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    # 1 라운드: 내가 다친다(10 → 3)
    load_dice(app, [FAIL, 3, 4])
    await declare(client, me, table, JUMP, jump('heavy'))
    await declare(client, friend, table, LAUGH)
    await narrated()

    # 2 라운드: 친구가 나를 돌본다
    load_dice(app, [PASS, 4])
    await declare(client, me, table, GROAN)
    closing = await declare(client, friend, table, TEND, tend(ME))

    assert effects(closing) == {
        '영애': {
            'kind': 'recovery',
            'magnitude': 'light',
            # HP 가 바뀐 것은 행동한 사람이 아니라 대상이다
            'user_id': str(ME),
            'character_name': '엘프',
            'rolls': [4],
            'amount': 4,
            'before': 3,
            'after': 7,
            'max_hp': 10,
            'downed': False,
        }
    }
    assert await hp_of(client, me, table) == {'엘프': 7, '영애': 10}


async def test_recovery_without_a_target_is_for_oneself(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 3, 4])
    await declare(client, me, table, JUMP, jump('heavy'))
    await declare(client, friend, table, LAUGH)
    await narrated()

    load_dice(app, [PASS, 2])
    opened = await declare(client, me, table, TEND, tend())
    closing = await declare(client, friend, table, LAUGH)

    # 비워 둔 대상은 자기 자신으로 채워 저장한다
    assert opened['declarations'][0]['action']['target'] == str(ME)
    effect = effects(closing)['엘프']
    assert (effect['user_id'], effect['before'], effect['after']) == (str(ME), 3, 5)


async def test_failing_to_heal_heals_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 3, 4])
    await declare(client, me, table, JUMP, jump('heavy'))
    await declare(client, friend, table, LAUGH)
    await narrated()

    dice = load_dice(app, [FAIL, 4])
    await declare(client, me, table, GROAN)
    closing = await declare(client, friend, table, TEND, tend(ME))

    assert effects(closing) == {'영애': None}
    assert await hp_of(client, me, table) == {'엘프': 3, '영애': 10}
    assert dice.remaining == 1


async def test_recovery_stops_at_the_maximum(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [PASS, 4])

    await declare(client, me, table, LAUGH)
    closing = await declare(client, friend, table, TEND, tend(ME))

    effect = effects(closing)['영애']
    # 다치지 않은 사람을 돌봤다. 주사위는 굴렸지만 HP 는 최대에서 멈춘다. DB 의 조건(최대 이하)에 부딪히지 않는다
    assert (effect['amount'], effect['before'], effect['after']) == (4, 10, 10)
    assert await hp_of(client, me, table) == {'엘프': 10, '영애': 10}


async def test_one_action_can_carry_both_a_risk_and_a_reward(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 2])

    await declare(client, me, table, LAUGH)
    closing = await declare(client, friend, table, TEND, {**tend(ME), 'risk': 'light'})

    # 실패했으므로 대가만 치른다. 다치는 것은 대상이 아니라 행동한 사람이다
    effect = effects(closing)['영애']
    assert (effect['kind'], effect['user_id'], effect['after']) == ('damage', str(FRIEND), 8)
    assert await hp_of(client, me, table) == {'엘프': 10, '영애': 8}


async def test_what_the_one_before_broke_the_next_one_can_mend(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    # 앉은 순서로 한 사람씩 끝낸다. 나: 판정 1, 피해 8 + 8. 친구: 판정 20, 회복 2
    load_dice(app, [FAIL, 8, 8, PASS, 2])

    # 나중에 앉은 친구가 먼저 선언한다. 그래도 내 것이 먼저 처리된다
    await declare(client, friend, table, TEND, tend(ME))
    closing = await declare(client, me, table, JUMP, jump('heavy'))

    changes = effects(closing)
    assert (changes['엘프']['before'], changes['엘프']['after'], changes['엘프']['downed']) == (10, 0, True)
    # 같은 라운드 안에서 쓰러졌다가 일어났다
    assert (changes['영애']['before'], changes['영애']['after'], changes['영애']['downed']) == (0, 2, False)
    assert await hp_of(client, me, table) == {'엘프': 2, '영애': 10}


# --- 받을 때 검사한다 ---


@pytest.mark.parametrize(
    ('changes', 'field'),
    [({'risk': 'deadly'}, 'risk'), ({'recover': 'miracle'}, 'recover')],
    ids=['risk', 'recover'],
)
async def test_a_magnitude_must_be_one_the_rules_of_the_table_have(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], changes: dict, field: str
):
    table = await start_duo(client, me, friend)

    response = await send(client, me, table, JUMP, {'kind': 'check', 'ability': 'dex', **changes})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': f'action.{field} 가 이 테이블의 규칙에 없습니다.'}
    assert (await current(client, me, table))['declarations'] == []


async def test_the_target_must_be_seated_at_the_table(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_duo(client, me, friend)

    response = await send(client, me, table, TEND, tend(STRANGER))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'action.target 이 이 테이블에 앉은 사람이 아닙니다.'}
    assert (await current(client, me, table))['declarations'] == []


@pytest.mark.parametrize(
    'action',
    [
        # 대상은 회복에만 쓴다. 남에게 피해를 주는 행동은 없다
        {'kind': 'check', 'ability': 'dex', 'target': str(FRIEND)},
        {'kind': 'check', 'ability': 'dex', 'risk': 'light', 'target': str(FRIEND)},
        # 양을 숫자로 적지 못한다
        {'kind': 'check', 'ability': 'dex', 'risk': 9},
        {'kind': 'check', 'ability': 'dex', 'recover': 'light', 'amount': 9},
    ],
    ids=['target alone', 'target with risk', 'number', 'amount'],
)
async def test_rejects_a_consequence_with_a_bad_shape(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], action: dict
):
    table = await start_duo(client, me, friend)

    response = await send(client, me, table, JUMP, action)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_a_target_who_left_recovers_nothing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    dice = load_dice(app, [PASS, 4])
    # 낼 때는 친구가 앉아 있었다
    await declare(client, me, table, TEND, tend(FRIEND))

    # 친구가 떠난다. 남은 사람이 모두 냈으므로 방장이 닫는다
    left = await client.delete(table_url(table, '/members/me'), headers=friend)
    closing = (await client.post(table_url(table, '/rounds/current/close'), headers=me)).json()

    assert left.status_code == status.HTTP_204_NO_CONTENT
    # 판정은 했지만 회복할 사람이 없다. 양을 정하는 주사위는 굴리지 않는다
    assert closing['declarations'][0]['outcome']['success'] is True
    assert effects(closing) == {'엘프': None}
    assert dice.remaining == 1


# --- 쓰러진 사람 ---


async def test_a_downed_character_cannot_attach_an_action(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    response = await send(client, me, table, TEND, tend())

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_downed'
    assert (await current(client, me, table))['declarations'] == []


async def test_a_downed_character_can_still_declare_in_words(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    await declare(client, me, table, GROAN)
    await declare(client, friend, table, LAUGH)
    await narrated()

    # 쓰러진 사람의 글도 서술자에게 간다
    assert (await read_round(client, me, table, 3))['scene'] == '[2 라운드의 결과]\n엘프: 신음한다.\n영애: 크게 웃는다.'


async def test_the_round_does_not_wait_for_a_downed_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    opened = await current(client, me, table)
    closing = await declare(client, friend, table, LAUGH)
    await narrated()

    # 기다리는 사람에 쓰러진 사람이 없다. 서 있는 사람이 모두 내면 닫기 시작한다
    assert (opened['number'], opened['waiting_for']) == (2, [str(FRIEND)])
    assert closing['status'] == 'closing'
    # 쓰러진 사람은 "아무것도 하지 않았다"가 아니다
    assert (await read_round(client, me, table, 3))[
        'scene'
    ] == '[2 라운드의 결과]\n엘프: 쓰러져 있다.\n영애: 크게 웃는다.'
    # 선언을 내지 않은 사람(idle)에도 들어가지 않는다
    closed = [event for event in await read_events(client, me, table) if event['type'] == 'round_closed']
    assert closed[-1]['payload'] == {'number': 2, 'idle': []}


async def test_a_character_helped_up_acts_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    # 2 라운드: 친구가 나를 일으킨다
    load_dice(app, [PASS, 3])
    await declare(client, friend, table, TEND, tend(ME))
    await narrated()

    opened = await current(client, me, table)
    load_dice(app, [PASS])
    response = await send(client, me, table, JUMP, jump())

    assert await hp_of(client, me, table) == {'엘프': 3, '영애': 10}
    # 일어난 사람은 다시 기다려 주고, 다시 행동을 붙일 수 있다
    assert (opened['number'], opened['waiting_for']) == (3, [str(ME), str(FRIEND)])
    assert response.status_code == status.HTTP_200_OK


async def test_when_everyone_is_down_the_host_moves_the_table_on(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    # 한 라운드에 둘 다 쓰러진다
    load_dice(app, [FAIL, 8, 8, FAIL, 8, 8])
    await declare(client, me, table, JUMP, jump('heavy'))
    await declare(client, friend, table, JUMP, jump('heavy'))
    await narrated()

    opened = await current(client, me, table)
    closing = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    # 기다릴 사람이 없다. 저절로 닫히지는 않는다. 닫는 것은 선언이 들어올 때다
    assert (opened['number'], opened['status'], opened['waiting_for']) == (2, 'open', [])
    # 방장이 닫아 넘긴다
    assert closing.status_code == status.HTTP_202_ACCEPTED
    assert (await current(client, me, table))['number'] == 3


# --- 이벤트와 서술 ---


async def test_a_change_of_hp_is_recorded_after_the_check_that_caused_it(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 3])
    await declare(client, me, table, JUMP, jump('light'))
    await declare(client, friend, table, LAUGH)

    events = await read_events(client, friend, table)

    assert types(events)[:5] == ['player_action', 'check_rolled', 'hp_changed', 'player_action', 'round_closed']
    acted, rolled, changed = events[0], events[1], events[2]
    assert changed['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '엘프',
        'kind': 'damage',
        'magnitude': 'light',
        'rolls': [3],
        'amount': 3,
        'before': 10,
        'after': 7,
        'max_hp': 10,
        'downed': False,
    }
    # 행동 → 판정 → HP 의 변화로 이어지고, 같은 묶음이다
    assert rolled['caused_by_sequence'] == acted['sequence']
    assert changed['caused_by_sequence'] == rolled['sequence']
    assert changed['action_group_id'] == acted['action_group_id']
    # HP 를 바꾼 것은 엔진이다
    assert changed['actor_id'] is None
    # 판정의 이벤트에는 HP 의 변화가 섞여 들어가지 않는다
    assert 'effect' not in rolled['payload']


async def test_a_check_that_changes_nothing_records_no_change(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)
    load_dice(app, [PASS])
    await declare(client, me, table, JUMP, jump('heavy'))
    await declare(client, friend, table, LAUGH)

    events = await read_events(client, me, table)

    assert types(events)[:4] == ['player_action', 'check_rolled', 'player_action', 'round_closed']


async def test_the_narrator_is_told_what_changed(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    load_dice(app, [FAIL, 8, 8, PASS, 2])
    await declare(client, me, table, JUMP, jump('heavy'))
    await declare(client, friend, table, TEND, tend(ME))
    await narrated()

    scene = (await read_round(client, me, table, 2))['scene']

    assert scene == (
        '[1 라운드의 결과]\n'
        '엘프: 달리는 바이크에서 뛰어내린다. (민첩 판정 실패: 1 + 0 = 1, 목표 15) → 엘프 피해 16 (HP 0/10, 쓰러짐)\n'
        '영애: 상처를 싸맨다. (지혜 판정 성공: 20 + 0 = 20, 목표 15) → 엘프 회복 2 (HP 2/10)'
    )


# --- 다시 맡겨도 다시 바뀌지 않는다 ---


async def test_narrating_again_does_not_hurt_again(
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
    load_dice(app, [FAIL, 3])
    await declare(client, me, table, JUMP, jump('light'))
    await declare(client, friend, table, LAUGH)
    # 첫 서술이 실패했다. 라운드는 닫는 중에 머문다. HP 는 이미 바뀌어 있다
    await narrated()
    assert (await read_round(client, me, table, 1))['status'] == 'closing'
    assert await hp_of(client, me, table) == {'엘프': 7, '영애': 10}

    # 이번에 굴리면 또 다친다. 굴리지 않아야 한다
    dice = load_dice(app, [FAIL, 4])
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    assert again.status_code == status.HTTP_202_ACCEPTED
    assert dice.remaining == 2
    assert await hp_of(client, me, table) == {'엘프': 7, '영애': 10}
    # 서술자는 두 번 다 같은 것을 받았다
    assert narrator.requests[0] == narrator.requests[1]
    assert narrator.requests[0].moves[0].verdict.impact.hp == 7
    # HP 의 이벤트는 하나뿐이다
    assert types(await read_events(client, me, table)).count('hp_changed') == 1
