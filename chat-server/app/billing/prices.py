# chat-server/app/billing/prices.py

"""
chat 의 가격표 이름. 결제 서버가 이 서버에 허락한 머리(chat)와 모델의 이름표로 짓는다.

가격 목록의 값과 그것을 읽는 함수(Tier, PriceBook, parse_price_list, price_at 등)는
공용 코드(server_core/billing/prices.py)에 있다(#1266). 이 서버만의 것은 이름을 짓는 법뿐이다.
"""

# 말 한 번의 가격표 이름의 앞부분(chat.<이름표>.i0.o0). 결제 서버가 이 서버에 허락한 머리다
PRICE_CODE_PREFIX = 'chat'
# 입력·출력 옵션의 단계. 지금은 기본(0단계)만 판다(model-pricing-plan 4-1)
BASE_STEPS = 'i0.o0'


def chat_code(slug: str) -> str:
    """모델 이름표의 가격표 이름(chat.claude-sonnet-5-5.i0.o0). 이름표 문자열 그대로 넣는다."""
    return f'{PRICE_CODE_PREFIX}.{slug}.{BASE_STEPS}'
