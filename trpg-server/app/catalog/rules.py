# trpg-server/app/catalog/rules.py

"""
모델 목록을 관리할 때의 판단들. DB 를 모른다. 받은 값만 보고 답한다.

  - round_cost_usd: 단가로 어림한 1인 1라운드의 원가

AI 를 부르는 코드와 모델 목록의 파일도 쓰는 판단(always_thinks, is_retired, is_offered, 출력 상한의 칸과 생각의 방식이
창구에 맞나)은 모델 목록의 계약에 있다(ai_core/catalog_contract.py, #496, #499).
"""

from decimal import Decimal

from app.catalog.models import AiModelCost
from app.catalog.steps import ROUND_INPUT_TOKENS, ROUND_OUTPUT_TOKENS

MILLION = Decimal(1_000_000)


def round_cost_usd(cost: AiModelCost) -> Decimal:
    """1인 1라운드의 원가(USD) 어림. 기본 단계(i0.o0)다. 캐시를 쓰지 않았다고 본다."""
    return (cost.input_per_mtok * ROUND_INPUT_TOKENS + cost.output_per_mtok * ROUND_OUTPUT_TOKENS) / MILLION
