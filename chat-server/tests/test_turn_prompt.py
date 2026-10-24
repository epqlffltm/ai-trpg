# chat-server/tests/test_turn_prompt.py

"""
모델에 보낼 메시지(app/turns/prompt.py)와 결제의 이름표. DB 도 모델도 쓰지 않는다.
최근 대화의 창과 SSE 의 글자는 공용 코드의 테스트(shared/conversation-core/tests)가 본다.
"""

import uuid

from ai_core.provider import Role
from conversation_core.window import Turn

from app.turns.charging import hold_reference
from app.turns.prompt import CharacterCard, PersonaCard, build_messages, plain_text, render_card

CHARACTER = CharacterCard(
    name='세라',
    intro_html='<p>도서관의 <b>사서</b>.</p><p>조용한 걸 좋아한다.</p>',
    speech_examples='"조용히 해 주세요."',
    age='스물넷',
    gender='',
)
PERSONA = PersonaCard(
    name='한서윤',
    description='',
    age='스물',
    gender='여성',
    form_of_address='서윤 씨',
    speech_examples='',
    personality='밝다',
)


# --- 카드 ---


def test_the_card_has_rules_character_persona_and_start_in_order():
    card = render_card(CHARACTER, PERSONA, '문을 두드리는 소리가 난다.')

    sections = card.split('\n\n')
    assert sections[0].startswith('너는 아래의 캐릭터로만 말한다.')
    assert sections[1:] == [
        '[캐릭터]\n이름: 세라\n나이: 스물넷\n소개: 도서관의 사서.\n조용한 걸 좋아한다.\n말투의 예: "조용히 해 주세요."',
        '[사용자]\n이름: 한서윤\n캐릭터가 부르는 호칭: 서윤 씨\n나이: 스물\n성별: 여성\n성격: 밝다',
        '[시작 상황]\n문을 두드리는 소리가 난다.',
    ]


def test_empty_fields_and_sections_are_left_out():
    card = render_card(CHARACTER, None, '  ')

    # 적지 않은 칸(성별)과 없는 블록(사용자, 시작 상황)을 "없음" 같은 말로 채우지 않는다
    assert '성별' not in card
    assert '[사용자]' not in card
    assert '[시작 상황]' not in card


def test_only_the_text_of_the_intro_is_sent():
    assert plain_text('<p>한 줄</p><ul><li>둘</li><li>셋</li></ul><p> </p>') == '한 줄\n둘\n셋'


def test_the_card_comes_first_and_turns_keep_their_roles():
    messages = build_messages('카드', [Turn('assistant', '어서 와요.'), Turn('user', '안녕')])

    assert [(message.role, message.content) for message in messages] == [
        (Role.SYSTEM, '카드'),
        (Role.ASSISTANT, '어서 와요.'),
        (Role.USER, '안녕'),
    ]


# --- 이름표 ---


def test_the_hold_reference_is_the_generation():
    reference = hold_reference(uuid.UUID('00000000-0000-4000-8000-000000000001'))

    # 결제 서버가 받는 모양(영문자, 숫자, : - 로 된 8~200자)이다
    assert reference == 'chat:gen:00000000-0000-4000-8000-000000000001'
