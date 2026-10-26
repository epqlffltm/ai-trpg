# trpg-server/tests/test_friendly_fire.py

"""
앉은 사람끼리 해치는 것(#803)을 검증한다. 설정(app/tables/friendly_fire.py, friendly_fire_changes.py)과
받기·판정(app/rounds/friendly_fire.py, checks.py, item_actions.py, throws.py)이다.

판은 물건의 효과의 시험(tests/test_item_effects.py)의 수로다. 나(엘프, 방장)와 동료(드워프 기사)가 입구에 선다.
둘 다 최대 HP 10 이다. 룰북은 SRD5 다. 노릴 수 있는 부상은 모두 오래 가는 것이나 결손이다(팔 골절, 눈을 잃음).
부상 표의 11~12 는 기절(짧은 것), 20 은 눈을 잃음(결손)이다. 큰 타격은 최대 HP 의 절반 이상의 피해다.

보는 것.
  - 설정: 테이블과 자리 모두 끔이 기본이다. 테이블의 것은 방장만, 자리의 것은 본인만 바꾸고 이벤트로 남는다.
    드는 것은 둘 중 낮은 것, 자기 자신은 늘 다 됨이다.
  - 받기: 끔이면 409 friendly_fire_off(어느 쪽이 꺼도), 자기 자신은 된다. 동료를 죽이려 하면(lethal) 422,
    장난으로 오래 가는 부상을 노리면 409 friendly_fire_prank, 쓰러진 동료는 409 ally_down 이다.
  - 다 됨: 몬스터에게 맞은 것과 같다. 장난: HP 가 1 에서 멈추고, 짧은 부상만 입는다(오래 가는 것은 spared).
  - 닫을 때 다시 본다: 그사이에 받아들이지 않게 바꾸면 굴리지 않는다(target_gone, friendly_fire_off).
  - 쓰기와 던지기: 해로운 물건을 동료에게 쓰고 던지는 것도 같다. 이로운 물건은 설정을 보지 않는다.
  - 서술: 장난이 HP 의 줄에, 장난이라 입지 않은 부상이 그 뒤에 붙는다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.rounds.move_lines import describe_impact
from app.rounds.narrator import Impact
from app.tables.friendly_fire import level_toward, lower
from app.tables.models import FriendlyFire, GameTable, TableMember, TableSheet
from tests import test_item_effects as effects
from tests.test_monster_combat import FAIL, NO_INJURY, PASS

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = effects.ME
FRIEND = effects.FRIEND

me = effects.me
friend = effects.friend
load_dice = effects.load_dice
send = effects.send
declare = effects.declare
events_of = effects.events_of
outcome_of = effects.outcome_of
read_table = effects.read_table
sheet_of = effects.sheet_of
held = effects.held
table_url = effects.table_url
use = effects.use

# 부상 표의 눈. 11 은 기절(짧은 것, 1 라운드), 20 은 눈을 잃음(결손)
STUNNED = 11
LOST_EYE = 20


def strike(target: uuid.UUID, harm: str = 'heavy', **more) -> dict:
    """근력·보통으로 target 을 치는 판정."""
    return {'kind': 'check', 'ability': 'str', 'difficulty': 'medium', 'harm': harm, 'target': str(target), **more}


def throw(item: dict, target: uuid.UUID) -> dict:
    return {'kind': 'throw', 'item': item['id'], 'target': str(target)}


async def set_table(client: AsyncClient, headers: dict, table: dict, level: str):
    return await client.put(table_url(table, '/friendly-fire'), json={'friendly_fire': level}, headers=headers)


async def set_consent(client: AsyncClient, headers: dict, table: dict, level: str):
    return await client.put(
        table_url(table, '/members/me/friendly-fire'), json={'friendly_fire': level}, headers=headers
    )


async def allow(client: AsyncClient, me: dict, friend: dict, table: dict, level: str) -> None:
    """방장이 테이블을, 동료가 자기 자리를 level 로 둔다."""
    assert (await set_table(client, me, table, level)).status_code == status.HTTP_200_OK
    assert (await set_consent(client, friend, table, level)).status_code == status.HTTP_200_OK


async def start(client: AsyncClient, me: dict, friend: dict) -> dict:
    """나와 동료가 앉아 시작한 수로. 둘 다 물건 넷(독 단검, 기절 가루, 치유 물약, 연막탄)을 하나씩 가졌다."""
    return await effects.start_table(client, me, friend)


async def strike_friend(client: AsyncClient, me: dict, friend: dict, table: dict, action: dict) -> dict:
    """내가 action 을 선언하고, 동료가 웃어 라운드를 닫는다. 닫는 중인 라운드를 돌려준다."""
    await declare(client, me, table, '동료를 친다.', action)
    return await declare(client, friend, table, '웃는다.')


def member_row(user_id: uuid.UUID, consent: FriendlyFire) -> TableMember:
    return TableMember(user_id=user_id, friendly_fire=consent)


# --- 설정 ---


def test_the_lower_level_counts_and_oneself_is_always_fair_game():
    table = GameTable(friendly_fire=FriendlyFire.FULL)

    assert lower(FriendlyFire.FULL, FriendlyFire.PRANK) == FriendlyFire.PRANK
    assert lower(FriendlyFire.OFF, FriendlyFire.FULL) == FriendlyFire.OFF
    assert level_toward(table, ME, member_row(FRIEND, FriendlyFire.PRANK)) == FriendlyFire.PRANK
    off_table = GameTable(friendly_fire=FriendlyFire.OFF)
    assert level_toward(off_table, ME, member_row(FRIEND, FriendlyFire.FULL)) == FriendlyFire.OFF
    assert level_toward(off_table, ME, member_row(ME, FriendlyFire.OFF)) == FriendlyFire.FULL


async def test_both_settings_are_off_by_default(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)

    read = await read_table(client, me, world['table'])

    assert read['friendly_fire'] == 'off'
    assert [member['friendly_fire'] for member in read['members']] == ['off', 'off']


async def test_the_host_changes_the_table_and_everyone_sees_it(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)
    table = world['table']

    changed = await set_table(client, me, table, 'prank')
    again = await set_table(client, me, table, 'prank')
    refused = await set_table(client, friend, table, 'full')

    assert changed.status_code == status.HTTP_200_OK
    assert changed.json()['friendly_fire'] == 'prank'
    assert again.status_code == status.HTTP_200_OK
    assert refused.status_code == status.HTTP_403_FORBIDDEN
    # 같은 값으로 바꾸면 이벤트를 적지 않는다
    (event,) = await events_of(client, friend, table, 'friendly_fire_changed')
    assert (event['payload'], event['actor_id']) == ({'friendly_fire': 'prank'}, str(ME))


async def test_each_seat_sets_only_its_own_consent(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)
    table = world['table']

    changed = await set_consent(client, friend, table, 'full')
    wrong = await set_consent(client, friend, table, 'everything')

    assert changed.status_code == status.HTTP_200_OK
    consents = {member['user_id']: member['friendly_fire'] for member in changed.json()['members']}
    assert consents == {str(ME): 'off', str(FRIEND): 'full'}
    assert wrong.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    (event,) = await events_of(client, me, table, 'friendly_fire_consent_changed')
    assert event['payload'] == {'user_id': str(FRIEND), 'friendly_fire': 'full'}


# --- 받기 ---


@pytest.mark.parametrize(('table_level', 'consent'), [('off', 'full'), ('full', 'off')], ids=['table-off', 'seat-off'])
async def test_a_friend_is_safe_unless_both_allow_it(
    client: AsyncClient, me: dict, friend: dict, table_level: str, consent: str
):
    world = await start(client, me, friend)
    await set_table(client, me, world['table'], table_level)
    await set_consent(client, friend, world['table'], consent)

    response = await send(client, me, world['table'], '동료를 친다.', strike(FRIEND))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'friendly_fire_off'


async def test_one_can_always_hurt_oneself(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    world = await start(client, me, friend)
    load_dice(app, [PASS, 2])

    closing = await strike_friend(client, me, friend, world['table'], strike(ME, 'moderate'))

    effect = outcome_of(closing)['effect']
    assert (effect['user_id'], effect['before'], effect['after'], effect['prank']) == (str(ME), 10, 8, False)


@pytest.mark.parametrize(
    ('action', 'status_code', 'field'),
    [
        (strike(FRIEND, lethal=True), status.HTTP_422_UNPROCESSABLE_CONTENT, None),
        ({'kind': 'check', 'ability': 'str', 'target': str(FRIEND)}, status.HTTP_422_UNPROCESSABLE_CONTENT, None),
        (strike(uuid.UUID(effects.NO_SUCH_ID)), status.HTTP_422_UNPROCESSABLE_CONTENT, 'target'),
    ],
    ids=['lethal', 'no-harm', 'not-seated'],
)
async def test_misshaped_strikes_are_refused(
    client: AsyncClient, me: dict, friend: dict, action: dict, status_code: int, field: str | None
):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'full')

    response = await send(client, me, world['table'], '동료를 친다.', action)

    assert response.status_code == status_code
    if field is not None:
        assert response.json()['detail'].startswith(f'action.{field}')


async def test_a_prank_cannot_aim_at_a_lasting_injury(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'prank')

    pranked = await send(client, me, world['table'], '눈을 찌른다.', strike(FRIEND, 'light', aim='lost_eye'))
    await allow(client, me, friend, world['table'], 'full')
    allowed = await send(client, me, world['table'], '눈을 찌른다.', strike(FRIEND, 'light', aim='lost_eye'))

    assert pranked.status_code == status.HTTP_409_CONFLICT
    assert pranked.json()['reason'] == 'friendly_fire_prank'
    assert allowed.status_code == status.HTTP_200_OK


async def test_a_downed_friend_is_not_struck(client: AsyncClient, me: dict, friend: dict, session: AsyncSession):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'full')
    await session.execute(update(TableSheet).where(TableSheet.user_id == FRIEND).values(hp=0))
    await session.commit()

    response = await send(client, me, world['table'], '동료를 친다.', strike(FRIEND))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'ally_down'


async def test_a_friend_elsewhere_is_out_of_reach(client: AsyncClient, me: dict, friend: dict, session: AsyncSession):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'full')
    # 동료를 다른 장소로 옮긴다(이 판의 맵에는 없는 장소다. 같은 곳이 아니기만 하면 된다)
    await session.execute(update(TableSheet).where(TableSheet.user_id == FRIEND).values(place_id=uuid.uuid4()))
    await session.commit()

    response = await send(client, me, world['table'], '동료를 친다.', strike(FRIEND))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'].startswith('action.target')


# --- 다 됨과 장난 ---


async def test_full_friendly_fire_hurts_like_a_monster(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'full')
    # 4 는 최대 HP 의 절반이 안 된다. 부상 표를 굴리지 않는다
    dice = load_dice(app, [PASS, 4])

    closing = await strike_friend(client, me, friend, world['table'], strike(FRIEND, 'moderate'))

    outcome = outcome_of(closing)
    assert outcome['success'] is True
    effect = outcome['effect']
    assert (effect['user_id'], effect['before'], effect['after'], effect['prank']) == (str(FRIEND), 10, 6, False)
    assert dice.remaining == 0
    (changed,) = await events_of(client, me, world['table'], 'hp_changed')
    assert changed['payload']['user_id'] == str(FRIEND)
    assert 'prank' not in changed['payload']


async def test_a_prank_stops_at_one_hp_and_spares_a_lasting_injury(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'prank')
    # 16 은 큰 타격이다. 부상 표가 눈을 잃음을 낸다
    load_dice(app, [PASS, 8, 8, LOST_EYE])

    closing = await strike_friend(client, me, friend, world['table'], strike(FRIEND))

    effect = outcome_of(closing)['effect']
    assert (effect['amount'], effect['before'], effect['after'], effect['downed']) == (16, 10, 1, False)
    assert effect['prank'] is True
    roll = effect['injury_roll']
    assert (roll['injury'], roll['spared']) == (None, 'lost_eye')
    after = await read_table(client, me, world['table'])
    assert (sheet_of(after, FRIEND)['hp'], sheet_of(after, FRIEND)['injuries']) == (1, [])
    (changed,) = await events_of(client, me, world['table'], 'hp_changed')
    assert changed['payload']['prank'] is True
    assert await events_of(client, me, world['table'], 'injury_gained') == []


async def test_a_prank_still_leaves_a_short_injury(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'prank')
    load_dice(app, [PASS, 8, 8, STUNNED])

    closing = await strike_friend(client, me, friend, world['table'], strike(FRIEND))

    assert outcome_of(closing)['effect']['injury_roll']['injury'] == 'stunned'
    after = await read_table(client, me, world['table'])
    assert [one['injury'] for one in sheet_of(after, FRIEND)['injuries']] == ['stunned']


async def test_a_prank_on_a_friend_with_one_hp_takes_nothing_more(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, session: AsyncSession
):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'prank')
    await session.execute(update(TableSheet).where(TableSheet.user_id == FRIEND).values(hp=1))
    await session.commit()
    load_dice(app, [PASS, 3])

    closing = await strike_friend(client, me, friend, world['table'], strike(FRIEND, 'light'))

    effect = outcome_of(closing)['effect']
    assert (effect['before'], effect['after'], effect['downed']) == (1, 1, False)


async def test_a_miss_does_nothing(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    world = await start(client, me, friend)
    await allow(client, me, friend, world['table'], 'full')
    load_dice(app, [FAIL])

    closing = await strike_friend(client, me, friend, world['table'], strike(FRIEND))

    outcome = outcome_of(closing)
    assert (outcome['success'], outcome['effect']) == (False, None)


# --- 닫을 때 다시 본다 ---


async def test_consent_withdrawn_before_the_close_stops_the_strike(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    world = await start(client, me, friend)
    table = world['table']
    await allow(client, me, friend, table, 'full')
    dice = load_dice(app, [PASS, 8, 8])
    await declare(client, me, table, '동료를 친다.', strike(FRIEND))

    await set_consent(client, friend, table, 'off')
    closing = await declare(client, friend, table, '웃는다.')

    gone = outcome_of(closing)['target_gone']
    assert (gone['user_id'], gone['name'], gone['reason']) == (str(FRIEND), '드워프 기사', 'friendly_fire_off')
    # 굴리지 않았다
    assert dice.remaining == 3
    assert sheet_of(await read_table(client, me, table), FRIEND)['hp'] == 10


async def test_a_table_lowered_to_prank_before_the_close_caps_the_strike(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    world = await start(client, me, friend)
    table = world['table']
    await allow(client, me, friend, table, 'full')
    load_dice(app, [PASS, 8, 8, NO_INJURY])
    await declare(client, me, table, '동료를 친다.', strike(FRIEND))

    await set_table(client, me, table, 'prank')
    closing = await declare(client, friend, table, '웃는다.')

    effect = outcome_of(closing)['effect']
    assert (effect['after'], effect['prank']) == (1, True)


# --- 쓰기와 던지기 ---


async def test_a_harmful_thing_used_on_a_friend_follows_the_settings(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    world = await start(client, me, friend)
    table = world['table']

    refused = await send(client, me, table, '가루를 뿌린다.', use(world['dagger'], target=str(FRIEND)))
    await allow(client, me, friend, table, 'prank')
    # 굴리지 않는다. 피해의 눈만 쓴다
    load_dice(app, [4])
    await declare(client, me, table, '단검으로 찌른다.', use(world['dagger'], target=str(FRIEND)))
    closing = await declare(client, friend, table, '웃는다.')

    assert refused.json()['reason'] == 'friendly_fire_off'
    outcome = outcome_of(closing)
    assert (outcome['effect']['user_id'], outcome['effect']['after'], outcome['effect']['prank']) == (
        str(FRIEND),
        6,
        True,
    )
    # 중독은 짧은 부상이라 장난에도 든다
    assert effects.injured_keys(outcome['item_use']) == ['poisoned']


async def test_a_harmful_thing_is_not_used_once_consent_is_withdrawn(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    world = await start(client, me, friend)
    table = world['table']
    await allow(client, me, friend, table, 'full')
    await declare(client, me, table, '가루를 뿌린다.', use(world['powder'], target=str(FRIEND)))

    await set_table(client, me, table, 'off')
    closing = await declare(client, friend, table, '웃는다.')

    used = outcome_of(closing)['item_use']
    assert (used['used'], used['reason']) == (False, 'friendly_fire_off')
    assert held(await read_table(client, me, table), ME)['기절 가루'] == 1


async def test_a_kind_thing_needs_no_consent(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    world = await start(client, me, friend)
    load_dice(app, [2])

    response = await send(client, me, world['table'], '물약을 건넨다.', use(world['potion'], target=str(FRIEND)))

    assert response.status_code == status.HTTP_200_OK


async def test_a_thrown_dagger_hits_a_friend(client: AsyncClient, app: FastAPI, me: dict, friend: dict):
    world = await start(client, me, friend)
    table = world['table']
    await allow(client, me, friend, table, 'full')
    # 맞히는 판정(민첩·보통), 피해의 눈
    load_dice(app, [PASS, 3])

    closing = await strike_friend(client, me, friend, table, throw(world['dagger'], FRIEND))

    outcome = outcome_of(closing)
    assert (outcome['effect']['user_id'], outcome['effect']['after']) == (str(FRIEND), 7)
    thrown = outcome['item_throw']
    assert thrown['target'] == {'monster_id': None, 'entry_id': None, 'user_id': str(FRIEND), 'name': '드워프 기사'}
    assert effects.injured_keys(thrown) == ['poisoned']
    assert '독 단검' not in held(await read_table(client, me, table), ME)


async def test_a_harmful_throw_follows_the_settings(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)

    response = await send(client, me, world['table'], '단검을 던진다.', throw(world['dagger'], FRIEND))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()['reason'] == 'friendly_fire_off'


async def test_a_potion_is_thrown_to_a_friend_without_consent(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict
):
    world = await start(client, me, friend)
    load_dice(app, [PASS, 2])

    closing = await strike_friend(client, me, friend, world['table'], throw(world['potion'], FRIEND))

    effect = outcome_of(closing)['effect']
    assert (effect['user_id'], effect['kind']) == (str(FRIEND), 'recovery')


async def test_one_does_not_throw_at_oneself(client: AsyncClient, me: dict, friend: dict):
    world = await start(client, me, friend)

    response = await send(client, me, world['table'], '단검을 던진다.', throw(world['dagger'], ME))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()['detail'].startswith('action.target')


async def start_with_breaking_powder(client: AsyncClient, me: dict, friend: dict) -> dict:
    """기절 가루 대신 팔을 부러뜨리는 가루(팔 골절, 오래 가는 부상)를 둔 수로. 나머지는 start 와 같다."""
    world = await effects.make_world(client, me)
    items = effects.the_items(world)
    items[1] = {**items[1], 'effects': [{'kind': 'injure', 'injury': 'broken_arm'}]}
    scenario = await effects.make_scenario(client, me, world, items)
    await effects.post(client, f'{effects.combat.SCENARIOS_URL}/{scenario["id"]}/versions', me)
    table = await effects.post(client, effects.combat.TABLES_URL, me, scenario_id=scenario['id'], version=1, capacity=2)
    await client.post(f'{effects.combat.TABLES_URL}/join', json={'invite_code': table['invite_code']}, headers=friend)
    for headers, name in ((me, '엘프'), (friend, '드워프 기사')):
        await client.put(table_url(table, '/character'), json={'name': name}, headers=headers)
    started = await client.post(table_url(table, '/start'), headers=me)
    assert started.status_code == status.HTTP_200_OK, started.text
    return {**world, 'table': started.json()}


@pytest.mark.parametrize('how', ['use', 'throw'])
async def test_a_prank_spares_a_lasting_injury_from_a_thing(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, how: str
):
    world = await start_with_breaking_powder(client, me, friend)
    table = world['table']
    await allow(client, me, friend, table, 'prank')
    # 쓰기는 굴리지 않는다. 던지기는 맞히는 판정을 굴린다
    load_dice(app, [] if how == 'use' else [PASS])
    action = use(world['powder'], target=str(FRIEND)) if how == 'use' else throw(world['powder'], FRIEND)

    closing = await strike_friend(client, me, friend, table, action)

    document = outcome_of(closing)['item_use' if how == 'use' else 'item_throw']
    assert [(one['injury'], one['spared']) for one in document['injured']] == [(None, 'broken_arm')]
    assert sheet_of(await read_table(client, me, table), FRIEND)['injuries'] == []


# --- 서술 ---


def test_the_narration_line_marks_a_prank_and_what_it_spared():
    impact = Impact(
        kind='damage', character_name='영애', amount=6, hp=1, max_hp=10, downed=False, prank=True, spared='팔 골절'
    )

    assert describe_impact(impact) == '→ 영애 피해 6 (HP 1/10, 장난). 장난이라 입지 않은 부상: 팔 골절'
