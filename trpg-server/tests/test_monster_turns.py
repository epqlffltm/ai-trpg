# trpg-server/tests/test_monster_turns.py

"""
라운드의 차례와 몬스터의 공격(#231 3c)을 검증한다.

맵은 수로 입구(시작) 하나다. 입구에 수로 쥐가 있다(야수, 최대 HP 4). 쥐의 공격은 "물기"(근력, 보통, 가벼움 1d4)다.
캐릭터의 시트는 모든 능력치 10, 최대 HP 10 이다. 쥐도 따로 정하지 않으면 능력치 10 이다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 쓰는 차례는 이렇다.
  1. 차례의 주사위: 자리(기습, 민첩)가 같은 무리만 굴린다. 앉은 사람, 그다음 장면의 마리 순서다.
  2. 차례마다: 앉은 사람은 판정의 눈 → 양의 눈. 몬스터는 (대상이 여럿이면) 대상 → (공격이 여럿이면) 공격 →
     판정의 눈 → (맞히면) 양의 눈.

보는 것은 여섯이다.
  - 차례가 생기는 때: 공격이 있는 살아 있는 마리가 장면에 있을 때만. 없으면 지금처럼 앉은 순서이고 turns 는 비어 있다.
  - 차례의 순서: 기습한 쪽 → 민첩이 높은 쪽 → 주사위. 기습은 만난 첫 라운드에만 쓴다.
  - 몬스터의 공격: 맞히면 캐릭터의 HP 가 깎이고, 빗나가면 그대로다. 대상과 공격은 주사위로 고른다.
  - 차례 전에 쓰러지거나 죽은 것: 쓰러진 캐릭터는 행동하지 못하고(turn_lost), 죽은 마리는 공격하지 못한다(skipped).
  - 이벤트: 차례 순서로 적힌다. monster_attacked 뒤에 HP 의 변화가 그것을 원인으로 잇는다.
    몬스터의 숫자는 보이지 않는다.
  - 만난 첫 라운드(engaged_round)가 적힌다.
맨 아래에는 DB 를 쓰지 않는 작은 함수들의 테스트가 있다.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from server_core.testing.tokens import SigningKey, make_access_claims, make_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models import Surprise
from app.engine.dice import ScriptedDice
from app.engine.templates import SRD5
from app.main import API_PREFIX
from app.rounds import initiative
from app.rounds.initiative import Turn, TurnKind
from app.rounds.models import Round
from app.rounds.monster_attacks import Skipped, choose, roll_attack, stopped_by, take_monster_turn
from app.rounds.move_lines import describe_move
from app.rounds.narrator import Move
from app.tables.models import NpcStatus, TableInjury, TableMonster, TableSheet
from tests.narration_model import asset_body
from tests.sheets import SHEET, make_sheet

pytestmark = pytest.mark.usefixtures('clean_tables')

SCENARIOS_URL = f'{API_PREFIX}/scenarios'
RULEBOOKS_URL = f'{API_PREFIX}/rulebooks'
LOREBOOKS_URL = f'{API_PREFIX}/lorebooks'
BESTIARIES_URL = f'{API_PREFIX}/bestiaries'
TABLES_URL = f'{API_PREFIX}/tables'

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')

BITE = {'name': '물기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'light'}
CLAW = {'name': '할퀴기', 'ability': 'str', 'difficulty': 'medium', 'harm': 'moderate'}
RAT_SHEET = make_sheet(max_hp=4)

# 판정의 눈. 보통(목표 15)에 도전한다. 시트의 보정은 0 이다
FAIL = 1
PASS = 20
# 부상 표의 눈. SRD5 의 1~10 은 아무 부상도 없다. 쥐를 쓰러뜨리면 부상 표를 굴린다(#799)
NO_INJURY = 1

REST = '숨을 고른다.'
KICK = '쥐를 걷어찬다.'


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


def rest() -> dict:
    """민첩으로 보통에 도전한다. 대가도 효과도 없는 판정이다."""
    return {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium'}


def kick(monster: str, lethal: bool = True) -> dict:
    """근력으로 보통에 도전한다. 성공하면 그 마리가 1d8 만큼 다친다."""
    return {
        'kind': 'check',
        'ability': 'str',
        'difficulty': 'medium',
        'harm': 'moderate',
        'monster': monster,
        'lethal': lethal,
    }


async def post(client: AsyncClient, url: str, headers: dict[str, str], **body) -> dict:
    response = await client.post(url, json=asset_body(url, body), headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def table_url(table: dict, path: str = '') -> str:
    return f'{TABLES_URL}/{table["id"]}{path}'


async def start_table(
    client: AsyncClient,
    me: dict[str, str],
    *others: dict[str, str],
    attacks: list[dict] | None = None,
    rat_sheet: dict = RAT_SHEET,
    count: int = 1,
    surprise: str = 'none',
    sheet: dict = SHEET,
) -> dict:
    """
    수로 입구에 쥐를 둔 시나리오로 테이블을 시작한다. 나와 others 가 앉는다. 모두 수로 입구에 선다.

    attacks 를 주지 않으면 쥐는 물기 하나를 가진다. 돌려주는 것은 테이블이다.
    """
    lorebook = await post(client, LOREBOOKS_URL, me, title='지하 수로')
    gate = await post(client, f'{LOREBOOKS_URL}/{lorebook["id"]}/entries', me, name='수로 입구', kind='place')
    bestiary = await post(client, BESTIARIES_URL, me, title='지하 수로의 것들')
    rat = await post(client, f'{BESTIARIES_URL}/{bestiary["id"]}/monsters', me, name='수로 쥐', kind='beast')
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
        default_sheet=sheet,
        monster_sheets=[
            {'monster_id': rat['id'], 'sheet': rat_sheet, 'attacks': [BITE] if attacks is None else attacks}
        ],
        start_place=gate['id'],
        encounters=[{'place_id': gate['id'], 'monster_id': rat['id'], 'count': count, 'surprise': surprise}],
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
    return table


async def monsters_of(client: AsyncClient, headers: dict[str, str], table: dict) -> list[dict]:
    response = await client.get(table_url(table, '/rounds/current/people'), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['monsters']


async def declare(
    client: AsyncClient, headers: dict[str, str], table: dict, content: str, action: dict | None = None
) -> dict:
    body = {'content': content} if action is None else {'content': content, 'action': action}
    response = await client.put(table_url(table, '/rounds/current/declaration'), json=body, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def turns_of(session: AsyncSession, table: dict, number: int = 1) -> list[dict]:
    """DB 에 적힌 그 라운드의 차례."""
    query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == number)
    round_ = await session.scalar(query.execution_options(populate_existing=True))
    return round_.turns


async def moves_of(session: AsyncSession, table: dict, number: int = 1) -> list[dict]:
    """DB 에 굳힌 그 라운드의 각자 한 일(서술자에게 줄 것)."""
    query = select(Round).where(Round.table_id == uuid.UUID(table['id']), Round.number == number)
    round_ = await session.scalar(query.execution_options(populate_existing=True))
    return round_.moves


async def hp_of(session: AsyncSession, table: dict, user_id: uuid.UUID = ME) -> int:
    """DB 에 적힌 그 사람의 지금 캐릭터의 HP."""
    query = select(TableSheet.hp).where(TableSheet.table_id == uuid.UUID(table['id']), TableSheet.user_id == user_id)
    return await session.scalar(query.execution_options(populate_existing=True))


async def engaged_rounds(session: AsyncSession, table: dict) -> list[int | None]:
    query = select(TableMonster.engaged_round).where(TableMonster.table_id == uuid.UUID(table['id']))
    return list((await session.scalars(query.order_by(TableMonster.number))).all())


async def events_of(client: AsyncClient, headers: dict[str, str], table: dict) -> list[dict]:
    response = await client.get(table_url(table, '/events'), params={'limit': 100}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['items']


def who(turns: list[dict]) -> list[str]:
    """차례의 주인들을 짧게. 캐릭터는 이름, 몬스터는 부르는 이름이다."""
    return [turn['character_name'] if turn['kind'] == 'pc' else turn['name'] for turn in turns]


# --- 차례가 생기는 때 ---


async def test_monsters_without_attacks_keep_the_seated_order(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    table = await start_table(client, me, attacks=[])
    dice = load_dice(app, [FAIL])

    await declare(client, me, table, REST, rest())

    assert await turns_of(session, table) == []
    assert dice.remaining == 0


async def test_an_attacking_monster_makes_turns(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    # 차례의 주사위: 엘프 15, 쥐 5. 엘프의 판정 1(실패). 쥐의 물기 1(빗나감)
    dice = load_dice(app, [15, 5, FAIL, FAIL])
    table = await start_table(client, me)

    await declare(client, me, table, REST, rest())

    turns = await turns_of(session, table)
    assert who(turns) == ['엘프', '수로 쥐']
    assert turns[0] == {
        'kind': 'pc',
        'first': False,
        'score': 10,
        'tiebreak': 15,
        'user_id': str(ME),
        'character_name': '엘프',
    }
    assert turns[1]['tiebreak'] == 5
    assert turns[1]['outcome']['attack'] == BITE
    assert turns[1]['outcome']['success'] is False
    assert dice.remaining == 0


async def test_a_free_declaration_still_lets_the_monster_attack(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    # 행동이 없는 선언은 차례가 없다. 쥐만 차례를 받는다. 무리가 하나라 차례의 주사위를 굴리지 않는다
    dice = load_dice(app, [PASS, 3])
    table = await start_table(client, me)

    await declare(client, me, table, REST)

    assert who(await turns_of(session, table)) == ['수로 쥐']
    assert await hp_of(session, table) == 7
    assert dice.remaining == 0


# --- 차례의 순서 ---


async def test_the_higher_initiative_goes_first_without_dice(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    # 쥐의 민첩이 높다. 차례의 주사위를 굴리지 않는다. 쥐의 물기 1, 엘프의 판정 1
    dice = load_dice(app, [FAIL, FAIL])
    table = await start_table(client, me, rat_sheet=make_sheet(max_hp=4, dex=14))

    await declare(client, me, table, REST, rest())

    turns = await turns_of(session, table)
    assert who(turns) == ['수로 쥐', '엘프']
    assert [turn['tiebreak'] for turn in turns] == [None, None]
    assert dice.remaining == 0


async def test_a_tie_is_broken_by_dice(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    # 차례의 주사위: 엘프 2, 쥐 18. 쥐가 먼저다
    dice = load_dice(app, [2, 18, FAIL, FAIL])
    table = await start_table(client, me)

    await declare(client, me, table, REST, rest())

    assert who(await turns_of(session, table)) == ['수로 쥐', '엘프']
    assert dice.remaining == 0


async def test_ambushing_monsters_go_first_only_in_the_first_round(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    # 엘프의 민첩이 높지만, 첫 라운드에는 기습한 쥐가 먼저다
    dice = load_dice(app, [FAIL, FAIL])
    table = await start_table(client, me, surprise='monsters', sheet=make_sheet(dex=14))

    await declare(client, me, table, REST, rest())
    await narrated()
    turns = await turns_of(session, table)
    assert who(turns) == ['수로 쥐', '엘프']
    assert [turn['first'] for turn in turns] == [True, False]

    # 둘째 라운드에는 민첩대로 엘프가 먼저다
    dice = load_dice(app, [FAIL, FAIL])
    await declare(client, me, table, REST, rest())
    assert who(await turns_of(session, table, 2)) == ['엘프', '수로 쥐']
    assert dice.remaining == 0


async def test_an_ambushing_party_goes_first(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    # 쥐의 민첩이 높지만, 일행이 기습해 엘프가 먼저다
    dice = load_dice(app, [FAIL, FAIL])
    table = await start_table(client, me, surprise='party', rat_sheet=make_sheet(max_hp=4, dex=14))

    await declare(client, me, table, REST, rest())

    turns = await turns_of(session, table)
    assert who(turns) == ['엘프', '수로 쥐']
    assert [turn['first'] for turn in turns] == [True, False]
    assert dice.remaining == 0


async def test_the_first_round_is_recorded_when_met(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    load_dice(app, [10, 5, FAIL, FAIL])
    table = await start_table(client, me)
    assert await engaged_rounds(session, table) == [None]

    await declare(client, me, table, REST, rest())

    assert await engaged_rounds(session, table) == [1]


# --- 몬스터의 공격 ---


async def test_a_hit_hurts_the_character(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    # 쥐가 먼저(민첩 14). 물기 20(맞힘), 피해 3. 엘프의 판정 1
    dice = load_dice(app, [PASS, 3, FAIL])
    table = await start_table(client, me, rat_sheet=make_sheet(max_hp=4, dex=14))

    await declare(client, me, table, REST, rest())

    outcome = (await turns_of(session, table))[0]['outcome']
    assert outcome['success'] is True
    assert outcome['user_id'] == str(ME)
    assert outcome['effect']['kind'] == 'damage'
    assert outcome['effect']['before'] == 10
    assert outcome['effect']['after'] == 7
    assert await hp_of(session, table) == 7
    assert dice.remaining == 0


async def test_a_miss_leaves_the_character_alone(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    load_dice(app, [FAIL, FAIL])
    table = await start_table(client, me, rat_sheet=make_sheet(max_hp=4, dex=14))

    await declare(client, me, table, REST, rest())

    assert (await turns_of(session, table))[0]['outcome']['effect'] is None
    assert await hp_of(session, table) == 10


async def test_the_target_and_the_attack_are_chosen_by_dice(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    # 둘 다 행동 없는 선언이라 쥐만 차례를 받는다. 대상 2(드워프 기사), 공격 2(할퀴기), 판정 1
    dice = load_dice(app, [2, 2, FAIL])
    table = await start_table(client, me, friend, attacks=[BITE, CLAW])

    await declare(client, me, table, REST)
    await declare(client, friend, table, REST)

    outcome = (await turns_of(session, table))[0]['outcome']
    assert outcome['character_name'] == '드워프 기사'
    assert outcome['attack'] == CLAW
    assert dice.remaining == 0


# --- 차례 전에 쓰러지거나 죽은 것 ---


async def test_a_character_downed_before_their_turn_does_not_act(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    # 할퀴기(1d8)에 8. 엘프의 HP 는 6 이라 쓰러지고 부상 표를 굴린다(1). 엘프는 판정을 굴리지 않는다
    dice = load_dice(app, [PASS, 8, 1])
    table = await start_table(
        client, me, attacks=[CLAW], rat_sheet=make_sheet(max_hp=4, dex=14), sheet=make_sheet(max_hp=6)
    )

    closing = await declare(client, me, table, REST, rest())

    assert closing['declarations'][0]['outcome'] == {'turn_lost': 'downed'}
    assert dice.remaining == 0
    assert (await moves_of(session, table))[0]['lost_turn'] == 'downed'
    move = Move(character_name='엘프', content=REST, downed=True, lost_turn='downed')
    assert describe_move(move) == '엘프: 숨을 고른다. (하려던 일을 하기 전에 쓰러졌다)'


async def test_a_monster_killed_before_its_turn_does_not_attack(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    # 엘프가 먼저(민첩 14). 판정 20, 피해 8 로 쥐(HP 4)가 죽는다. 쥐는 굴리지 않는다
    dice = load_dice(app, [PASS, 8])
    table = await start_table(client, me, sheet=make_sheet(dex=14))
    rat = (await monsters_of(client, me, table))[0]

    await declare(client, me, table, KICK, kick(rat['id']))

    turns = await turns_of(session, table)
    assert turns[1]['outcome'] == {'skipped': 'dead'}
    assert dice.remaining == 0
    attacked = [event for event in await events_of(client, me, table) if event['type'] == 'monster_attacked']
    assert attacked == []


async def test_a_downed_monster_gets_no_turn(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession, narrated
):
    # 첫 라운드에 엘프가 쥐를 제압해 쓰러뜨린다
    load_dice(app, [PASS, 8, NO_INJURY])
    table = await start_table(client, me, sheet=make_sheet(dex=14))
    rat = (await monsters_of(client, me, table))[0]
    await declare(client, me, table, KICK, kick(rat['id'], lethal=False))
    await narrated()
    assert (await turns_of(session, table))[1]['outcome'] == {'skipped': 'downed'}

    # 둘째 라운드에는 쓰러진 쥐뿐이라 차례가 없다
    dice = load_dice(app, [FAIL])
    await declare(client, me, table, REST, rest())
    assert await turns_of(session, table, 2) == []
    assert dice.remaining == 0


# --- 이벤트 ---


async def test_events_follow_the_turns(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    # 쥐가 먼저. 물기 20, 피해 3. 그다음 엘프의 판정 1
    load_dice(app, [PASS, 3, FAIL])
    table = await start_table(client, me, rat_sheet=make_sheet(max_hp=4, dex=14))

    await declare(client, me, table, REST, rest())

    events = await events_of(client, me, table)
    kinds = [event['type'] for event in events]
    start = kinds.index('monster_attacked')
    assert kinds[start : start + 4] == ['monster_attacked', 'hp_changed', 'player_action', 'check_rolled']
    attacked, changed = events[start], events[start + 1]
    assert attacked['payload'] == {
        'round': 1,
        'monster_id': attacked['payload']['monster_id'],
        'name': '수로 쥐',
        'attack': BITE,
        'user_id': str(ME),
        'character_name': '엘프',
        'success': True,
    }
    assert changed['caused_by_sequence'] == attacked['sequence']


# --- 작은 함수들 ---


def pc(name: str, dex: int, place: uuid.UUID | None = None) -> SimpleNamespace:
    sheet = SimpleNamespace(abilities={'dex': dex}, place_id=place)
    return SimpleNamespace(user_id=uuid.uuid4(), character_name=name, sheet=sheet)


def mob(
    name: str, dex: int, engaged: int | None = None, status_: str = NpcStatus.ALIVE, injuries: list | None = None
) -> SimpleNamespace:
    state = SimpleNamespace(
        id=uuid.uuid4(),
        monster_id=uuid.uuid4(),
        place_id=uuid.uuid4(),
        abilities={'dex': dex},
        engaged_round=engaged,
        status=status_,
        surprise=None,
        injuries=injuries or [],
    )
    return SimpleNamespace(state=state, name=name, definition=SimpleNamespace(attacks=[BITE]))


def turn_of(owner: SimpleNamespace, first: bool = False) -> Turn:
    if hasattr(owner, 'state'):
        return Turn(TurnKind.MONSTER, None, owner, first, owner.state.abilities['dex'])
    return Turn(TurnKind.PC, owner, None, first, owner.sheet.abilities['dex'])


def names(turns: list[Turn]) -> list[str]:
    return [turn.member.character_name if turn.member else turn.monster.name for turn in turns]


def test_order_puts_the_ambushers_then_the_quick_first():
    turns = [turn_of(pc('느림', 8)), turn_of(pc('빠름', 16)), turn_of(mob('쥐', 12), first=True)]

    ordered = initiative.order_turns(turns, 20, ScriptedDice([]))

    assert names(ordered) == ['쥐', '빠름', '느림']


def test_only_tied_turns_roll():
    turns = [turn_of(pc('하나', 10)), turn_of(pc('둘', 10)), turn_of(pc('셋', 12))]

    ordered = initiative.order_turns(turns, 20, ScriptedDice([3, 9]))

    assert names(ordered) == ['셋', '둘', '하나']
    assert [turn.tiebreak for turn in ordered] == [None, 9, 3]


def test_the_same_tiebreak_keeps_the_given_order():
    turns = [turn_of(pc('먼저 앉음', 10)), turn_of(mob('쥐', 10))]

    ordered = initiative.order_turns(turns, 20, ScriptedDice([7, 7]))

    assert names(ordered) == ['먼저 앉음', '쥐']


def test_without_an_initiative_ability_everyone_ties():
    ruleset = SRD5.model_copy(update={'initiative_ability': None})

    assert initiative.score_of(ruleset, {'dex': 18}) is None
    assert initiative.score_of(SRD5, {'dex': 18}) == 18


def test_surprise_counts_only_in_the_first_round():
    snapshot = SimpleNamespace(encounters=[])
    rat = mob('쥐', 10, engaged=1)
    encounter = SimpleNamespace(
        place_id=rat.state.place_id, monster_id=rat.state.monster_id, surprise=Surprise.MONSTERS
    )
    snapshot.encounters.append(encounter)

    assert initiative.surprise_of(snapshot, rat, 1) == Surprise.MONSTERS
    assert initiative.surprise_of(snapshot, rat, 2) == Surprise.NONE


def test_mark_engaged_keeps_the_first_round():
    met, new = mob('쥐 1', 10, engaged=1), mob('쥐 2', 10)

    initiative.mark_engaged([met, new], 3)

    assert [met.state.engaged_round, new.state.engaged_round] == [1, 3]


def test_choose_rolls_only_for_several_options():
    assert choose(['하나'], ScriptedDice([])) == '하나'
    assert choose(['하나', '둘', '셋'], ScriptedDice([3])) == '셋'


def test_a_monster_with_nobody_standing_by_skips():
    rat = mob('쥐', 10)
    away = pc('엘프', 10, place=uuid.uuid4())
    away.sheet.died_at, away.sheet.hp = None, 10
    # 같은 장소의 드워프 기사는 이번 라운드에 쓰러졌다. 다음 라운드부터 대상이다(#369)
    downed = pc('드워프 기사', 10, place=rat.state.place_id)
    downed.sheet.died_at, downed.sheet.hp = None, 0
    judging = SimpleNamespace(
        table=SimpleNamespace(members=[away, downed]), dice=ScriptedDice([]), ruleset=SRD5, downed_at_start=frozenset()
    )

    assert take_monster_turn(judging, rat) == {'skipped': Skipped.NO_TARGET}


def test_a_monster_down_or_dead_or_stunned_is_stopped():
    judging = SimpleNamespace(ruleset=SRD5)
    stunned = [TableInjury(injury='stunned')]
    healed = [TableInjury(injury='stunned', ended_at=datetime.now(UTC))]

    assert stopped_by(judging, mob('쥐', 10)) is None
    assert stopped_by(judging, mob('쥐', 10, status_=NpcStatus.DOWNED)) == Skipped.DOWNED
    assert stopped_by(judging, mob('쥐', 10, status_=NpcStatus.DEAD)) == Skipped.DEAD
    # 행동을 막는 부상(기절)을 입은 마리도 움직이지 못한다(#799). 풀렸으면 움직인다
    assert stopped_by(judging, mob('쥐', 10, injuries=stunned)) == Skipped.INCAPACITATED
    assert stopped_by(judging, mob('쥐', 10, injuries=healed)) is None


def test_a_monster_with_a_broken_arm_bites_at_a_disadvantage():
    # 팔 골절은 근력의 판정을 불리하게 한다(#799). 두 번 굴려 낮은 눈을 쓴다
    rat = mob('쥐', 10, injuries=[TableInjury(injury='broken_arm')])
    rat.state.abilities['str'] = 10
    judging = SimpleNamespace(ruleset=SRD5, dice=ScriptedDice([20, 2]))

    rolled = roll_attack(judging, rat, SimpleNamespace(**BITE))

    assert (rolled.rolls, rolled.check.roll, rolled.check.success) == ((20, 2), 2, False)
    assert rolled.hindrance.disadvantage
    assert rolled.hindrance.injuries == ('broken_arm',)
