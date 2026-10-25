# story-server/tests/test_engine_scene.py

"""
인물의 자리와 장면의 인물(app/engine/scene.py)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 자리: 동행이면 사용자와 같은 곳, 그다음 지금의 시간대와 조건이 맞는 일정의 첫 줄, 그다음 기본 장소.
    아무것도 없으면 어디에도 없다. 조건이 맞지 않는 줄은 건너뛴다
  - 장면: 사용자와 같은 장소의 인물, 동행, 이벤트가 부른 인물. 다른 장소의 인물은 없다
  - 상한(4명): 동행, 이벤트, 일정, 기본 장소의 차례로, 같은 차례는 판의 차례로 고른다. 목록도 그 차례다
"""

from dataclasses import replace

from app.engine.scene import NOWHERE, SCENE_MAX_CAST, Presence, Whereabouts, place_of_character, scene_cast
from app.engine.state import StoryState, start_state
from tests.engine_worlds import clock, condition, line, member, world

# 미나: 기본은 카페, 낮에는 공원, 3일째부터 밤에는 바닷가(조건이 맞지 않으면 밤에도 카페)
MINA = member(
    'mina',
    'cafe',
    [line('day', 'park'), line('night', 'beach', condition('day_at_least', count=3)), line('night', 'bar')],
)
WORLD = world([MINA, member('yuna', 'home'), member('sora')])
START = start_state(WORLD)


def at(**changes) -> StoryState:
    return replace(START, **changes)


def where(cast_id: str, now: StoryState) -> Whereabouts:
    return place_of_character(WORLD.member(cast_id), now, WORLD)


def test_the_home_is_the_default():
    assert where('mina', at()) == Whereabouts('cafe', Presence.HOME)


def test_the_schedule_comes_before_the_home():
    assert where('mina', at(minutes=clock(1, 13))) == Whereabouts('park', Presence.SCHEDULE)


def test_a_line_whose_conditions_fail_is_skipped():
    assert where('mina', at(minutes=clock(2, 20))) == Whereabouts('bar', Presence.SCHEDULE)
    assert where('mina', at(minutes=clock(3, 20))) == Whereabouts('beach', Presence.SCHEDULE)


def test_a_companion_is_where_the_user_is():
    assert where('mina', at(minutes=clock(1, 13), place='library', companions=('mina',))) == Whereabouts(
        'library', Presence.COMPANION
    )


def test_without_home_or_schedule_one_is_nowhere():
    assert where('sora', at()) == NOWHERE


def test_the_scene_is_who_is_here():
    assert scene_cast(WORLD, at()) == ['yuna']
    assert scene_cast(WORLD, at(place='cafe')) == ['mina']
    assert scene_cast(WORLD, at(place='park', minutes=clock(1, 13))) == ['mina']
    assert scene_cast(WORLD, at(place='beach')) == []


def test_companions_and_called_ones_join_the_scene():
    assert scene_cast(WORLD, at(place='park', companions=('sora',))) == ['sora']
    assert scene_cast(WORLD, at(place='park'), called=('sora', 'yuna')) == ['yuna', 'sora']


def test_a_called_companion_counts_as_a_companion():
    assert scene_cast(WORLD, at(place='park', companions=('yuna',)), called=('yuna', 'sora')) == ['yuna', 'sora']


def test_over_the_limit_the_order_picks():
    # 여섯이 모두 광장에 있다. 둘은 기본 장소, 둘은 일정, 하나는 이벤트, 하나는 동행
    cast = [
        member('h1', 'square'),
        member('h2', 'square'),
        member('s1', schedule=[line('morning', 'square')]),
        member('s2', schedule=[line('morning', 'square')]),
        member('e1', 'faraway'),
        member('c1', 'faraway'),
    ]
    crowd = world(cast)
    now = replace(start_state(crowd), place='square', companions=('c1',))

    picked = scene_cast(crowd, now, called=('e1',))

    assert len(picked) == SCENE_MAX_CAST
    assert picked == ['c1', 'e1', 's1', 's2']


def test_within_one_reason_the_world_order_picks():
    crowd = world([member(f'h{number}', 'square') for number in range(6)])

    assert scene_cast(crowd, replace(start_state(crowd), place='square')) == ['h0', 'h1', 'h2', 'h3']
