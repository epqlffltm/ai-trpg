# trpg-server/app/billing/prices.py

"""
서술의 가격표 이름. 결제 서버가 게임 서버에 허락한 머리(narration)와 모델의 이름표, 입력·출력 단계로 짓는다.

가격 목록의 값과 그것을 읽는 함수(Tier, PriceBook, parse_price_list, price_at 등)는
공용 코드(server_core/billing/prices.py)에 있다(#1266). 이 서버만의 것은 이름을 짓는 법뿐이다.
"""

from app.catalog.steps import BASE_STEPS, NarrationSteps, steps_code

# 서술의 가격표 이름의 앞부분(narration.<이름표>.i<입력>.o<출력>)
PRICE_CODE_PREFIX = 'narration'


def narration_code(slug: str, steps: NarrationSteps = BASE_STEPS) -> str:
    """
    모델 이름표와 단계의 가격표 이름(narration.claude-sonnet-5-5.i1.o0). 이름표 문자열 그대로 넣는다(9절).

    단계는 입력·출력 옵션이다(#387, app/catalog/steps.py). 단계마다 결제 서버의 가격표에 줄이 따로 있다.
    """
    return f'{PRICE_CODE_PREFIX}.{slug}.{steps_code(steps)}'
