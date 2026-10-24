# chat-server/tests/test_suggestions.py

"""
다음 답 추천의 지시가 카드(app/turns/prompt.py)에 들어가는 자리. DB 도 모델도 쓰지 않는다.
나누기와 거르기는 공용 코드의 테스트(shared/conversation-core/tests/test_suggestions.py)가 본다.

보는 것.
  - 카드에는 켰을 때만 지시가 맨 끝에 들어간다
"""

from conversation_core.suggestions import MARKER, instruction

from app.turns.prompt import CharacterCard, render_card

CHARACTER = CharacterCard(name='세라', intro_html='', speech_examples='', age='', gender='')


def test_the_instruction_is_the_last_section_only_when_on():
    on = render_card(CHARACTER, None, '', suggest=True)
    off = render_card(CHARACTER, None, '')

    assert on.split('\n\n')[-1] == f'[다음 답 추천]\n{instruction()}'
    assert MARKER in instruction()
    assert '[다음 답 추천]' not in off
