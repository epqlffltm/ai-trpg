# game-server/tests/test_character_death.py

"""
쓰러진 캐릭터의 죽음을 검증한다. 죽음의 굴림과, 플레이어가 캐릭터를 스스로 보내는 것.

캐릭터가 죽는 길은 둘이다.
  - 규칙이 정한다. 쓰러진 채로 라운드가 닫힐 때마다 죽음의 굴림을 굴린다. 실패가 다 모이면 죽는다.
  - 플레이어가 정한다. 쓰러진 캐릭터를 그 전에 스스로 보낼 수 있다.
굴림의 계산 자체는 tests/test_death.py 가 본다. 여기는 그것이 라운드와 테이블에 어떻게 이어지는지를 본다.

보는 것은 다섯이다.
  - 언제 굴리나. 쓰러진 라운드에는 굴리지 않고, 그 뒤로 쓰러진 채 닫히는 라운드마다 한 번 굴린다.
    그 라운드에 회복을 받아 일어났으면 굴리지 않는다.
  - 센 것은 시트에 쌓인다. 일어나면 처음으로 돌아간다. 고비를 넘기면 더 굴리지 않는다.
  - 죽은 캐릭터는 되살아나지 않는다. 그 플레이어는 선언을 낼 수 없다.
  - 굴림과 죽음은 라운드와 이벤트에 남고 모두에게 보인다. 서술을 다시 맡겨도 다시 굴리지 않는다.
  - 쓰러진 캐릭터만 스스로 보낼 수 있다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import ScriptedDice
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.rounds import service
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
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

# 모두가 받는 시트. 모든 능력치가 10(보정 0)이고 최대 HP 가 10 이다
PLAIN = make_sheet()

# 판정의 눈. 보통(목표 15)에 도전한다
FAIL = 1
PASS = 20
# 부상 표(d20)의 눈. 1~10 은 부상이 없다. 큰 타격이나 쓰러짐에 표를 굴린다(#114). 부상은 tests/test_injuries.py 가 본다
NO_INJURY = 1

# 죽음의 굴림의 눈. 목표는 10 이다. 능력치의 보정은 없다
LIVE = 15
DIE = 5

# 죽음의 굴림이 없는 규칙
NO_DEATH_SAVE = Ruleset.model_validate({**SRD5.model_dump(mode='json'), 'death_save': None})


def jump(risk: str = 'heavy') -> dict:
    """민첩으로 보통에 도전한다. 실패하면 심하게 다친다(2d8)."""
    return {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium', 'risk': risk}


def tend(target: uuid.UUID) -> dict:
    """지혜로 보통에 도전한다. 성공하면 대상이 가볍게 회복한다(1d4)."""
    return {'kind': 'check', 'ability': 'wis', 'difficulty': 'medium', 'recover': 'light', 'target': str(target)}


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


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않은 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    """앱의 주사위를 정해진 눈을 내는 것으로 바꿔 꽂는다. 꽂은 주사위를 돌려준다."""
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


class FlakyNarrator:
    """처음 한 번은 실패하고 그 뒤로는 답하는 서술자. 받은 것을 적어 둔다."""

    def __init__(self) -> None:
        self.requests: list[NarrationRequest] = []

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise RuntimeError('서술자가 답하지 못했다')
        return '먼지가 가라앉는다.'


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def seat_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉아 캐릭터를 정한 테이블. 아직 시작하지 않았다."""
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
    return table


async def start_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str]) -> dict:
    """나와 친구가 앉은 테이블을 시작한다. 규칙은 SRD5 템플릿이고, 둘 다 PLAIN 시트를 받는다. HP 는 10 이다."""
    table = await seat_duo(client, me, friend)
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


async def sheets_of(client: AsyncClient, headers: dict[str, str], table: dict) -> dict[str, dict]:
    """테이블에 앉은 사람들의 시트를 {캐릭터 이름: 시트} 로 읽는다."""
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return {member['character']['name']: member['sheet'] for member in response.json()['members']}


async def saves_of(client: AsyncClient, headers: dict[str, str], table: dict, name: str) -> tuple[int, int, int, bool]:
    """그 캐릭터의 (HP, 죽음의 굴림의 성공, 실패, 죽었는가)."""
    sheet = (await sheets_of(client, headers, table))[name]
    return sheet['hp'], sheet['death_successes'], sheet['death_failures'], sheet['dead']


async def read_events(
    client: AsyncClient, headers: dict[str, str], table: dict, type_: str | None = None
) -> list[dict]:
    """이 테이블의 이벤트. 종류를 주면 그 종류만 꺼낸다."""
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    events = response.json()['items']
    return events if type_ is None else [event for event in events if event['type'] == type_]


async def knock_me_down(client: AsyncClient, app: FastAPI, me: dict, friend: dict, table: dict, narrated) -> None:
    """한 라운드를 써서 나(엘프)를 쓰러뜨린다. 심한 대가가 붙은 행동에 실패해 16 의 피해를 입는다."""
    load_dice(app, [FAIL, 8, 8, NO_INJURY])
    await declare(client, me, table, JUMP, jump())
    await declare(client, friend, table, LAUGH)
    await narrated()


async def pass_round(client: AsyncClient, app: FastAPI, friend: dict, table: dict, narrated, rolls: list[int]) -> dict:
    """
    내가 쓰러져 있는 채로 한 라운드를 넘긴다. 서 있는 친구만 선언을 내면 닫힌다.

    rolls 는 이 라운드가 닫힐 때 굴릴 눈이다. 닫기 시작한 라운드를 돌려준다. 남은 눈이 없는지도 본다.
    """
    dice = load_dice(app, rolls)
    closing = await declare(client, friend, table, LAUGH)
    await narrated()
    assert dice.remaining == 0
    return closing


# --- 언제 굴리나 ---


async def test_a_character_does_not_roll_in_the_round_it_went_down(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)

    # 판정의 눈 하나와 피해의 눈 둘뿐이다. 죽음의 굴림을 굴리려 하면 눈이 모자라 오류가 난다
    await knock_me_down(client, app, me, friend, table, narrated)

    # 방금 쓰러졌다. 동료가 일으킬 틈이 한 라운드는 있다
    assert (await read_round(client, me, table, 1))['death_saves'] == []
    assert await saves_of(client, me, table, '엘프') == (0, 0, 0, False)


async def test_a_downed_character_rolls_when_the_next_round_closes(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    opened = await current(client, me, table)
    closing = await pass_round(client, app, friend, table, narrated, [DIE])

    # 선언을 받는 동안에는 굴린 것이 없다. 닫기 시작할 때 굴린다
    assert opened['death_saves'] == []
    assert closing['death_saves'] == [
        {
            'user_id': str(ME),
            'character_name': '엘프',
            'roll': DIE,
            'target': 10,
            'success': False,
            'successes': 0,
            'failures': 1,
            'fate': 'dying',
        }
    ]
    assert await saves_of(client, me, table, '엘프') == (0, 0, 1, False)
    # 서 있는 사람은 굴리지 않는다
    assert await saves_of(client, me, table, '영애') == (10, 0, 0, False)


async def test_the_roll_is_made_whether_or_not_the_downed_player_wrote_something(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    load_dice(app, [LIVE])

    await declare(client, me, table, GROAN)
    await declare(client, friend, table, LAUGH)
    await narrated()

    # 쓰러진 사람도 글은 낼 수 있다. 글을 냈다고 굴림을 건너뛰지 않는다
    assert await saves_of(client, me, table, '엘프') == (0, 1, 0, False)
    scene = (await read_round(client, me, table, 3))['scene']
    assert scene == (
        '[2 라운드의 결과]\n'
        '엘프: 신음한다. (죽음의 굴림 성공: 15, 목표 10. 성공 1, 실패 0, 죽어 가는 중)\n'
        '영애: 크게 웃는다.'
    )


async def test_a_character_helped_up_in_the_round_does_not_roll(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    # 판정의 눈과 회복의 눈뿐이다. 죽음의 굴림의 눈은 없다
    dice = load_dice(app, [PASS, 3])

    closing = await declare(client, friend, table, TEND, tend(ME))
    await narrated()

    # 행동의 결과를 먼저 끝내고 나서 굴린다. 이번 라운드에 일어난 캐릭터는 굴리지 않는다
    assert closing['death_saves'] == []
    assert dice.remaining == 0
    assert await saves_of(client, me, table, '엘프') == (3, 0, 0, False)


async def test_the_dying_roll_in_the_order_they_sat_down(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    # 한 라운드에 둘 다 쓰러진다
    load_dice(app, [FAIL, 8, 8, NO_INJURY, FAIL, 8, 8, NO_INJURY])
    await declare(client, me, table, JUMP, jump())
    await declare(client, friend, table, JUMP, jump())
    await narrated()
    load_dice(app, [LIVE, DIE])

    # 기다릴 사람이 없어서 방장이 닫는다
    await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    saves = (await read_round(client, me, table, 2))['death_saves']
    assert [(save['character_name'], save['roll']) for save in saves] == [('엘프', LIVE), ('영애', DIE)]


# --- 센 것이 쌓인다 ---


async def test_successes_and_failures_pile_up_over_the_rounds(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    await pass_round(client, app, friend, table, narrated, [DIE])
    await pass_round(client, app, friend, table, narrated, [LIVE])
    await pass_round(client, app, friend, table, narrated, [DIE])

    assert await saves_of(client, me, table, '엘프') == (0, 1, 2, False)


async def test_the_third_failure_kills_the_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await pass_round(client, app, friend, table, narrated, [DIE])
    await pass_round(client, app, friend, table, narrated, [DIE])

    closing = await pass_round(client, app, friend, table, narrated, [DIE])

    assert closing['death_saves'][0]['fate'] == 'dead'
    assert await saves_of(client, me, table, '엘프') == (0, 0, 3, True)
    scene = (await read_round(client, me, table, 5))['scene']
    assert scene == (
        '[4 라운드의 결과]\n엘프: 죽었다. (죽음의 굴림 실패: 5, 목표 10. 성공 0, 실패 3, 죽음)\n영애: 크게 웃는다.'
    )


async def test_the_third_success_stops_the_rolls(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await pass_round(client, app, friend, table, narrated, [LIVE])
    await pass_round(client, app, friend, table, narrated, [LIVE])
    stable = await pass_round(client, app, friend, table, narrated, [LIVE])

    # 고비를 넘겼다. 이제 주사위를 건드리지 않는다. 눈을 꽂지 않고 라운드를 넘겨도 된다
    later = await pass_round(client, app, friend, table, narrated, [])

    assert stable['death_saves'][0]['fate'] == 'stable'
    assert later['death_saves'] == []
    # 쓰러진 채로 있다. 죽지는 않는다
    assert await saves_of(client, me, table, '엘프') == (0, 3, 0, False)


async def test_being_helped_up_starts_the_count_over(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await pass_round(client, app, friend, table, narrated, [DIE])
    await pass_round(client, app, friend, table, narrated, [DIE])
    # 실패 둘인 채로 친구가 일으킨다
    load_dice(app, [PASS, 3])
    await declare(client, friend, table, TEND, tend(ME))
    await narrated()
    risen = await saves_of(client, me, table, '엘프')

    # 다시 쓰러진다
    load_dice(app, [FAIL, 8, 8, NO_INJURY])
    await declare(client, me, table, JUMP, jump())
    await declare(client, friend, table, LAUGH)
    await narrated()
    await pass_round(client, app, friend, table, narrated, [DIE])

    assert risen == (3, 0, 0, False)
    # 처음부터 센다. 앞의 실패 둘에 이어서 죽지 않는다
    assert await saves_of(client, me, table, '엘프') == (0, 0, 1, False)


async def test_a_stable_character_can_still_be_helped_up(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    for _ in range(3):
        await pass_round(client, app, friend, table, narrated, [LIVE])

    load_dice(app, [PASS, 4])
    await declare(client, friend, table, TEND, tend(ME))
    await narrated()

    assert await saves_of(client, me, table, '엘프') == (4, 0, 0, False)


async def test_a_table_whose_rules_have_no_death_save_never_rolls(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    friend: dict[str, str],
    narrated,
    monkeypatch: pytest.MonkeyPatch,
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    # 지금의 템플릿(srd5)에는 죽음의 굴림이 있다. 없는 규칙의 테이블을 만들 길이 없어서 읽는 곳을 바꿔 끼운다
    monkeypatch.setattr(service, 'rules_of', lambda table: NO_DEATH_SAVE)

    closing = await pass_round(client, app, friend, table, narrated, [])

    # 주사위가 캐릭터를 죽이지 않는 규칙이다. 쓰러진 채로 있다
    assert closing['death_saves'] == []
    assert await saves_of(client, me, table, '엘프') == (0, 0, 0, False)


# --- 죽은 캐릭터 ---


async def kill_me(client: AsyncClient, app: FastAPI, me: dict, friend: dict, table: dict, narrated) -> None:
    """나(엘프)를 쓰러뜨리고, 죽음의 굴림에 세 번 실패하게 한다. 네 라운드를 쓴다."""
    await knock_me_down(client, app, me, friend, table, narrated)
    for _ in range(3):
        await pass_round(client, app, friend, table, narrated, [DIE])


async def test_the_dead_do_not_roll_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    # 눈을 꽂지 않는다. 굴리려 하면 오류가 난다
    closing = await pass_round(client, app, friend, table, narrated, [])

    assert closing['death_saves'] == []
    assert await saves_of(client, me, table, '엘프') == (0, 0, 3, True)


async def test_the_dead_cannot_be_healed_back(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    # 판정의 눈뿐이다. 회복의 양을 정하는 눈은 없다
    dice = load_dice(app, [PASS])

    closing = await declare(client, friend, table, TEND, tend(ME))
    await narrated()

    # 판정은 성공했지만 회복은 없다. 죽음은 되돌릴 수 없다
    outcome = closing['declarations'][0]['outcome']
    assert (outcome['success'], outcome['effect']) == (True, None)
    assert dice.remaining == 0
    assert await saves_of(client, me, table, '엘프') == (0, 0, 3, True)


async def test_the_player_of_a_dead_character_cannot_declare(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    opened = await current(client, me, table)
    words = await send(client, me, table, GROAN)

    # 쓰러진 캐릭터와 다르다. 죽은 캐릭터는 글도 내지 못한다. 새 캐릭터가 있어야 한다
    assert words.status_code == status.HTTP_409_CONFLICT
    assert words.json()['reason'] == 'character_dead'
    # 라운드는 그 사람을 기다리지 않는다
    assert opened['waiting_for'] == [str(FRIEND)]
    assert opened['declarations'] == []


# --- 기록 ---


async def test_the_roll_and_the_death_are_recorded_in_order(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    events = await read_events(client, me, table)

    # 마지막 라운드가 닫히면서 적힌 것. 행동 → 죽음의 굴림 → 죽음 → 닫힘 → 서술 → 열림 순서다
    last = events[-6:]
    assert [event['type'] for event in last] == [
        'player_action',
        'death_save_rolled',
        'character_died',
        'round_closed',
        'gm_narration',
        'round_opened',
    ]
    action, rolled, died, closed = last[:4]
    # 굴린 것도 죽인 것도 엔진이다. 사람이 한 일이 아니다
    assert (rolled['actor_id'], died['actor_id']) == (None, None)
    assert rolled['payload'] == {
        'round': 4,
        'user_id': str(ME),
        'character_name': '엘프',
        'roll': DIE,
        'target': 10,
        'success': False,
        'successes': 0,
        'failures': 3,
        'fate': 'dead',
    }
    assert died['payload'] == {'round': 4, 'user_id': str(ME), 'character_name': '엘프', 'cause': 'death_save'}
    # 죽음은 그 굴림에 이어진다. 한 라운드가 닫히면서 생긴 것은 한 묶음이다
    assert died['caused_by_sequence'] == rolled['sequence']
    assert len({event['action_group_id'] for event in (action, rolled, died, closed)}) == 1


async def test_a_roll_that_does_not_kill_records_no_death(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    await pass_round(client, app, friend, table, narrated, [DIE])

    assert len(await read_events(client, me, table, 'death_save_rolled')) == 1
    assert await read_events(client, me, table, 'character_died') == []


async def test_retrying_the_narration_does_not_roll_again(
    client: AsyncClient,
    app: FastAPI,
    me: dict[str, str],
    friend: dict[str, str],
    narrated,
    monkeypatch: pytest.MonkeyPatch,
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    narrator = FlakyNarrator()
    app.state.narrator = narrator
    load_dice(app, [DIE])
    await declare(client, friend, table, LAUGH)
    # 첫 서술이 실패했다. 라운드는 닫는 중에 머문다. 죽음의 굴림은 이미 굴렸다
    await narrated()
    assert (await read_round(client, me, table, 2))['status'] == 'closing'

    # 이번에 굴리면 실패가 하나 더 쌓인다. 굴리지 않아야 한다
    dice = load_dice(app, [DIE])
    monkeypatch.setattr(service, 'CLOSING_RETRY_SECONDS', 0)
    again = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()

    assert again.status_code == status.HTTP_202_ACCEPTED
    assert dice.remaining == 1
    assert await saves_of(client, me, table, '엘프') == (0, 0, 1, False)
    # 서술자는 두 번 다 같은 것을 받았다. 라운드에 적어 둔 굴림을 읽는다
    assert narrator.requests[0] == narrator.requests[1]
    assert narrator.requests[0].moves[0].death_save.failures == 1
    assert len(await read_events(client, me, table, 'death_save_rolled')) == 1


# --- 스스로 보낸다 ---


async def give_up(client: AsyncClient, headers: dict[str, str], table: dict):
    """자기 캐릭터를 보내는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.delete(table_url(table, '/character'), headers=headers)


async def test_a_downed_character_can_be_given_up(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    response = await give_up(client, me, table)

    assert response.status_code == status.HTTP_200_OK
    sheet = response.json()['members'][0]['sheet']
    # 죽음의 굴림을 기다리지 않았다. 센 것 없이 죽었다
    assert (sheet['hp'], sheet['death_successes'], sheet['death_failures'], sheet['dead']) == (0, 0, 0, True)
    (died,) = await read_events(client, friend, table, 'character_died')
    # 스스로 보낸 것은 그 사람이 한 일이다. 라운드가 닫히면서 생긴 일이 아니라서 라운드의 번호가 없다
    assert died['actor_id'] == str(ME)
    assert died['payload'] == {'user_id': str(ME), 'character_name': '엘프', 'cause': 'gave_up'}


async def test_a_character_given_up_is_dead_like_any_other(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await give_up(client, me, table)

    words = await send(client, me, table, GROAN)
    # 눈을 꽂지 않는다. 죽은 캐릭터는 굴리지 않는다
    closing = await pass_round(client, app, friend, table, narrated, [])

    assert words.json()['reason'] == 'character_dead'
    assert closing['death_saves'] == []
    assert (await read_round(client, me, table, 3))['scene'] == '[2 라운드의 결과]\n엘프: 죽었다.\n영애: 크게 웃는다.'


async def test_a_character_can_be_given_up_in_the_middle_of_the_rolls(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await pass_round(client, app, friend, table, narrated, [LIVE])

    response = await give_up(client, me, table)

    # 성공을 하나 모았어도 보낼 수 있다. 센 것은 기록으로 남는다
    assert response.status_code == status.HTTP_200_OK
    assert await saves_of(client, me, table, '엘프') == (0, 1, 0, True)


async def test_a_character_on_its_feet_cannot_be_given_up(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await start_duo(client, me, friend)

    response = await give_up(client, me, table)

    # 마음에 안 드는 캐릭터를 버리고 새로 만드는 길이 되면 안 된다. 쓰러진 캐릭터만 보낸다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_not_downed'
    assert (await sheets_of(client, me, table))['엘프']['dead'] is False


async def test_a_dead_character_cannot_be_given_up_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await give_up(client, me, table)

    again = await give_up(client, me, table)

    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'character_dead'
    assert len(await read_events(client, me, table, 'character_died')) == 1


async def test_only_ones_own_character_is_given_up(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    # 친구가 보낸다. 친구의 캐릭터는 서 있다. 쓰러진 내 캐릭터가 대신 죽지 않는다
    response = await give_up(client, friend, table)

    assert response.json()['reason'] == 'character_not_downed'
    assert (await sheets_of(client, me, table))['엘프']['dead'] is False


async def test_a_character_cannot_be_given_up_before_the_game_starts(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await seat_duo(client, me, friend)

    response = await give_up(client, me, table)

    # 모집 중에는 캐릭터를 다시 정하면 된다. 보낼 것이 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_playing'


async def test_a_character_cannot_be_given_up_after_the_table_ends(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    await client.post(table_url(table, '/end'), headers=me)

    response = await give_up(client, me, table)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_playing'


async def test_someone_who_is_not_seated_cannot_give_up(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], stranger: dict[str, str]
):
    table = await start_duo(client, me, friend)

    response = await give_up(client, stranger, table)

    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- DB 의 마지막 방어선 ---


@pytest.mark.parametrize(
    ('change', 'constraint'),
    [
        # 서 있는 캐릭터가 죽어 있다
        ('died_at = now()', 'death_only_when_downed'),
        # 서 있는 캐릭터에 죽음의 굴림이 세어져 있다
        ('death_failures = 1', 'death_only_when_downed'),
        ('death_successes = 1', 'death_only_when_downed'),
        ('hp = 0, death_failures = -1', 'death_saves_not_negative'),
    ],
    ids=['dead on its feet', 'failures on its feet', 'successes on its feet', 'negative'],
)
async def test_the_database_rejects_death_on_a_character_that_is_up(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession, change: str, constraint: str
):
    await start_duo(client, me, friend)

    with pytest.raises(IntegrityError, match=constraint):
        await session.execute(text(f'UPDATE table_sheets SET {change}'))


async def test_the_database_takes_death_on_a_downed_character(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    await start_duo(client, me, friend)

    await session.execute(text('UPDATE table_sheets SET hp = 0, death_failures = 3, died_at = now()'))
    await session.commit()

    assert await session.scalar(text('SELECT count(*) FROM table_sheets WHERE died_at IS NOT NULL')) == 2
