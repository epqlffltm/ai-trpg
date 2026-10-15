# game-server/tests/test_monster_combat.py

"""
행동이 몬스터를 겨누는 것(#231 3a)을 검증한다.

맵은 수로 입구(시작)와 깊은 수로다. 입구에 수로 쥐 둘(야수, 최대 HP 4), 깊은 수로에 해골 병사 하나(언데드, 최대 HP 6).
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 판정의 눈을 먼저, 양의 눈을 그다음에 쓴다.

보는 것은 다섯이다.
  - 이번 장면의 몬스터: 살아 있는 캐릭터가 서 있는 장소의 마리만, 번호가 붙은 이름과 몸 상태로 보인다.
  - 타격: 성공하면 그 마리의 HP 와 생사가 바뀐다. 제압은 쓰러뜨리고, 죽이려는 타격은 죽인다.
    언데드와 구조물은 HP 가 0 이면 제압이어도 부서진다(타입의 성질).
  - 받을 때와 판정할 때의 검사: 다른 장소의 마리, 죽은 마리, 같은 라운드에 앞사람이 죽인 마리(굴리지 않는다).
  - 내보내는 것: 응답과 이벤트에 HP 의 숫자가 없다.
  - 행동의 모양: 몬스터에게는 타격만 한다(회복, 노려 치기 없음).
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.bestiaries.models import MonsterKind
from app.engine.action import CheckAction
from app.engine.dice import ScriptedDice
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.tables.models import NpcStatus, TableMonster
from app.tables.monsters import TRAITS, Traits, change_monster, status_after, traits_of
from tests.sheets import SHEET, make_sheet
from tests.signing import SigningKey, make_access_claims, make_token

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

RAT_SHEET = make_sheet(max_hp=4)
SKELETON_SHEET = make_sheet(max_hp=6)

# 판정의 눈. 보통(목표 15)에 도전한다. 시트의 보정은 0 이다
FAIL = 1
PASS = 20

BITE_BACK = '쥐를 걷어찬다.'
LAUGH = '크게 웃는다.'


def bearer(signing_key: SigningKey, user_id: uuid.UUID) -> dict[str, str]:
    token = make_token(signing_key, make_access_claims(sub=str(user_id)))
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람. 캐릭터는 '드워프 기사'다."""
    return bearer(signing_key, FRIEND)


def load_dice(app: FastAPI, rolls: list[int]) -> ScriptedDice:
    """앱의 주사위를 정해진 눈을 내는 것으로 바꿔 꽂는다."""
    dice = ScriptedDice(rolls)
    app.state.dice = dice
    return dice


def strike(monster: str, harm: str = 'moderate', lethal: bool = False, **fields) -> dict:
    """근력으로 보통에 도전한다. 성공하면 그 마리가 다친다."""
    action = {'kind': 'check', 'ability': 'str', 'difficulty': 'medium', 'harm': harm, 'monster': monster}
    return {**action, 'lethal': lethal, **fields}


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def start_table(client: AsyncClient, me: dict[str, str], *others: dict[str, str]) -> dict:
    """
    수로의 맵과 몬스터를 둔 시나리오로 테이블을 시작한다. 나와 others 가 앉는다. 모두 수로 입구에 선다.

    돌려주는 것은 테이블과 장소(gate, deep)다.
    """
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    entries = f'{LOREBOOKS_URL}/{lorebook["id"]}/entries'
    gate = await post(client, entries, me, name='수로 입구', kind='place')
    deep = await post(client, entries, me, name='깊은 수로', kind='place')
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    monsters = f'{BESTIARIES_URL}/{bestiary["id"]}/monsters'
    rat = await post(client, monsters, me, name='수로 쥐', kind='beast', content='개만 한 쥐')
    skeleton = await post(client, monsters, me, name='해골 병사', kind='undead', content='녹슨 창을 든 해골')
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    scenario = await post(
        client,
        SCENARIOS_URL,
        me,
        title='지하 수로',
        rulebook_id=rulebook['id'],
        lorebook_ids=[lorebook['id']],
        bestiary_ids=[bestiary['id']],
        openings=['물 떨어지는 소리가 난다.'],
        default_sheet=SHEET,
        monster_sheets=[
            {'monster_id': rat['id'], 'sheet': RAT_SHEET},
            {'monster_id': skeleton['id'], 'sheet': SKELETON_SHEET},
        ],
        start_place=gate['id'],
        routes=[{'from_place': gate['id'], 'to_place': deep['id']}],
        encounters=[
            {'place_id': gate['id'], 'monster_id': rat['id'], 'count': 2},
            {'place_id': deep['id'], 'monster_id': skeleton['id'], 'count': 1},
        ],
    )
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1 + len(others))
    names = ['엘프', '드워프 기사']
    for headers, name in zip([me, *others], names, strict=False):
        if headers is not me:
            await client.post(f'{TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=headers)
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {'table': table, 'gate': gate, 'deep': deep}


async def scene(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.get(table_url(table, '/rounds/current/people'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def monster_named(client: AsyncClient, headers: dict[str, str], table: dict, name: str) -> dict:
    """이번 장면의 몬스터 중 이 이름의 마리."""
    return next(monster for monster in (await scene(client, headers, table))['monsters'] if monster['name'] == name)


async def send(client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None):
    body = {'content': content} if action is None else {'content': content, 'action': action}
    return await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)


async def declare(
    client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None
) -> dict:
    response = await send(client, headers, table, content, action)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def state_of(session: AsyncSession, monster_id: str) -> tuple[int, str]:
    """DB 에 적힌 마리의 (HP, 생사)."""
    query = select(TableMonster).where(TableMonster.id == uuid.UUID(monster_id))
    monster = await session.scalar(query.execution_options(populate_existing=True))
    return monster.hp, monster.status


async def stand_everyone_at(session: AsyncSession, table: dict, place: dict) -> None:
    """앉은 사람 모두의 캐릭터를 그 장소에 세운다. 이동을 거치지 않고 DB 를 고친다."""
    await session.execute(
        text('UPDATE table_sheets SET place_id = :place WHERE table_id = :table'),
        {'place': place['id'], 'table': table['id']},
    )
    await session.commit()


async def events_of(client: AsyncClient, headers: dict[str, str], table: dict, type_: str) -> list[dict]:
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return [event for event in response.json()['items'] if event['type'] == type_]


# --- 이번 장면의 몬스터 ---


async def test_the_scene_lists_the_monsters_where_someone_stands(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    listed = await scene(client, me, world['table'])

    # 입구의 쥐 둘만 보인다. 아무도 서 있지 않은 깊은 수로의 해골은 보이지 않는다
    assert [(monster['name'], monster['place_id']) for monster in listed['monsters']] == [
        ('수로 쥐 1', world['gate']['id']),
        ('수로 쥐 2', world['gate']['id']),
    ]
    assert {(monster['status'], monster['condition']) for monster in listed['monsters']} == {('alive', '멀쩡함')}
    # 숫자도 도감의 글도 싣지 않는다
    assert set(listed['monsters'][0]) == {'id', 'name', 'place_id', 'status', 'condition'}
    assert '개만 한 쥐' not in str(listed)


async def test_a_single_monster_is_called_without_a_number(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await stand_everyone_at(session, world['table'], world['deep'])

    listed = await scene(client, me, world['table'])

    # 해골 병사는 테이블에 하나뿐이다. 입구에 남은 사람이 없으니 쥐는 보이지 않는다
    assert [monster['name'] for monster in listed['monsters']] == ['해골 병사']


# --- 타격 ---


async def test_a_hit_wounds_the_monster(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3])

    closing = await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))

    effect = closing['declarations'][0]['outcome']['monster_effect']
    assert effect == {
        'kind': 'damage',
        'magnitude': 'moderate',
        'monster_id': rat['id'],
        'name': '수로 쥐 1',
        'rolls': [3],
        'amount': 3,
        'lethal': False,
        'status': 'alive',
    }
    assert await state_of(session, rat['id']) == (1, NpcStatus.ALIVE)
    # 다른 쥐는 그대로다
    other = await monster_named(client, me, world['table'], '수로 쥐 2')
    assert await state_of(session, other['id']) == (4, NpcStatus.ALIVE)


async def test_the_scene_shows_how_badly_the_monster_is_hurt(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3])
    await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))

    after = await monster_named(client, me, world['table'], '수로 쥐 1')

    # HP 4 중 1 이 남았다. 숫자는 보이지 않고 말로만 보인다
    assert (after['status'], after['condition']) == ('alive', '크게 다침')


async def test_a_failed_check_leaves_the_monster_alone(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [FAIL])

    closing = await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))

    assert closing['declarations'][0]['outcome']['monster_effect'] is None
    assert await state_of(session, rat['id']) == (4, NpcStatus.ALIVE)


@pytest.mark.parametrize(('lethal', 'expected'), [(False, NpcStatus.DOWNED), (True, NpcStatus.DEAD)])
async def test_a_beast_at_zero_is_downed_or_killed(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, lethal: bool, expected: NpcStatus
):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 8])

    closing = await declare(client, me, world['table'], BITE_BACK, strike(rat['id'], lethal=lethal))

    assert closing['declarations'][0]['outcome']['monster_effect']['status'] == expected
    assert await state_of(session, rat['id']) == (0, expected)


async def test_an_undead_at_zero_is_destroyed_even_when_subdued(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await stand_everyone_at(session, world['table'], world['deep'])
    skeleton = await monster_named(client, me, world['table'], '해골 병사')
    load_dice(app, [PASS, 8])

    # 제압하려 했지만 해골은 쓰러질 의식이 없다. 부서진다
    closing = await declare(client, me, world['table'], '해골을 부순다.', strike(skeleton['id'], lethal=False))

    assert closing['declarations'][0]['outcome']['monster_effect']['status'] == 'dead'
    assert await state_of(session, skeleton['id']) == (0, NpcStatus.DEAD)
    assert (await monster_named(client, me, world['table'], '해골 병사'))['condition'] == '죽음'


# --- 받을 때와 판정할 때의 검사 ---


async def test_a_monster_somewhere_else_cannot_be_targeted(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await stand_everyone_at(session, world['table'], world['deep'])
    skeleton = await monster_named(client, me, world['table'], '해골 병사')
    await stand_everyone_at(session, world['table'], world['gate'])

    away = await send(client, me, world['table'], '해골을 친다.', strike(skeleton['id']))
    unknown = await send(client, me, world['table'], '허공을 친다.', strike(str(uuid.uuid4())))

    # 다른 장소의 마리와 없는 마리는 같은 답이다. 가르면 아무도 없는 곳에 무엇이 있는지 드러난다
    assert away.status_code == unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert away.json() == unknown.json()


async def test_a_dead_monster_cannot_be_targeted(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 8])
    await declare(client, me, world['table'], BITE_BACK, strike(rat['id'], lethal=True))
    await narrated()

    response = await send(client, me, world['table'], BITE_BACK, strike(rat['id']))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'monster_dead'


async def test_a_monster_killed_earlier_in_the_round_is_not_rolled_for(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    # 판정의 눈과 양의 눈, 한 사람 몫만 있다. 둘째 사람이 굴리면 눈이 모자라 실패한다
    load_dice(app, [PASS, 8])

    await declare(client, me, world['table'], BITE_BACK, strike(rat['id'], lethal=True))
    closing = await declare(client, friend, world['table'], BITE_BACK, strike(rat['id']))

    outcomes = {declaration['character_name']: declaration['outcome'] for declaration in closing['declarations']}
    assert outcomes['엘프']['monster_effect']['status'] == 'dead'
    # 앞사람이 죽였다. 굴리지 않았으니 실패의 대가도 없다
    assert outcomes['드워프 기사'] == {'target_gone': {'monster_id': rat['id'], 'name': '수로 쥐 1', 'reason': 'dead'}}


# --- 내보내는 것 ---


async def test_the_change_is_recorded_without_hp_numbers(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    rat = await monster_named(client, me, world['table'], '수로 쥐 1')
    load_dice(app, [PASS, 3])
    await declare(client, me, world['table'], BITE_BACK, strike(rat['id']))

    changed = await events_of(client, me, world['table'], 'monster_changed')
    rolled = await events_of(client, me, world['table'], 'check_rolled')

    assert len(changed) == 1
    payload = changed[0]['payload']
    assert payload['monster_id'] == rat['id']
    assert payload['name'] == '수로 쥐 1'
    assert (payload['amount'], payload['status']) == (3, 'alive')
    assert not {'before', 'after', 'max_hp', 'condition'} & set(payload)
    # 원인은 그 판정이다
    assert changed[0]['caused_by_sequence'] == rolled[0]['sequence']


async def test_a_table_without_encounters_shows_no_monsters(client: AsyncClient, me: dict[str, str]):
    rulebook = await post(client, RULEBOOKS_URL, me, title='룰북')
    scenario = await post(
        client,
        SCENARIOS_URL,
        me,
        title='빈 방',
        rulebook_id=rulebook['id'],
        openings=['조용하다.'],
        default_sheet=SHEET,
    )
    await post(client, f'{SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await post(client, TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=1)
    await client.put(table_url(table, '/character'), json={'name': '엘프'}, headers=me)
    await client.post(table_url(table, '/start'), headers=me)

    assert (await scene(client, me, table))['monsters'] == []


# --- 행동의 모양 ---


@pytest.mark.parametrize(
    'fields',
    [
        # 몬스터에게는 타격만 한다
        {'harm': None},
        {'harm': None, 'recover': 'light'},
        {'aim': 'lost_eye'},
        # 대상은 하나다
        {'npc': str(uuid.uuid4())},
        {'target': str(uuid.uuid4()), 'recover': 'light', 'harm': None},
    ],
)
def test_a_monster_takes_only_a_plain_hit(fields: dict):
    with pytest.raises(ValidationError):
        CheckAction.model_validate(strike(str(uuid.uuid4()), **fields))


def test_a_hit_needs_someone_to_hit():
    with pytest.raises(ValidationError):
        CheckAction.model_validate({'kind': 'check', 'ability': 'str', 'harm': 'moderate'})


# --- DB 를 쓰지 않는 작은 함수들 ---


def test_every_kind_has_traits():
    # 타입을 더하면 성질도 정해야 한다
    assert set(TRAITS) == set(MonsterKind)


@pytest.mark.parametrize(
    ('hp', 'lethal', 'traits', 'expected'),
    [
        (3, False, Traits(), NpcStatus.ALIVE),
        (0, False, Traits(), NpcStatus.DOWNED),
        (0, True, Traits(), NpcStatus.DEAD),
        (0, False, Traits(destroyed_at_zero=True), NpcStatus.DEAD),
        (2, False, Traits(destroyed_at_zero=True), NpcStatus.ALIVE),
    ],
)
def test_status_after(hp: int, lethal: bool, traits: Traits, expected: NpcStatus):
    assert status_after(hp, lethal, traits) == expected


def test_change_monster_uses_the_traits_of_its_kind():
    construct = TableMonster(hp=2, max_hp=5, status=NpcStatus.ALIVE)
    beast = TableMonster(hp=2, max_hp=5, status=NpcStatus.ALIVE)
    moderate = SRD5.magnitudes[1]

    change_monster(construct, traits_of(MonsterKind.CONSTRUCT), moderate, False, ScriptedDice([6]))
    change_monster(beast, traits_of(MonsterKind.BEAST), moderate, False, ScriptedDice([6]))

    assert (construct.hp, construct.status) == (0, NpcStatus.DEAD)
    assert (beast.hp, beast.status) == (0, NpcStatus.DOWNED)
