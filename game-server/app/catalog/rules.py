# game-server/app/catalog/rules.py

"""
모델 목록의 판단들. DB 를 모른다. 받은 값만 보고 답한다.

  - token_field_problem: 출력 상한의 칸이 창구에 맞나
  - is_retired, is_offered: 그날 은퇴했나, 그날 쓸 수 있나
  - round_cost_usd: 단가로 어림한 1인 1라운드의 원가
"""

from datetime import date
from decimal import Decimal

from app.catalog.models import AiModel, AiModelCost, Provider, TokenLimitField

# 출력 상한의 칸을 적어야 하는 창구. OpenAI 모양의 API 다. 나머지 창구는 칸이 정해져 있어 적지 않는다
TOKEN_FIELD_PROVIDERS = frozenset({Provider.OPENAI, Provider.LOCAL})

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


def is_retired(model: AiModel, today: date) -> bool:
    """그날 은퇴했나. 은퇴일 당일부터 은퇴다."""
    return model.retires_on is not None and today >= model.retires_on


def is_offered(model: AiModel, today: date) -> bool:
    """그날 쓸 수 있나. 켜져 있고 은퇴하지 않았다."""
    return model.enabled and not is_retired(model, today)


def round_cost_usd(cost: AiModelCost) -> Decimal:
    """1인 1라운드의 원가(USD) 어림. 캐시를 쓰지 않았다고 본다."""
    return (cost.input_per_mtok * ROUND_INPUT_TOKENS + cost.output_per_mtok * ROUND_OUTPUT_TOKENS) / MILLION
