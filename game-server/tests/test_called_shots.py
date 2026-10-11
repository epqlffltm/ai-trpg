# game-server/tests/test_called_shots.py

"""
노려 치기(#114 나)를 검증한다.

타격(harm)에 노릴 부상(aim)을 적으면 판정이 어려워지고, 성공하면 그 부상이 확정으로 생긴다.
그 타격에서는 부상 표를 굴리지 않는다.
srd5 템플릿은 목표값을 5 올린다. 보통(15)이 20 이 된다. 불리함 방식은 테이블의 판을 고쳐서 본다.

보는 것은 넷이다.
  - 계산: 노릴 수 있는지, 얼마나 어려워지는지(app/engine/action.py).
  - 받을 때의 검사: 노릴 수 없는 부상, 규칙이 노려 치기를 끈 테이블, 이미 입은 부상.
  - 닫을 때: 성공하면 피해와 그 부상, 실패하면 빗나감. 죽이면 부상이 없다. 같은 라운드에 둘이 같은 것을 노리면 하나만.
  - 기록과 서술: 판정의 결과, 이벤트, 서술자에게 주는 것.
"""

import uuid

import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.action import ActionKind, CheckAction, attempt_hindered, called_shot_terms, can_aim, find_fault
from app.engine.check import find_difficulty, resolve_hindered
from app.engine.dice import ScriptedDice
from app.engine.injury import NO_HINDRANCE, Hindrance
from app.engine.ruleset import CalledShot, CalledShotMode
from app.engine.templates import SRD5
from app.rounds import prompt
from tests.signing import SigningKey
from tests.test_npc_actions import (
    PASS,
    PUNCH,
    RecordingNarrator,
    bearer,
    declare,
    events_of,
    load_dice,
    npc_effect,
    people,
    send,
    start_table,
)

pytestmark = pytest.mark.usefixtures('clean_tables')

ME = uuid.UUID('11111111-2222-4333-8444-555555555555')
FRIEND = uuid.UUID('22222222-2222-4333-8444-555555555555')
NPC = uuid.UUID('33333333-2222-4333-8444-555555555555')


@pytest.fixture
def me(signing_key: SigningKey) -> dict[str, str]:
    """내 토큰이 실린 머리말. 방장이다. 캐릭터는 '엘프'다(모든 능력치 10, 보정 0)."""
    return bearer(signing_key, ME)


@pytest.fixture
def friend(signing_key: SigningKey) -> dict[str, str]:
    """두 번째로 앉는 사람. 캐릭터는 '드워프 기사'다."""
    return bearer(signing_key, FRIEND)


def aimed(npc: str, aim: str = 'lost_eye', harm: str = 'moderate', lethal: bool = False) -> dict:
    """민첩으로 보통에 도전해 그 NPC 의 부상을 노린다. 성공하면 다치고 그 부상을 입는다."""
    return {
        'kind': 'check',
        'ability': 'dex',
        'difficulty': 'medium',
        'harm': harm,
        'npc': npc,
        'lethal': lethal,
        'aim': aim,
    }


def outcome(round_: dict, index: int = 0) -> dict:
    return round_['declarations'][index]['outcome']


async def set_rules(session: AsyncSession, table: dict, path: str, value: str) -> None:
    """테이블의 판(content)에 굳은 규칙의 한 칸을 고친다. 템플릿에 없는 규칙으로 돌려 볼 때 쓴다."""
    query = text(
        f"UPDATE game_tables SET content = jsonb_set(content, '{{rulebook,rules,{path}}}', CAST(:value AS JSONB)) "
        'WHERE id = :id'
    )
    await session.execute(query, {'value': value, 'id': table['id']})
    await session.commit()


# --- 계산 ---


def shot(**fields) -> CheckAction:
    return CheckAction(kind=ActionKind.CHECK, ability='dex', difficulty='medium', harm='light', npc=NPC, **fields)


def test_an_aim_goes_with_a_hit():
    assert shot(aim='lost_eye').aim == 'lost_eye'
    with pytest.raises(ValidationError):
        CheckAction(kind=ActionKind.CHECK, ability='dex', aim='lost_eye')
    with pytest.raises(ValidationError):
        CheckAction(kind=ActionKind.CHECK, ability='dex', recover='light', npc=NPC, aim='lost_eye')


@pytest.mark.parametrize(
    ('aim', 'fault'), [('lost_eye', None), ('broken_arm', None), ('stunned', 'aim'), ('nose', 'aim')]
)
def test_only_aimable_injuries_can_be_aimed_at(aim: str, fault: str | None):
    assert find_fault(SRD5, shot(aim=aim)) == fault


def test_nothing_can_be_aimed_at_when_the_rules_turn_it_off():
    off = SRD5.model_copy(update={'injury_triggers': SRD5.injury_triggers.model_copy(update={'called_shot': False})})

    assert not can_aim(off, 'lost_eye')


def test_the_rules_decide_how_much_harder_it_gets():
    disadvantage = SRD5.model_copy(update={'called_shot': CalledShot(mode=CalledShotMode.DISADVANTAGE)})

    assert called_shot_terms(SRD5, shot(aim='lost_eye')) == (5, False)
    assert called_shot_terms(disadvantage, shot(aim='lost_eye')) == (0, True)
    assert called_shot_terms(SRD5, shot()) == (0, False)


def test_aiming_raises_the_target():
    hindered = attempt_hindered(SRD5, shot(aim='lost_eye'), {'dex': 10}, ScriptedDice([19]), NO_HINDRANCE)

    # 보통(15)에서 5 가 올라 20. 노리지 않았으면 19 로 성공이다
    assert (hindered.check.target, hindered.check.success) == (20, False)


def test_aiming_by_disadvantage_takes_the_lower_roll_but_is_not_an_injury():
    disadvantage = SRD5.model_copy(update={'called_shot': CalledShot(mode=CalledShotMode.DISADVANTAGE)})

    hindered = attempt_hindered(disadvantage, shot(aim='lost_eye'), {'dex': 10}, ScriptedDice([18, 4]), NO_HINDRANCE)

    assert (hindered.rolls, hindered.check.roll, hindered.check.target) == ((18, 4), 4, 15)
    # 부상 때문이 아니다. 부상의 영향에는 섞지 않는다
    assert not hindered.hindrance.any


def test_two_reasons_for_disadvantage_still_roll_twice():
    hindrance = Hindrance(disadvantage=True, injuries=('broken_arm',))

    hindered = resolve_hindered(
        SRD5, 10, find_difficulty(SRD5, 'medium'), ScriptedDice([18, 4]), hindrance, forced_disadvantage=True
    )

    assert hindered.rolls == (18, 4)


# --- 받을 때의 검사 ---


async def test_an_injury_that_cannot_be_aimed_at_is_refused(client: AsyncClient, me: dict[str, str]):
    world = await start_table(client, me)

    response = await send(client, me, world['table'], PUNCH, aimed(world['lady']['id'], aim='stunned'))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {'detail': 'action.aim 가 이 테이블의 규칙에 없습니다.'}


async def test_a_table_whose_rules_turn_it_off_refuses_aiming(
    client: AsyncClient, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await set_rules(session, world['table'], 'injury_triggers,called_shot', 'false')

    response = await send(client, me, world['table'], PUNCH, aimed(world['lady']['id']))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_an_injury_already_taken_cannot_be_aimed_at_again(
    client: AsyncClient, app: FastAPI, me: dict[str, str], narrated
):
    world = await start_table(client, me)
    load_dice(app, [PASS, 3])
    await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id']))
    await narrated()

    again = await send(client, me, world['table'], PUNCH, aimed(world['lady']['id']))

    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()['reason'] == 'already_injured'
    # 다른 부상은 노릴 수 있다
    load_dice(app, [PASS, 3])
    other = await send(client, me, world['table'], PUNCH, aimed(world['lady']['id'], aim='lost_right_hand'))
    assert other.status_code == status.HTTP_200_OK


# --- 닫을 때 ---


async def test_a_hit_that_lands_takes_the_eye_without_rolling_the_table(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    world = await start_table(client, me)
    # 5 는 큰 타격(최대 HP 10 의 절반)이지만 노려 친 타격이라 표를 굴리지 않는다
    dice = load_dice(app, [PASS, 5])

    closing = await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id']))

    result = outcome(closing)
    assert (result['target'], result['success']) == (20, True)
    assert result['called_shot'] == {'aim': 'lost_eye', 'mode': 'target_plus', 'amount': 5}
    assert npc_effect(closing)['amount'] == 5
    assert npc_effect(closing)['injury_roll'] == {
        'trigger': 'called_shot',
        'roll': None,
        'injury': 'lost_eye',
        'ends_after_round': None,
    }
    assert dice.remaining == 0
    assert (await people(client, me, world['table']))['people'][0]['injuries'] == ['lost_eye']


async def test_a_miss_does_nothing_even_where_a_plain_hit_would_land(
    client: AsyncClient, app: FastAPI, me: dict[str, str]
):
    world = await start_table(client, me)
    dice = load_dice(app, [19, 5])

    closing = await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id']))

    # 19 는 보통(15)이면 성공이지만 노려 쳐서 20 이 필요했다
    assert (outcome(closing)['target'], outcome(closing)['success']) == (20, False)
    assert npc_effect(closing) is None
    assert dice.remaining == 1
    assert (await people(client, me, world['table']))['people'][0]['injuries'] == []


async def test_a_hit_that_downs_still_takes_the_aimed_injury(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    dice = load_dice(app, [PASS, 8, 8])

    closing = await declare(
        client, me, world['table'], PUNCH, aimed(world['lady']['id'], aim='broken_arm', harm='heavy')
    )

    assert npc_effect(closing)['status'] == 'downed'
    assert npc_effect(closing)['injury_roll']['injury'] == 'broken_arm'
    assert dice.remaining == 0


async def test_a_hit_that_kills_leaves_no_injury(client: AsyncClient, app: FastAPI, me: dict[str, str]):
    world = await start_table(client, me)
    load_dice(app, [PASS, 8, 8])

    closing = await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id'], harm='heavy', lethal=True))

    assert npc_effect(closing)['status'] == 'dead'
    assert npc_effect(closing)['injury_roll'] is None


async def test_two_aiming_at_the_same_eye_take_it_once(
    client: AsyncClient, app: FastAPI, me: dict[str, str], friend: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me, friend)
    load_dice(app, [PASS, 1, PASS, 1])

    await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id']))
    closing = await declare(client, friend, world['table'], PUNCH, aimed(world['lady']['id']))

    rolls = [outcome(closing, index)['npc_effect']['injury_roll']['injury'] for index in range(2)]
    # 뒷사람의 타격도 맞았지만 이미 잃은 눈을 또 잃지는 않는다
    assert rolls == ['lost_eye', None]
    assert await session.scalar(text('SELECT count(*) FROM table_injuries')) == 1


async def test_aiming_by_disadvantage_rolls_twice(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    await set_rules(session, world['table'], 'called_shot', '{"mode": "disadvantage", "amount": 0}')
    load_dice(app, [PASS, 6])

    closing = await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id']))

    result = outcome(closing)
    # 낮은 눈 6 을 쓴다. 목표값은 그대로 15 다. 부상의 영향은 없다
    assert (result['roll'], result['target'], result['success']) == (6, 15, False)
    assert result['called_shot'] == {'aim': 'lost_eye', 'mode': 'disadvantage', 'amount': 0}
    assert result['hindrance'] is None


# --- 기록과 서술 ---


async def test_the_aimed_injury_is_recorded_as_a_called_shot(
    client: AsyncClient, app: FastAPI, me: dict[str, str], session: AsyncSession
):
    world = await start_table(client, me)
    load_dice(app, [PASS, 3])

    await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id']))

    (rolled,) = await events_of(client, me, world['table'], 'check_rolled')
    (gained,) = await events_of(client, me, world['table'], 'injury_gained')
    assert rolled['payload']['called_shot'] == {'aim': 'lost_eye', 'mode': 'target_plus', 'amount': 5}
    assert (gained['payload']['injury'], gained['payload']['source']) == ('lost_eye', 'called_shot')
    assert await session.scalar(text('SELECT source FROM table_injuries')) == 'called_shot'


async def test_the_narrator_hears_what_was_aimed_at(client: AsyncClient, app: FastAPI, me: dict[str, str], narrated):
    world = await start_table(client, me)
    narrator = RecordingNarrator()
    app.state.narrator = narrator
    load_dice(app, [PASS, 3])

    await declare(client, me, world['table'], PUNCH, aimed(world['lady']['id']))
    await narrated()

    (request,) = narrator.requests
    verdict = request.moves[0].verdict
    assert (verdict.aimed, verdict.target, verdict.npc_impact.injury) == ('한쪽 눈 잃음', 20, '한쪽 눈 잃음')
    text_ = '\n'.join(message.content for message in prompt.build_messages(request))
    assert '목표 20. 노려 치기: 한쪽 눈 잃음' in text_
    assert '새 부상: 한쪽 눈 잃음' in text_
