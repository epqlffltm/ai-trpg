# game-server/tests/test_replacement.py

"""
캐릭터가 죽은 플레이어가 새 캐릭터를 들이는 것을 검증한다.

진행 중인 테이블에서는 캐릭터를 바꾸지 못한다. 자기 캐릭터가 죽었을 때 새 캐릭터를 들이는 길만 있다.
캐릭터가 어떻게 죽는지는 tests/test_character_death.py 가 본다. 여기는 그 뒤를 본다.

보는 것은 여섯이다.
  - 언제 되나. 진행 중이고, 자기 캐릭터가 죽었고, 라운드가 열려 있을 때만.
  - 새 캐릭터는 새 시트를 바로 받는다. 죽은 캐릭터의 시트는 남는다. 물려받는 것은 없다.
  - 정하는 조건은 모집 중과 같다. 이 테이블이 허용한 방식이어야 하고, 방식의 제한을 지켜야 한다.
  - 이 테이블에서 시트를 받은 적이 있는 프리젠은 다시 고르지 못한다.
  - 주사위로 정하는 방식이면 새로 굴린다. 지난 캐릭터의 점수를 쓰지 못한다.
  - 새 캐릭터는 들어온 라운드에 선언을 내지 않는다. 서술자가 이야기에 들이고, 다음 라운드부터 행동한다.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import ScriptedDice
from app.engine.sheet import Sheet
from app.main import API_PREFIX
from app.rounds.narrator import NO_PREVIEW, NarrationRequest, Preview
from app.tables import service, sheets
from app.tables.models import GameTable, TableMember, TableRoll, TableStatus
from app.tables.router import find_pregen_holders
from app.tables.service import Conflict, TableConflictError
from tests.sheets import make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'
MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations' / 'versions'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

JUMP = '달리는 바이크에서 뛰어내린다.'
LAUGH = '크게 웃는다.'
GROAN = '신음한다.'
REV = '시동을 건다.'

# 기본 시트. 모든 능력치가 10(보정 0)이고 최대 HP 가 10 이다. 직접 만든 캐릭터(custom)가 받는다
PLAIN = make_sheet()
# 프리젠의 시트. 누구의 것인지 알아볼 수 있게 서로 다르게 둔다
BIKER_SHEET = make_sheet(dex=16, max_hp=8)
LADY_SHEET = make_sheet(cha=18, max_hp=6)
PREGENS = [
    {'name': '폭주족 엘프', 'description': '귀가 길어서 헬멧을 못 쓴다.', 'sheet': BIKER_SHEET},
    {'name': '악역영애', 'description': '바이크는 처음이지만 웃음소리는 크다.', 'sheet': LADY_SHEET},
]
# 플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 건강 보정을 더하고 12 를 넘지 않는다
PLAYER_MADE_HP = {'base': 10, 'cap': 12}
EVERY_MODE = ['pregen', 'custom', 'manual', 'point_buy', 'rolled']

ABILITY_KEYS = ['str', 'dex', 'con', 'int', 'wis', 'cha']
# 직접 적은 능력치. 건강이 14(보정 +2)라 최대 HP 는 12 다
STURDY = {'str': 12, 'dex': 12, 'con': 14, 'int': 12, 'wis': 12, 'cha': 12}

# 판정의 눈. 보통(목표 15)에 도전한다
FAIL = 1
# 죽음의 굴림의 눈. 목표는 10 이다
DIE = 5

# 능력치를 굴리는 눈. 4d6 에서 높은 셋을 더한다. 점수 여섯을 굴리는 데 눈이 스물넷 든다
ONE_ROLL = 24


def all_scores(score: int) -> dict[str, int]:
    """모든 능력치가 같은 점수인 능력치."""
    return dict.fromkeys(ABILITY_KEYS, score)


def dice_for_all(top: int) -> list[int]:
    """점수 여섯이 모두 top * 3 이 나오게 하는 눈. 넷 중 하나는 1 이라 버려진다."""
    return [top, top, top, 1] * 6


def jump() -> dict:
    """민첩으로 보통에 도전한다. 실패하면 심하게 다친다(2d8)."""
    return {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium', 'risk': 'heavy'}


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 먼저 앉았다. 캐릭터는 '엘프'다. 이 파일에서 죽는 것은 늘 나다."""
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


def load_migration(name: str):
    """마이그레이션 파일 하나를 모듈로 읽는다. 파일 이름 앞의 번호는 만들 때마다 달라서 뒤의 이름으로 찾는다."""
    (path,) = MIGRATIONS.glob(f'*_{name}.py')
    spec = importlib.util.spec_from_file_location(f'{name}_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StuckNarrator:
    """답하지 못하는 서술자. 라운드를 닫는 중에 머물게 한다."""

    async def narrate(self, request: NarrationRequest, preview: Preview = NO_PREVIEW) -> str:
        raise RuntimeError('서술자가 답하지 못했다')


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def seat_duo(client: AsyncClient, me: dict[str, str], friend: dict[str, str], **scenario) -> dict:
    """
    나와 친구가 앉은 테이블. 캐릭터는 아직 정하지 않았다.

    시나리오는 모든 캐릭터 방식을 허용하고 프리젠이 둘 있다. 제작자가 다시 굴리기를 허락했다.
    scenario 로 시나리오의 칸을 바꾼다. 예: character_modes=['custom'].
    """
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {
        'title': '추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': PLAIN,
        'pregens': PREGENS,
        'character_modes': EVERY_MODE,
        'player_made_hp': PLAYER_MADE_HP,
        'reroll_allowed': True,
        **scenario,
    }
    created = await client.post(SCENARIOS_URL, json=body, headers=me)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    published = await client.post(f'{SCENARIOS_URL}/{created.json()["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    body = {'scenario_id': created.json()['id'], 'version': 1, 'capacity': 2}
    table = (await client.post(TABLES_URL, json=body, headers=me)).json()
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    return table


async def start_duo(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str], mine: dict | None = None, **scenario
) -> dict:
    """
    나와 친구가 앉은 테이블을 시작한다. 나는 '엘프', 친구는 '영애'다. 둘 다 기본 시트를 받는다. HP 는 10 이다.

    mine 을 주면 내 캐릭터를 그것으로 정한다. 예: {'pregen_index': 0}.
    """
    table = await seat_duo(client, me, friend, **scenario)
    chosen = await client.put(table_url(table, '/character'), json=mine or {'name': '엘프'}, headers=me)
    assert chosen.status_code == status.HTTP_200_OK, chosen.text
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


async def read(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def seat_of(table: dict, user_id: uuid.UUID) -> dict:
    """테이블의 응답에서 그 사람의 자리를 꺼낸다."""
    return next(member for member in table['members'] if member['user_id'] == str(user_id))


async def my_seat(client: AsyncClient, me: dict[str, str], table: dict) -> dict:
    return seat_of(await read(client, me, table), ME)


async def read_events(
    client: AsyncClient, headers: dict[str, str], table: dict, type_: str | None = None
) -> list[dict]:
    """이 테이블의 이벤트. 종류를 주면 그 종류만 꺼낸다."""
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    events = response.json()['items']
    return events if type_ is None else [event for event in events if event['type'] == type_]


async def knock_me_down(client: AsyncClient, app: FastAPI, me: dict, friend: dict, table: dict, narrated) -> None:
    """한 라운드를 써서 내 캐릭터를 쓰러뜨린다. 심한 대가가 붙은 행동에 실패해 16 의 피해를 입는다."""
    load_dice(app, [FAIL, 8, 8])
    await declare(client, me, table, JUMP, jump())
    await declare(client, friend, table, LAUGH)
    await narrated()


async def give_up(client: AsyncClient, headers: dict[str, str], table: dict):
    """쓰러진 자기 캐릭터를 보내는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.delete(table_url(table, '/character'), headers=headers)


async def kill_me(client: AsyncClient, app: FastAPI, me: dict, friend: dict, table: dict, narrated) -> None:
    """
    한 라운드를 써서 내 캐릭터를 죽인다. 쓰러진 다음 라운드에 스스로 보낸다.

    끝나면 내 캐릭터는 죽어 있고, 그다음 라운드가 열려 있다. 아무도 선언을 내지 않았다.
    """
    await knock_me_down(client, app, me, friend, table, narrated)
    gone = await give_up(client, me, table)
    assert gone.status_code == status.HTTP_200_OK, gone.text


async def bring_in(client: AsyncClient, headers: dict[str, str], table: dict, **body):
    """새 캐릭터를 들이는 요청을 보낸다. 응답을 그대로 돌려준다. 예: bring_in(..., name='드워프')."""
    return await client.post(table_url(table, '/character'), json=body, headers=headers)


async def arrive(client: AsyncClient, headers: dict[str, str], table: dict, **body) -> dict:
    """새 캐릭터를 들이고, 돌아온 테이블을 돌려준다."""
    response = await bring_in(client, headers, table, **body)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def roll(client: AsyncClient, headers: dict[str, str], table: dict):
    """능력치의 점수를 굴리는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.post(table_url(table, '/character/roll'), headers=headers)


async def grant(client: AsyncClient, headers: dict[str, str], table: dict, user_id: uuid.UUID):
    """방장이 "한 번 더 굴리기"를 주는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.post(table_url(table, f'/members/{user_id}/reroll'), headers=headers)


# --- 언제 되나 ---


async def test_a_player_whose_character_died_brings_in_a_new_one(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, name='드워프', description='수염에 기름때가 묻었다.')

    assert response.status_code == status.HTTP_201_CREATED
    seat = seat_of(response.json(), ME)
    # 자리의 캐릭터가 새 캐릭터로 바뀌었다. 시트를 바로 받았다. HP 는 가득 차 있고 죽음의 굴림은 센 것이 없다
    assert seat['character'] == {'name': '드워프', 'description': '수염에 기름때가 묻었다.'}
    assert seat['character_mode'] == 'custom'
    assert seat['sheet'] == {**PLAIN, 'number': 2, 'hp': 10, 'death_successes': 0, 'death_failures': 0, 'dead': False}
    # 죽은 캐릭터는 지워지지 않고 떠난 캐릭터로 남는다
    assert seat['fallen'] == [{'number': 1, 'character_name': '엘프', 'pregen_index': None, **PLAIN}]


async def test_the_host_is_not_asked(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    # 죽는 것이 방장이 아닌 사람이어도 된다. 방장의 승인은 받지 않는다
    load_dice(app, [FAIL, 8, 8])
    await declare(client, friend, table, JUMP, jump())
    await declare(client, me, table, LAUGH)
    await narrated()
    await give_up(client, friend, table)

    response = await bring_in(client, friend, table, name='드워프')

    assert response.status_code == status.HTTP_201_CREATED
    assert seat_of(response.json(), FRIEND)['character']['name'] == '드워프'


async def test_a_living_character_cannot_be_replaced(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await start_duo(client, me, friend)

    response = await bring_in(client, me, table, name='드워프')

    # 마음에 안 드는 캐릭터를 버리고 새로 만드는 길이 되면 안 된다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_alive'
    assert (await my_seat(client, me, table))['character']['name'] == '엘프'


async def test_a_downed_character_is_still_alive(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, name='드워프')

    # 쓰러진 캐릭터는 동료가 일으킬 수 있다. 죽기 전에는 새 캐릭터를 들이지 못한다. 먼저 보내야 한다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_alive'


async def test_a_character_killed_by_the_rules_is_replaced_the_same_way(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    # 죽음의 굴림에 세 번 실패한다
    for _ in range(3):
        load_dice(app, [DIE])
        await declare(client, friend, table, LAUGH)
        await narrated()
    assert (await my_seat(client, me, table))['sheet']['dead'] is True

    response = await bring_in(client, me, table, name='드워프')

    assert response.status_code == status.HTTP_201_CREATED


async def test_nobody_is_replaced_before_the_game_starts(
    client: AsyncClient, me: dict[str, str], friend: dict[str, str]
):
    table = await seat_duo(client, me, friend)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)

    response = await bring_in(client, me, table, name='드워프')

    # 모집 중에는 캐릭터를 정하는 길(PUT)로 마음대로 바꾼다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_started'


async def test_nobody_is_replaced_after_the_table_ended(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    await client.post(table_url(table, '/end'), headers=me)

    response = await bring_in(client, me, table, name='드워프')

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_playing'


async def test_nobody_is_replaced_while_the_round_is_closing(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    app.state.narrator = StuckNarrator()
    await declare(client, friend, table, LAUGH)
    await narrated()
    assert (await current(client, me, table))['status'] == 'closing'

    response = await bring_in(client, me, table, name='드워프')

    # 닫는 중인 라운드는 서술자가 읽고 있다. 그사이에 자리의 캐릭터가 바뀌면 서술이 어긋난다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'round_closing'
    assert (await my_seat(client, me, table))['character']['name'] == '엘프'


async def test_someone_who_is_not_seated_cannot_bring_in_a_character(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, stranger: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, stranger, table, name='드워프')

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_the_new_character_cannot_be_replaced_while_it_lives(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    await arrive(client, me, table, name='드워프')

    again = await bring_in(client, me, table, name='오크')

    # 한 번만 된다. 새 캐릭터가 들어오면 그 캐릭터는 살아 있다
    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'character_alive'
    assert (await my_seat(client, me, table))['character']['name'] == '드워프'


async def test_the_way_to_set_a_character_stays_closed_during_play(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    response = await client.put(table_url(table, '/character'), json={'name': '드워프'}, headers=me)

    # 모집 중에 캐릭터를 정하는 길로는 진행 중에 아무것도 바꾸지 못한다. 캐릭터가 죽었어도 그렇다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_recruiting'
    assert (await my_seat(client, me, table))['sheet']['number'] == 1


# --- 새 시트를 받는다. 물려받는 것은 없다 ---


async def test_the_dead_characters_sheet_is_kept(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    await arrive(client, me, table, name='드워프')

    query = text('SELECT number, character_name, hp, died_at IS NOT NULL FROM table_sheets WHERE user_id = :me')
    rows = (await session.execute(query.bindparams(me=ME))).all()
    # 죽은 캐릭터의 시트는 죽을 때의 모습 그대로 남는다. 새 캐릭터의 시트가 그 뒤에 놓인다
    assert sorted(rows) == [(1, '엘프', 0, True), (2, '드워프', 10, False)]


async def test_a_player_goes_through_as_many_characters_as_die(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    await arrive(client, me, table, name='드워프')
    # 새 캐릭터가 들어온 라운드를 넘긴다. 다음 라운드부터 행동한다
    await declare(client, friend, table, LAUGH)
    await narrated()
    # 새 캐릭터도 같은 길로 죽는다
    await kill_me(client, app, me, friend, table, narrated)

    seat = seat_of(await arrive(client, me, table, name='오크'), ME)

    assert seat['character']['name'] == '오크'
    assert seat['sheet']['number'] == 3
    assert [(fallen['number'], fallen['character_name']) for fallen in seat['fallen']] == [(1, '엘프'), (2, '드워프')]


async def test_everyone_at_the_table_sees_who_fell(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    await arrive(client, me, table, name='드워프')

    seen = await read(client, friend, table)

    assert [fallen['character_name'] for fallen in seat_of(seen, ME)['fallen']] == ['엘프']
    assert seat_of(seen, FRIEND)['fallen'] == []


async def test_leaving_takes_every_sheet_along(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    await arrive(client, me, table, name='드워프')

    await client.delete(table_url(table, '/members/me'), headers=me)

    # 사람이 떠나면 그 사람의 시트는 죽은 캐릭터의 것까지 모두 지워진다
    remaining = await session.scalars(text('SELECT character_name FROM table_sheets'))
    assert remaining.all() == ['영애']


# --- 정하는 조건은 모집 중과 같다 ---


async def test_the_new_character_follows_the_modes_of_the_table(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend, character_modes=['custom'], pregens=[])
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, mode='manual', name='드워프', abilities=STURDY)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_mode_not_allowed'
    assert (await my_seat(client, me, table))['character']['name'] == '엘프'


async def test_a_new_character_with_written_abilities_gets_a_sheet_made_from_them(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    seat = seat_of(await arrive(client, me, table, mode='manual', name='드워프', abilities=STURDY), ME)

    # 최대 HP 는 규칙으로 구한다. 기준값 10 에 건강 보정 2 를 더한다
    assert seat['character_mode'] == 'manual'
    assert (seat['sheet']['abilities'], seat['sheet']['max_hp'], seat['sheet']['hp']) == (STURDY, 12, 12)


async def test_abilities_outside_the_rules_are_refused(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, mode='manual', name='드워프', abilities={**STURDY, 'str': 99})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (await my_seat(client, me, table))['sheet']['number'] == 1


async def test_point_buy_still_has_a_budget(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    # 총점은 27 점이다. 15 는 9 점이라 여섯이면 54 점이고, 12 는 4 점이라 여섯이면 24 점이다
    over = await bring_in(client, me, table, mode='point_buy', name='드워프', abilities=all_scores(15))
    within = await bring_in(client, me, table, mode='point_buy', name='드워프', abilities=all_scores(12))

    assert over.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert within.status_code == status.HTTP_201_CREATED
    assert seat_of(within.json(), ME)['character_mode'] == 'point_buy'


async def test_the_body_has_the_same_shape_as_setting_a_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    nameless = await bring_in(client, me, table)
    stray = await bring_in(client, me, table, name='드워프', sheet=PLAIN)

    # 이름이 없거나, 모르는 칸이 있으면 받지 않는다. 숫자를 보내는 칸은 없다
    assert nameless.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert stray.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 프리젠 ---


async def test_a_free_pregen_can_be_brought_in(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    seat = seat_of(await arrive(client, me, table, pregen_index=1), ME)

    assert seat['character']['name'] == '악역영애'
    assert (seat['character_mode'], seat['pregen_index']) == ('pregen', 1)
    assert (seat['sheet']['abilities'], seat['sheet']['max_hp']) == (LADY_SHEET['abilities'], LADY_SHEET['max_hp'])


async def test_a_dead_pregen_does_not_walk_back_in(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend, mine={'pregen_index': 0})
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, pregen_index=0)

    # 방금 죽은 인물이 같은 사람의 새 캐릭터로 다시 들어오지 못한다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'pregen_taken'


async def test_a_dead_pregen_stays_taken_after_its_player_moved_on(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend, mine={'pregen_index': 0})
    await kill_me(client, app, me, friend, table, narrated)
    # 나는 다른 캐릭터로 넘어갔다. 내 자리에는 더는 0 번 프리젠이 적혀 있지 않다
    moved_on = await arrive(client, me, table, name='드워프')
    # 친구의 캐릭터도 죽는다
    await declare(client, friend, table, LAUGH)
    await narrated()
    load_dice(app, [FAIL, 8, 8])
    await declare(client, friend, table, JUMP, jump())
    await declare(client, me, table, REV)
    await narrated()
    await give_up(client, friend, table)

    response = await bring_in(client, friend, table, pregen_index=0)

    # 떠난 캐릭터의 프리젠은 누구도 다시 고르지 못한다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'pregen_taken'
    assert seat_of(moved_on, ME)['fallen'][0]['pregen_index'] == 0
    # 고를 수 있는 프리젠의 목록에서 죽었다고 보인다. 누구의 캐릭터였는지도 남아 있다
    assert [(pregen['taken_by'], pregen['dead']) for pregen in moved_on['pregens']] == [(str(ME), True), (None, False)]


async def test_a_pregen_someone_is_playing_cannot_be_brought_in(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await seat_duo(client, me, friend)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'pregen_index': 1}, headers=friend)
    await client.post(table_url(table, '/start'), headers=me)
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, pregen_index=1)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'pregen_taken'


async def test_a_pregen_that_is_not_there_cannot_be_brought_in(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, pregen_index=9)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- 주사위로 정하는 방식. 새 캐릭터는 새로 굴린다 ---


async def start_with_rolled_elf(client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str]) -> dict:
    """내가 주사위로 굴려 만든 '엘프'로 시작한 테이블. 점수는 모두 15 다. 건강 보정 2 로 최대 HP 는 12 다."""
    table = await seat_duo(client, me, friend)
    load_dice(app, dice_for_all(5))
    await roll(client, me, table)
    mine = {'mode': 'rolled', 'name': '엘프', 'abilities': all_scores(15)}
    chosen = await client.put(table_url(table, '/character'), json=mine, headers=me)
    assert chosen.status_code == status.HTTP_200_OK, chosen.text
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    await client.post(table_url(table, '/start'), headers=me)
    return table


async def test_the_scores_of_the_dead_character_cannot_be_used_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with_rolled_elf(client, app, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, mode='rolled', name='드워프', abilities=all_scores(15))

    # 굴려 둔 점수가 있지만 지난 캐릭터를 위해 굴린 것이다. 새 캐릭터는 새로 굴려야 한다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_rolled'


async def test_a_new_character_is_rolled_anew(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with_rolled_elf(client, app, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    dice = load_dice(app, dice_for_all(4))

    rolled = await roll(client, me, table)
    stale = await bring_in(client, me, table, mode='rolled', name='드워프', abilities=all_scores(15))
    fresh = await bring_in(client, me, table, mode='rolled', name='드워프', abilities=all_scores(12))

    assert rolled.status_code == status.HTTP_200_OK
    assert dice.remaining == 0
    # 두 번째 캐릭터를 위해 굴린 것으로 적힌다. 굴린 횟수는 테이블에서 이어서 센다
    kept = seat_of(rolled.json(), ME)['roll']
    assert (kept['scores'], kept['times_rolled'], kept['character_number']) == ([12] * 6, 2, 2)
    # 새로 굴린 점수만 쓸 수 있다
    assert stale.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert fresh.status_code == status.HTTP_201_CREATED
    sheet = seat_of(fresh.json(), ME)['sheet']
    assert (sheet['abilities'], sheet['max_hp']) == (all_scores(12), 11)


async def test_rolling_for_the_next_character_leaves_the_dead_one_in_the_seat(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with_rolled_elf(client, app, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    load_dice(app, dice_for_all(4))

    seat = seat_of((await roll(client, me, table)).json(), ME)

    # 모집 중에 다시 굴리면 옛 점수로 만든 캐릭터가 지워진다. 죽은 캐릭터는 지워지지 않는다. 이미 시트를 받은 캐릭터다
    assert seat['character']['name'] == '엘프'
    assert (seat['character_mode'], seat['abilities']) == ('rolled', all_scores(15))
    assert seat['sheet']['dead'] is True


async def test_a_new_character_is_rolled_only_once(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with_rolled_elf(client, app, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    dice = load_dice(app, dice_for_all(4) + dice_for_all(6))
    await roll(client, me, table)

    again = await roll(client, me, table)

    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'already_rolled'
    assert dice.remaining == ONE_ROLL


async def test_a_roll_left_unused_before_the_death_does_not_count(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await seat_duo(client, me, friend)
    # 굴리기만 하고, 캐릭터는 다른 방식으로 만들었다
    load_dice(app, dice_for_all(5))
    await roll(client, me, table)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.put(table_url(table, '/character'), json={'name': '영애'}, headers=friend)
    await client.post(table_url(table, '/start'), headers=me)
    await kill_me(client, app, me, friend, table, narrated)

    response = await bring_in(client, me, table, mode='rolled', name='드워프', abilities=all_scores(15))

    # 쓰지 않은 점수여도 첫 캐릭터 때 굴린 것이다. 아껴 뒀다가 다음 캐릭터에 쓰지 못한다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_rolled'


async def test_the_host_grants_one_more_roll_for_the_new_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    # 죽는 것은 친구다. 방장인 내가 준다
    load_dice(app, [FAIL, 8, 8])
    await declare(client, friend, table, JUMP, jump())
    await declare(client, me, table, LAUGH)
    await narrated()
    await give_up(client, friend, table)
    dice = load_dice(app, dice_for_all(1) + dice_for_all(6))

    too_early = await grant(client, me, table, FRIEND)
    await roll(client, friend, table)
    granted = await grant(client, me, table, FRIEND)
    rerolled = await roll(client, friend, table)

    # 새 캐릭터를 위해 굴린 뒤에야 줄 수 있다
    assert too_early.status_code == status.HTTP_409_CONFLICT
    assert too_early.json()['reason'] == 'not_rolled'
    assert granted.status_code == status.HTTP_200_OK
    assert rerolled.status_code == status.HTTP_200_OK
    kept = seat_of(rerolled.json(), FRIEND)['roll']
    assert (kept['scores'], kept['character_number'], kept['reroll_granted']) == ([18] * 6, 2, False)
    assert dice.remaining == 0


async def test_one_more_roll_is_not_granted_to_a_living_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with_rolled_elf(client, app, me, friend)

    response = await grant(client, me, table, ME)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_alive'


# --- 들어온 라운드와 그다음 라운드 ---


async def test_the_arrival_is_written_on_the_round(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    before = await current(client, friend, table)

    await arrive(client, me, table, name='드워프')

    after = await current(client, friend, table)
    assert before['arrivals'] == []
    # 누가 들어왔는지는 가리지 않는다. 선언과 다르다
    assert after['arrivals'] == [{'user_id': str(ME), 'character_name': '드워프', 'replaces': '엘프'}]
    # 라운드는 새 캐릭터를 기다리지 않는다
    assert after['waiting_for'] == [str(FRIEND)]


async def test_the_new_character_does_not_act_in_the_round_it_arrived(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    await arrive(client, me, table, name='드워프')

    response = await send(client, me, table, REV)

    # 이 라운드의 장면에 아직 없는 인물이다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'character_arriving'
    assert (await current(client, me, table))['declarations'] == []


async def test_the_round_closes_without_the_new_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    await arrive(client, me, table, name='드워프')
    # 굴릴 것이 없다. 새 캐릭터는 쓰러져 있지 않다
    dice = load_dice(app, [])

    closing = await declare(client, friend, table, LAUGH)
    await narrated()

    assert closing['status'] == 'closing'
    assert closing['death_saves'] == []
    assert dice.remaining == 0
    # 서술자가 새 캐릭터를 이야기에 들인다. 누구의 뒤를 잇는지를 안다
    scene = (await read_round(client, me, table, 3))['scene']
    assert scene == '[2 라운드의 결과]\n드워프: 죽은 엘프의 뒤를 이어 새로 이야기에 들어온다.\n영애: 크게 웃는다.'
    # 닫힌 라운드에서 "선언을 내지 않은 사람"으로 적히지 않는다
    closed = (await read_events(client, me, table, 'round_closed'))[-1]
    assert closed['payload'] == {'number': 2, 'idle': []}


async def test_the_new_character_acts_from_the_next_round(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    # 민첩이 16(보정 +3)인 프리젠을 들인다. 새 시트로 판정하는지 본다
    await arrive(client, me, table, pregen_index=0)
    await declare(client, friend, table, LAUGH)
    await narrated()
    opened = await current(client, me, table)
    load_dice(app, [12])

    await declare(client, me, table, JUMP, jump())
    closing = await declare(client, friend, table, LAUGH)
    await narrated()

    # 다음 라운드에는 들어온 캐릭터가 없고, 라운드는 새 캐릭터의 선언을 기다린다
    assert opened['arrivals'] == []
    assert opened['waiting_for'] == [str(ME), str(FRIEND)]
    mine = next(declaration for declaration in closing['declarations'] if declaration['user_id'] == str(ME))
    assert mine['character_name'] == '폭주족 엘프'
    # 12 + 3 = 15. 보통(목표 15)에 성공한다. 죽은 캐릭터의 민첩(10)으로 굴렸다면 실패다
    assert (mine['outcome']['modifier'], mine['outcome']['success']) == (3, True)


async def test_words_the_dead_character_left_in_the_round_are_dropped(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    # 쓰러진 캐릭터가 글을 내고, 같은 라운드에 그 캐릭터를 보내고, 새 캐릭터를 들인다
    await declare(client, me, table, GROAN)
    await give_up(client, me, table)

    await arrive(client, me, table, name='드워프')
    await declare(client, friend, table, LAUGH)
    await narrated()

    # 남겨 두면 그 글이 새 캐릭터가 한 일로 읽힌다
    closed = await read_round(client, me, table, 2)
    assert [declaration['character_name'] for declaration in closed['declarations']] == ['영애']
    assert GROAN not in (await read_round(client, me, table, 3))['scene']
    actions = await read_events(client, me, table, 'player_action')
    assert [action['payload']['content'] for action in actions if action['payload']['round'] == 2] == [LAUGH]


async def test_the_new_character_starts_its_own_count_when_it_goes_down(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await knock_me_down(client, app, me, friend, table, narrated)
    # 첫 캐릭터가 죽음의 굴림에 한 번 실패한 뒤에 보낸다
    load_dice(app, [DIE])
    await declare(client, friend, table, LAUGH)
    await narrated()
    await give_up(client, me, table)
    await arrive(client, me, table, name='드워프')
    await declare(client, friend, table, LAUGH)
    await narrated()

    # 새 캐릭터가 쓰러지고, 다음 라운드에 죽음의 굴림을 굴린다
    await knock_me_down(client, app, me, friend, table, narrated)
    load_dice(app, [DIE])
    await declare(client, friend, table, LAUGH)
    await narrated()

    sheet = (await my_seat(client, me, table))['sheet']
    # 첫 캐릭터가 센 실패를 물려받지 않는다
    assert (sheet['number'], sheet['hp'], sheet['death_failures'], sheet['dead']) == (2, 0, 1, False)


async def test_a_lone_player_carries_on_with_a_new_character(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    rulebook = await client.post(RULEBOOKS_URL, json={'title': '룰북'}, headers=me)
    body = {'title': '추격전', 'rulebook_id': rulebook.json()['id'], 'openings': ['사이렌.'], 'default_sheet': PLAIN}
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=me)).json()
    await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    table = (
        await client.post(TABLES_URL, json={'scenario_id': scenario['id'], 'capacity': 1, 'version': 1}, headers=me)
    ).json()
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.post(table_url(table, '/start'), headers=me)
    load_dice(app, [FAIL, 8, 8])
    await declare(client, me, table, JUMP, jump())
    await narrated()
    await give_up(client, me, table)

    await arrive(client, me, table, name='드워프')
    # 기다릴 사람이 없다. 방장이 라운드를 닫아 새 캐릭터를 이야기에 들인다
    closed = await client.post(table_url(table, '/rounds/current/close'), headers=me)
    await narrated()
    acted = await send(client, me, table, REV)

    assert closed.status_code == status.HTTP_202_ACCEPTED
    assert acted.status_code == status.HTTP_200_OK
    assert acted.json()['declarations'][0]['character_name'] == '드워프'


# --- 기록 ---


async def test_the_arrival_is_recorded_with_the_sheet_it_got(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    await arrive(client, me, table, pregen_index=1)

    (joined,) = await read_events(client, friend, table, 'character_joined')
    assert joined['actor_id'] == str(ME)
    # 받은 시트를 함께 적는다. 처음의 값이 기록에 있어야 뒤에 HP 가 바뀐 일들을 따라갈 수 있다
    assert joined['payload'] == {
        'round': 2,
        'user_id': str(ME),
        'character_name': '악역영애',
        'replaces': '엘프',
        'mode': 'pregen',
        'pregen_index': 1,
        'number': 2,
        'sheet': LADY_SHEET,
    }


async def test_a_refused_arrival_leaves_no_trace(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, narrated, session: AsyncSession
):
    table = await start_duo(client, me, friend)
    await kill_me(client, app, me, friend, table, narrated)

    await bring_in(client, me, table, mode='manual', name='드워프', abilities={**STURDY, 'str': 99})

    assert await read_events(client, me, table, 'character_joined') == []
    assert (await current(client, me, table))['arrivals'] == []
    assert await session.scalar(text('SELECT count(*) FROM table_sheets WHERE user_id = :me').bindparams(me=ME)) == 1


async def test_the_roll_for_a_new_character_says_which_character_it_is_for(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], narrated
):
    table = await start_with_rolled_elf(client, app, me, friend)
    await kill_me(client, app, me, friend, table, narrated)
    load_dice(app, dice_for_all(4))

    await roll(client, me, table)

    rolled = await read_events(client, friend, table, 'abilities_rolled')
    assert [event['payload']['character_number'] for event in rolled] == [1, 2]


# --- 이 칸들이 생기기 전에 받은 시트 ---


async def test_the_migration_writes_on_each_sheet_whose_it_is(session: AsyncSession):
    # 조건이 걸린 진짜 표에는 옛 모양의 행을 넣을 수 없다. 같은 이름의 임시 표를 만들어 채우는 문장만 돌려 본다.
    # 임시 표는 진짜 표보다 먼저 찾아지고, 트랜잭션이 끝나면 사라진다
    await session.execute(
        text(
            'CREATE TEMP TABLE table_members '
            '(table_id int, user_id int, character_name text, pregen_index int) ON COMMIT DROP'
        )
    )
    await session.execute(
        text(
            'CREATE TEMP TABLE table_sheets '
            '(table_id int, user_id int, character_name text, pregen_index int) ON COMMIT DROP'
        )
    )
    await session.execute(
        text("""
            INSERT INTO table_members (table_id, user_id, character_name, pregen_index) VALUES
                (1, 1, '폭주족 엘프', 0),
                (1, 2, '드워프', NULL),
                (2, 1, '악역영애', 1),
                (2, 2, NULL, NULL),
                (3, 1, '시트가 없는 사람', NULL)
        """)
    )
    await session.execute(text('INSERT INTO table_sheets (table_id, user_id) VALUES (1, 1), (1, 2), (2, 1), (2, 2)'))
    migration = load_migration('sheet_per_character')

    await session.execute(text(migration.COPY_CHARACTERS))

    rows = await session.execute(text('SELECT table_id, user_id, character_name, pregen_index FROM table_sheets'))
    assert sorted(rows.all()) == [
        # 같은 사람이 다른 테이블에 앉아 있어도 그 테이블의 캐릭터를 받는다
        (1, 1, '폭주족 엘프', 0),
        (1, 2, '드워프', None),
        (2, 1, '악역영애', 1),
        # 이름이 없는 자리의 시트는 빈 글을 받는다. 비워 둘 수 없는 칸이다
        (2, 2, '', None),
    ]


async def test_going_back_keeps_only_the_latest_sheet_of_each_player(session: AsyncSession):
    await session.execute(text('CREATE TEMP TABLE table_sheets (table_id int, user_id int, number int) ON COMMIT DROP'))
    await session.execute(
        text('INSERT INTO table_sheets VALUES (1, 1, 1), (1, 1, 2), (1, 1, 3), (1, 2, 1), (2, 1, 1), (2, 1, 2)')
    )
    migration = load_migration('sheet_per_character')

    await session.execute(text(migration.DROP_FALLEN))

    # 한 사람에 시트가 하나이던 때로 돌아간다. 지금 캐릭터의 것만 남는다
    rows = await session.execute(text('SELECT table_id, user_id, number FROM table_sheets'))
    assert sorted(rows.all()) == [(1, 1, 3), (1, 2, 1), (2, 1, 2)]


# --- 판단만 하는 작은 것. DB 를 쓰지 않는다 ---


# 판의 시트 하나. 숫자는 중요하지 않다
SOURCE = Sheet.model_validate(PLAIN)


def make_seat(*dead: bool) -> TableMember:
    """시트를 받은 자리를 만든다. dead 하나가 시트 하나다. True 면 그 캐릭터는 죽었다. 예: make_seat(True, False)."""
    seat = TableMember(user_id=ME, character_name='아무개')
    for is_dead in dead:
        sheet = sheets.give_sheet(seat, SOURCE)
        if is_dead:
            sheet.hp = 0
            sheets.mark_dead(sheet)
    return seat


def make_roll(character_number: int, reroll_granted: bool = False) -> TableRoll:
    return TableRoll(
        user_id=ME,
        dice=[],
        scores=[],
        times_rolled=1,
        character_number=character_number,
        reroll_granted=reroll_granted,
    )


def make_table(status_: TableStatus, seat: TableMember) -> GameTable:
    return GameTable(status=status_, members=[seat], rolls=[])


@pytest.mark.parametrize(
    ('status_', 'dead', 'reason'),
    [
        # 모집 중에는 누구나 정한다
        (TableStatus.RECRUITING, (), None),
        # 진행 중에는 캐릭터가 죽은 사람만
        (TableStatus.PLAYING, (False,), Conflict.CHARACTER_ALIVE),
        (TableStatus.PLAYING, (True,), None),
        (TableStatus.PLAYING, (True, False), Conflict.CHARACTER_ALIVE),
        (TableStatus.PLAYING, (True, True), None),
        # 끝난 테이블에서는 아무도
        (TableStatus.ENDED, (True,), Conflict.NOT_RECRUITING),
    ],
)
def test_who_may_choose_a_character(status_: TableStatus, dead: tuple[bool, ...], reason: Conflict | None):
    seat = make_seat(*dead)
    table = make_table(status_, seat)

    if reason is None:
        service.require_choosing(table, seat)
        return
    with pytest.raises(TableConflictError) as refused:
        service.require_choosing(table, seat)
    assert refused.value.reason == reason


def test_the_number_of_the_character_being_chosen():
    assert sheets.next_number(make_seat()) == 1
    assert sheets.next_number(make_seat(True)) == 2
    assert sheets.next_number(make_seat(True, True)) == 3


def test_a_roll_counts_only_for_the_character_it_was_made_for():
    choosing_second = make_seat(True)

    # 첫 캐릭터를 위해 굴린 것은 두 번째 캐릭터에게는 없는 것과 같다
    assert not sheets.is_fresh(None, choosing_second)
    assert not sheets.is_fresh(make_roll(1), choosing_second)
    assert sheets.is_fresh(make_roll(2), choosing_second)
    assert sheets.may_roll(make_roll(1), choosing_second)
    assert not sheets.may_roll(make_roll(2), choosing_second)
    assert sheets.may_roll(make_roll(2, reroll_granted=True), choosing_second)
    # 지난 캐릭터 때 받아 두고 쓰지 않은 "한 번 더"가 있어도, 새 캐릭터의 첫 굴림은 그것과 상관없이 된다
    assert sheets.may_roll(make_roll(1, reroll_granted=True), choosing_second)


def test_a_stale_roll_is_not_found_for_the_character_being_chosen():
    seat = make_seat(True)
    table = make_table(TableStatus.PLAYING, seat)
    table.rolls.append(make_roll(1))
    assert sheets.find_fresh_roll(table, seat) is None

    table.rolls[0].character_number = 2

    assert sheets.find_fresh_roll(table, seat) is table.rolls[0]


def test_pregen_holders_come_from_seats_and_from_sheets():
    recruiting = TableMember(user_id=ME, character_name='폭주족 엘프', pregen_index=0)
    assert find_pregen_holders(GameTable(members=[recruiting])) == {0: (ME, False)}

    # 시작해서 시트를 받았고, 그 캐릭터가 죽었고, 다른 프리젠으로 넘어갔다
    first = sheets.give_sheet(recruiting, SOURCE)
    first.hp = 0
    sheets.mark_dead(first)
    recruiting.character_name, recruiting.pregen_index = '악역영애', 1
    sheets.give_sheet(recruiting, SOURCE)

    assert find_pregen_holders(GameTable(members=[recruiting])) == {0: (ME, True), 1: (ME, False)}
