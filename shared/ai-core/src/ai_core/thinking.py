# shared/ai-core/src/ai_core/thinking.py

"""
생각(thinking)의 몫을 정한다. 생각의 방식이 모델마다 다른 provider(Claude, Gemini)가 함께 쓴다.

서술은 생각을 꺼서 부른다. 하지만 끌 수 없는 모델이 있다(ai_core/catalog_contract.py 의 always_thinks).
생각을 하면 출력 상한에 생각의 토큰도 들어가서, 상한을 그대로 두면 생각이 장면의 몫을 먹고 장면이 잘린다.
그래서 생각할 때는 그 깊이의 몫(THINKING_TOKENS)을 출력 상한에 더한다.
끌 수 없는 모델에 끄라고 하면 가장 낮은 깊이의 몫이다.
이 몫이 판매가의 계산과 같다(끌 수 없는 모델은 출력 2,224 = 장면 1,200 + 생각 1,024, model-pricing-plan 9-2).
"""

from ai_core.catalog_contract import ReasoningStyle, always_thinks
from ai_core.openai_compat import THINKING_TOKENS
from ai_core.provider import Reasoning

# 끌 수 없는 모델에 끄라고 할 때 주는 생각의 깊이
LOWEST_EFFORT = Reasoning.LOW


def thinks(style: ReasoningStyle, reasoning: Reasoning) -> bool:
    """이 호출에서 모델이 생각하나. 생각을 켰거나, 끌 수 없는 모델이다."""
    return reasoning != Reasoning.NONE or always_thinks(style)


def thinking_budget(style: ReasoningStyle, reasoning: Reasoning) -> int:
    """생각에 더 주는 토큰. 생각하지 않으면 0. 끌 수 없는 모델에 끄라고 하면 가장 낮은 깊이의 몫이다."""
    if not thinks(style, reasoning):
        return 0
    return THINKING_TOKENS[LOWEST_EFFORT if reasoning == Reasoning.NONE else reasoning]
