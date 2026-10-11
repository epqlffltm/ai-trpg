# game-server/tests/test_injuries.py

"""
부상(#114 가)을 검증한다.

보는 것은 다섯이다.
  - 규칙의 모양: 부상, 부상 표, 표를 굴리는 때, 노려 치기의 검사. 템플릿(srd5)의 값.
  - 계산: 언제 표를 굴리는지, 무엇이 나오는지, 입은 부상이 판정에 무엇을 하는지(app/engine/injury.py).
  - 테이블: 큰 타격이나 쓰러짐에 부상이 생기고, 판정에 효과가 걸리고, 짧은 것은 풀린다. 응답과 이벤트.
  - NPC 도 같다. 죽은 인물에게는 굴리지 않는다.
  - 서술: 입은 부상과 사실, 새 부상, 판정에 준 영향이 들어간다.
주사위는 정해진 눈을 내는 것으로 바꿔 꽂는다. 판정의 눈 → 양의 눈 → 부상 표의 눈 순서다.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.scenarios.snapshot import INJURY_FIELDS, UPGRADES, read_snapshot, upgrade_from_13
from app.engine.check import find_difficulty, resolve_hindered
from app.engine.dice import ScriptedDice
from app.engine.health import Change, ChangeKind
from app.engine.injury import (
    Hindrance,
    Trigger,
    blocks_actions,
    ends_after,
    find_injury,
    hindrance_of,
    roll_table,
    row_injury,
    trigger_of,
)
from app.engine.ruleset import Ruleset
from app.engine.templates import SRD5
from app.rounds import prompt
from app.rounds.narrator import InjuryNote
from app.tables.models import TableInjury
from tests.signing import SigningKey
from tests.test_npc_actions import (
    FAIL,
    NO_INJURY,
    PASS,
    PUNCH,
    RecordingNarrator,
    bearer,
    declare,
    events_of,
    load_dice,
    npc_effect,
    people,
    punch,
    send,
    start_table,
    table_url,
)
from tests.test_versions_api import FORMAT_1

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')

JUMP = '달리는 리무진에서 뛰어내린다.'
LIFT = '쓰러진 바이크를 들어 올린다.'
REST = '숨을 고른다.'

# 부상 표(d20)의 눈
BROKEN_ARM = 17
STUNNED = 11
LOST_EYE = 20


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다(모든 능력치 10, 최대 HP 10)."""
    return bearer(signing_key, ME)


def jump(risk: str = 'heavy') -> dict:
    """민첩으로 보통에 도전한다. 실패하면 다친다."""
    return {'kind': 'check', 'ability': 'dex', 'difficulty': 'medium', 'risk': risk}


def lift() -> dict:
    """근력으로 보통에 도전한다. 팔 골절이면 불리하다."""
    return {'kind': 'check', 'ability': 'str', 'difficulty': 'medium'}


def rules(**changes) -> dict:
    """SRD5 템플릿의 문서에서 몇 칸만 바꾼 것."""
    return {**SRD5.model_dump(mode='json'), **changes}


def injury(**fields) -> dict:
    """짧은 부상 하나의 문서. 칸을 바꿔 틀린 부상을 만들어 본다."""
    return {'key': 'dizzy', 'name': '어지러움', 'fact': '머리가 핑 돈다.', 'healing': 'rounds', 'rounds': 1, **fields}


async def my_sheet(client: AsyncClient, headers: dict[str, str], table: dict) -> dict:
    response = await client.get(table_url(table), headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()['members'][0]['sheet']


async def injury_rows(session: AsyncSession) -> list[TableInjury]:
    """DB 에 적힌 부상들. 생긴 순서다."""
    query = select(TableInjury).order_by(TableInjury.created_at).execution_options(populate_existing=True)
    return list(await session.scalars(query))


# --- 규칙의 모양 ---


def test_the_template_has_injuries_a_table_and_triggers():
    keys = [injury.key for injury in SRD5.injuries]

    assert {'stunned', 'poisoned', 'blinded', 'deafened'} <= set(keys)
    assert {'broken_arm', 'leg_wound', 'lost_left_hand', 'lost_right_hand', 'lost_eye'} <= set(keys)
    assert (SRD5.injury_table.sides, SRD5.injury_triggers.big_hit_percent, SRD5.injury_triggers.downed) == (
        20,
        50,
        True,
    )
    assert (SRD5.called_shot.mode, SRD5.called_shot.amount) == ('target_plus', 5)


def test_the_template_table_never_takes_a_hand_and_mostly_leaves_you_whole():
    faces = [row_injury(SRD5.injury_table, face) for face in range(1, 21)]

    # 손을 잃는 것은 노려 쳐야만 생긴다. 절반은 부상이 없다
    assert not {'lost_left_hand', 'lost_right_hand'} & set(faces)
    assert faces.count(None) == 10


def test_healing_injuries_leave_aftermath_from_their_own_table():
    arm = find_injury(SRD5, 'broken_arm')

    assert (arm.healing, arm.rounds) == ('heals', 30)
    assert row_injury(arm.aftermath, 1) == 'crooked_arm'
    assert row_injury(arm.aftermath, 20) is None


@pytest.mark.parametrize(
    'changes',
    [
        # 표가 눈을 빠뜨리거나, 겹치거나, 주사위를 넘는다
        {'injury_table': {'sides': 6, 'rows': [{'low': 1, 'high': 3, 'injury': None}]}},
        {
            'injury_table': {
                'sides': 6,
                'rows': [{'low': 1, 'high': 4, 'injury': None}, {'low': 4, 'high': 6, 'injury': None}],
            }
        },
        {'injury_table': {'sides': 6, 'rows': [{'low': 1, 'high': 8, 'injury': None}]}},
        # 표에 없는 부상
        {'injury_table': {'sides': 2, 'rows': [{'low': 1, 'high': 2, 'injury': 'ghost'}]}},
        # 같은 부상이 둘
        {'injuries': [injury(), injury()], 'injury_table': None, 'called_shot': None},
        # 효과가 모르는 능력을 가리킨다
        {'injuries': [injury(effects=[{'kind': 'disadvantage', 'abilities': ['luck']}])]},
        # 보정 깎기에 크기가 없거나, 불리함에 크기가 있거나, 행동 불가에 능력이 있다
        {'injuries': [injury(effects=[{'kind': 'penalty', 'abilities': ['str']}])]},
        {'injuries': [injury(effects=[{'kind': 'disadvantage', 'amount': 2}])]},
        {'injuries': [injury(effects=[{'kind': 'no_actions', 'abilities': ['str']}])]},
        # 결손이 아닌데 라운드가 없거나, 결손인데 라운드가 있다
        {'injuries': [injury(rounds=None)]},
        {'injuries': [injury(healing='permanent')]},
        # 후유증 표는 오래 가는 부상에만
        {'injuries': [injury(aftermath={'sides': 2, 'rows': [{'low': 1, 'high': 2, 'injury': None}]})]},
        # 표를 굴리게 켰는데 표가 없다
        {'injury_table': None},
        # 노려 치기를 켰는데 어려움을 정하는 법이 없다
        {'called_shot': None},
        # 목표값을 올리는 방식인데 크기가 없다. 불리함인데 크기가 있다
        {'called_shot': {'mode': 'target_plus'}},
        {'called_shot': {'mode': 'disadvantage', 'amount': 3}},
    ],
)
def test_rejects_rules_that_make_no_sense(changes: dict):
    with pytest.raises(ValidationError):
        Ruleset.model_validate(rules(**changes))


def test_triggers_can_be_turned_off_one_by_one():
    quiet = Ruleset.model_validate(
        rules(
            injury_table=None,
            injury_triggers={'big_hit_percent': None, 'downed': False, 'called_shot': False},
            called_shot=None,
        )
    )

    assert quiet.injury_table is None


def test_called_shot_needs_something_to_aim_at():
    no_aim = [injury.model_dump(mode='json') | {'aimable': False} for injury in SRD5.injuries]

    with pytest.raises(ValidationError):
        Ruleset.model_validate(rules(injuries=no_aim))


# --- 표를 굴리는 때와 나오는 것 ---


def hit(amount: int, before: int = 10) -> Change:
    return Change(kind=ChangeKind.DAMAGE, rolls=(amount,), amount=amount, before=before, after=max(0, before - amount))


@pytest.mark.parametrize(
    ('change', 'dead', 'expected'),
    [
        # 최대 HP(10)의 절반 이상이면 큰 타격이다
        (hit(5), False, Trigger.BIG_HIT),
        (hit(4), False, None),
        # 작은 피해라도 쓰러지면 굴린다
        (hit(3, before=3), False, Trigger.DOWNED),
        # 이미 쓰러져 있으면 쓰러짐이 아니다. 작으면 굴리지 않는다
        (hit(3, before=0), False, None),
        (hit(6, before=0), False, Trigger.BIG_HIT),
        # 쓰러짐과 큰 타격이 함께여도 한 번이다. 쓰러짐으로 적는다
        (hit(16), False, Trigger.DOWNED),
        # 죽은 대상에게는 굴리지 않는다
        (hit(16), True, None),
        # 회복은 굴리지 않는다
        (Change(kind=ChangeKind.RECOVERY, rolls=(8,), amount=8, before=1, after=9), False, None),
    ],
)
def test_when_the_table_is_rolled(change: Change, dead: bool, expected: Trigger | None):
    assert trigger_of(SRD5, change, 10, dead) == expected


def test_turned_off_triggers_roll_nothing():
    quiet = SRD5.model_copy(
        update={'injury_triggers': SRD5.injury_triggers.model_copy(update={'big_hit_percent': None, 'downed': False})}
    )

    assert trigger_of(quiet, hit(16), 10, False) is None


def test_the_table_gives_the_row_of_the_roll():
    rolled = roll_table(SRD5.injury_table, Trigger.BIG_HIT, ScriptedDice([BROKEN_ARM]))

    assert (rolled.trigger, rolled.roll, rolled.injury) == (Trigger.BIG_HIT, 17, 'broken_arm')
    assert roll_table(SRD5.injury_table, Trigger.DOWNED, ScriptedDice([7])).injury is None


# --- 입은 부상이 판정에 주는 것 ---


def injuries(*keys: str) -> list:
    return [find_injury(SRD5, key) for key in keys]


def test_effects_touch_only_their_abilities():
    arm = hindrance_of(injuries('broken_arm'), 'str')

    assert arm == Hindrance(penalty=0, disadvantage=True, injuries=('broken_arm',))
    assert not hindrance_of(injuries('broken_arm'), 'dex').any


def test_penalties_add_up_and_an_effect_without_abilities_touches_all():
    hindrance = hindrance_of(injuries('crooked_arm', 'poisoned', 'deep_scar'), 'str')

    # 굽은 팔(근력 -1)과 중독(모든 능력 불리). 흉터는 효과가 없다
    assert hindrance == Hindrance(penalty=1, disadvantage=True, injuries=('crooked_arm', 'poisoned'))


def test_only_some_injuries_stop_actions():
    assert blocks_actions(injuries('stunned'))
    assert not blocks_actions(injuries('broken_arm', 'poisoned'))
    # 행동 불가는 판정에 주는 것이 아니다
    assert not hindrance_of(injuries('stunned'), 'str').any


def test_only_short_injuries_have_an_end():
    assert ends_after(find_injury(SRD5, 'stunned'), 3) == 4
    assert ends_after(find_injury(SRD5, 'poisoned'), 3) == 6
    assert ends_after(find_injury(SRD5, 'broken_arm'), 3) is None
    assert ends_after(find_injury(SRD5, 'lost_eye'), 3) is None


def test_disadvantage_takes_the_lower_roll_and_a_penalty_cuts_the_modifier():
    medium = find_difficulty(SRD5, 'medium')
    hindrance = Hindrance(penalty=2, disadvantage=True, injuries=('x',))

    hindered = resolve_hindered(SRD5, 14, medium, ScriptedDice([18, 9]), hindrance)

    # 보정 +2 에서 2 를 깎아 0. 낮은 눈 9
    assert (hindered.rolls, hindered.check.roll, hindered.check.modifier, hindered.check.total) == ((18, 9), 9, 0, 9)
    assert hindered.check.success is False


# --- 판의 형식 ---


def make_format_13() -> dict:
    """부상이 없던 때의 판. 형식 1 을 13 까지 올리고 규칙에서 부상의 칸들을 뺀다."""
    document = FORMAT_1
    while document['format'] < 13:
        document = UPGRADES[document['format']](document)
    rules = {key: value for key, value in document['rulebook']['rules'].items() if key not in INJURY_FIELDS}
    return {**document, 'rulebook': {**document['rulebook'], 'rules': rules}}


def test_an_old_version_is_read_with_the_template_injuries():
    old = read_snapshot(make_format_13())

    # 부상이 없던 판은 그때의 규칙(SRD5)의 부상으로 읽는다
    assert old.rulebook.rules.injuries == SRD5.injuries
    assert old.rulebook.rules.injury_triggers == SRD5.injury_triggers


def test_upgrades_a_format_13_document():
    current = upgrade_from_13({'format': 13, 'rulebook': {'id': 'x', 'rules': {'template': 'srd5'}}})

    template = SRD5.model_dump(mode='json')
    assert current['format'] == 14
    assert {field: current['rulebook']['rules'][field] for field in INJURY_FIELDS} == {
        field: template[field] for field in INJURY_FIELDS
    }


# --- 테이블: 캐릭터가 다친다 ---


async def test_a_big_hit_can_break_an_arm(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, BROKEN_ARM])

    closing = await declare(client, me, world['table'], JUMP, jump())

    effect = closing['declarations'][0]['outcome']['effect']
    assert effect['injury_roll'] == {'trigger': 'big_hit', 'roll': 17, 'injury': 'broken_arm', 'ends_after_round': None}
    assert (await my_sheet(client, me, world['table']))['injuries'] == [
        {'injury': 'broken_arm', 'round': 1, 'ends_after_round': None}
    ]
    (row,) = await injury_rows(session)
    assert (row.injury, row.source, row.round_number, row.npc_entry_id) == ('broken_arm', 'injury_table', 1, None)


async def test_the_narrator_hears_of_the_new_injury(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    load_dice(app, [FAIL, 3, 4, BROKEN_ARM])

    await declare(client, me, world['table'], JUMP, jump())
    await narrated()

    (request,) = narrator.requests
    assert request.moves[0].verdict.impact.injury == '팔 골절'
    text_ = '\n'.join(message.content for message in prompt.build_messages(request))
    assert '새 부상: 팔 골절' in text_
    assert '[입은 부상: 팔 골절(한쪽 팔이 부러져 제대로 쓰지 못한다.)]' in text_


async def test_a_lucky_roll_leaves_no_injury(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, NO_INJURY])

    closing = await declare(client, me, world['table'], JUMP, jump())

    # 굴린 것은 남는다. 큰 타격을 받고도 멀쩡했다
    assert closing['declarations'][0]['outcome']['effect']['injury_roll'] == {
        'trigger': 'big_hit',
        'roll': 1,
        'injury': None,
        'ends_after_round': None,
    }
    assert (await my_sheet(client, me, world['table']))['injuries'] == []
    assert await events_of(client, me, world['table'], 'injury_gained') == []


async def test_a_small_hit_rolls_nothing(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    dice = load_dice(app, [FAIL, 4])

    closing = await declare(client, me, world['table'], JUMP, jump('light'))

    assert closing['declarations'][0]['outcome']['effect']['injury_roll'] is None
    assert dice.remaining == 0


async def test_a_broken_arm_makes_lifting_harder(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, BROKEN_ARM])
    await declare(client, me, world['table'], JUMP, jump())
    await narrated()

    # 근력 판정이 불리하다. 두 번 굴려 낮은 눈을 쓴다
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    load_dice(app, [18, 6])
    closing = await declare(client, me, world['table'], LIFT, lift())
    await narrated()

    outcome = closing['declarations'][0]['outcome']
    assert (outcome['roll'], outcome['success']) == (6, False)
    assert outcome['hindrance'] == {'injuries': ['broken_arm'], 'penalty': 0, 'disadvantage': True, 'rolls': [18, 6]}
    (rolled,) = [
        event for event in await events_of(client, me, world['table'], 'check_rolled') if event['payload']['round'] == 2
    ]
    assert rolled['payload']['hindrance'] == outcome['hindrance']
    (request,) = narrator.requests
    move = request.moves[0]
    assert move.verdict.hindrances == ['팔 골절']
    assert move.injuries == [InjuryNote(name='팔 골절', fact='한쪽 팔이 부러져 제대로 쓰지 못한다.')]


async def test_an_untouched_ability_is_not_hindered(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, BROKEN_ARM])
    await declare(client, me, world['table'], JUMP, jump())
    await narrated()

    dice = load_dice(app, [18])
    closing = await declare(client, me, world['table'], JUMP, {'kind': 'check', 'ability': 'dex'})

    assert closing['declarations'][0]['outcome']['hindrance'] is None
    assert dice.remaining == 0


async def test_the_injury_is_recorded_after_the_hit_that_caused_it(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, BROKEN_ARM])

    await declare(client, me, world['table'], JUMP, jump())

    (changed,) = await events_of(client, me, world['table'], 'hp_changed')
    (gained,) = await events_of(client, me, world['table'], 'injury_gained')
    assert gained['payload'] == {
        'round': 1,
        'user_id': str(ME),
        'character_name': '엘프',
        'injury': 'broken_arm',
        'source': 'injury_table',
        'ends_after_round': None,
    }
    assert gained['caused_by_sequence'] == changed['sequence']
    assert gained['actor_id'] is None


async def test_a_stunned_character_cannot_act_and_then_comes_to(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await start_table(client, me)
    table = world['table']
    load_dice(app, [FAIL, 3, 4, STUNNED])
    await declare(client, me, table, JUMP, jump())
    await narrated()
    assert (await my_sheet(client, me, table))['injuries'] == [{'injury': 'stunned', 'round': 1, 'ends_after_round': 2}]

    # 2 라운드: 행동을 붙이지 못한다. 글은 낼 수 있다
    refused = await send(client, me, table, LIFT, lift())
    assert refused.status_code == status.HTTP_409_CONFLICT
    assert refused.json()['reason'] == 'character_incapacitated'
    await declare(client, me, table, REST)
    await narrated()

    # 2 라운드가 닫힐 때 풀렸다
    assert (await my_sheet(client, me, table))['injuries'] == []
    (ended,) = await events_of(client, me, table, 'injury_ended')
    assert ended['payload'] == {
        'round': 2,
        'user_id': str(ME),
        'character_name': '엘프',
        'injury': 'stunned',
        'reason': 'expired',
    }
    load_dice(app, [PASS])
    assert (await send(client, me, table, LIFT, lift())).status_code == status.HTTP_200_OK


async def test_a_lasting_injury_does_not_end_by_itself_yet(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated, session: AsyncSession
):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, LOST_EYE])
    await declare(client, me, world['table'], JUMP, jump())
    await narrated()
    for _ in range(3):
        await declare(client, me, world['table'], REST)
        await narrated()

    (row,) = await injury_rows(session)
    assert (row.injury, row.ended_at) == ('lost_eye', None)


# --- NPC 도 다친다 ---


async def test_an_npc_knocked_down_can_lose_an_eye(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    load_dice(app, [PASS, 8, 8, LOST_EYE])

    closing = await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'heavy'))
    await narrated()

    assert npc_effect(closing)['injury_roll'] == {
        'trigger': 'downed',
        'roll': 20,
        'injury': 'lost_eye',
        'ends_after_round': None,
    }
    (request,) = narrator.requests
    (lady,) = request.people
    assert lady.injuries == [InjuryNote(name='한쪽 눈 잃음', fact='한쪽 눈을 잃어 거리를 잘 가늠하지 못한다.')]
    assert request.moves[0].verdict.npc_impact.injury == '한쪽 눈 잃음'
    (gained,) = await events_of(client, me, world['table'], 'injury_gained')
    assert (gained['payload']['entry_id'], gained['payload']['name']) == (world['lady']['id'], '악역영애')
    # 다음 장면(서술자가 악역영애를 다시 부른다)의 인물 목록에도 부상이 보인다
    assert (await people(client, me, world['table']))['people'][0]['injuries'] == ['lost_eye']


async def test_a_dead_npc_gets_no_injury_roll(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    dice = load_dice(app, [PASS, 8, 8])

    closing = await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'heavy', lethal=True))

    assert npc_effect(closing)['injury_roll'] is None
    assert dice.remaining == 0


async def test_an_npc_out_of_the_scene_comes_to_quietly(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated, session: AsyncSession
):
    world = await start_table(client, me)

    class Elsewhere:
        """악역영애를 부르지 않는 서술자. 다음 장면에 그 인물이 없다."""

        async def narrate(self, request, preview=None) -> str:
            return '리무진이 멀어진다. 엘프 혼자 남았다.'

    app.state.narrator = Elsewhere()
    # 보통(1d8)에서 6. 최대 HP(10)의 절반을 넘는 큰 타격이라 표를 굴린다
    load_dice(app, [PASS, 6, STUNNED])
    await declare(client, me, world['table'], PUNCH, punch(world['lady']['id'], 'moderate'))
    await narrated()
    await declare(client, me, world['table'], REST)
    await narrated()

    # 기절은 풀렸다. 장면에 없는 인물을 부를 이름이 없어서 이벤트에는 적지 않는다
    (row,) = await injury_rows(session)
    assert (row.injury, row.ended_at is not None) == ('stunned', True)
    assert await events_of(client, me, world['table'], 'injury_ended') == []


async def test_injuries_go_with_the_table(client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, BROKEN_ARM])
    await declare(client, me, world['table'], JUMP, jump())

    await session.execute(text('DELETE FROM game_tables WHERE id = :id'), {'id': world['table']['id']})
    await session.commit()

    assert await session.scalar(text('SELECT count(*) FROM table_injuries')) == 0


async def test_an_injury_belongs_to_exactly_one(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    load_dice(app, [FAIL, 3, 4, BROKEN_ARM])
    await declare(client, me, world['table'], JUMP, jump())
    (row,) = await injury_rows(session)

    row.npc_entry_id = uuid.UUID(world['lady']['id'])

    with pytest.raises(Exception, match='one_holder'):
        await session.commit()


# --- 서술 ---


def test_the_rules_tell_the_narrator_to_keep_injuries():
    assert '부상' in prompt.GM_RULES
    assert '못 하는 일을 하게 쓰지 마라' in prompt.GM_RULES


def test_a_person_line_carries_the_injuries():
    from app.rounds.narrator import PersonState

    line = prompt.person_line(PersonState('악역영애', '크게 다침', [InjuryNote('오른손 잃음', '오른손을 쓸 수 없다.')]))

    assert line == '- 악역영애: 크게 다침. 부상: 오른손 잃음(오른손을 쓸 수 없다.)'
