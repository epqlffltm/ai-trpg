# game-server/tests/test_persona_saving.py

"""
테이블의 내 캐릭터를 보관함에 저장하는 것과, 보관함의 캐릭터를 테이블로 가져가는 것을 검증한다.

보는 것은 넷이다.
  - 저장하는 것은 처음 모습이다. 이름, 설명, 시작할 때의 능력치. HP 는 저장하지 않는다.
  - 저장한 것은 사본이다. 저장한 뒤에 테이블에서 바뀐 것은 보관함으로 오지 않는다.
  - 프리젠과, 아직 정하지 않은 캐릭터는 저장하지 못한다.
  - 가져가는 주소는 따로 없다. 화면이 보관함의 캐릭터로 캐릭터를 정하는 요청을 채운다.
    그 요청은 늘 하던 대로 그 테이블의 규칙과 방식으로 검사받는다. 보관함이 그 검사를 우회하지 못한다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.dice import ScriptedDice
from app.main import API_PREFIX
from app.personas.models import PERSONA_MAX_PER_OWNER, Persona
from tests.sheets import make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
TABLES_URL = f'{API_PREFIX}/tables'
PERSONAS_URL = f'{API_PREFIX}/personas'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
STRANGER = uuid.UUID('99999999-2222-4333-8444-555555555555')

RULEBOOK_TITLE = '추격전 규칙'

# 기본 시트. 직접 만든 캐릭터(custom)가 받는다
PLAIN = make_sheet(con=14, max_hp=12)
PREGENS = [{'name': '폭주족 엘프', 'description': '귀가 길어서 헬멧을 못 쓴다.', 'sheet': make_sheet(dex=16, max_hp=8)}]
PLAYER_MADE_HP = {'base': 10, 'cap': 12}
EVERY_MODE = ['pregen', 'custom', 'manual', 'point_buy', 'rolled']

ABILITY_KEYS = ['str', 'dex', 'con', 'int', 'wis', 'cha']
# 직접 적은 능력치. 점수제로는 살 수 없다(15 여섯은 54 점이고 총점은 27 점이다)
STRONG = dict.fromkeys(ABILITY_KEYS, 15)
# 점수제로 살 수 있는 능력치(12 여섯은 24 점)
MODEST = dict.fromkeys(ABILITY_KEYS, 12)

JUMP = '달리는 바이크에서 뛰어내린다.'
LAUGH = '크게 웃는다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 테이블의 방장이다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """같은 테이블에 앉는 사람의 머리말."""
    return bearer(signing_key, FRIEND)


@pytest.fixture
def stranger(signing_key: SigningKey) -> dict[str, str]:
    """테이블에 앉지 않은 사람의 머리말."""
    return bearer(signing_key, STRANGER)


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    """앱의 주사위를 정해진 눈을 내는 것으로 바꿔 꽂는다."""
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def open_table(
    client: AsyncClient, me: dict[str, str], capacity: int = 1, modes: list[str] | None = None
) -> dict:
    """내가 방장인 테이블을 연다. 시나리오는 모든 캐릭터 방식을 허용한다. modes 로 테이블에서 좁힌다."""
    rulebook = await client.post(RULEBOOKS_URL, json={'title': RULEBOOK_TITLE}, headers=me)
    body = {
        'title': '추격전',
        'rulebook_id': rulebook.json()['id'],
        'openings': ['사이렌이 울린다.'],
        'default_sheet': PLAIN,
        'pregens': PREGENS,
        'character_modes': EVERY_MODE,
        'player_made_hp': PLAYER_MADE_HP,
    }
    scenario = (await client.post(SCENARIOS_URL, json=body, headers=me)).json()
    published = await client.post(f'{SCENARIOS_URL}/{scenario["id"]}/versions', json={}, headers=me)
    assert published.status_code == status.HTTP_201_CREATED, published.text
    body = {'scenario_id': scenario['id'], 'version': 1, 'capacity': capacity}
    if modes is not None:
        body['character_modes'] = modes
    created = await client.post(TABLES_URL, json=body, headers=me)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    return created.json()


async def set_character(client: AsyncClient, headers: dict[str, str], table: dict, **body):
    """캐릭터를 정하는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.put(table_url(table, '/character'), json=body, headers=headers)


async def keep(client: AsyncClient, headers: dict[str, str], table: dict):
    """테이블의 내 캐릭터를 보관함에 저장하는 요청을 보낸다. 응답을 그대로 돌려준다."""
    return await client.post(table_url(table, '/character/persona'), headers=headers)


async def kept(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    """테이블의 내 캐릭터를 보관함에 저장하고, 저장한 것을 돌려준다."""
    response = await keep(client, headers, table)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def my_vault(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    return (await client.get(PERSONAS_URL, headers=headers)).json()['items']


# --- 저장하는 것은 처음 모습이다 ---


async def test_keeps_a_character_made_at_the_table(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, mode='manual', name='드워프', description='수염이 길다.', abilities=STRONG)

    response = await keep(client, me, table)

    assert response.status_code == status.HTTP_201_CREATED
    persona = response.json()
    assert (persona['name'], persona['description'], persona['abilities']) == ('드워프', '수염이 길다.', STRONG)
    # 어느 룰북의 규칙으로 만든 숫자인지 적힌다
    assert persona['rulebook_title'] == RULEBOOK_TITLE
    assert await my_vault(client, me) == [persona]


async def test_a_character_with_the_default_sheet_keeps_its_numbers(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, name='드워프')

    persona = await kept(client, me, table)

    # 아직 시작하지 않았다. 시작할 때 받을 시트의 능력치를 저장한다
    assert persona['abilities'] == PLAIN['abilities']


async def test_rolled_numbers_are_kept_too(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await open_table(client, me)
    load_dice(app, [5, 5, 5, 1] * 6)
    await client.post(table_url(table, '/character/roll'), headers=me)
    await set_character(client, me, table, mode='rolled', name='드워프', abilities=STRONG)

    persona = await kept(client, me, table)

    assert persona['abilities'] == STRONG


async def test_keeps_the_starting_numbers_and_not_the_wounds(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, mode='manual', name='드워프', abilities=STRONG)
    await client.post(table_url(table, '/start'), headers=me)
    # 심하게 다친다(2d8 = 6). 큰 타격이라 부상 표(d20)도 굴린다. 1 은 부상이 없다
    load_dice(app, [1, 3, 3, 1])
    action = {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium', 'risk': 'heavy'}
    await client.put(
        table_url(table, '/rounds/current/declaration'), json={'content': JUMP, 'action': action}, headers=me
    )
    seat = (await client.get(table_url(table), headers=me)).json()['members'][0]
    assert seat['sheet']['hp'] < seat['sheet']['max_hp']

    persona = await kept(client, me, table)

    # HP 는 그 이야기 안의 상태다. 보관함에는 HP 를 담는 칸이 없다
    assert persona['abilities'] == STRONG
    assert 'hp' not in persona
    assert 'max_hp' not in persona


async def test_a_dead_character_can_be_kept(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, name='드워프')
    await client.post(table_url(table, '/start'), headers=me)
    # 16 의 피해로 쓰러지고, 부상 표(d20)를 굴린다. 1 은 부상이 없다
    load_dice(app, [1, 8, 8, 1])
    action = {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium', 'risk': 'heavy'}
    await client.put(
        table_url(table, '/rounds/current/declaration'), json={'content': JUMP, 'action': action}, headers=me
    )
    # 혼자 앉은 테이블이라 선언 하나로 라운드가 닫히고, 그때 16 의 피해로 쓰러진다
    gone = await client.delete(table_url(table, '/character'), headers=me)
    assert gone.status_code == status.HTTP_200_OK, gone.text

    response = await keep(client, me, table)

    # 이 이야기에서는 죽었지만, 다른 이야기에서는 살아 있는 인물이다
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()['name'] == '드워프'


async def test_keeping_twice_makes_two_copies(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, name='드워프')

    first = await kept(client, me, table)
    second = await kept(client, me, table)

    assert first['id'] != second['id']
    assert len(await my_vault(client, me)) == 2


# --- 저장한 것은 사본이다 ---


async def test_changes_at_the_table_do_not_reach_the_vault(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, mode='manual', name='드워프', abilities=STRONG)
    persona = await kept(client, me, table)

    await set_character(client, me, table, name='오크')

    assert (await client.get(f'{PERSONAS_URL}/{persona["id"]}', headers=me)).json() == persona


async def test_changes_in_the_vault_do_not_reach_the_table(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, name='드워프', description='수염이 길다.')
    persona = await kept(client, me, table)

    changed = await client.put(f'{PERSONAS_URL}/{persona["id"]}', json={'name': '오크'}, headers=me)
    await client.delete(f'{PERSONAS_URL}/{persona["id"]}', headers=me)

    seat = (await client.get(table_url(table), headers=me)).json()['members'][0]
    assert seat['character'] == {'name': '드워프', 'description': '수염이 길다.'}
    # 손으로 고친 숫자는 더는 그 룰북에서 만든 숫자가 아니다. 룰북의 제목이 지워진다
    assert changed.json()['rulebook_title'] is None


# --- 저장하지 못하는 것 ---


async def test_a_pregen_is_not_kept(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)
    await set_character(client, me, table, pregen_index=0)

    response = await keep(client, me, table)

    # 시나리오의 제작자가 쓴 인물이다. 보관함은 등급이 없어서, 저장하면 다른 등급의 테이블로 걸어 들어갈 길이 생긴다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'pregen_not_kept'
    assert await my_vault(client, me) == []


async def test_there_is_nothing_to_keep_before_a_character_is_set(client: AsyncClient, me: dict[str, str]):
    table = await open_table(client, me)

    response = await keep(client, me, table)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'no_character'


async def test_someone_who_is_not_seated_keeps_nothing(
    client: AsyncClient, me: dict[str, str], stranger: dict[str, str]
):
    table = await open_table(client, me)
    await set_character(client, me, table, name='드워프')

    response = await keep(client, stranger, table)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await my_vault(client, stranger) == []


async def test_only_my_own_character_is_kept(client: AsyncClient, me: dict[str, str], friend: dict[str, str]):
    table = await open_table(client, me, capacity=2)
    await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    await set_character(client, me, table, name='드워프')
    await set_character(client, friend, table, name='악역영애')

    persona = await kept(client, friend, table)

    # 주소에 누구의 캐릭터인지 적는 칸이 없다. 남의 캐릭터를 내 보관함에 넣는 길이 없다
    assert persona['name'] == '악역영애'
    assert await my_vault(client, me) == []


async def test_a_full_vault_keeps_nothing_more(client: AsyncClient, me: dict[str, str], session: AsyncSession):
    table = await open_table(client, me)
    await set_character(client, me, table, name='드워프')
    session.add_all(Persona(owner_id=ME, name=f'엑스트라 {number}') for number in range(PERSONA_MAX_PER_OWNER))
    await session.commit()

    response = await keep(client, me, table)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'vault_full'


# --- 가져간다. 그 테이블의 규칙과 방식으로 다시 검사받는다 ---


def from_vault(persona: dict, mode: str) -> dict:
    """화면이 하는 일. 보관함의 캐릭터로 캐릭터를 정하는 요청을 채운다."""
    body = {'mode': mode, 'name': persona['name'], 'description': persona['description']}
    if mode != 'custom':
        body['abilities'] = persona['abilities']
    return body


async def strong_dwarf(client: AsyncClient, me: dict[str, str]) -> dict:
    """보관함에 넣어 둔 드워프. 직접 적은 능력치가 점수제로는 살 수 없을 만큼 높다."""
    response = await client.post(PERSONAS_URL, json={'name': '드워프', 'abilities': STRONG}, headers=me)
    return response.json()


async def test_a_kept_character_walks_into_a_table_that_takes_written_numbers(client: AsyncClient, me: dict[str, str]):
    persona = await strong_dwarf(client, me)
    table = await open_table(client, me, modes=['manual'])

    response = await set_character(client, me, table, **from_vault(persona, 'manual'))

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['members'][0]['abilities'] == STRONG


async def test_kept_numbers_still_have_to_fit_the_budget(client: AsyncClient, me: dict[str, str]):
    persona = await strong_dwarf(client, me)
    table = await open_table(client, me, modes=['point_buy'])

    too_strong = await set_character(client, me, table, **from_vault(persona, 'point_buy'))
    modest = await set_character(client, me, table, **{**from_vault(persona, 'point_buy'), 'abilities': MODEST})

    # 보관함이 점수제를 우회하는 길이 되면 안 된다. 제작자의 재량이 무너진다
    assert too_strong.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert modest.status_code == status.HTTP_200_OK


async def test_kept_numbers_cannot_stand_in_for_dice(client: AsyncClient, me: dict[str, str]):
    persona = await strong_dwarf(client, me)
    table = await open_table(client, me, modes=['rolled'])

    response = await set_character(client, me, table, **from_vault(persona, 'rolled'))

    # 주사위는 그 테이블에서 서버가 굴린다. 굴리지 않았으니 놓을 점수가 없다
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'not_rolled'


async def test_words_alone_walk_into_any_table_that_takes_its_own_sheet(client: AsyncClient, me: dict[str, str]):
    persona = await strong_dwarf(client, me)
    table = await open_table(client, me, modes=['custom'])

    response = await set_character(client, me, table, **from_vault(persona, 'custom'))

    # 숫자는 그 판의 기본 시트에서 온다. 보관함의 숫자는 쓰지 않는다
    assert response.status_code == status.HTTP_200_OK
    seat = response.json()['members'][0]
    assert (seat['character']['name'], seat['abilities']) == ('드워프', None)
