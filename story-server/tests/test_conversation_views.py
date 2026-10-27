# story-server/tests/test_conversation_views.py

"""
세션에서 화면이 쓰는 세계관의 칸(app/conversations/views.py)을 검증한다. 순수 함수라 DB 도 앱도 없다.

보는 것.
  - 만남은 답들의 장면의 인물을 모은 것이다
  - 인물: 만나기 전에는 제작자가 고른 공개(보임, 실루엣은 가림, 숨김은 없음), 만나면 보임이다
  - 인물 창: 고른 항목만 싣는다. 호감도를 보이는 인물에만 고백 대기, 건넨 선물, 함께 본 이벤트가 실린다
  - 상태의 호감도 값: 호감도를 고른 인물 가운데 보이는 인물만(실루엣과 숨김은 만나기 전에는 없다)
  - 이벤트: 이 가지에서 열린 것만, 선택지의 글은 기다리는 이벤트에만 싣는다. 조건과 효과는 없다
  - 엔딩: 칸은 모두, 이름과 일러스트는 본 것(계정의 기록, 이 가지의 엔딩)만, 힌트는 늘 싣는다
  - 지도: 가 본 곳은 시작 장소와 상태들의 장소, 지금 장소다. 인물은 가 본 곳에 있고 만났고 지도 보이기를
    통과해야 보인다(보임, 숨김, 호감도 단계). 함께 다니는 인물은 장소에 없다
"""

import uuid
from types import MappingProxyType

from app.conversations.views import affection_shown, met_on, shown_reveal, visited_on, world_view
from app.engine.state import StoryState
from app.engine.world import read_world
from tests.engine_worlds import condition, confession, document, ending, event, member

PICTURE = uuid.UUID('aaaaaaaa-1111-4222-8333-444444444444')
SPRITE = {'id': 'smile', 'image_id': str(PICTURE), 'expression': '웃음'}


def person(cast_id: str, reveal: str = 'shown', panel: list[str] | None = None, **fields) -> dict:
    """인물 하나. 캐릭터의 그림과 소개, 나이가 있다."""
    body = member(cast_id, home='home', **fields)
    body['character'] = {
        'name': f'{cast_id}의 이름',
        'intro_html': f'<p>{cast_id}</p>',
        'age': '17',
        'gender': '',
        'image_id': str(PICTURE),
        'sprites': [SPRITE],
    }
    return {**body, 'reveal': reveal, 'panel': panel if panel is not None else ['intro']}


def at_home(**fields) -> StoryState:
    return StoryState(minutes=7 * 60, place='home', **fields)


def view(
    doc: dict,
    state: StoryState,
    met: frozenset[str] = frozenset(),
    recorded: frozenset[str] = frozenset(),
    visited: frozenset[str] = frozenset(),
):
    return world_view(read_world(doc), doc, state, met, recorded, visited)


def test_met_is_every_cast_member_of_the_answers():
    assert met_on([('mina',), (), ('mina', 'jun')]) == frozenset({'mina', 'jun'})


def test_the_reveal_follows_the_maker_until_met():
    assert [shown_reveal(reveal, False) for reveal in ('shown', 'silhouette', 'hidden')] == [
        'shown',
        'silhouette',
        None,
    ]
    assert [shown_reveal(reveal, True) for reveal in ('shown', 'silhouette', 'hidden')] == ['shown'] * 3


def test_silhouettes_are_masked_and_hidden_members_are_left_out_until_met():
    doc = document([person('mina'), person('jun', 'silhouette'), person('yu', 'hidden')])

    before = view(doc, at_home()).cast
    after = view(doc, at_home(), met=frozenset({'jun', 'yu'})).cast

    assert [(member.id, member.reveal, member.name, member.met) for member in before] == [
        ('mina', 'shown', 'mina의 이름', False),
        ('jun', 'silhouette', None, False),
    ]
    assert (before[1].image_id, before[1].sprites, before[1].intro_html) == (None, [], None)
    assert [(member.id, member.reveal, member.met) for member in after] == [
        ('mina', 'shown', False),
        ('jun', 'shown', True),
        ('yu', 'shown', True),
    ]


def test_the_panel_carries_only_the_chosen_fields():
    doc = document([person('mina', panel=['age'])])

    mina = view(doc, at_home()).cast[0]

    assert (mina.age, mina.intro_html, mina.gender, mina.affection, mina.events) == ('17', None, None, None, [])
    # 이름과 그림은 보임이면 늘 싣는다
    assert (mina.name, mina.image_id, [sprite.expression for sprite in mina.sprites]) == (
        'mina의 이름',
        PICTURE,
        ['웃음'],
    )


def test_the_affection_panel_carries_waiting_gifts_and_events():
    rain = event('rain', condition('reach_place', 'home'), cast=['mina'])
    doc = document([person('mina', panel=['affection'], confession=confession('연인'))], events=[rain])
    state = at_home(
        gifts=frozenset({('mina', 'flower'), ('mina', 'shell'), ('jun', 'ring')}),
        cooldowns=MappingProxyType({'mina': 7 * 60 + 30}),
        seen=frozenset({'rain'}),
    )

    mina = view(doc, state).cast[0]

    assert mina.confessable is True
    assert (mina.affection.display, [stage.name for stage in mina.affection.stages]) == (
        'stage',
        ['낯섦', '친함', '연인'],
    )
    assert (mina.affection.cooling_until, mina.affection.gifts, mina.events) == (
        7 * 60 + 30,
        ['flower', 'shell'],
        ['rain'],
    )
    # 대기 시각이 지났으면 대기가 아니다
    later = view(doc, StoryState(minutes=8 * 60, place='home', cooldowns=state.cooldowns)).cast[0]
    assert later.affection.cooling_until is None


def test_affection_values_are_shown_only_for_visible_members_with_the_affection_panel():
    doc = document(
        [
            person('mina', panel=['affection']),
            person('jun', panel=['intro']),
            person('yu', 'silhouette', panel=['affection']),
            person('sora', 'hidden', panel=['affection']),
        ]
    )

    assert affection_shown(doc, frozenset()) == frozenset({'mina'})
    assert affection_shown(doc, frozenset({'yu', 'sora'})) == frozenset({'mina', 'yu', 'sora'})


def test_only_opened_events_and_the_waiting_choices_are_carried():
    keep = {'id': 'keep', 'text': '줍는다', 'effects': []}
    shell = event('shell', condition('reach_place', 'beach'), cast=['mina'], choices=[keep])
    rain = event('rain', choices=[{'id': 'run', 'text': '뛴다', 'effects': []}])
    doc = document(events=[shell, rain, event('never')])

    events = view(doc, at_home(seen=frozenset({'shell', 'rain'}), choosing='shell')).events

    assert [(item.id, item.cast, [choice.text for choice in item.choices]) for item in events] == [
        ('shell', ['mina'], ['줍는다']),
        ('rain', [], []),
    ]
    assert 'when' not in events[0].model_dump()


def test_endings_show_names_only_when_seen_and_hints_always():
    secret = {**ending('secret', 'deadline'), 'hint': '기한까지 기다려 보자.'}
    solo = ending('solo', 'deadline', unlock=False)
    doc = document(endings=[ending('with_mina', 'confess_success', 'mina'), secret, solo])

    endings = view(doc, at_home(ending='solo'), recorded=frozenset({'with_mina'})).endings

    assert [(item.id, item.seen, item.name, item.hint, item.unlock) for item in endings] == [
        ('with_mina', True, 'with_mina', '', True),
        ('secret', False, None, '기한까지 기다려 보자.', True),
        ('solo', True, 'solo', '', False),
    ]


def test_places_items_and_slots_are_carried_without_rules():
    doc = document(
        places=[{'id': 'home', 'name': '집', 'description': '작은 집', 'image_id': None, 'backgrounds': {}}],
        paths=[{'a': 'home', 'b': 'beach', 'minutes': 30}],
        items=[{'id': 'shell', 'name': '조개', 'description': '', 'consumable': True, 'image_id': None}],
    )

    world = view(doc, at_home())

    assert ([place.name for place in world.places], world.paths[0].minutes, world.items[0].consumable) == (
        ['집'],
        30,
        True,
    )
    assert [slot.id for slot in world.slots] == ['morning', 'day', 'night']


PLACES = [
    {'id': place_id, 'name': place_id, 'description': '', 'image_id': None, 'backgrounds': {}}
    for place_id in ('home', 'beach', 'school')
]


def on_map(cast_id: str, home: str, shows: str = 'shown', stage: str | None = None, start: int = 0) -> dict:
    """지도 보이기를 고른 인물 하나."""
    return {**member(cast_id, home=home, start=start), 'map': shows, 'map_stage': stage}


def test_visited_places_are_the_start_and_the_places_of_the_states():
    assert visited_on('home', [None, 'beach', 'beach', None]) == frozenset({'home', 'beach'})


def test_the_map_marks_visited_places_and_the_current_place():
    doc = document(places=PLACES)

    places = view(doc, StoryState(minutes=7 * 60, place='school'), visited=frozenset({'home'})).map

    assert [(place.id, place.visited) for place in places] == [('home', True), ('beach', False), ('school', True)]


def test_the_map_shows_met_members_at_visited_places_only():
    cast = [on_map('mina', 'home'), on_map('jun', 'beach'), on_map('yu', 'home')]
    doc = document(cast, places=PLACES)

    places = view(doc, at_home(), met=frozenset({'mina', 'jun'}), visited=frozenset({'home'})).map

    # 준은 만났지만 해변에 가 본 적이 없다. 유는 집에 있지만 만난 적이 없다
    assert [(place.id, place.cast) for place in places] == [('home', ['mina']), ('beach', []), ('school', [])]


def test_the_map_follows_the_makers_choice():
    cast = [
        on_map('mina', 'home', 'hidden'),
        on_map('jun', 'home', 'stage', '친함'),
        on_map('yu', 'home', 'stage', '친함', start=30),
    ]
    doc = document(cast, places=PLACES)
    met = frozenset({'mina', 'jun', 'yu'})

    before = view(doc, at_home(), met=met).map[0].cast
    after = view(doc, at_home(affection=MappingProxyType({'jun': 40})), met=met).map[0].cast

    # 숨김은 늘 보이지 않는다. 단계는 호감도가 친함(30) 이상일 때 보인다
    assert (before, after) == (['yu'], ['jun', 'yu'])


def test_companions_are_not_on_the_map():
    doc = document([on_map('mina', 'home')], places=PLACES)

    places = view(doc, at_home(companions=('mina',)), met=frozenset({'mina'})).map

    assert places[0].cast == []
