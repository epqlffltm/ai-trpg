# story-server/tests/test_turn_prompt.py

"""
모델에 보낼 메시지(app/turns/prompt.py, briefing.py)와 상태의 저장 모양(app/turns/states.py)을 검증한다.
순수 함수라 DB 도 앱도 없다.

보는 것.
  - 카드: 지킬 것, 세계관, 지금(날, 시간대, 장소, 소지품), 장면의 인물(표식, 이름, 칸, 호감도 단계), 쓰는 법.
    빈 칸은 빼고, 소개의 HTML 은 글자만 보낸다. 장면에 아무도 없으면 서술만 쓰라고 한다. 장면 지시는 있을 때만.
    다음 답 추천의 지시는 켰을 때만 맨 끝에 붙는다.
    그림에 표정이 있는 장면의 인물이 있으면 쓰는 법에 표정을 고르는 법이 붙는다
  - 메시지: 카드가 먼저, 그 뒤에 최근의 말. 행동 말은 [행동] 을 붙인 사람의 차례다
  - 상태: 저장한 모양에서 그대로 되돌아온다. 가지의 끝에서 가장 가까운 상태를 쓰고, 없으면 처음의 상태다
"""

from types import MappingProxyType

from ai_core.provider import Role
from conversation_core.window import Turn

from app.engine.clock import MINUTES_PER_DAY
from app.engine.state import StoryState, start_state
from app.engine.world import read_world
from app.turns.briefing import read_briefing
from app.turns.prompt import ACTION_PREFIX, build_messages, plain_text, render_card, scene_card, stage_name
from app.turns.states import state_from_json, state_on_path, state_to_json
from tests.engine_worlds import clock, document, member

DOCUMENT = document(
    [
        {
            **member('mina', home='home', start=40),
            'character': {
                'name': '미나',
                'intro_html': '<p>옆집 <b>친구</b>.</p><p>수영을 좋아한다.</p>',
                'speech_examples': '"오늘도 덥네."',
                'age': '17',
                'gender': '',
            },
        },
        member('jun', home='beach'),
    ],
    name='여름 마을',
    intro_html='<p>바닷가 마을.</p>',
    places=[{'id': 'home', 'name': '집', 'description': '작은 마당이 있다.'}, {'id': 'beach', 'name': '해변'}],
    items=[{'id': 'shell', 'name': '조개껍데기'}],
    start_items=[{'item': 'shell', 'count': 2}],
)
WORLD = read_world(DOCUMENT)
BRIEFING = read_briefing(DOCUMENT)


def test_plain_text_keeps_only_words():
    assert plain_text('<p>옆집 <b>친구</b>.</p><p>수영을 좋아한다.</p>') == '옆집 친구.\n수영을 좋아한다.'


def test_the_stage_is_the_highest_reached():
    mina = WORLD.member('mina')

    assert [stage_name(mina, value) for value in (0, 29, 30, 99)] == ['낯섦', '낯섦', '친함', '연인']
    assert stage_name(None, 50) == ''


def test_the_card_tells_the_scene():
    state = start_state(WORLD)

    card = render_card(BRIEFING, scene_card(BRIEFING, WORLD, state, ['mina']))

    assert '[세계관]\n이름: 여름 마을\n소개: 바닷가 마을.' in card
    assert (
        '[지금]\n날: 1일째\n시간대: 아침\n장소: 집\n장소의 모습: 작은 마당이 있다.\n사용자의 소지품: 조개껍데기 2개'
        in card
    )
    # 빈 칸(성별)은 빼고, 소개는 글자만이다. 호감도는 단계의 이름이다
    assert (
        '@mina (미나)\n나이: 17\n소개: 옆집 친구.\n수영을 좋아한다.\n'
        '말투의 예: "오늘도 덥네."\n사용자에 대한 마음: 친함'
    ) in card
    assert '쓸 수 있는 인물: @mina' in card
    assert '@jun' not in card
    assert '[장면 지시]' not in card


def test_an_empty_scene_asks_for_narration_and_an_event_adds_its_direction():
    state = start_state(WORLD)

    card = render_card(BRIEFING, scene_card(BRIEFING, WORLD, state, [], event='비가 쏟아진다.'))

    assert '지금 이 장소에는 아무도 없다. 서술만 쓴다.' in card
    assert '쓸 수 있는 인물' not in card
    assert '[장면 지시]\n비가 쏟아진다.' in card


def test_the_suggestions_instruction_comes_last_only_when_asked():
    scene = scene_card(BRIEFING, WORLD, start_state(WORLD), ['mina'])

    asked = render_card(BRIEFING, scene, suggest=True)

    assert '[다음 답 추천]' not in render_card(BRIEFING, scene)
    assert asked.rsplit('\n\n', 1)[1].startswith('[다음 답 추천]\n')
    assert asked.endswith('선택지의 줄에는 말하는 사람의 표식을 붙이지 않는다.')


def test_the_card_lists_the_expressions_of_the_scene():
    sprites = [{'expression': ''}, {'expression': '웃음'}, {'expression': ' 웃음 '}, {'expression': '화남'}]
    doc = document([{**member('mina', home='home'), 'character': {'name': '미나', 'sprites': sprites}}])
    briefing, world = read_briefing(doc), read_world(doc)

    card = render_card(briefing, scene_card(briefing, world, start_state(world), ['mina']))

    # 기본(빈 이름)은 빼고 같은 것은 하나다
    assert briefing.expressions('mina') == ('웃음', '화남')
    assert briefing.expressions('nobody') == ()
    assert '고를 수 있는 표정: @mina: 기본, 웃음, 화남' in card
    assert '예: @mina: <expression>웃음</expression>정말?' in card


def test_messages_start_with_the_card():
    messages = build_messages(
        '카드', [Turn('assistant', '@narration: 바람.'), Turn('action', '해변으로'), Turn('user', '안녕')]
    )

    assert [(message.role, message.content) for message in messages] == [
        (Role.SYSTEM, '카드'),
        (Role.ASSISTANT, '@narration: 바람.'),
        (Role.USER, f'{ACTION_PREFIX} 해변으로'),
        (Role.USER, '안녕'),
    ]


def test_a_state_round_trips():
    state = StoryState(
        minutes=clock(2, 19),
        place='beach',
        items=MappingProxyType({'shell': 1}),
        affection=MappingProxyType({'mina': 55}),
        gifts=frozenset({('mina', 'shell'), ('jun', 'shell')}),
        seen=frozenset({'meet', 'rain'}),
        companions=('mina',),
        choosing='rain',
        cooldowns=MappingProxyType({'jun': MINUTES_PER_DAY * 3}),
        ending=None,
    )

    data = state_to_json(state)

    assert data['gifts'] == [['jun', 'shell'], ['mina', 'shell']]
    assert data['seen'] == ['meet', 'rain']
    assert state_from_json(data) == state


def test_a_saved_state_reads_with_missing_fields_as_start_values():
    assert state_from_json({'minutes': 600, 'place': 'home', 'later_field': 1}) == StoryState(minutes=600, place='home')


def test_the_branch_uses_the_nearest_state():
    early = state_to_json(StoryState(minutes=100, place='home'))
    late = state_to_json(StoryState(minutes=900, place='beach'))

    assert state_on_path(WORLD, [None, early, None, late, None]).place == 'beach'
    assert state_on_path(WORLD, [None, None]) == start_state(WORLD)
    assert state_on_path(WORLD, []) == start_state(WORLD)
