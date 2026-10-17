# game-server/app/ai/costs.py

"""
AI 호출 한 번의 원가를 센다. 모델 목록의 그날의 단가(app/catalog/lookup.py 의 UnitCost)와 provider 가 알려 준 토큰 수로.

센 원가는 호출의 기록(ai_invocations.cost_usd)에 남는다. 모델마다 실제로 얼마가 드는지, 판매가가 맞는지 볼 근거다.
사용자의 크레딧과는 상관없다. 크레딧은 라운드를 열 때 정한 값(결제 서버의 가격표)으로만 받는다.

세는 법(토큰의 뜻은 app/ai/provider.py 의 Completion, OpenAI 의 뜻이다).
  - 캐시에서 읽은 입력은 캐시 읽기 단가로, 캐시에 쓴 입력은 캐시 쓰기 단가로, 나머지 입력은 입력 단가로 센다.
    캐시 단가를 적지 않은 모델이면 입력 단가로 센다.
  - 출력은 생각에 쓴 것까지 출력 단가로 센다.
  - 토큰 수를 모르면(알려 주지 않는 provider) 원가도 모른다(None). 0 으로 적으면 쓴 돈이 없던 것처럼 보인다.
  - 받지 못한 호출은 원가가 없다. 공급자가 값을 매기지 않는다.
  - 소수 여덟째 자리까지 적는다. 한 번의 원가가 $0.0018 같은 값이다.
값을 매긴 단가의 줄(cost_id)을 함께 남긴다. 나중에 단가를 고쳐 적어도 그때 어느 값으로 셌는지 안다.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.ai.calls import NO_USAGE, CallUsage
from app.ai.provider import Completion
from app.catalog.lookup import UnitCost

MILLION = Decimal(1_000_000)
# 원가를 적는 자릿수
COST_PLACES = Decimal('0.00000001')


@dataclass(frozen=True)
class PriceTag:
    """이 호출에 매길 것. 모델 목록의 이름표와 그날의 단가. 단가를 적지 않은 날이면 cost 가 None 이다."""

    model_slug: str
    cost: UnitCost | None


def cost_usd(completion: Completion, cost: UnitCost) -> Decimal | None:
    """답 하나의 원가(USD). 입력이나 출력의 토큰 수를 모르면 None."""
    if completion.input_tokens is None or completion.output_tokens is None:
        return None
    cached = completion.cached_input_tokens or 0
    written = completion.cache_write_tokens or 0
    plain = max(completion.input_tokens - cached - written, 0)
    total = (
        plain * cost.input_per_mtok
        + cached * (cost.cached_input_per_mtok if cost.cached_input_per_mtok is not None else cost.input_per_mtok)
        + written * (cost.cache_write_per_mtok if cost.cache_write_per_mtok is not None else cost.input_per_mtok)
        + completion.output_tokens * cost.output_per_mtok
    )
    return (total / MILLION).quantize(COST_PLACES)


def charge_of(completion: Completion | None, price: PriceTag | None) -> tuple[Decimal | None, int | None]:
    """원가와 그것을 센 단가의 줄. 답이 없거나 단가가 없거나 토큰 수를 모르면 둘 다 None."""
    if completion is None or price is None or price.cost is None:
        return None, None
    amount = cost_usd(completion, price.cost)
    return (amount, price.cost.cost_id) if amount is not None else (None, None)


def usage_of(completion: Completion | None, price: PriceTag | None) -> CallUsage:
    """호출 한 번의 자세한 사용량과 원가. 모델 목록에 없는 모델이고 답도 없으면 NO_USAGE."""
    if completion is None and price is None:
        return NO_USAGE
    amount, cost_id = charge_of(completion, price)
    return CallUsage(
        cached_input_tokens=completion.cached_input_tokens if completion else None,
        cache_write_tokens=completion.cache_write_tokens if completion else None,
        reasoning_tokens=completion.reasoning_tokens if completion else None,
        model_slug=price.model_slug if price else None,
        cost_usd=amount,
        cost_id=cost_id,
    )
