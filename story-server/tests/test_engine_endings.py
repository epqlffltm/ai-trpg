# story-server/tests/test_engine_endings.py

"""
엔딩의 판정(app/engine/endings.py)과 고백(app/engine/confession.py)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 판정: 그 시작(종류와 대상)의 엔딩을 판의 차례로 맞춰 조건이 맞는 첫 엔딩을 고른다. 다른 시작의 엔딩은 보지 않는다.
    맞는 것이 없거나 이미 엔딩을 봤으면 None 이다. 엔딩을 보면 상태에 적고 기다리던 선택지가 사라진다
  - 기한: 지나야 판정한다. 기한이 없으면 판정하지 않는다. 이벤트: 그 이벤트의 엔딩을 판정한다
  - 고백의 성공: 호감도가 그 단계 이상이고 조건이 맞아야 한다. 성공이면 고백 성공의 엔딩을 본다
  - 실패하면 계속(호감도를 내리고 0 아래로는 가지 않는다, 정한 날 동안 다시 못 한다) 또는 끝(고백 실패의 엔딩)이다
  - 받지 않는 고백: 엔딩을 봤다, 장면에 없다, 고백할 수 없는 인물, 다시 할 시각이 아직이다
  - 판의 고백과 엔딩의 칸을 읽는다
"""

from dataclasses import replace
from types import MappingProxyType

import pytest

from app.engine.confession import ConfessionRefused, Refusal, confess
from app.engine.endings import deadline_ending, event_ending, pick_ending, reach_ending
from app.engine.state import StoryState, start_state
from app.engine.world import AfterEnding, ConfessionFailure, EndingTrigger
from tests.engine_worlds import clock, condition, confession, ending, member, world

MINA = member('mina', 'home', start=10, confession=confession('친함', condition('event_seen', 'meet')))
YUNA = member('yuna', 'home', start=50, confession=confession('친함', on_fail='end'))
SORA = member('sora', 'home')
ENDINGS = [
    ending('mina-lover', 'confess_success', 'mina', condition('affection_at_least', 'mina', '연인')),
    ending('mina-friend', 'confess_success', 'mina'),
    ending('yuna-sad', 'confess_fail', 'yuna'),
    ending('yuna-happy', 'confess_success', 'yuna'),
    ending('solo', 'deadline'),
    ending('secret', 'event', 'door'),
]
WORLD = world([MINA, YUNA, SORA], endings=ENDINGS, deadline_days=30, after_ending='epilogue')
START = start_state(WORLD)
SCENE = ('mina', 'yuna', 'sora')


def at(**changes) -> StoryState:
    if 'affection' in changes:
        changes['affection'] = MappingProxyType({**START.affection, **changes['affection']})
    return replace(START, **changes)


# --- 판정 ---


def test_the_first_matching_ending_of_that_trigger_is_picked():
    friend = pick_ending(WORLD, at(affection={'mina': 40}), EndingTrigger.CONFESS_SUCCESS, 'mina')
    lover = pick_ending(WORLD, at(affection={'mina': 80}), EndingTrigger.CONFESS_SUCCESS, 'mina')

    assert (friend.id, lover.id) == ('mina-friend', 'mina-lover')


def test_other_triggers_are_not_looked_at():
    assert pick_ending(WORLD, START, EndingTrigger.CONFESS_FAIL, 'mina') is None
    assert pick_ending(WORLD, START, EndingTrigger.EVENT, 'window') is None


def test_after_an_ending_nothing_is_picked():
    over = reach_ending(at(choosing='offer'), WORLD.endings[1])

    assert (over.ending, over.choosing) == ('mina-friend', None)
    assert pick_ending(WORLD, over, EndingTrigger.DEADLINE) is None


def test_the_deadline_ending_comes_after_the_deadline():
    assert deadline_ending(WORLD, at(minutes=clock(30, 23))) is None
    assert deadline_ending(WORLD, at(minutes=clock(31, 7))).id == 'solo'
    endless = world([SORA], endings=ENDINGS)
    assert deadline_ending(endless, replace(start_state(endless), minutes=clock(99, 7))) is None


def test_an_event_ending():
    assert event_ending(WORLD, START, 'door').id == 'secret'
    assert event_ending(WORLD, START, 'window') is None


# --- 고백 ---


def test_a_confession_succeeds_with_the_stage_and_the_conditions():
    ready = at(affection={'mina': 40}, seen=frozenset({'meet'}))

    outcome = confess(WORLD, ready, 'mina', SCENE)

    assert (outcome.succeeded, outcome.ending.id, outcome.state.ending) == (True, 'mina-friend', 'mina-friend')


@pytest.mark.parametrize(
    'state',
    [
        at(affection={'mina': 29}, seen=frozenset({'meet'})),  # 단계가 모자라다
        at(affection={'mina': 40}),  # 조건(만남)을 채우지 않았다
    ],
)
def test_without_the_stage_or_the_conditions_it_fails_and_continues(state: StoryState):
    outcome = confess(WORLD, state, 'mina', SCENE)

    assert (outcome.succeeded, outcome.ending, outcome.state.ending) == (False, None, None)
    assert outcome.state.affection['mina'] == state.affection['mina'] - 10
    assert outcome.state.cooldowns['mina'] == state.minutes + clock(2, 0)


def test_a_failed_confession_does_not_go_below_zero():
    outcome = confess(WORLD, at(affection={'mina': 3}), 'mina', SCENE)

    assert outcome.state.affection['mina'] == 0


def test_one_cannot_confess_again_until_the_cooldown_ends():
    failed = confess(WORLD, at(affection={'mina': 40}), 'mina', SCENE).state
    later = replace(failed, minutes=failed.cooldowns['mina'], seen=frozenset({'meet'}))

    with pytest.raises(ConfessionRefused) as refused:
        confess(WORLD, replace(failed, minutes=failed.cooldowns['mina'] - 1), 'mina', SCENE)
    assert refused.value.reason == Refusal.COOLING_DOWN
    assert confess(WORLD, replace(later, affection=MappingProxyType({'mina': 40})), 'mina', SCENE).succeeded


def test_a_failure_that_ends_picks_the_failure_ending():
    outcome = confess(WORLD, at(affection={'yuna': 10}), 'yuna', SCENE)

    assert (outcome.succeeded, outcome.ending.id, outcome.state.ending) == (False, 'yuna-sad', 'yuna-sad')
    assert outcome.state.affection['yuna'] == 10


@pytest.mark.parametrize(
    ('state', 'cast_id', 'scene', 'reason'),
    [
        (at(ending='solo'), 'mina', SCENE, Refusal.OVER),
        (START, 'mina', ('yuna',), Refusal.NOT_IN_SCENE),
        (START, 'sora', SCENE, Refusal.NOT_CONFESSABLE),
        (START, 'nobody', ('nobody',), Refusal.NOT_CONFESSABLE),
    ],
)
def test_refused_confessions(state: StoryState, cast_id: str, scene: tuple, reason: Refusal):
    with pytest.raises(ConfessionRefused) as refused:
        confess(WORLD, state, cast_id, scene)

    assert refused.value.reason == reason


def test_an_unknown_stage_fails():
    odd = world([member('mina', 'home', start=100, confession=confession('원수'))], endings=ENDINGS)

    assert confess(odd, start_state(odd), 'mina', ('mina',)).succeeded is False


def test_without_a_matching_ending_the_story_goes_on():
    bare = world([member('mina', 'home', start=100, confession=confession('친함'))])

    outcome = confess(bare, start_state(bare), 'mina', ('mina',))

    assert (outcome.succeeded, outcome.ending, outcome.state.ending) == (True, None, None)


# --- 판 읽기 ---


def test_the_worlds_confessions_and_endings_are_read():
    yuna = WORLD.member('yuna').confession

    assert (yuna.stage, yuna.on_fail, yuna.fail_drop, yuna.cooldown_days) == ('친함', ConfessionFailure.END, 10, 1)
    assert WORLD.member('sora').confession is None
    assert [item.id for item in WORLD.endings] == [item['id'] for item in ENDINGS]
    assert (WORLD.endings[4].trigger.kind, WORLD.endings[4].trigger.target) == (EndingTrigger.DEADLINE, None)
    assert WORLD.after_ending == AfterEnding.EPILOGUE
    assert world().endings == ()
