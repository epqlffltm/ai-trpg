# trpg-server/tests/test_prices.py

"""
이 서버의 가격표 이름을 짓는 법(app/billing/prices.py)을 검증한다.

가격 목록의 값과 그것을 읽는 함수는 공용 코드(server_core/billing/prices.py)에 있고 그 테스트도 거기 있다(#1266).
"""

from app.billing import charges
from app.billing.prices import narration_code


def test_the_price_code_of_a_model_is_its_slug_with_the_base_steps():
    assert narration_code('claude-sonnet-5-5') == 'narration.claude-sonnet-5-5.i0.o0'
    # 모델이 없는 옛 라운드의 가격표 이름과 앞부분이 같다(app/billing/charges.py)
    assert charges.LEGACY_PRICE_CODE.split('.')[0] == narration_code('x').split('.')[0]
