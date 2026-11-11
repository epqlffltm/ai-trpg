# story-server/tests/test_prices.py

"""
이 서버의 가격표 이름을 짓는 법(app/billing/prices.py)을 검증한다.

가격 목록의 값과 그것을 읽는 함수는 공용 코드(server_core/billing/prices.py)에 있고 그 테스트도 거기 있다(#1266).
"""

from app.billing.prices import story_code


def test_the_price_code_of_a_model_is_its_slug_with_the_base_steps():
    # 결제 서버가 story 서버에 허락한 머리(story)다. 다른 머리는 결제 서버가 없는 가격표로 답한다
    assert story_code('claude-sonnet-5-5') == 'story.claude-sonnet-5-5.i0.o0'
