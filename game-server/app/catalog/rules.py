# game-server/app/catalog/rules.py

"""
모델 목록을 관리할 때의 판단들. DB 를 모른다. 받은 값만 보고 답한다.

  - token_field_problem: 출력 상한의 칸이 창구에 맞나
  - reasoning_style_problem: 생각을 켜고 끄는 방식이 창구에 맞나
  - round_cost_usd: 단가로 어림한 1인 1라운드의 원가

AI 를 부르는 코드도 쓰는 판단(always_thinks, is_retired, is_offered)은 모델 목록의 계약에 있다
(app/ai/catalog_contract.py, #496).
"""

from decimal import Decimal

from app.ai.catalog_contract import Provider, ReasoningStyle, TokenLimitField
from app.catalog.models import AiModelCost

# 출력 상한의 칸을 적어야 하는 창구. OpenAI 모양의 API 다. 나머지 창구는 칸이 정해져 있어 적지 않는다
TOKEN_FIELD_PROVIDERS = frozenset({Provider.OPENAI, Provider.LOCAL})

# 생각을 켜고 끄는 방식을 적어야 하는 창구와, 그 창구가 받는 방식들. 모델마다 방식이 다르다
STYLES_BY_PROVIDER = {
    Provider.ANTHROPIC: frozenset(
        {ReasoningStyle.ADAPTIVE, ReasoningStyle.ALWAYS, ReasoningStyle.BETWEEN_TOOLS, ReasoningStyle.BUDGET}
    ),
    Provider.GEMINI: frozenset(
        {ReasoningStyle.LEVEL_MINIMAL, ReasoningStyle.LEVEL_LOW, ReasoningStyle.BUDGET, ReasoningStyle.BUDGET_MIN}
    ),
    # 끌 수 있으면 thinking 칸으로 끈다. 끌 수 없는 모델(GLM-5.3 계열)은 칸을 보내지 않고 생각의 몫을 더한다
    Provider.ZAI: frozenset({ReasoningStyle.THINKING_TYPE, ReasoningStyle.ALWAYS}),
}
# 1라운드를 어림하는 토큰 수. 판매가를 정할 때 쓴 값과 같다(프로젝트 문서 model-pricing-plan)
ROUND_INPUT_TOKENS = 12_000
ROUND_OUTPUT_TOKENS = 1_200
MILLION = Decimal(1_000_000)


def token_field_problem(provider: Provider, field: TokenLimitField | None) -> str | None:
    """출력 상한의 칸이 창구에 맞지 않으면 그 까닭, 맞으면 None."""
    if provider in TOKEN_FIELD_PROVIDERS and field is None:
        return f'{provider} 창구의 모델은 출력 상한의 칸(max_tokens, max_completion_tokens)을 적어야 한다'
    if provider not in TOKEN_FIELD_PROVIDERS and field is not None:
        return f'{provider} 창구의 모델은 출력 상한의 칸을 적지 않는다'
    return None


def styles_text(provider: Provider) -> str:
    """그 창구가 받는 방식들을 글로(안내에 쓴다)."""
    return ', '.join(sorted(STYLES_BY_PROVIDER[provider]))


def reasoning_style_problem(provider: Provider, style: ReasoningStyle | None) -> str | None:
    """생각을 켜고 끄는 방식이 창구에 맞지 않으면 그 까닭, 맞으면 None."""
    if provider not in STYLES_BY_PROVIDER:
        return None if style is None else f'{provider} 창구의 모델은 생각을 켜고 끄는 방식을 적지 않는다'
    if style is None:
        return f'{provider} 창구의 모델은 생각을 켜고 끄는 방식({styles_text(provider)})을 적어야 한다'
    if style not in STYLES_BY_PROVIDER[provider]:
        return f'{provider} 창구가 받는 생각의 방식이 아니다({styles_text(provider)} 중 하나)'
    return None


def round_cost_usd(cost: AiModelCost) -> Decimal:
    """1인 1라운드의 원가(USD) 어림. 캐시를 쓰지 않았다고 본다."""
    return (cost.input_per_mtok * ROUND_INPUT_TOKENS + cost.output_per_mtok * ROUND_OUTPUT_TOKENS) / MILLION
